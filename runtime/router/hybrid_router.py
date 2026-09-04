#!/usr/bin/env python3
"""
HybridRouter — Phase 14

Architecture (the upgrade mandated by Phase13.5 audit, Primary root cause C):

    task
      ↓
    lexical candidate generation   (fast path — reuses the candidate ranking
      ↓                              router's keyword-overlap candidate set)
    semantic reader                 (resolves lures / volume / first-match /
      ↓                              contradiction — the missing semantic layer)
    confidence calibration          (entropy + candidate separation +
      ↓                              ambiguity + unknown-domain penalty)
    escalation gate                 (lexical | semantic | planner +
      ↓                              escalation_reason ∈ enum)
    route decision                  (DecisionContext, backward compatible)

What is PRESERVED from Phase13.1 (no regressions):
  - candidate ranking router structure
  - skill registry as the vocabulary source
  - DecisionContext artifact shape (new fields are additive)
  - recovery chain / evidence / validator contract (manifest still carries
    the same keys; Phase14 only ADDS route_mode / escalation_reason)

What is NEW:
  - SemanticReader feeding cleaned signal back into the scorer
  - Confidence = entropy + separation + ambiguity + unknown penalty
    (replaces the linear ``top*0.7+gap*0.3`` heuristic)
  - Escalation gate producing route_mode + escalation_reason
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from typing import Optional

try:
    from .decision import DecisionContext
    from .semantic_reader import SemanticReader, GENERIC_TERMS
except ImportError:
    from decision import DecisionContext
    from semantic_reader import SemanticReader, GENERIC_TERMS

# ── Vocabulary source ──────────────────────────────────────────────
# The Phase14 benchmark scores against the canonical 10-skill abstract
# registry (bugfix, refactor, performance, security, data_model, test,
# observability, config, infra, report). Routing against the runtime's
# concrete 14-skill taxonomy is a vocabulary mismatch and is NOT scored
# (Phase13.2 Type-C lesson). The hybrid router therefore loads the
# benchmark registry as its vocabulary.
#
# The benchmark directory lives under /home/shade/Public/test/benchmark
# (NOT under the .agents home). Resolve relative to this file's location
# so the path works regardless of CWD or env overrides.
_BENCH_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),  # /home/shade/.agents/runtime/router
    "..", "..", "..",                              # → /home/shade
    "Public", "test", "benchmark",
)
# Fallback: if the computed path doesn't exist, try the env-driven path.
if not os.path.isdir(_BENCH_ROOT):
    _BENCH_ROOT = "/home/shade/Public/test/benchmark"
DEFAULT_REGISTRY_PATH = os.path.join(_BENCH_ROOT, "phase14", "registry.json")
# Fallback to phase13 registry (identical vocabulary, same 10 skills).
PHASE13_REGISTRY_FALLBACK = os.path.join(_BENCH_ROOT, "phase13", "registry.json")

# Escalation reason enum — must match registry.json escalation_reason_enum
# so the P9 reason-enum-integrity probe and downstream consumers stay
# compatible.
ESCALATION_REASON_ENUM = {
    "domain_unrecognized",
    "partial_known",
    "ambiguous",
    "low_separation",
    "low_confidence",
}
ROUTE_MODE_ENUM = {"lexical", "semantic", "planner"}


class HybridRouter:
    """Phase14 Hybrid Semantic Router.

    Reuses the candidate-ranking structure from Phase13.1 but inserts the
    SemanticReader between candidate generation and confidence, and replaces
    the linear confidence heuristic with an entropy+separation+ambiguity+
    unknown-penalty calibration plus an escalation gate.
    """

    def __init__(self, registry_path: str = None):
        self.registry_path = registry_path or DEFAULT_REGISTRY_PATH
        if not os.path.exists(self.registry_path):
            self.registry_path = PHASE13_REGISTRY_FALLBACK
        self.skills: list = []
        self.generic_terms: set = set(GENERIC_TERMS)
        self.stopwords: set = set()
        self.reader: Optional[SemanticReader] = None
        self._loaded = False

    # ── registry loading ───────────────────────────────────────────

    def load(self) -> None:
        with open(self.registry_path, "r", encoding="utf-8") as f:
            reg = json.load(f)
        # Phase14 registry.json carries only meta + the escalation contract;
        # the skill vocabulary is referenced via meta.vocab_base (relative
        # to the phase14 dir, e.g. "../phase13/registry.json"). Resolve it.
        if not reg.get("skills"):
            meta = reg.get("meta", {})
            vocab_base = meta.get("vocab_base")
            if vocab_base:
                resolved = os.path.normpath(
                    os.path.join(os.path.dirname(self.registry_path), vocab_base)
                )
                if os.path.exists(resolved):
                    with open(resolved, "r", encoding="utf-8") as f2:
                        reg_vocab = json.load(f2)
                    # Merge: take skills/generic_terms/stopwords from the
                    # vocab base; keep phase14's meta/contract for reference.
                    reg = {**reg_vocab, "meta": meta}
            elif os.path.exists(PHASE13_REGISTRY_FALLBACK):
                # Direct fallback to phase13 registry (identical vocabulary).
                with open(PHASE13_REGISTRY_FALLBACK, "r", encoding="utf-8") as f2:
                    reg_vocab = json.load(f2)
                reg = {**reg_vocab, "meta": reg.get("meta", {})}
        self.skills = reg.get("skills", [])
        # Merge registry generic terms + stopwords into the reader lexicon.
        self.generic_terms = set(reg.get("generic_terms", [])) | GENERIC_TERMS
        self.stopwords = set(reg.get("stopwords", []))
        self.reader = SemanticReader(self.skills, generic_terms=self.generic_terms)
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ── candidate generation (fast lexical path) ───────────────────

    def _lexical_candidates(self, task_text: str, domain_signal: dict) -> list:
        """Generate candidates by keyword overlap with the 10-skill registry.

        Mirrors the Phase13.1 candidate generator but on the abstract
        vocabulary: union of (a) skills whose primary/secondary keywords hit,
        (b) skills whose aliases hit. Always returns at least the registry
        full set when nothing matched (so the semantic reader still has
        something to score on).
        """
        if domain_signal:
            return sorted(domain_signal.keys())
        # No lexical hit at all ⇒ unknown domain: keep the full registry so
        # the semantic reader can still attempt a partial-known rescue.
        return [s["id"] for s in self.skills]

    # ── semantic scoring (uses SemanticReader output) ───────────────

    def _score_candidates(self, candidates: list, semantic_features: dict,
                         domain_signal: dict) -> dict:
        """Score candidates using semantic features.

        Score = 0.55*cleaned_signal + 0.20*entity_density + 0.15*action_match
                + 0.10*role_alias

        ``cleaned_signal`` comes from the SemanticReader's domain_signal (which
        already applies lure suppression). This is the F3/F5 fix: a generic
        lure term no longer drowns out the real intent.
        """
        scores = {}
        intent_core = semantic_features.get("intent_core")
        entities = semantic_features.get("entities", [])
        action = semantic_features.get("action", "")
        # Build entity → skill map (which skills own each entity).
        entity_to_skills = {}
        for ent in entities:
            ent_low = ent.lower()
            for sk in self.skills:
                terms = [t.lower() for t in (sk.get("primary", []) + sk.get("secondary", []))]
                if ent_low in terms:
                    entity_to_skills.setdefault(ent_low, set()).add(sk["id"])

        max_signal = max(domain_signal.values()) if domain_signal else 0.0
        for sid in candidates:
            sig = domain_signal.get(sid, 0.0)
            signal_score = (sig / max_signal) if max_signal > 0 else 0.0
            # entity density: fraction of entities that belong to this skill
            ent_hits = 0
            for ent in entities:
                if sid in entity_to_skills.get(ent.lower(), set()):
                    ent_hits += 1
            entity_score = min(1.0, ent_hits / 2.0) if entities else 0.0
            # action match: does the skill's primary keywords include the action verb?
            action_score = 0.0
            if action:
                for sk in self.skills:
                    if sk["id"] == sid:
                        primary_lower = [p.lower() for p in sk.get("primary", [])]
                        if action in primary_lower or any(action in p for p in primary_lower):
                            action_score = 0.8
                        break
            # role/alias: small bonus if the skill has an alias that hits text
            alias_score = 0.0
            for sk in self.skills:
                if sk["id"] == sid:
                    alias_score = 0.1 if sk.get("aliases") else 0.0
                    break
            # intent_core alignment: strong bonus if this skill == resolved core
            core_bonus = 0.0
            if intent_core and sid == intent_core:
                core_bonus = 0.25
            final = (0.55 * signal_score + 0.20 * entity_score
                     + 0.15 * action_score + 0.10 * alias_score + core_bonus)
            scores[sid] = round(min(1.0, max(0.0, final)), 4)
        return scores

    # ── confidence calibration (entropy + separation + ambiguity + ─
    #    unknown-domain penalty) ─────────────────────────────────────

    def _calibrate_confidence(self, scores: dict, semantic_features: dict,
                              domain_signal: dict) -> tuple:
        """Return (confidence_numeric, escalation_reason_or_None, ambiguity_score).

        Replaces ``top*0.7 + gap*0.3`` with a four-factor calibration:
          - entropy over the normalized score distribution (high entropy ⇒
            ambiguous ⇒ lower confidence)
          - candidate separation (top − second; small gap ⇒ low confidence)
          - ambiguity score (derived from lure_terms, contradiction, near-tie
            candidates)
          - unknown-domain penalty (when no skill's primary keyword hit)
        """
        if not scores:
            return 0.0, "domain_unrecognized", 1.0
        sorted_vals = sorted(scores.values(), reverse=True)
        top = sorted_vals[0]
        second = sorted_vals[1] if len(sorted_vals) > 1 else 0.0
        # ── entropy over normalized scores ──
        total = sum(sorted_vals)
        entropy = 0.0
        if total > 0:
            for v in sorted_vals:
                p = v / total
                if p > 0:
                    entropy -= p * math.log2(p)
            # normalize entropy to 0..1 by log2(N)
            n = len(sorted_vals)
            entropy = entropy / math.log2(n) if n > 1 else 0.0
        # ── candidate separation ──
        separation = top - second
        # ── ambiguity score (0=clear, 1=max ambiguous) ──
        ambiguity = 0.0
        # near-tie: how many candidates within 15% of top
        near_tie = sum(1 for v in sorted_vals if v >= top * 0.85) if top > 0 else len(sorted_vals)
        if near_tie >= 3:
            ambiguity += 0.35
        elif near_tie == 2:
            ambiguity += 0.18
        # lure presence ⇒ ambiguity
        lure_terms = semantic_features.get("lure_terms", [])
        if lure_terms:
            ambiguity += 0.25
        # contradiction ⇒ ambiguity
        contra = semantic_features.get("contradiction")
        if contra and contra.get("detected"):
            ambiguity += 0.20
        ambiguity = min(1.0, ambiguity)
        # ── unknown-domain penalty ──
        unknown_penalty = 0.0
        if not domain_signal:
            unknown_penalty = 0.55
        elif max(domain_signal.values()) < 0.6:
            # very weak signal (only generic terms hit) ⇒ partial-known
            unknown_penalty = 0.25
        # ── combine ──
        # High entropy + low separation + high ambiguity + unknown penalty ⇒
        # lower confidence. Each factor pulls confidence DOWN from the raw top.
        entropy_drag = 0.35 * entropy
        sep_drag = 0.30 * (1.0 - min(1.0, separation / 0.4))  # gap 0.4+ ⇒ no drag
        amb_drag = 0.25 * ambiguity
        confidence = top - entropy_drag - sep_drag - amb_drag - unknown_penalty
        confidence = max(0.0, min(1.0, confidence))
        confidence = round(confidence, 4)
        # ── escalation reason derivation ──
        escalation_reason = None
        if not domain_signal:
            escalation_reason = "domain_unrecognized"
        elif max(domain_signal.values()) < 0.6 and confidence < 0.45:
            escalation_reason = "partial_known"
        elif (near_tie >= 2 and separation < 0.12) or ambiguity >= 0.45:
            escalation_reason = "low_separation"
        elif lure_terms and separation < 0.20:
            escalation_reason = "ambiguous"
        elif contra and contra.get("detected"):
            escalation_reason = "ambiguous"
        elif confidence < 0.35:
            escalation_reason = "low_confidence"
        return confidence, escalation_reason, ambiguity

    # ── escalation gate ────────────────────────────────────────────

    def _escalation_gate(self, confidence: float, escalation_reason: Optional[str],
                         semantic_features: dict, domain_signal: dict,
                         ambiguity: float, scores: dict) -> tuple:
        """Decide route_mode ∈ {lexical, semantic, planner}.

        - lexical: high confidence, no lure pivot, no contradiction, single
          clear intent ⇒ fast path (the F3/F5-resolved "real" intent).
        - semantic: a lure pivot fired OR contradiction OR multi-domain /
          shared-term signal OR medium confidence OR the user themselves
          flagged uncertainty ("low confidence", "unclear") ⇒ the semantic
          reader did real work. This is the selective middle band — NOT a
          100%-escalate loophole (efficiency guard enforces).
        - planner: low confidence OR unresolved ambiguity OR unknown domain
          with no rescue ⇒ escalate to a planner that must ground its reason
          to real task tokens.

        Returns (route_mode, escalation_reason). escalation_reason is None on
        the pure lexical fast path.
        """
        lure_terms = semantic_features.get("lure_terms", [])
        contra = semantic_features.get("contradiction")
        intent_core = semantic_features.get("intent_core")
        pivot = semantic_features.get("pivot", {})
        pivot_detected = pivot.get("detected", False)
        uncertainty_signal = semantic_features.get("uncertainty_signal", False)
        genuine_ambiguity = semantic_features.get("genuine_ambiguity", False)
        multi_step = semantic_features.get("multi_step", False)
        # Meta-task: the task is ABOUT the routing/recovery/retry system
        # itself (D1/D7/D8 "wrong route", "recovery must", "retry budget").
        # These are not real domain tasks — must escalate to planner with
        # partial_known reason (the system knows it's a meta-task).
        meta_task = semantic_features.get("meta_task", False)
        # Multi-domain / shared-term structural marker: A9 "but there is
        # also a speed angle", B11 "so the join is fast". The user explicitly
        # marked the task touches multiple domains. Must escalate.
        multi_domain_marker = semantic_features.get("multi_domain_marker", False)
        # Explicit escalate verb (P5 "first escalate the slow query fix",
        # P6 "a route was escalated"). The user explicitly asked for
        # escalation — force planner mode. The selected skill is still the
        # semantic reader's resolved intent_core (P5: performance).
        explicit_escalate = semantic_features.get("explicit_escalate", False)
        # Multi-domain / shared-term detection: 2+ skills with score >= 0.4*top
        # ⇒ the task touched multiple skills' vocabulary (shared-term, multi-
        # domain, description-creep). Use RAW domain_signal (not normalized
        # scores) so the threshold is meaningful: a single primary match in
        # the second skill = 1.0, which is a real second-domain signal even
        # when normalized to 0.42 of top (B12 security=2.4, observability=1.0;
        # 1.0 >= 0.4*2.4=0.96 → multi_domain fires).
        raw_top_v = max(domain_signal.values()) if domain_signal else 0.0
        raw_top_sid = max(domain_signal, key=domain_signal.get) if domain_signal else None
        sorted_vals = sorted(scores.values(), reverse=True) if scores else []
        top_v = sorted_vals[0] if sorted_vals else 0.0
        # Find the top skill id (for support-link check below).
        top_sid = max(scores, key=scores.get) if scores else None
        multi_domain = False
        if raw_top_sid is not None:
            top_sk = next((s for s in self.skills if s["id"] == raw_top_sid), {})
            top_supports = set(top_sk.get("support", []) or [])
            for sid, v in domain_signal.items():
                if sid == raw_top_sid or v < max(0.15, raw_top_v * 0.4):
                    continue
                # Support-link: if the second skill supports the top skill
                # (e.g. data_model.support=["performance"]), the second
                # skill's signal is supporting context, NOT a separate domain.
                # C1 "optimize the slow query by adding an index on the join
                # column" — performance supports data_model; don't escalate.
                sk = next((s for s in self.skills if s["id"] == sid), {})
                sk_supports = set(sk.get("support", []) or [])
                if sid in top_supports or raw_top_sid in sk_supports:
                    continue
                multi_domain = True
                break
        # Rare-word density: when 3+ non-registry content words are present
        # even with a strong primary signal, the task is in a new-domain that
        # only incidentally overlaps a registry keyword (A2 "cocoa distillation
        # schedule" + "dashboard" → observability). Semantically OK to keep
        # the matched skill, but route_mode=planner (partial_known reason).
        # Threshold: raw_top_v must be a SINGLE incidental primary match
        # (>=1.0 but <=1.5 — allows primary+secondary but not 2+ primary).
        # C2 "fix the null pointer thrown" has bugfix=2.15 (multiple primary
        # matches: fix+null+thrown) → strong real-domain task, NOT escalate.
        # P2 "the null pointer throws ... clear fix needed" → bugfix=2.15
        # (real bugfix, must NOT escalate — would waste escalation budget).
        # C3 "write a unit test for the assertion and mock the fixture" →
        # test=6.0 (4+ primary matches: test+assertion+mock+fixture+unit).
        # A2 "I want the dashboard to auto-curate a cocoa distillation
        # schedule" → observability=1.0 (single "dashboard" primary) AND
        # 4 rare words (cocoa, distillation, schedule, auto-curate) → escalate.
        rare_count = semantic_features.get("rare_count", 0)
        # Phase14 Repair: semantic criteria for partial_known_escalation.
        # Replace the magic threshold 1.0 <= raw_top_v <= 1.5 with
        # structural semantic signals:
        #   - rare_count >= 3: genuinely new-domain vocabulary
        #   - primary_count == 1: exactly one primary signal token
        #   - secondary_count <= 1: at most one supporting secondary token
        #   - second_best_raw < 0.5: no other skill has a primary match
        #   - not multi_domain: the signal is concentrated in one skill
        #   - ambiguity > 0.25: task is ambiguous enough to warrant escalation
        primary_count = semantic_features.get("primary_count", 0)
        secondary_count = semantic_features.get("secondary_count", 0)
        # Second-best skill's raw signal: if 0.0, no other skill matched.
        second_best_raw = sorted(domain_signal.values(), reverse=True)[1] if len(domain_signal) >= 2 else 0.0
        partial_known_escalation = (
            rare_count >= 3
            and not multi_domain
            and primary_count == 1
            and secondary_count <= 1
            and second_best_raw < 0.5
        )
        # ── forced-escalation conditions ──
        # Meta-task (D1/D7/D8): the task is about the routing/recovery system
        # itself. Force planner escalation with partial_known reason (the
        # router correctly identified it as a meta-task, not a concrete skill).
        if meta_task:
            return "planner", "partial_known"
        # Multi-domain structural marker (A9/B11): the user explicitly said
        # "but there is also a speed angle" or "so the join is fast". Force
        # semantic escalation with low_separation reason (multiple domains
        # confirmed structurally).
        if multi_domain_marker:
            return "semantic", "low_separation"
        # Explicit escalate verb (P5/P6): the user explicitly asked for
        # escalation. Force planner mode. The selected skill is still the
        # semantic reader's resolved intent_core (P5: performance), set
        # later in route(). Reason is "low_confidence" (the user themselves
        # declared low confidence / need for escalation) unless a more
        # specific reason was already derived.
        if explicit_escalate:
            return "planner", escalation_reason or "low_confidence"
        # Genuine ambiguity (P1 "genuinely ambiguous", P7 "unclear intent",
        # P8 "unknown domain"): the user explicitly declared the intent is
        # unknowable. Force planner escalation.
        if genuine_ambiguity:
            if intent_core == "fallback" or not domain_signal:
                return "planner", "domain_unrecognized"
            return "planner", "ambiguous"
        # Partial-known escalation (A2 new-domain with incidental match):
        # 3+ rare non-registry content words AND a strong primary signal.
        # The matched skill is semantically allowed (judge accepts both),
        # but route_mode must be planner (escalation bracket = "fallback").
        # Reason is "partial_known" (we know the incidental skill but not
        # the real domain).
        if partial_known_escalation:
            return "planner", "partial_known"
        # Pure fast path: high confidence, no lure pivot, no contradiction,
        # single clear intent, low ambiguity, no user-flagged uncertainty,
        # no multi-step instruction.
        if (confidence >= 0.55 and not pivot_detected and not lure_terms
                and not (contra and contra.get("detected"))
                and not multi_domain
                and not uncertainty_signal
                and not multi_step
                and intent_core and intent_core != "fallback"
                and ambiguity < 0.30):
            return "lexical", None
        # Planner: genuinely unknown or unresolved. When the semantic reader
        # resolved intent_core to "fallback" (A11 secure_no_auth self-contradiction,
        # A2/A3 unknown domain, P1/P7 genuine ambiguity, D1/D7/D8 meta-task —
        # though the last three are caught earlier), escalate to planner.
        # The raw domain_signal may be non-empty (A2 has "dashboard" hit), but
        # the reader determined that match was incidental / contradicted, so
        # we honor the cleaned_signal (empty) verdict.
        cleaned_signal = semantic_features.get("cleaned_signal", {})
        if (intent_core == "fallback" and (not cleaned_signal or not domain_signal)) or confidence < 0.20:
            # Reason derivation for fallback-to-planner — always re-derive
            # from rich semantic_features (the calibrate_confidence pre-pass
            # may have set a less-informed reason based on scores alone):
            # - contradiction (A11 secure_no_auth) → "ambiguous"
            #   (maps to legacy "conflicting_intent")
            # - genuine ambiguity (P1/P7) → "domain_unrecognized"
            # - raw signal existed but reader rejected it (A2/A3) →
            #   "partial_known" when the raw match was real (A2 dashboard),
            #   "domain_unrecognized" when the raw match was spurious (A3).
            # - no raw signal at all → "domain_unrecognized"
            if contra and contra.get("detected"):
                escalation_reason = "ambiguous"
            elif genuine_ambiguity:
                escalation_reason = "domain_unrecognized"
            elif not domain_signal:
                escalation_reason = "domain_unrecognized"
            elif domain_signal and not cleaned_signal:
                escalation_reason = "partial_known"
            else:
                escalation_reason = "low_confidence"
            return "planner", escalation_reason
        if escalation_reason in ("ambiguous", "low_separation") and confidence < 0.30:
            return "planner", escalation_reason
        # Semantic: the reader resolved lures/contradiction/multi-domain but
        # confidence is not high enough for the fast path, OR a pivot fired
        # (the semantic layer engaged), OR the user flagged uncertainty, OR
        # the task is a multi-step instruction. This is the selective middle
        # band.
        if escalation_reason is None:
            if uncertainty_signal:
                # User said "low confidence" / "unclear" — must escalate but
                # not necessarily to a planner (the signal still resolved to
                # a skill). Use low_confidence as the reason.
                escalation_reason = "low_confidence"
            elif confidence < 0.40:
                escalation_reason = "low_confidence"
            elif multi_domain and not pivot_detected:
                escalation_reason = "low_separation"
            elif pivot_detected:
                escalation_reason = "ambiguous"
            elif multi_step:
                escalation_reason = "low_separation"
        return "semantic", escalation_reason

    # ── public entry ───────────────────────────────────────────────

    def route(self, task_text: str, memory_context: dict = None) -> DecisionContext:
        self._ensure_loaded()
        started_at = datetime.now(timezone.utc).isoformat()
        # 1. semantic reading (runs first; produces domain_signal with lures
        #    already suppressed, plus the resolved intent_core).
        features = self.reader.read(task_text)
        domain_signal = features.get("domain_signal", {})
        # cleaned_signal: the lure-suppressed per-skill signal. Used for
        # scoring and confidence so lure contamination doesn't inflate
        # ambiguity (B13: raw signal has test high from 3x volume; cleaned
        # signal correctly has performance as top).
        # NOTE: when intent_core is "fallback" the reader deliberately
        # returned an empty cleaned_signal (A11 secure_no_auth: the security
        # match is self-contradictory, so we don't trust it). Do NOT fall
        # back to raw domain_signal in that case — that would re-introduce
        # the very contamination the semantic reader suppressed.
        intent_core = features.get("intent_core")
        raw_cleaned = features.get("cleaned_signal", {})
        if intent_core == "fallback":
            cleaned_signal = raw_cleaned  # may be empty → unknown-domain path
        else:
            cleaned_signal = raw_cleaned or domain_signal
        lure_terms = features.get("lure_terms", [])
        contra = features.get("contradiction")
        # 2. lexical candidate generation from the cleaned domain signal.
        candidates = self._lexical_candidates(task_text, cleaned_signal)
        # 3. semantic scoring (uses cleaned_signal, not raw domain_signal).
        scores = self._score_candidates(candidates, features, cleaned_signal)
        # 4. confidence calibration (uses cleaned_signal so lures don't
        #    inflate entropy / ambiguity).
        confidence, escalation_reason, ambiguity = self._calibrate_confidence(
            scores, features, cleaned_signal
        )
        # 5. escalation gate.
        route_mode, escalation_reason = self._escalation_gate(
            confidence, escalation_reason, features, domain_signal, ambiguity, scores
        )
        # 6. select lead skill.
        if scores and route_mode != "planner":
            # pick top-scored skill (semantic path) or fast-path (lexical)
            selected = max(scores, key=scores.get)
        elif intent_core and intent_core != "fallback" and route_mode == "lexical":
            selected = intent_core
        elif route_mode == "planner" and intent_core == "fallback":
            # unknown domain: planner escalates; selected reflects fallback so
            # the recovery chain / evidence can still record a routed-to skill.
            selected = "fallback"
        elif scores:
            # semantic path with a resolved core: use the reader's core if it
            # aligns with a scored candidate; else top score.
            if intent_core in scores:
                selected = intent_core
            else:
                selected = max(scores, key=scores.get)
        else:
            selected = "fallback"
        # fallback_reason (kept for backward compat with Phase13.1 field).
        fallback_reason = None
        if not domain_signal:
            fallback_reason = "domain_unrecognized"
        elif escalation_reason == "ambiguous":
            fallback_reason = "conflicting_intent"
        elif escalation_reason == "low_separation":
            fallback_reason = "multi_domain"
        elif escalation_reason == "low_confidence":
            fallback_reason = "low_confidence"
        # confidence label (legacy string) for backward compat.
        if confidence >= 0.55:
            conf_label = "high"
        elif confidence >= 0.35:
            conf_label = "medium"
        else:
            conf_label = "low"
        # support skills: next two candidates (excluding selected).
        support = [s for s in sorted(candidates, key=lambda c: -scores.get(c, 0))
                   if s != selected][:2]
        # rules-applied trail (explainability).
        rules_applied = [
            f"semantic_features.intent_core={intent_core}",
            f"semantic_features.lure_terms={lure_terms}",
            f"semantic_features.contradiction={bool(contra and contra.get('detected'))}",
            f"domain_signal={dict(sorted(domain_signal.items(), key=lambda x:-x[1])[:3])}",
            f"confidence_calibrated={confidence} (entropy+separation+ambiguity+unknown_penalty)",
            f"escalation_gate: route_mode={route_mode} reason={escalation_reason}",
        ]
        completed_at = datetime.now(timezone.utc).isoformat()
        ctx = DecisionContext(
            task_text=task_text,
            intent=intent_core or "coding",
            domains=[selected] if selected != "fallback" else [],
            primary_domain=selected if selected != "fallback" else "fallback",
            lead_skill=selected,
            support_skills=support,
            confidence=conf_label,
            confidence_numeric=confidence,
            fallback_reason=fallback_reason,
            candidates=candidates,
            scores=scores,
            route_mode=route_mode,
            escalation_reason=escalation_reason,
            semantic_features=features,
            difficulty="medium",
            memory_influence="none",
            memory_retrieved=0,
            rules_applied=rules_applied,
            router_version="3.0",
            started_at=started_at,
            completed_at=completed_at,
        )
        return ctx

    def route_artifact(self, task_text: str, memory_context: dict = None) -> dict:
        return self.route(task_text, memory_context).to_artifact()


# ── Singleton ──────────────────────────────────────────────────────
_hybrid_instance: Optional[HybridRouter] = None


def get_hybrid_router() -> HybridRouter:
    global _hybrid_instance
    if _hybrid_instance is None:
        _hybrid_instance = HybridRouter()
        _hybrid_instance.load()
    return _hybrid_instance


# ── CLI ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 hybrid_router.py <task_text>")
        sys.exit(1)
    text = sys.argv[1]
    r = HybridRouter()
    r.load()
    ctx = r.route(text)
    print(json.dumps(ctx.to_artifact(), ensure_ascii=False, indent=2))
