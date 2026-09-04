#!/usr/bin/env python3
"""
Memory Retrieval Audit Layer — Phase 8.9

Records every memory retrieval event with full provenance for auditability.

Each retrieval event captures:
  - query (task classification result)
  - timestamp
  - retrieved memory IDs + confidence scores
  - hypothesis IDs
  - decision: used / rejected / irrelevant (per-memory)

Output: ~/.agents/reports/{session}/memory-retrieval.json

This is a NON-INTRUSIVE audit layer. It hooks into existing retrieval flows
without modifying the retrieval adapter or optimizer logic.
"""

import os
import json
import time
from datetime import datetime, timezone

BASE = "/home/shade/.agents"
REPORTS_DIR = os.path.join(BASE, "reports")


def _session_id():
    """Generate a session ID from timestamp or environment."""
    return os.environ.get("AOS_SESSION_ID", datetime.now(timezone.utc).strftime("SESS-%Y%m%d-%H%M%S"))


def _session_dir(session=None):
    """Get or create the session reports directory."""
    sid = session or _session_id()
    d = os.path.join(REPORTS_DIR, sid)
    os.makedirs(d, exist_ok=True)
    return d


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def record_retrieval(query, raw_result, decision_context, task_id="", loop_id="", session_id=""):
    """
    Record a retrieval event to the audit log.

    Args:
        query: dict — task classification result (from retrieval_adapter.classify_task)
        raw_result: dict — raw retrieval result from retrieval_optimizer.retrieve()
        decision_context: dict — the full DecisionContext returned by retrieval_adapter.adapt()
        task_id: str — task identifier
        loop_id: str — loop execution identifier
        session_id: str — Phase 10.5: unified session ID

    Returns:
        str — path to the audit file written
    """
    session = session_id or _session_id()
    session_dir = _session_dir(session)

    now = _now_iso()

    # Build per-memory decision records
    memory_decisions = []
    for mem in decision_context.get("memories", []):
        mid = mem.get("memory_id", "?")
        decision = _classify_decision(mem, decision_context)
        memory_decisions.append({
            "memory_id": mid,
            "type": mem.get("type", "established"),
            "category": mem.get("category", ""),
            "static_relevance": mem.get("static_relevance", 0),
            "confidence_score": mem.get("confidence_score", 0),
            "final_score": mem.get("final_score", 0),
            "decision": decision,
            "match_reasons": mem.get("match_reasons", []),
        })

    for hyp in decision_context.get("hypotheses", []):
        hid = hyp.get("memory_id", "?")
        decision = _classify_decision(hyp, decision_context)
        memory_decisions.append({
            "memory_id": hid,
            "type": "hypothesis",
            "category": hyp.get("category", ""),
            "static_relevance": hyp.get("static_relevance", 0),
            "confidence_score": hyp.get("confidence_score", 0),
            "final_score": hyp.get("final_score", 0),
            "decision": decision,
            "match_reasons": hyp.get("match_reasons", []),
            "created_loop": hyp.get("created_loop", ""),
        })

    event = {
        "event": "retrieval",
        "session": session,
        "loop_id": loop_id,
        "task_id": task_id,
        "timestamp": now,
        "query": {
            "category": query.get("category", ""),
            "domains": query.get("domains", []),
            "keywords": query.get("keywords", []),
            "difficulty": query.get("difficulty", ""),
        },
        "retrieval_stats": {
            "total_retrieved": decision_context.get("total_retrieved", 0),
            "total_considered": decision_context.get("total_considered", 0),
            "after_filter": decision_context.get("after_filter", 0),
            "memory_count": len(decision_context.get("memories", [])),
            "hypothesis_count": len(decision_context.get("hypotheses", [])),
        },
        "memory_decisions": memory_decisions,
        "ranking": decision_context.get("ranking", []),
    }

    # Append to session audit log (append-only, JSON Lines)
    audit_path = os.path.join(session_dir, "memory-retrieval.jsonl")
    with open(audit_path, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    return audit_path


def _classify_decision(memory, decision_context):
    """
    Classify whether a memory was used, rejected, or irrelevant.

    Rules:
      - If final_score >= 0.6 and in ranking: "used"
      - If final_score >= 0.3 but not in ranking: "rejected"
      - If final_score < 0.3: "irrelevant"
    """
    final_score = memory.get("final_score", 0)
    ranking = decision_context.get("ranking", [])
    mid = memory.get("memory_id", "")

    if mid in ranking:
        return "used"
    elif final_score >= 0.3:
        return "rejected"
    else:
        return "irrelevant"


def get_session_audit(session=None):
    """
    Read the full retrieval audit log for a session.

    Returns:
        list of dict — all retrieval events in the session
    """
    sid = session or _session_id()
    audit_path = os.path.join(_session_dir(sid), "memory-retrieval.jsonl")
    if not os.path.exists(audit_path):
        return []
    events = []
    with open(audit_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def get_retrieval_stats(session=None):
    """
    Compute retrieval statistics for a session.

    Returns:
        dict with usage counts, rejection rates, etc.
    """
    events = get_session_audit(session)
    if not events:
        return {"total_events": 0, "total_memories": 0, "used": 0, "rejected": 0, "irrelevant": 0}

    stats = {"total_events": len(events), "total_memories": 0, "used": 0, "rejected": 0, "irrelevant": 0}
    for evt in events:
        for md in evt.get("memory_decisions", []):
            stats["total_memories"] += 1
            d = md.get("decision", "irrelevant")
            if d in stats:
                stats[d] += 1
    return stats