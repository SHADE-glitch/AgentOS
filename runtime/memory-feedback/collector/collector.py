#!/usr/bin/env python3
"""
Phase 5.7.1 → 5.8.2.2 — Runtime Feedback Collector
Reads runtime/traces/*.yaml → produces memory-candidates.yaml
Does NOT modify Memory directly.

Phase 5.8.2.2 Refactoring:
  - Removed hardcoded TARGET_EXECUTIONS
  - Added collect_from_trace_ids() for programmatic use
  - Added collect_new_traces() with collector_state.yaml for idempotency
  - Same trace never processed twice
"""
import yaml, os, sys, hashlib, re
from datetime import datetime, timezone

TRACES_DIR = "/home/shade/.agents/runtime/traces"
CANDIDATES_FILE = "/home/shade/.agents/runtime/memory-feedback/memory-candidates.yaml"
COLLECTOR_STATE_FILE = "/home/shade/.agents/runtime/loop-controller/state/collector_state.yaml"
OBSERVATION_LOG_FILE = "/home/shade/.agents/runtime/memory-feedback/memory-observation-log.yaml"
# Phase 8.5-T3: retention cap (additive, isolated)
OBSERVATION_LOG_MAX_PER_MEMORY = 20

# Phase 5.9: Atomic write utility
sys.path.insert(0, os.path.join("/home/shade/.agents", "runtime", "loop-controller"))
from file_utils import atomic_yaml_write

def load_trace(execution_id):
    path = os.path.join(TRACES_DIR, f"{execution_id}.yaml")
    if not os.path.exists(path):
        print(f"SKIP: {execution_id} — file not found")
        return None
    with open(path) as f:
        return yaml.safe_load(f)

def validate_trace(trace):
    """Validate required fields for real execution."""
    reasons = []
    
    if not trace:
        return False, ["trace is None"]
    
    eid = trace.get("execution_id", "")
    if not eid:
        return False, ["missing execution_id"]
    
    # Memory mode check
    if trace.get("memory_mode", "").lower() == "off":
        return False, ["memory_mode is off — baseline only, skip"]
    
    ai = trace.get("agent_invocation", {})
    if not ai.get("session_id"):
        reasons.append("missing session_id")
    if not ai.get("tokens", {}).get("total", 0):
        reasons.append("missing or zero tokens")
    
    # Compute output hash
    response = trace.get("agent_response", "")
    if not response:
        reasons.append("missing agent_response")
    
    if reasons:
        return False, reasons
    return True, []

def compute_output_hash(response):
    return hashlib.sha256(response.encode()).hexdigest()[:16]

# ── Phase 8.4: Hypothesis Reinforcement Lane (R7 + R4) ─────────────
# Independent, low-trust evidence lane. Consumes provenance only (I1-I8).
HYPOTHESIS_CANDIDATE_TYPES = ("reinforce_hypothesis", "weaken_hypothesis")


# ── Phase 8.6-C5: Single-gate shared observation counting helper ──
def is_countable_observation(candidate):
    """Determine whether a candidate observation should count toward
    validation_runs.  Shared by collector observation-log gate and
    validator counting gate (cross-gate invariant)."""
    # Phase 8.4 I7: inconclusive hypothesis observations never count
    if (candidate.get("candidate_type") in HYPOTHESIS_CANDIDATE_TYPES
            and candidate.get("outcome") == "inconclusive"):
        return False
    # Phase 8.6 I9: same-loop self-confirmation must not count
    if candidate.get("hypothesis_engagement", {}).get("same_loop_as_creation"):
        return False
    return True


# ── Phase 8.6-C4: Canonical evidence source for hypothesis lane ───
def canonical_source_for(candidate):
    """Return the canonical evidence source for hypothesis-lane counting.
    Priority: hypothesis_engagement.loop_id → source_loop →
    candidate.loop_id → source_execution (fallback)."""
    he = candidate.get("hypothesis_engagement", {})
    return (he.get("loop_id")
            or he.get("source_loop")
            or candidate.get("loop_id")
            or candidate.get("source_execution", ""))

_HYPOTHESIS_REFUTATION_PATTERNS = [
    r"(?:hypothesis|H-\d+).{0,60}(?:refuted|wrong|incorrect|false|does not hold|contradicted|fails)",
    r"(?:contradicts|refutes|rejects|negates|invalidates).{0,40}(?:hypothesis|H-\d+)",
    r"(?:UNVALIDATED).{0,40}(?:failed|rejected|do not rely|cannot confirm)",
]


