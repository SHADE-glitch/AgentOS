"""Hybrid semantic router (ported from the Phase14 ``HybridRouter``).

Pipeline:

    task
      -> lexical candidate generation
      -> semantic reader        (lure / volume / first-match / contradiction)
      -> confidence calibration (entropy + separation + ambiguity + unknown)
      -> escalation gate        (lexical | semantic | planner)
      -> DecisionContext

The algorithm is unchanged from the original. What changed in the port:

  - the registry is bundled inside the package (no external benchmark path)
  - the registry path is overridable via ``AOS_REGISTRY_PATH`` or a
    content-layer override at ``content/routing/registry.json``
  - the abstract -> concrete role mapping lives in ``taxonomy.py``
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from aos.config import get_paths
from aos.core.routing import taxonomy
from aos.core.routing.decision import DecisionContext
from aos.core.routing.semantic_reader import GENERIC_TERMS, SemanticReader

# ── Vocabulary source ──────────────────────────────────────────────
# The canonical vocabulary is the 10-skill abstract registry bundled with
# the engine. It can be overridden by a content-layer copy.
_REGISTRY_DIR = Path(__file__).resolve().parent / "registry"
_PHASE14_REGISTRY = _REGISTRY_DIR / "phase14" / "registry.json"
PHASE13_REGISTRY_FALLBACK = _REGISTRY_DIR / "phase13" / "registry.json"

ESCALATION_REASON_ENUM = {
    "domain_unrecognized",
    "partial_known",
    "ambiguous",
    "low_separation",
    "low_confidence",
}
ROUTE_MODE_ENUM = {"lexical", "semantic", "planner"}


def _resolve_registry_path() -> Path:
    """Resolve the routing registry path: env > content override > bundled."""
    env = os.environ.get("AOS_REGISTRY_PATH")
    if env:
        return Path(env).expanduser()
    try:
        override = get_paths().content_dir / "routing" / "registry.json"
    except Exception:  # pragma: no cover - config should not fail here
        override = None
    if override is not None and override.is_file():
        return override
    return _PHASE14_REGISTRY


class HybridRouter:
    """Hybrid semantic router.

    Reuses candidate ranking, inserts the :class:`SemanticReader` between
    candidate generation and confidence, and replaces the linear confidence
    heuristic with entropy+separation+ambiguity calibration plus an
    escalation gate.
    """

    def __init__(self, registry_path: str | os.PathLike | None = None):
        self.registry_path = Path(registry_path) if registry_path else _resolve_registry_path()
        if not self.registry_path.exists():
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
        # A registry may carry only meta + the escalation contract and refer
        # to the skill vocabulary via meta.vocab_base (relative to its dir).
        if not reg.get("skills"):
            meta = reg.get("meta", {})
            vocab_base = meta.get("vocab_base")
            if vocab_base:
                resolved = os.path.normpath(
                    os.path.join(os.path.dirname(str(self.registry_path)), vocab_base)
                )
                if os.path.exists(resolved):
                    with open(resolved, "r", encoding="utf-8") as f2:
                        reg_vocab = json.load(f2)
                    reg = {**reg_vocab, "meta": meta}
            elif PHASE13_REGISTRY_FALLBACK.exists():
                with open(PHASE13_REGISTRY_FALLBACK, "r", encoding="utf-8") as f2:
                    reg_vocab = json.load(f2)
                reg = {**reg_vocab, "meta": reg.get("meta", {})}
        self.skills = reg.get("skills", [])
        self.generic_terms = set(reg.get("generic_terms", [])) | GENERIC_TERMS
        self.stopwords = set(reg.get("stopwords", []))
        self.reader = SemanticReader(self.skills, generic_terms=self.generic_terms)
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ── candidate generation (fast lexical path) ───────────────────

    def _lexical_candidates(self, task_text: str, domain_signal: dict) -> list:
        if domain_signal:
            return sorted(domain_signal.keys())
        return [s["id"] for s in self.skills]

    # ── semantic scoring ───────────────────────────────────────────

    def _score_candidates(self, candidates: list, semantic_features: dict,
                          domain_signal: dict) -> dict:
        scores = {}
        intent_core = semantic_features.get("intent_core")
        entities = semantic_features.get("entities", [])
        action = semantic_features.get("action", "")
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
            ent_hits = 0
            for ent in entities:
                if sid in entity_to_skills.get(ent.lower(), set()):
                    ent_hits += 1
            entity_score = min(1.0, ent_hits / 2.0) if entities else 0.0
            action_score = 0.0
            if action:
                for sk in self.skills:
                    if sk["id"] == sid:
                        primary_lower = [p.lower() for p in sk.get("primary", [])]
                        if action in primary_lower or any(action in p for p in primary_lower):
                            action_score = 0.8
                        break
            alias_score = 0.0
            for sk in self.skills:
                if sk["id"] == sid:
                    alias_score = 0.1 if sk.get("aliases") else 0.0
                    break
            core_bonus = 0.0
            if intent_core and sid == intent_core:
                core_bonus = 0.25
            final = (0.55 * signal_score + 0.20 * entity_score
                     + 0.15 * action_score + 0.10 * alias_score + core_bonus)
            scores[sid] = round(min(1.0, max(0.0, final)), 4)
        return scores

    # ── confidence calibration ─────────────────────────────────────

    def _calibrate_confidence(self, scores: dict, semantic_features: dict,
                              domain_signal: dict) -> tuple:
        if not scores:
            return 0.0, "domain_unrecognized", 1.0
        sorted_vals = sorted(scores.values(), reverse=True)
        top = sorted_vals[0]
        second = sorted_vals[1] if len(sorted_vals) > 1 else 0.0
        total = sum(sorted_vals)
        entropy = 0.0
        if total > 0:
            for v in sorted_vals:
                p = v / total
                if p > 0:
                    entropy -= p * math.log2(p)
            n = len(sorted_vals)
            entropy = entropy / math.log2(n) if n > 1 else 0.0
        separation = top - second
        ambiguity = 0.0
        near_tie = sum(1 for v in sorted_vals if v >= top * 0.85) if top > 0 else len(sorted_vals)
        if near_tie >= 3:
            ambiguity += 0.35
        elif near_tie == 2:
            ambiguity += 0.18
        lure_terms = semantic_features.get("lure_terms", [])
        if lure_terms:
            ambiguity += 0.25
        contra = semantic_features.get("contradiction")
        if contra and contra.get("detected"):
            ambiguity += 0.20
        ambiguity = min(1.0, ambiguity)
        unknown_penalty = 0.0
        if not domain_signal:
            unknown_penalty = 0.55
        elif max(domain_signal.values()) < 0.6:
            unknown_penalty = 0.25
        entropy_drag = 0.35 * entropy
        sep_drag = 0.30 * (1.0 - min(1.0, separation / 0.4))
        amb_drag = 0.25 * ambiguity
        confidence = top - entropy_drag - sep_drag - amb_drag - unknown_penalty
        confidence = max(0.0, min(1.0, confidence))
        confidence = round(confidence, 4)
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
        lure_terms = semantic_features.get("lure_terms", [])
        contra = semantic_features.get("contradiction")
        intent_core = semantic_features.get("intent_core")
        pivot = semantic_features.get("pivot", {})
        pivot_detected = pivot.get("detected", False)
        uncertainty_signal = semantic_features.get("uncertainty_signal", False)
        genuine_ambiguity = semantic_features.get("genuine_ambiguity", False)
        multi_step = semantic_features.get("multi_step", False)
        meta_task = semantic_features.get("meta_task", False)
        multi_domain_marker = semantic_features.get("multi_domain_marker", False)
        explicit_escalate = semantic_features.get("explicit_escalate", False)
        raw_top_v = max(domain_signal.values()) if domain_signal else 0.0
        raw_top_sid = max(domain_signal, key=domain_signal.get) if domain_signal else None
        sorted_vals = sorted(scores.values(), reverse=True) if scores else []
        multi_domain = False
        if raw_top_sid is not None:
            top_sk = next((s for s in self.skills if s["id"] == raw_top_sid), {})
            top_supports = set(top_sk.get("support", []) or [])
            for sid, v in domain_signal.items():
                if sid == raw_top_sid or v < max(0.15, raw_top_v * 0.4):
                    continue
                sk = next((s for s in self.skills if s["id"] == sid), {})
                sk_supports = set(sk.get("support", []) or [])
                if sid in top_supports or raw_top_sid in sk_supports:
                    continue
                multi_domain = True
                break
        rare_count = semantic_features.get("rare_count", 0)
        primary_count = semantic_features.get("primary_count", 0)
        secondary_count = semantic_features.get("secondary_count", 0)
        second_best_raw = sorted(domain_signal.values(), reverse=True)[1] if len(domain_signal) >= 2 else 0.0
        partial_known_escalation = (
            rare_count >= 3
            and not multi_domain
            and primary_count == 1
            and secondary_count <= 1
            and second_best_raw < 0.5
        )
        if meta_task:
            return "planner", "partial_known"
        if multi_domain_marker:
            return "semantic", "low_separation"
        if explicit_escalate:
            return "planner", escalation_reason or "low_confidence"
        if genuine_ambiguity:
            if intent_core == "fallback" or not domain_signal:
                return "planner", "domain_unrecognized"
            return "planner", "ambiguous"
        if partial_known_escalation:
            return "planner", "partial_known"
        if (confidence >= 0.55 and not pivot_detected and not lure_terms
                and not (contra and contra.get("detected"))
                and not multi_domain
                and not uncertainty_signal
                and not multi_step
                and intent_core and intent_core != "fallback"
                and ambiguity < 0.30):
            return "lexical", None
        cleaned_signal = semantic_features.get("cleaned_signal", {})
        if (intent_core == "fallback" and (not cleaned_signal or not domain_signal)) or confidence < 0.20:
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
        if escalation_reason is None:
            if uncertainty_signal:
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
        features = self.reader.read(task_text)
        domain_signal = features.get("domain_signal", {})
        intent_core = features.get("intent_core")
        raw_cleaned = features.get("cleaned_signal", {})
        if intent_core == "fallback":
            cleaned_signal = raw_cleaned
        else:
            cleaned_signal = raw_cleaned or domain_signal
        lure_terms = features.get("lure_terms", [])
        contra = features.get("contradiction")
        candidates = self._lexical_candidates(task_text, cleaned_signal)
        scores = self._score_candidates(candidates, features, cleaned_signal)
        confidence, escalation_reason, ambiguity = self._calibrate_confidence(
            scores, features, cleaned_signal
        )
        route_mode, escalation_reason = self._escalation_gate(
            confidence, escalation_reason, features, domain_signal, ambiguity, scores
        )
        if scores and route_mode != "planner":
            selected = max(scores, key=scores.get)
        elif intent_core and intent_core != "fallback" and route_mode == "lexical":
            selected = intent_core
        elif route_mode == "planner" and intent_core == "fallback":
            selected = "fallback"
        elif scores:
            if intent_core in scores:
                selected = intent_core
            else:
                selected = max(scores, key=scores.get)
        else:
            selected = "fallback"
        fallback_reason = None
        if not domain_signal:
            fallback_reason = "domain_unrecognized"
        elif escalation_reason == "ambiguous":
            fallback_reason = "conflicting_intent"
        elif escalation_reason == "low_separation":
            fallback_reason = "multi_domain"
        elif escalation_reason == "low_confidence":
            fallback_reason = "low_confidence"
        if confidence >= 0.55:
            conf_label = "high"
        elif confidence >= 0.35:
            conf_label = "medium"
        else:
            conf_label = "low"
        support = [s for s in sorted(candidates, key=lambda c: -scores.get(c, 0))
                   if s != selected][:2]
        rules_applied = [
            f"semantic_features.intent_core={intent_core}",
            f"semantic_features.lure_terms={lure_terms}",
            f"semantic_features.contradiction={bool(contra and contra.get('detected'))}",
            f"domain_signal={dict(sorted(domain_signal.items(), key=lambda x: -x[1])[:3])}",
            f"confidence_calibrated={confidence} (entropy+separation+ambiguity+unknown_penalty)",
            f"escalation_gate: route_mode={route_mode} reason={escalation_reason}",
        ]
        completed_at = datetime.now(timezone.utc).isoformat()
        return DecisionContext(
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


def reset() -> None:
    """Drop the singleton (used by tests when the registry changes)."""
    global _hybrid_instance
    _hybrid_instance = None


def route_task(task_text: str) -> dict:
    """Route a task and return the artifact plus resolved concrete roles."""
    ctx = get_hybrid_router().route(task_text)
    artifact = ctx.to_artifact()
    artifact["lead_role"] = taxonomy.resolve_role(ctx.lead_skill)
    artifact["support_roles"] = taxonomy.resolve_roles(ctx.support_skills)
    return artifact
