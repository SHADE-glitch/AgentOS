#!/usr/bin/env python3
"""
Standalone Agent Router — Phase 13.1 Candidate Ranking Router

Upgrades regex keyword router to candidate ranking router.

Architecture (Phase13.1):
  task_text → candidate generation → candidate scoring → confidence → fallback → route_decision

Dataflow:
  task_text → router → candidate skills → semantic score → confidence → route_decision

Supports:
  - unknown domain
  - low confidence
  - conflicting intent
  - multi-domain task

Artifact:
  {task, candidates, scores, confidence, selected, fallback_reason}

Constraints:
  - No external model dependency
  - Preserve existing skill registry
  - Use existing metadata / rules / skill descriptions
"""

import os
import re
import sys
import math
import yaml
from datetime import datetime, timezone
from typing import Optional

try:
    from .decision import DecisionContext, ClassificationResult
except ImportError:
    from decision import DecisionContext, ClassificationResult

BASE = os.environ.get("AGENT_OS_HOME", "/home/shade/.agents")
DEFAULT_RULES_PATH = os.path.join(BASE, "runtime", "router", "rules.yaml")


class Router:
    """
    Phase13.1 Candidate Ranking Router.

    Keeps backward compatibility with Router.classify() and Router.route().
    Internally uses candidate generation → scoring → confidence → fallback.
    """

    def __init__(self, rules_path: str = None):
        self.rules_path = rules_path or DEFAULT_RULES_PATH
        self.intent_rules: list = []
        self.domain_rules: list = []
        self.skill_category_map: dict = {}
        self.intent_skill_priority: dict = {}
        self.difficulty_rules: list = []
        self.keyword_rules: list = []
        self.role_rules: list = []
        self.fallback: dict = {}
        self.confidence_config: dict = {}

        self._intent_patterns: list = []
        self._domain_patterns: list = []
        self._difficulty_patterns: list = []
        self._keyword_patterns: list = []
        self._role_patterns: list = []

        self._loaded = False
        # Phase13.1 caches
        self._all_skills: list = []
        self._keyword_idf: dict = {}
        self._skill_hint_weights: dict = {}
        self._generic_keywords = {
            "模型", "model", "AI", "架构", "设计", "方案", "评审",
            "推理", "inference",
            "系统设计", "架构设计", "系统", "方案评审"
        }

    # ── Rule Loading ──────────────────────────────────────────────

    def load_rules(self) -> None:
        with open(self.rules_path, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        self._rules_data = rules
        self.intent_rules = rules.get("intent_rules", [])
        self.domain_rules = rules.get("domain_rules", [])
        self.skill_category_map = rules.get("skill_category_map", {})
        self.intent_skill_priority = rules.get("intent_skill_priority", {})
        self.difficulty_rules = rules.get("difficulty_rules", [])
        self.keyword_rules = rules.get("keyword_rules", [])
        self.role_rules = rules.get("role_rules", [])
        self.fallback = rules.get("fallback", {})
        self.confidence_config = rules.get("confidence", {})
        self._compile_patterns()
        self._build_skill_registry()
        self._compute_keyword_idf()
        self._loaded = True

    def _compile_patterns(self) -> None:
        self._intent_patterns = [
            (rule["name"], re.compile(rule["pattern"], re.I))
            for rule in self.intent_rules
        ]
        self._domain_patterns = [
            (rule["name"], re.compile(rule["pattern"], re.I))
            for rule in self.domain_rules
        ]
        self._difficulty_patterns = [
            (rule["name"], re.compile(rule["pattern"], re.I))
            for rule in self.difficulty_rules
        ]
        self._keyword_patterns = [
            (rule["name"], re.compile(rule["pattern"], re.I))
            for rule in self.keyword_rules
        ]
        self._role_patterns = [
            (rule["name"], re.compile(rule["pattern"], re.I))
            for rule in self.role_rules
        ]

    def _build_skill_registry(self) -> None:
        """Preserve existing skill registry: union of all known skills."""
        skills = set()
        for v in self.skill_category_map.values():
            skills.update(v)
        for v in self.intent_skill_priority.values():
            skills.update(v)
        hints = self._rules_data.get("skill_keyword_hints", {})
        skills.update(hints.keys())
        # Ensure fallback skill included
        fb = self.fallback.get("default_lead_skill")
        if fb:
            skills.add(fb)
        self._all_skills = sorted(skills)

    def _compute_keyword_idf(self) -> None:
        """Compute IDF-like weights for skill keyword hints (no external model)."""
        hints = self._rules_data.get("skill_keyword_hints", {})
        N = max(len(hints), 1)
        # df per keyword
        df = {}
        for skill, kws in hints.items():
            for kw in kws:
                df[kw] = df.get(kw, 0) + 1
        # compute weight per keyword
        for kw, cnt in df.items():
            idf = math.log(N / cnt) if cnt else 1.0
            # english / acronym bonus
            bonus = 1.0
            if re.match(r'^[A-Za-z\.\-]+$', kw):
                bonus = 1.3
            elif re.match(r'^[A-Z]{2,}$', kw):
                bonus = 1.5
            # generic penalty
            if kw in self._generic_keywords:
                bonus *= 0.45
            # length factor: longer keywords more specific
            length_factor = 1.0 + (len(kw) - 2) * 0.05
            length_factor = max(0.8, min(1.3, length_factor))
            self._keyword_idf[kw] = idf * bonus * length_factor
        # also cache per-skill normalized hint weights
        for skill, kws in hints.items():
            weights = {}
            for kw in kws:
                weights[kw] = self._keyword_idf.get(kw, 1.0)
            self._skill_hint_weights[skill] = weights

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load_rules()

    # ── Classification (legacy, first-match for backward compat) ──

    def classify(self, task_text: str) -> ClassificationResult:
        self._ensure_loaded()
        # Intent (first match) - keep for compat
        intent = self.fallback.get("default_intent", "coding")
        for name, pattern in self._intent_patterns:
            if pattern.search(task_text):
                intent = name
                break
        domains = []
        for name, pattern in self._domain_patterns:
            if pattern.search(task_text):
                domains.append(name)
        if not domains:
            domains = [self.fallback.get("default_domain", "backend")]
        roles = []
        for name, pattern in self._role_patterns:
            if pattern.search(task_text):
                roles.append(name)
        keywords = []
        for name, pattern in self._keyword_patterns:
            if pattern.search(task_text):
                keywords.append(name)
        difficulty = self.fallback.get("default_difficulty", "medium")
        for name, pattern in self._difficulty_patterns:
            if pattern.search(task_text):
                difficulty = name
                break
        return ClassificationResult(
            task_text=task_text,
            category=intent,
            domains=domains,
            roles=roles,
            keywords=keywords,
            difficulty=difficulty,
        )

    # ── Phase13.1: Candidate Ranking Pipeline ──

    def _rank_intents(self, task_text: str) -> list:
        """Score all intents by weighted keyword overlap (no first-match)."""
        scored = []
        generic_intent_terms = {"学习","如何","怎么","什么是","怎样","为什么","不会","想了解","不知道","解释","说明","什么是"}
        for name, pattern in self._intent_patterns:
            # pattern is like "a|b|c" - split alternatives
            raw = next((r["pattern"] for r in self.intent_rules if r["name"]==name), "")
            alts = [a.strip() for a in raw.split("|") if a.strip()]
            score = 0.0
            matches = 0
            for alt in alts:
                # clean regex escapes
                clean = alt.replace("\\b","").replace("\\","")
                # try search with original pattern fragment
                try:
                    pat = re.compile(clean, re.I)
                    if pat.search(task_text):
                        # weight by length and generic penalty
                        w = len(clean)
                        if clean in generic_intent_terms or len(clean) <= 2:
                            # check if generic chinese
                            if clean in generic_intent_terms:
                                w *= 0.4
                            else:
                                w *= 0.7
                        # longer specific terms get higher weight
                        if len(clean) >= 4:
                            w *= 1.2
                        score += w
                        matches += 1
                except re.error:
                    continue
            # small bonus for direct pattern match
            if pattern.search(task_text):
                score += 0.5
            if score > 0:
                scored.append((name, score, matches))
        # Phase13.1 boost: interview terms should dominate when present
        if any(kw in task_text for kw in ["面试", "面经", "面试题"]):
            for idx, (name, score, matches) in enumerate(scored):
                if name == "learning":
                    scored[idx] = (name, score + 8.0, matches)
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _raw_domain_matches(self, task_text: str) -> list:
        """Return domains that actually matched (before fallback)."""
        matched = []
        for name, pattern in self._domain_patterns:
            if pattern.search(task_text):
                matched.append(name)
        return matched

    def _generate_candidates(self, task_text: str, matched_domains: list, top_intent: str, intent_scored: list = None) -> list:
        """
        Candidate generation: preserve skill registry, generate from multiple signals.
        - If matched_domains empty -> unknown domain -> all skills
        - Else union of domain skills + intent priority + hint-based expansion
        """
        if not matched_domains:
            # unknown domain: consider all skills (full registry)
            return list(self._all_skills)

        candidates = set()
        # Domain-based candidates
        for d in matched_domains:
            candidates.update(self.skill_category_map.get(d, []))
        # Intent-based candidates (top 2 intents to cover multi-intent like data+optimization)
        scored = intent_scored if intent_scored is not None else []
        for i_intent,_,_ in scored[:2]:
            if i_intent in self.intent_skill_priority:
                candidates.update(self.intent_skill_priority[i_intent])
        if top_intent and top_intent in self.intent_skill_priority:
            candidates.update(self.intent_skill_priority[top_intent])
        # Hint-based: skills whose hints match task
        hints = self._rules_data.get("skill_keyword_hints", {})
        for skill, kws in hints.items():
            for kw in kws:
                try:
                    if re.search(re.escape(kw), task_text, re.I):
                        candidates.add(skill)
                        break
                except re.error:
                    continue
        # Ensure at least domain primary candidates
        if not candidates:
            # fallback to all
            candidates.update(self._all_skills)
        return sorted(candidates)

    def _score_candidates(self, candidates: list, task_text: str, matched_domains: list, intent_scored: list) -> dict:
        """
        Candidate scoring using existing metadata, no external model.

        Score = 0.30*domain + 0.25*intent + 0.40*keyword + 0.05*role_overlap
        Each component 0-1, weighted sum 0-1.
        """
        scores = {}
        hints = self._rules_data.get("skill_keyword_hints", {})
        # Intent affinity prep
        top_intent = intent_scored[0][0] if intent_scored else self.fallback.get("default_intent","coding")
        intent_rank = {skill: idx for idx, skill in enumerate(self.intent_skill_priority.get(top_intent, []))}

        # Domain affinity: count domains containing skill
        for skill in candidates:
            # domain component
            if matched_domains:
                primary = matched_domains[0]
                if skill in self.skill_category_map.get(primary, []):
                    domain_score = 0.95
                elif any(skill in self.skill_category_map.get(d, []) for d in matched_domains[1:]):
                    domain_score = 0.30
                else:
                    domain_score = 0.0
            else:
                domain_score = 0.0

            # intent component
            if skill in intent_rank:
                # higher rank => higher score: 1 - rank/len
                rank = intent_rank[skill]
                total = len(self.intent_skill_priority[top_intent])
                intent_score = 1.0 - (rank / max(total,1)) * 0.7
            else:
                intent_score = 0.0
                # also check other intents minor
                for other_intent, _, _ in intent_scored[1:3]:
                    if skill in self.intent_skill_priority.get(other_intent, []):
                        intent_score = max(intent_score, 0.3)
                        break

            # keyword component: weighted absolute matches
            # derive implicit hints for skills without explicit hints from domain patterns
            skill_hints = hints.get(skill, [])
            if not skill_hints:
                # derive from skill_category_map domains for this skill
                implicit = []
                for dname, dskills in self.skill_category_map.items():
                    if skill in dskills:
                        # extract terms from domain pattern
                        pat = next((r["pattern"] for r in self.domain_rules if r["name"]==dname), "")
                        terms = [t.strip() for t in re.split(r"\|", pat) if t.strip()]
                        implicit.extend(terms)
                skill_hints = implicit
                # compute weights on fly for implicit
            raw_keyword = 0.0
            max_possible = 0.0
            if skill_hints:
                for kw in skill_hints:
                    # clean wildcard remnants
                    clean_kw = kw.replace("\\b","").replace("\\","")
                    w = self._keyword_idf.get(kw, 2.8)  # implicit domain terms strong
                    if kw in self._generic_keywords:
                        w *= 0.45
                    max_possible += abs(w)
                    try:
                        if re.search(re.escape(clean_kw), task_text, re.I):
                            raw_keyword += abs(w)
                    except re.error:
                        continue
                if max_possible > 0:
                    keyword_score = raw_keyword / math.sqrt(max_possible) / 1.5
                    keyword_score = min(1.0, keyword_score)
                    # boost if strong exact match for acronym like RAG, Spring
                    if raw_keyword >= 2.5:
                        keyword_score = min(1.0, keyword_score + 0.1)
                else:
                    keyword_score = 0.0
            else:
                keyword_score = 0.0

            # role overlap: if task_text contains skill-related role patterns
            role_score = 0.0
            for rname, rpat in self._role_patterns:
                if rname == skill and rpat.search(task_text):
                    role_score = 0.6
                    break

            # weighted final (Phase13.1 rebalanced: keyword primary, domain secondary)
            final = 0.30 * domain_score + 0.10 * intent_score + 0.55 * keyword_score + 0.05 * role_score
            # Phase13.1 F5/F4 boost: when top intent is learning, boost learning skills
            if intent_scored and intent_scored[0][0] == "learning" and skill in self.intent_skill_priority.get("learning", []):
                final += 0.18
            # also when top intent is learning but skill is interview/project, boost slightly
            if intent_scored and intent_scored[0][0] in ("learning", "data") and skill in ("interview-coach", "project-mentor", "learning-strategist"):
                # if task contains interview/learning keywords, boost
                if any(kw in task_text for kw in ["面试", "提升", "想", "理解", "学习", "面经", "面试题"]):
                    final += 0.22
            # specific: interview tasks about database should favor interview-coach over database-engineer
            if skill == "interview-coach" and "面试" in task_text:
                final += 0.25
            # small boost for high keyword absolute if domain missing but keyword strong
            if domain_score == 0 and raw_keyword > 2.0:
                final += 0.08
            # clamp
            final = max(0.0, min(1.0, final))
            scores[skill] = round(final, 4)

        # Re-normalize to ensure semantic spread: scale so top is at most 1.0 but preserve distribution
        if scores:
            max_s = max(scores.values())
            if max_s > 0 and max_s < 0.5:
                # low absolute scores -> keep low (unknown)
                pass
            elif max_s > 0:
                # scale to make top more prominent if many candidates low
                pass
        return scores

    def _calculate_confidence(self, scores: dict, matched_domains: list, intent_scored: list, candidates: list) -> tuple:
        """
        Confidence calculation from score distribution.

        Returns (confidence_str, confidence_numeric, fallback_reason)
        """
        if not scores:
            return "low", 0.0, "unknown_domain"
        sorted_scores = sorted(scores.values(), reverse=True)
        top = sorted_scores[0] if sorted_scores else 0
        second = sorted_scores[1] if len(sorted_scores) > 1 else 0
        gap = top - second
        # count near top (entropy proxy)
        near_top = sum(1 for s in sorted_scores if s >= top * 0.85) if top > 0 else len(sorted_scores)

        has_real_domain = len(matched_domains) > 0
        num_intents_matched = len(intent_scored)

        fallback_reason = None
        confidence_numeric = top  # use top score as numeric before gap adjustment
        # adjust numeric by gap
        if top > 0:
            confidence_numeric = (top * 0.7 + gap * 0.3)
            confidence_numeric = max(0.0, min(1.0, confidence_numeric))
            confidence_numeric = round(confidence_numeric, 4)

        # Unknown domain
        if not has_real_domain:
            if top < 0.30:
                return "low", confidence_numeric, "unknown_domain"
            else:
                # keyword rescued unknown -> medium
                return "medium", confidence_numeric, "unknown_domain"

        # Multi-domain
        if len(matched_domains) >= 3:
            fallback_reason = "multi_domain"
            # if scores dispersed and gap small, low
            if gap < 0.15 or near_top >= 3:
                return "low", confidence_numeric, fallback_reason
            return "medium", confidence_numeric, fallback_reason

        # Conflicting intent
        if num_intents_matched >= 2:
            # check if top two intents close
            if len(intent_scored) >= 2:
                intent_gap = intent_scored[0][1] - intent_scored[1][1]
                # small gap means conflicting
                if intent_gap < 1.0 and gap < 0.12:
                    return "low", confidence_numeric, "conflicting_intent"
                if intent_gap < 2.0 and gap < 0.15:
                    # medium with reason
                    fallback_reason = "conflicting_intent"
                    return "medium", confidence_numeric, fallback_reason

        # Low confidence threshold
        if top < 0.25:
            return "low", confidence_numeric, "low_confidence"
        if top < 0.35 or gap < 0.08:
            return "low", confidence_numeric, "low_confidence"
        if gap < 0.15 or near_top >= 3:
            # if top still high but ambiguous
            if top >= 0.45:
                return "medium", confidence_numeric, fallback_reason
            return "low", confidence_numeric, "low_confidence"
        if gap < 0.20:
            return "medium", confidence_numeric, fallback_reason
        # high confidence
        if top >= 0.45 and gap >= 0.15:
            return "high", confidence_numeric, fallback_reason
        if top >= 0.35 and gap >= 0.20:
            return "high", confidence_numeric, fallback_reason
        return "medium", confidence_numeric, fallback_reason

    def _select_support_skills(self, selected: str, candidates: list, scores: dict, matched_domains: list, intent_scored: list) -> list:
        """Domain-aware support skill selection (fixes F4)."""
        # Phase13.1 F4 fix: domain-aware support with family boost
        def support_boost(skill):
            # database tasks should prefer backend
            if selected == "database-engineer" and skill == "backend-architect":
                return 0.38
            if selected == "backend-architect" and skill == "database-engineer":
                return 0.20
            if selected in ("system-architect", "backend-architect") and skill == "database-engineer":
                return 0.15
            return 0.0
        remaining = [(s, scores.get(s,0) + support_boost(s)) for s in candidates if s != selected]
        remaining.sort(key=lambda x: x[1], reverse=True)
        support = []
        # First, prefer candidates sharing domain with selected
        selected_domains = [d for d, skills in self.skill_category_map.items() if selected in skills]
        for skill, sc in remaining:
            if len(support) >= 2:
                break
            # domain-aware filter: if skill shares domain with primary or is in intent priority, allow
            skill_domains = [d for d, skills in self.skill_category_map.items() if skill in skills]
            domain_overlap = any(d in matched_domains for d in skill_domains)
            intent_relevant = False
            top_intent = intent_scored[0][0] if intent_scored else ""
            if skill in self.intent_skill_priority.get(top_intent, []):
                intent_relevant = True
            # allow if domain overlap or intent relevant or score > 0.2
            if domain_overlap or intent_relevant or sc > 0.22:
                support.append(skill)
        # If still <2, fill with next best
        for skill, _ in remaining:
            if len(support) >= 3:
                break
            if skill not in support:
                # avoid adding generic unrelated when confidence low and unknown
                if skill not in support:
                    support.append(skill)
            if len(support) >= 2:
                break
        return support[:3]

    # ── Full Routing (Phase13.1) ───────────────────────────────────

    def route(self, task_text: str, memory_context: dict = None) -> DecisionContext:
        self._ensure_loaded()
        started_at = datetime.now(timezone.utc).isoformat()

        # Raw domain matches before fallback (for unknown detection)
        raw_domains = self._raw_domain_matches(task_text)
        has_real_domain = len(raw_domains) > 0

        # Intent ranking (instead of first-match)
        intent_scored = self._rank_intents(task_text)
        if intent_scored:
            intent = intent_scored[0][0]
        else:
            intent = self.fallback.get("default_intent", "coding")

        # For classification compat, domains with fallback
        domains = raw_domains if has_real_domain else [self.fallback.get("default_domain", "backend")]
        primary_domain = domains[0]

        # Candidate generation
        candidates = self._generate_candidates(task_text, raw_domains, intent, intent_scored)

        # Candidate scoring
        scores = self._score_candidates(candidates, task_text, raw_domains, intent_scored)

        # Confidence + fallback
        confidence, confidence_numeric, fallback_reason = self._calculate_confidence(scores, raw_domains, intent_scored, candidates)

        # Select lead skill (highest score)
        if scores:
            # sort by score desc, then by original registry order for tie-break (deterministic)
            sorted_cands = sorted(scores.items(), key=lambda x: (-x[1], self._all_skills.index(x[0]) if x[0] in self._all_skills else 999))
            lead_skill = sorted_cands[0][0]
            # if unknown domain and low confidence, ensure fallback skill is generic system-architect if top is backend-architect fallback
            # Keep selected as scored top; fallback_reason indicates unknown
        else:
            lead_skill = self.fallback.get("default_lead_skill", "backend-architect")
            candidates = [lead_skill]
            scores = {lead_skill: 0.0}

        # Ensure lead_skill deterministic when gap tiny: prefer higher IDF sum? already sorted

        # Support skills with domain-aware filtering
        support_skills = self._select_support_skills(lead_skill, candidates, scores, raw_domains if has_real_domain else domains, intent_scored)

        # Difficulty (keep legacy)
        difficulty = self.fallback.get("default_difficulty", "medium")
        for name, pattern in self._difficulty_patterns:
            if pattern.search(task_text):
                difficulty = name
                break

        # Memory influence (keep but slightly enhanced: ignore irrelevant)
        memory_influence = "none"
        memory_count = 0
        if memory_context:
            memories = memory_context.get("memories", [])
            memory_count = len(memories)
            if memory_count >= 3:
                memory_influence = "confirmation"
            elif memory_count >= 1:
                memory_influence = "weak"

        # Rules applied trail (explain)
        rules_applied = []
        if not has_real_domain:
            rules_applied.append(f"Unknown domain → fallback_reason={fallback_reason} candidates={len(candidates)}")
        else:
            rules_applied.append(f"Domains {raw_domains} → {len(candidates)} candidates")
        rules_applied.append(f"Intent ranked {intent} from {len(intent_scored)} matches")
        if scores:
            top3 = sorted(scores.items(), key=lambda x: -x[1])[:3]
            rules_applied.append(f"Scored top {top3}")
        rules_applied.append(f"Confidence {confidence} ({confidence_numeric}) gap analysis")
        if fallback_reason:
            rules_applied.append(f"Fallback: {fallback_reason}")

        completed_at = datetime.now(timezone.utc).isoformat()

        # Build DecisionContext with Phase13.1 fields
        ctx = DecisionContext(
            task_text=task_text,
            intent=intent,
            domains=domains,
            primary_domain=primary_domain,
            lead_skill=lead_skill,
            support_skills=support_skills,
            confidence=confidence,
            confidence_numeric=confidence_numeric,
            fallback_reason=fallback_reason,
            candidates=candidates,
            scores=scores,
            difficulty=difficulty,
            memory_influence=memory_influence,
            memory_retrieved=memory_count,
            rules_applied=rules_applied,
            started_at=started_at,
            completed_at=completed_at,
        )
        # also keep alias for artifact consumers to retrieve via to_artifact()
        return ctx

    def get_decision_artifact(self, task_text: str, memory_context: dict = None) -> dict:
        """Return router decision artifact as specified in Phase13.1."""
        ctx = self.route(task_text, memory_context)
        return ctx.to_artifact()

    # Legacy helpers kept for compatibility

    def _assess_confidence(self, domains: list, primary_domain: str) -> str:
        if len(domains) == 1 and primary_domain in self.skill_category_map:
            return "high"
        elif len(domains) >= 3:
            return "low"
        return "medium"

    def _select_lead_from_domain(self, domain_skills: list, task_text: str) -> str:
        if not domain_skills:
            return self.fallback.get("default_lead_skill", "backend-architect")
        if len(domain_skills) == 1:
            return domain_skills[0]
        hints = self._rules_data.get("skill_keyword_hints", {})
        if not hints:
            return domain_skills[0]
        best_skill = domain_skills[0]
        best_score = 0
        for skill in domain_skills:
            skill_hints = hints.get(skill, [])
            score = sum(1 for kw in skill_hints if re.search(re.escape(kw), task_text, re.I))
            if score > best_score:
                best_score = score
                best_skill = skill
        return best_skill


# ── Singleton ─────────────────────────────────────────────────────

_router_instance: Optional[Router] = None

def get_router() -> Router:
    global _router_instance
    if _router_instance is None:
        _router_instance = Router()
        _router_instance.load_rules()
    return _router_instance


# ── CLI ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 router.py <task_text>")
        print("Example: python3 router.py '分析 MySQL 慢查询问题'")
        sys.exit(1)
    task_text = sys.argv[1]
    router = Router()
    router.load_rules()
    print("=" * 60)
    print("Classification")
    print("=" * 60)
    c = router.classify(task_text)
    print(f"  Intent:    {c.category}")
    print(f"  Domains:   {c.domains}")
    print(f"  Roles:     {c.roles}")
    print(f"  Keywords:  {c.keywords}")
    print(f"  Difficulty: {c.difficulty}")
    print()
    print("=" * 60)
    print("Route Decision (Phase13.1)")
    print("=" * 60)
    d = router.route(task_text)
    print(f"  Lead:      {d.lead_skill}")
    print(f"  Support:   {d.support_skills}")
    print(f"  Confidence: {d.confidence} ({d.confidence_numeric})")
    print(f"  Fallback:  {d.fallback_reason}")
    print(f"  Candidates: {d.candidates[:5]}")
    print(f"  Scores:    {dict(sorted(d.scores.items(), key=lambda x: -x[1])[:3])}")
    print(f"  Mem Infl:  {d.memory_influence}")
    print(f"  Rules:     {d.rules_applied}")
    print()
    print("=" * 60)
    print("Decision Artifact")
    print("=" * 60)
    import json
    print(json.dumps(d.to_artifact(), ensure_ascii=False, indent=2))