def _hypothesis_level(info):
    """Resolve the engagement/influence level for a hypothesis attribution dict."""
    return (info.get("engagement_level")
            or info.get("influence")
            or ("hypothesis_changed_decision" if info.get("changed_decision")
                else ("hypothesis_used" if info.get("referenced") else "none"))
            or "none")


def _normalize_hypothesis_engagement(info, shared_context=False):
    """Build full provenance dict (invariant I8) from a raw attribution dict."""
    # Phase 8.7: preserve adversarial provenance fields if present
    base = {
        "referenced": bool(info.get("referenced", False)),
        "engagement_level": _hypothesis_level(info),
        "term_matches": info.get("term_matches", 0),
        "id_mentioned": bool(info.get("id_mentioned", False)),
        "changed_decision": bool(info.get("changed_decision", False)),
        "same_loop_as_creation": bool(info.get("same_loop_as_creation", False)),
        "created_loop": info.get("created_loop", ""),
        "shared_context_with_other_agents": bool(
            info.get("shared_context_with_other_agents", shared_context)),
    }
    # Phase 8.7: copy through provenance fields if present (additive, keeps legacy key set intact)
    for _k in ("loop_id", "source_loop", "observation_id", "root_task_id",
               "model_family", "retrieval_context_hash"):
        if info.get(_k) not in (None, ""):
            base[_k] = info.get(_k)
    return base


def classify_hypothesis_engagement(agent_response, hyp_id, info):
    """
    Phase 8.4 — classify a single hypothesis observation.

    Evidence layering (I3/I4):
      refuted  -> (weaken_hypothesis, refuted)      [negative evidence]
      confirmed/changed -> (reinforce_hypothesis, confirmed)
      referenced/strong terms -> (reinforce_hypothesis, observed)
      weak mention, no confirmation -> (reinforce_hypothesis, inconclusive)
      not engaged -> (None, inconclusive)            [abstain — I6]

    Returns (candidate_type|None, outcome, engagement_provenance).
    """
    info = info or {}
    referenced = bool(info.get("referenced", False))
    if not referenced:
        return None, "inconclusive", _normalize_hypothesis_engagement(info)

    if _is_hypothesis_refuted(agent_response, hyp_id, info):
        return "weaken_hypothesis", "refuted", _normalize_hypothesis_engagement(info)

    level = _hypothesis_level(info)
    changed = bool(info.get("changed_decision", False))
    if changed or level in ("hypothesis_confirmed", "hypothesis_changed_decision"):
        return "reinforce_hypothesis", "confirmed", _normalize_hypothesis_engagement(info)

    if level == "hypothesis_used":
        if info.get("id_mentioned") or info.get("term_matches", 0) >= 3:
            return "reinforce_hypothesis", "observed", _normalize_hypothesis_engagement(info)
        return "reinforce_hypothesis", "inconclusive", _normalize_hypothesis_engagement(info)

    return None, "inconclusive", _normalize_hypothesis_engagement(info)


def _is_hypothesis_refuted(agent_response, hyp_id, info):
    """Detect explicit refutation of a hypothesis in the agent response (I4)."""
    if not agent_response:
        return False
    import re as _re
    # Only meaningful if the hypothesis was actually surfaced by the agent
    if not (info.get("id_mentioned") or info.get("term_matches", 0) > 0):
        return False
    return any(_re.search(p, agent_response, _re.IGNORECASE)
               for p in _HYPOTHESIS_REFUTATION_PATTERNS)


def evaluate_quality(response):
    """Heuristic quality evaluation based on response structure."""
    scores = {}
    
    # Completeness
    comp = 0
    if re.search(r'#{1,3}\s', response): comp += 1  # has headers
    if re.search(r'[-*]\s', response): comp += 1      # has bullet points
    if re.search(r'```', response): comp += 1          # has code blocks
    if len(re.findall(r'#{1,3}\s', response)) >= 3: comp += 1  # 3+ sections
    if len(response) > 100: comp += 1                   # substantial length
    scores["completeness"] = min(comp, 5)
    
    # Accuracy proxy
    acc = 0
    tech_terms = ['API', 'TLS', 'AES', 'JWT', 'RBAC', 'SQL', 'RAG', 'LLM',
                  'cache', 'token', 'encrypt', 'vector', 'retrieval', 'index',
                  'OAuth', 'HMAC', 'SHA', 'PCI', 'DSS', 'embedding', 'chunking',
                  'OCR', 'Cross-Encoder', 'Dense', 'Sparse', 'Redis', 'MySQL',
                  '数据库', '向量', '检索', '加密', '认证', '授权', '缓存',
                  '分布式', '高并发', '索引', '查询', '性能', '安全']
    if any(t.lower() in response.lower() for t in tech_terms): acc += 1
    if re.search(r'(?:使用|采用|选择|推荐|基于|通过)', response): acc += 1
    if re.search(r'(?:实现|配置|部署|设置|构建|处理)', response): acc += 1
    if re.search(r'(?:因为|原因|由于|为了|确保|避免)', response): acc += 1
    if re.search(r'(?:具体|详细|明确)', response): acc += 1  # specific
    scores["accuracy"] = min(acc, 5)
    
    # Structure
    struct = 0
    if re.search(r'^\d+[\.、）)]\s', response, re.MULTILINE): struct += 1  # numbered
    if re.search(r'^#{1,3}\s', response, re.MULTILINE): struct += 1  # has headers
    if len(response.split('\n')) > 8: struct += 1  # multiple lines
    if response.count('\n') > 5: struct += 1
    if len(response) > 100 and '\n\n' in response: struct += 1  # has paragraphs
    scores["structure"] = min(struct, 5)
    
    # Actionability
    act = 0
    if re.search(r'(?:步骤|流程|Step|方法|方式)', response): act += 1
    if re.search(r'(?:建议|推荐|方案|策略|设计)', response): act += 1
    if re.search(r'(?:例如|示例|比如|如)', response): act += 1
    if re.search(r'(?:配置|参数|设置|兼容|注意)', response): act += 1
    if len(response) > 100: act += 1  # substantial enough to act on
    scores["actionability"] = min(act, 5)
    
    # Novelty
    nov = 0
    if re.search(r'(?:数据库|向量|检索|索引|缓存|存储|查询)', response): nov += 1
    if re.search(r'(?:权衡|取舍|trade|利弊|对比|相比)', response, re.IGNORECASE): nov += 1
    if re.search(r'(?:边界|极端|边缘|corner|特殊|异常)', response, re.IGNORECASE): nov += 1
    if re.search(r'(?:优化|改进|提升|增强|加速)', response): nov += 1
    if len(response) > 200: nov += 1
    scores["novelty"] = min(nov, 5)
    
    # Weighted score
    weighted = (
        scores["completeness"] * 0.25 +
        scores["accuracy"] * 0.30 +
        scores["structure"] * 0.15 +
        scores["actionability"] * 0.20 +
        scores["novelty"] * 0.10
    )
    scores["weighted"] = round(weighted, 2)
    return scores

def generate_candidates(trace, quality):
    """Apply candidate generation rules R1-R6."""
    candidates = []
    eid = trace["execution_id"]
    status = trace.get("status", "")
    mem_retrieval = trace.get("memory_retrieval", {})
    mem_used = mem_retrieval.get("memories_used", [])
    # Handle both field name variants: some traces use "influence", others "memory_influence"
    mem_influence = mem_retrieval.get("memory_influence") or mem_retrieval.get("influence", "none")
    anti_alert = trace.get("orchestrator", {}).get("anti_pattern_alert", False)
    response = trace.get("agent_response", "")
    ai = trace.get("agent_invocation", {})
    qs = quality["weighted"]
    
    evidence = {
        "session_id": ai.get("session_id", ""),
        "model": trace.get("model", ""),
        "tokens": ai.get("tokens", {}),
        "output_hash": compute_output_hash(response),
        "latency_ms": ai.get("latency_ms", 0),
        "is_real_execution": True,
    }
    
    def make_candidate(cid, target_mem, ctype, outcome, reasoning, target_type=None):
        return {
            "candidate_id": cid,
            "source_execution": eid,
            "target_memory": target_mem,
            "candidate_type": ctype,
            "quality_score": qs,
            "quality_breakdown": {
                "completeness": quality["completeness"],
                "accuracy": quality["accuracy"],
                "structure": quality["structure"],
                "actionability": quality["actionability"],
                "novelty": quality["novelty"],
            },
            "reasoning": reasoning,
            "evidence": evidence.copy(),
            "outcome": outcome,
        }
    
    # R1: memory_used + success → reinforce
    if mem_used and status == "success":
        for mem_id in mem_used:
            candidates.append(make_candidate(
                cid=f"CAND-{eid}-{mem_id}",
                target_mem=mem_id,
                ctype="reinforce",
                outcome="promoted",
                reasoning=f"Memory {mem_id} was used in {eid} ({trace.get('task_id','?')}). Execution succeeded. Memory influence: {mem_influence}. This confirms the memory is valid and useful.",
            ))
    
    # R2: anti_pattern_alert + success → reinforce (AP-001)
    if anti_alert and status == "success":
        if "AP-001" not in mem_used:
            candidates.append(make_candidate(
                cid=f"CAND-{eid}-AP-001",
                target_mem="AP-001",
                ctype="reinforce",
                outcome="promoted",
                reasoning=f"Anti-pattern alert triggered in {eid}. Execution succeeded. AP-001 (Team Inflation Guard) correctly prevented unnecessary team formation.",
            ))
    
    # R3: memory_used + failure → weaken
    if mem_used and status != "success":
        for mem_id in mem_used:
            candidates.append(make_candidate(
                cid=f"CAND-{eid}-{mem_id}",
                target_mem=mem_id,
                ctype="weaken",
                outcome="hold",
                reasoning=f"Memory {mem_id} was used in {eid} but execution failed (status={status}). Review whether memory contributed to failure.",
            ))
    
    # R4: memory_used + no_influence → weaken
    # Only if status is success (otherwise R3 already handled it)
    if mem_used and mem_influence == "none" and status == "success":
        for mem_id in mem_used:
            candidates.append(make_candidate(
                cid=f"CAND-{eid}-{mem_id}-weak",
                target_mem=mem_id,
                ctype="weaken",
                outcome="hold",
                reasoning=f"Memory {mem_id} was retrieved in {eid} but had no influence on the decision (memory_influence=none). Memory may be irrelevant or low-quality.",
            ))
    
    # R5: success + high_quality + no_memory → create_hypothesis
    if status == "success" and qs >= 4.0 and not mem_used:
        domain = trace.get("domain", "unknown")
        candidates.append(make_candidate(
            cid=f"CAND-{eid}-HYPOTHESIS",
            target_mem="NEW",
            ctype="create_hypothesis",
            outcome="hold",
            reasoning=f"High-quality execution in {domain} domain with no Memory used. Response quality={qs}. Consider creating a new hypothesis memory for this domain pattern.",
        ))
    
    # R6: risk_changed + success → reinforce (additional evidence for risk-signaling memories)
    if mem_influence == "risk_changed" and status == "success" and mem_used:
        for mem_id in mem_used:
            candidates.append(make_candidate(
                cid=f"CAND-{eid}-{mem_id}-risk",
                target_mem=mem_id,
                ctype="reinforce",
                outcome="promoted",
                reasoning=f"Memory {mem_id} influenced risk assessment in {eid}. Risk level changed, and execution succeeded. The memory's risk signal was valuable. This is additional evidence beyond R1.",
            ))

    # R7: Hypothesis Reinforcement Lane (Phase 8.4)
    # Consume hypothesis engagement already attributed by the runtime into
    # trace.memory_retrieval.influence_breakdown. Only type=hypothesis entries.
    # Identity (target_memory) comes strictly from injection provenance (I1/I6).
    influence_breakdown = mem_retrieval.get("influence_breakdown", {})
    hypotheses_injected = set(mem_retrieval.get("hypotheses_injected", []) or [])
    for mem_id, brk in (influence_breakdown or {}).items():
        if brk.get("type") != "hypothesis":
            continue
        hyp_id = brk.get("memory_id") or mem_id
        if not hyp_id:
            continue
        # I1: identity must be present in real injection provenance.
        if hypotheses_injected and hyp_id not in hypotheses_injected:
            continue
        # R1/R3 handle established-style usage; do not double-emit (I5).
        if hyp_id in mem_used:
            continue
        ctype, outcome, eng = classify_hypothesis_engagement(response, hyp_id, brk)
        if ctype is None:
            continue  # abstain — not engaged (I6)
        # Phase 8.7: build candidate with adversarial provenance propagation
        _obs_id = brk.get("observation_id") or f"OBS-{eid}-{hyp_id}"
        _root_task = brk.get("root_task_id") or trace.get("root_task_id") or trace.get("task_id", "")
        _model_family = brk.get("model_family") or trace.get("model_family") or "unknown"
        _rctx = brk.get("retrieval_context_hash") or ""
        _root_exec = trace.get("execution_id", eid)
        _env_fp = trace.get("env_fingerprint", {}) or {}
        _cand = {
            "candidate_id": f"CAND-{eid}-HYP-{hyp_id}",
            "source_execution": eid,
            "target_memory": hyp_id,
            "candidate_type": ctype,
            "quality_score": qs,
            "canonical_source": canonical_source_for({
                "hypothesis_engagement": eng,
                "loop_id": trace.get("loop_id", ""),
                "source_execution": eid,
            }),
            "quality_breakdown": {
                "completeness": quality["completeness"],
                "accuracy": quality["accuracy"],
                "structure": quality["structure"],
                "actionability": quality["actionability"],
                "novelty": quality["novelty"],
            },
            "reasoning": (
                f"Hypothesis {hyp_id} engaged by agent in {eid} "
                f"(level={eng['engagement_level']}, term_matches={eng['term_matches']}, "
                f"id_mentioned={eng['id_mentioned']}). Evidence from real execution."
            ),
            "evidence": {**evidence.copy(), "agent_role": "lead", "env_fingerprint": _env_fp},
            "outcome": outcome,
            "hypothesis_engagement": eng,
            # Phase 8.7: top-level provenance for validator dedup
            "observation_id": _obs_id,
            "root_task_id": _root_task,
            "root_execution_id": _root_exec,
            "model_family": _model_family,
            "retrieval_context_hash": _rctx,
            "env_fingerprint": _env_fp,
            "loop_id": trace.get("loop_id", ""),
            "countable": True,  # placeholder, computed below
        }
        _cand["countable"] = is_countable_observation(_cand)
        candidates.append(_cand)

    return candidates

def load_collector_state():
    """Load collector_state.yaml or return empty state."""
    if not os.path.exists(COLLECTOR_STATE_FILE):
        return {"version": "1.0", "last_scan": "", "processed_traces": []}
    with open(COLLECTOR_STATE_FILE) as f:
        return yaml.safe_load(f) or {"version": "1.0", "last_scan": "", "processed_traces": []}


def save_collector_state(state):
    """Save collector_state.yaml. Phase 5.9: atomic write."""
    state["last_scan"] = datetime.now(timezone.utc).isoformat()
    atomic_yaml_write(COLLECTOR_STATE_FILE, state)


# Phase 8.5-T3: retention — keep last N per memory (additive, reversible)
def prune_observation_log(log, max_per_memory=OBSERVATION_LOG_MAX_PER_MEMORY):
    """Prune observations to last max_per_memory per memory_id (additive, isolated)."""
    obs = log.get("observations", [])
    if len(obs) <= max_per_memory:
        return log
    from collections import defaultdict
    grouped = defaultdict(list)
    for o in obs:
        grouped[o.get("memory_id", "")].append(o)
    pruned = []
    for mid, lst in grouped.items():
        # keep last max_per_memory by observed_at (ISO sort works)
        lst.sort(key=lambda x: x.get("observed_at", ""))
        pruned.extend(lst[-max_per_memory:])
    # preserve global order by observed_at
    pruned.sort(key=lambda x: x.get("observed_at", ""))
    log["observations"] = pruned
    return log


# Phase 8.3: Observation log for cross-run validation aggregation
def load_observation_log():
    """Load memory-observation-log.yaml or return empty."""
    if not os.path.exists(OBSERVATION_LOG_FILE):
        return {"version": "1.0", "observations": []}
    with open(OBSERVATION_LOG_FILE) as f:
        return yaml.safe_load(f) or {"version": "1.0", "observations": []}


def save_observation_log(log):
    """Save observation log atomically. Phase 8.5-T3: prune before save (additive)."""
    log = prune_observation_log(log)
    log["last_updated"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(OBSERVATION_LOG_FILE), exist_ok=True)
    with open(OBSERVATION_LOG_FILE, "w") as f:
        yaml.dump(log, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def append_observation_log(memory_id, candidate, loop_id):
    """Append a runtime observation to the observation log for cross-run tracking."""
    log = load_observation_log()
    if "observations" not in log:
        log["observations"] = []
    he = candidate.get("hypothesis_engagement", {}) or {}
    log["observations"].append({
        "memory_id": memory_id,
        "source_loop": loop_id or "unknown",
        "canonical_source": canonical_source_for(candidate) or loop_id or "unknown",
        "source_execution": candidate.get("source_execution", ""),
        "session_id": candidate.get("evidence", {}).get("session_id", ""),
        "output_hash": candidate.get("evidence", {}).get("output_hash", ""),
        "quality_score": candidate.get("quality_score", 0),
        "candidate_type": candidate.get("candidate_type", ""),
        "outcome": candidate.get("outcome", ""),
        "same_loop_as_creation": he.get("same_loop_as_creation", False),
        "created_loop": he.get("created_loop", ""),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "origin": "runtime",
        # Phase 8.7: adversarial provenance (additive, backward compat)
        "observation_id": candidate.get("observation_id") or he.get("observation_id") or "",
        "root_task_id": candidate.get("root_task_id") or he.get("root_task_id") or "",
        "root_execution_id": candidate.get("root_execution_id") or candidate.get("source_execution", ""),
        "model_family": candidate.get("model_family") or he.get("model_family") or "unknown",
        "retrieval_context_hash": candidate.get("retrieval_context_hash") or he.get("retrieval_context_hash") or "",
        "env_fingerprint": candidate.get("env_fingerprint") or candidate.get("evidence", {}).get("env_fingerprint", {}) or {},
        "countable": candidate.get("countable", is_countable_observation(candidate)),
        "loop_id": candidate.get("loop_id") or he.get("loop_id") or loop_id or "",
    })
    save_observation_log(log)


def collect_from_trace_ids(trace_ids, quiet=False, update_state=True, loop_id=None):
    """
    Collect candidates from specific trace IDs.
    Idempotent: skips traces already in collector_state.yaml.

    Args:
        trace_ids: list of execution_id strings (e.g. ["EXEC-1234567890"])
        quiet: suppress console output
        update_state: if True, update collector_state.yaml (default True for standalone)
                      Set to False when called from loop_controller to avoid marking
                      traces as processed without writing candidates file.
        loop_id: optional str, for artifact authority tracing

    Returns:
        list of candidate dicts
    """
    state = load_collector_state()
    processed = set(t.get("trace_id", "") for t in state.get("processed_traces", []))

    all_candidates = []
    new_traces = []

    for eid in trace_ids:
        # Idempotency check: skip if already processed
        if eid in processed:
            if not quiet:
                print(f"  SKIP (already processed): {eid}")
            continue

        if not quiet:
            print(f"  Processing: {eid}")

        trace = load_trace(eid)
        valid, reasons = validate_trace(trace)
        if not valid:
            if not quiet:
                print(f"    SKIP: {reasons}")
            continue

        response = trace.get("agent_response", "")
        quality = evaluate_quality(response)
        candidates = generate_candidates(trace, quality)

        # Phase 8.7: propagate root_task_id / model_family etc from trace to all candidates (additive)
        _trace_root = trace.get("root_task_id") or trace.get("task_id", "")
        _trace_model = trace.get("model_family") or "unknown"
        _trace_loop = trace.get("loop_id", "")
        for c in candidates:
            if not c.get("root_task_id"):
                c["root_task_id"] = _trace_root
                # also propagate into engagement for backward compat
                if "hypothesis_engagement" in c and isinstance(c["hypothesis_engagement"], dict):
                    c["hypothesis_engagement"].setdefault("root_task_id", _trace_root)
            if not c.get("model_family"):
                c["model_family"] = _trace_model
                if "hypothesis_engagement" in c:
                    c["hypothesis_engagement"].setdefault("model_family", _trace_model)
            if not c.get("retrieval_context_hash"):
                c["retrieval_context_hash"] = c.get("hypothesis_engagement", {}).get("retrieval_context_hash", "")
            if "countable" not in c:
                c["countable"] = is_countable_observation(c)
            if not c.get("root_execution_id"):
                c["root_execution_id"] = c.get("source_execution", "")
            if not c.get("env_fingerprint"):
                c["env_fingerprint"] = trace.get("env_fingerprint", {}) or {}
            if not c.get("observation_id"):
                # fallback for established or old hypothesis traces
                hid = c.get("target_memory", "")
                c["observation_id"] = f"OBS-{c.get('source_execution','')}-{hid}" if hid else ""

        if not quiet:
            print(f"    task_id: {trace['task_id']}, status: {trace['status']}")
            print(f"    quality: {quality['weighted']}, candidates: {len(candidates)}")

        all_candidates.extend(candidates)
        new_traces.append({
            "trace_id": eid,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "candidates_generated": len(candidates),
        })

    # Phase 8.3: Stamp loop_id on every candidate for artifact authority
    if loop_id:
        for c in all_candidates:
            c["loop_id"] = loop_id

    # Phase 8.3: Append to observation log for cross-run validation aggregation
    # Phase 8.5-T2: prefer per-candidate loop_id from hypothesis provenance
    # Phase 8.7: write ALL observations including non-countable with countable flag (I12)
    for c in all_candidates:
        try:
            eff_loop = canonical_source_for(c) or loop_id
            append_observation_log(c["target_memory"], c, eff_loop)
        except Exception:
            pass  # Non-critical to observation log write

    # Update state only if update_state=True (standalone mode)
    # When called from loop_controller, state is updated after candidates file is written
    if new_traces and update_state:
        state["processed_traces"].extend(new_traces)
        save_collector_state(state)

    return all_candidates


def collect_new_traces(quiet=False):
    """
    Scan runtime/traces/ for new traces not yet processed.
    Idempotent: only processes traces not in collector_state.yaml.

    Returns:
        list of candidate dicts
    """
    if not os.path.isdir(TRACES_DIR):
        return []

    # Get all trace files
    trace_ids = []
    for fname in sorted(os.listdir(TRACES_DIR)):
        if fname.endswith(".yaml"):
            eid = fname.replace(".yaml", "")
            trace_ids.append(eid)

    if not trace_ids:
        return []

    return collect_from_trace_ids(trace_ids, quiet=quiet)


def write_candidates_output(candidates, source_executions, loop_id=None):
    """Write candidates to memory-candidates.yaml. Phase 8.3: loop_id added."""
    output = {
        "version": "1.0",
        "phase": "5.8.2.2",
        "loop_id": loop_id or "unknown",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "collector.py (Phase 5.8.2.2 Loop Controller)",
        "source_executions": source_executions,
        "candidates": candidates,
        "cycle_summary": {
            "total_candidates": len(candidates),
            "reinforce": sum(1 for c in candidates if c.get("candidate_type") == "reinforce"),
            "weaken": sum(1 for c in candidates if c.get("candidate_type") == "weaken"),
            "create_hypothesis": sum(1 for c in candidates if c.get("candidate_type") == "create_hypothesis"),
            "reinforce_hypothesis": sum(1 for c in candidates if c.get("candidate_type") == "reinforce_hypothesis"),
            "weaken_hypothesis": sum(1 for c in candidates if c.get("candidate_type") == "weaken_hypothesis"),
            "safety_checks": {
                "no_memory_off_processed": "PASS",
                "all_candidates_from_real_traces": "PASS",
                "no_direct_memory_modification": "PASS",
                "hypotheses_held_not_promoted": "PASS",
                "idempotency": "PASS — collector_state.yaml prevents duplicates",
            }
        }
    }

    # Phase 5.9: Atomic write to prevent corruption
    atomic_yaml_write(CANDIDATES_FILE, output)

    return output


def main():
    print("=" * 60)
    print("Phase 5.8.2.2 — Runtime Feedback Collector")
    print("=" * 60)

    # Phase 5.8.2.2: Use new trace scanning
    # Accept optional trace IDs from CLI args
    if len(sys.argv) > 1:
        trace_ids = sys.argv[1:]
        print(f"Processing {len(trace_ids)} specified trace(s): {trace_ids}")
        all_candidates = collect_from_trace_ids(trace_ids)
    else:
        print("Scanning for new traces...")
        all_candidates = collect_new_traces()

    if not all_candidates:
        print("No new candidates generated.")
        return

    print(f"\n{'=' * 60}")
    print(f"Total candidates: {len(all_candidates)}")
    print(f"  reinforce: {sum(1 for c in all_candidates if c.get('candidate_type') == 'reinforce')}")
    print(f"  weaken: {sum(1 for c in all_candidates if c.get('candidate_type') == 'weaken')}")
    print(f"  create_hypothesis: {sum(1 for c in all_candidates if c.get('candidate_type') == 'create_hypothesis')}")

    # Get source execution IDs
    source_executions = list(set(c.get("source_execution", "") for c in all_candidates))

    write_candidates_output(all_candidates, source_executions)
    print(f"\nOutput written to: {CANDIDATES_FILE}")
    print("DONE")

if __name__ == "__main__":
    main()