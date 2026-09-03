#!/usr/bin/env python3
"""
Phase 8.2.1 — TeamResult Collector

Reads team-result-*.yaml files from the validation directory and produces
MemoryCandidate entries compatible with the existing Validator/Promoter pipeline.

This closes the Memory Feedback Loop for multi-agent execution:
  TeamResult → Experience Extract → Memory Candidate → Validator → Promoter → Memory Index

Design:
  - Extends base Collector interface
  - Delegates experience extraction to experience_extractor module
  - Produces candidates in the same format as TraceCollector
  - Does NOT duplicate logic from TraceCollector
"""

import os
import sys
import yaml
import re
import hashlib
from datetime import datetime, timezone
from typing import Optional

from base_collector import Collector
from experience_extractor import extract_experiences

# Phase 8.4: Reuse the shared hypothesis classification + runtime engagement detector.
from collector import (
    HYPOTHESIS_CANDIDATE_TYPES,
    classify_hypothesis_engagement,
)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                "loop-controller"))
from runtime_adapter import _detect_hypothesis_engagement

# Paths
VALIDATION_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "loop-controller", "validation"
)
COLLECTOR_STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "loop-controller", "state", "collector_state.yaml"
)


class TeamResultCollector(Collector):
    """
    Collects candidates from multi-agent TeamResult files.

    Input:  team-result-*.yaml files in validation/
    Output: MemoryCandidate dicts (same format as TraceCollector)
    """

    def __init__(self, validation_dir: str = None):
        self.validation_dir = validation_dir or VALIDATION_DIR

    # ── Abstract method implementations ──────────────────────────

    def load_source(self, source_id: str) -> Optional[dict]:
        """Load a team-result YAML file by loop_id."""
        path = os.path.join(self.validation_dir, f"team-result-{source_id}.yaml")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return yaml.safe_load(f)

    def validate_source(self, source: dict) -> tuple[bool, list[str]]:
        """Validate required fields in a TeamResult."""
        reasons = []

        if not source:
            return False, ["source is None"]

        if not source.get("team_id"):
            reasons.append("missing team_id")
        if not source.get("loop_id"):
            reasons.append("missing loop_id")

        team_result = source.get("team_result", {})
        if not team_result:
            reasons.append("missing team_result")

        if not team_result.get("lead_output", {}).get("output"):
            reasons.append("missing lead_output")

        if team_result.get("completed_count", 0) == 0:
            reasons.append("no completed agents")

        if reasons:
            return False, reasons
        return True, []

    def extract_experiences(self, source: dict) -> list[dict]:
        """Extract ExperienceRecords from TeamResult using the extractor."""
        return extract_experiences(source)

    def generate_candidates(self, experiences: list[dict], source: dict) -> list[dict]:
        """
        Convert ExperienceRecords into MemoryCandidate dicts compatible with
        the existing Validator/Promoter pipeline.

        Candidate generation rules (mirrors TraceCollector R1-R6):
          R1: Successful multi-agent execution → reinforce used memories
          R2: High confidence experience → create_hypothesis (new domain pattern)
          R3: Team success + all agents completed → reinforce team patterns
          R4: Failed agent → weaken (if any agents failed)
        """
        candidates = []
        loop_id = source.get("loop_id", "unknown")
        team_id = source.get("team_id", "unknown")
        team_result = source.get("team_result", {})
        team_status = team_result.get("status", "unknown")
        completed_count = team_result.get("completed_count", 0)
        failed_count = team_result.get("failed_count", 0)

        # ── R1: Successful team execution → reinforce "multi-agent" pattern ──
        if team_status == "success" and completed_count > 0:
            for exp in experiences:
                exp_id = exp["experience_id"]
                confidence = exp["confidence"]
                role = exp["agent_role"]

                # Quality assessment
                quality = self._assess_quality(exp)
                evidence = {
                    "session_id": f"TEAM-{team_id}-{loop_id}",
                    "output_hash": exp["evidence"]["output_hash"],
                    "token_usage": exp["evidence"]["token_usage"],
                    "latency_ms": exp["evidence"]["latency_ms"],
                    "output_length": exp["evidence"]["output_length"],
                    "is_real_execution": True,
                    "agent_role": role,
                    "team_id": team_id,
                    "is_lead": exp["is_lead"],
                }

                # Every successful agent output generates a reinforce candidate
                # targeting a pattern-based memory ID
                for pattern in exp.get("technical_patterns", [])[:3]:
                    mem_id = self._pattern_to_memory_id(pattern)
                    candidates.append(Collector.make_candidate(
                        candidate_id=f"CAND-{loop_id}-{role}-{mem_id}",
                        target_memory=mem_id,
                        candidate_type="reinforce",
                        outcome="promoted",
                        reasoning=(
                            f"Multi-agent team ({team_id}) execution succeeded. "
                            f"Agent '{role}' identified pattern: {pattern}. "
                            f"Confidence: {confidence:.2f}. "
                            f"Team: {completed_count}/{completed_count + failed_count} completed."
                        ),
                        quality_score=quality["weighted"],
                        quality_breakdown=quality,
                        evidence=evidence,
                        source_execution=loop_id,
                    ))

                # If no patterns extracted, create a general reinforce
                if not exp.get("technical_patterns"):
                    candidates.append(Collector.make_candidate(
                        candidate_id=f"CAND-{loop_id}-{role}-TEAM",
                        target_memory="TEAM-COLLAB",
                        candidate_type="reinforce",
                        outcome="promoted",
                        reasoning=(
                            f"Agent '{role}' contributed to successful multi-agent execution "
                            f"({team_id}). Output: {exp['evidence']['output_length']} chars, "
                            f"confidence: {confidence:.2f}."
                        ),
                        quality_score=quality["weighted"],
                        quality_breakdown=quality,
                        evidence=evidence,
                        source_execution=loop_id,
                    ))

        # ── R2: High confidence experiences → create_hypothesis ──
        for exp in experiences:
            if exp["confidence"] >= 0.75 and exp["is_lead"]:
                for problem in exp.get("problem_patterns", [])[:2]:
                    mem_id = self._pattern_to_memory_id(f"PROBLEM-{problem}")
                    quality = self._assess_quality(exp)
                    candidates.append(Collector.make_candidate(
                        candidate_id=f"CAND-{loop_id}-HYP-{mem_id}",
                        target_memory="NEW",
                        candidate_type="create_hypothesis",
                        outcome="hold",
                        reasoning=(
                            f"High-confidence lead agent ({exp['agent_role']}) "
                            f"identified problem: {problem}. "
                            f"Context: {exp['context'][:100]}. "
                            f"Confidence: {exp['confidence']:.2f}. "
                            f"Consider creating a new hypothesis memory for this pattern."
                        ),
                        quality_score=quality["weighted"],
                        quality_breakdown=quality,
                        evidence={
                            "session_id": f"TEAM-{team_id}-{loop_id}",
                            "output_hash": exp["evidence"]["output_hash"],
                            "token_usage": exp["evidence"]["token_usage"],
                            "latency_ms": exp["evidence"]["latency_ms"],
                            "output_length": exp["evidence"]["output_length"],
                            "is_real_execution": True,
                            "agent_role": exp["agent_role"],
                            "team_id": team_id,
                            "is_lead": True,
                        },
                        source_execution=loop_id,
                    ))

        # ── R3: Failed agents → weaken pattern ──
        if failed_count > 0:
            for exp in experiences:
                if exp["team_status"] != "success":
                    quality = self._assess_quality(exp)
                    for pattern in exp.get("technical_patterns", [])[:1]:
                        mem_id = self._pattern_to_memory_id(pattern)
                        candidates.append(Collector.make_candidate(
                            candidate_id=f"CAND-{loop_id}-{exp['agent_role']}-WEAK-{mem_id}",
                            target_memory=mem_id,
                            candidate_type="weaken",
                            outcome="hold",
                            reasoning=(
                                f"Agent '{exp['agent_role']}' failed in team {team_id}. "
                                f"Pattern '{pattern}' may need review. "
                                f"Team: {failed_count}/{completed_count + failed_count} failed."
                            ),
                            quality_score=quality["weighted"],
                            quality_breakdown=quality,
                            evidence={
                                "session_id": f"TEAM-{team_id}-{loop_id}",
                                "output_hash": exp["evidence"]["output_hash"],
                                "token_usage": exp["evidence"]["token_usage"],
                                "latency_ms": exp["evidence"]["latency_ms"],
                                "output_length": exp["evidence"]["output_length"],
                                "is_real_execution": True,
                            },
                            source_execution=loop_id,
                        ))

        # ── R4: Hypothesis Reinforcement Lane (Phase 8.4) ──
        # Only the lead-agent output is used for engagement attribution, kept
        # distinct from the generic pattern lane (R1). Identity comes strictly
        # from source["hypotheses_injected"] (I1/I6).
        hyp_ids = source.get("hypotheses_injected") or []
        hyp_ids = [h for h in hyp_ids if isinstance(h, str) and h]
        lead_output = team_result.get("lead_output", {})
        lead_text = lead_output.get("output", "") or ""
        lead_role = lead_output.get("agent", "lead")
        if hyp_ids and lead_text:
            # Minimal hyp stubs: zero tags/guidance so only explicit ID /
            # engagement-pattern mentions count (no text-grep false positives).
            hyp_stubs = [{"memory_id": hid, "tags": [], "guidance": ""} for hid in hyp_ids]
            eng_map = _detect_hypothesis_engagement(lead_text, hyp_stubs)
            for hid, eng in eng_map.items():
                if not eng.get("referenced"):
                    continue  # abstain — agent did not engage (I6)
                ctype, outcome, eng_norm = classify_hypothesis_engagement(
                    lead_text, hid, eng)
                if ctype is None:
                    continue  # abstain
                # I5: multiple agents share team context → record provenance marker.
                eng_norm["shared_context_with_other_agents"] = True
                # Phase 8.6-C1: mirror same_loop_as_creation for team lane
                eng_norm["created_loop"] = eng_norm.get("created_loop", "")
                # same_loop_as_creation: team lane uses loop_id == created_loop
                # (same logic as individual lane); defaults to false if created_loop unknown
                eng_norm["same_loop_as_creation"] = bool(
                    loop_id and eng_norm.get("created_loop") and loop_id == eng_norm.get("created_loop"))
                quality = self._assess_quality({"evidence": {
                    "output_length": len(lead_text),
                    "token_usage": lead_output.get("tokens", {}) or {},
                }})
                candidates.append(Collector.make_candidate(
                    candidate_id=f"CAND-{loop_id}-LEAD-HYP-{hid}",
                    target_memory=hid,
                    candidate_type=ctype,
                    outcome=outcome,
                    reasoning=(
                        f"Hypothesis {hid} engaged by lead agent '{lead_role}' "
                        f"(level={eng_norm['engagement_level']}, "
                        f"term_matches={eng_norm['term_matches']}). "
                        f"Multi-agent team {team_id} execution."
                    ),
                    quality_score=quality["weighted"],
                    quality_breakdown=quality,
                    evidence={
                        "session_id": f"TEAM-{team_id}-{loop_id}",
                        "output_hash": hashlib.sha256(lead_text.encode()).hexdigest()[:16],
                        "token_usage": lead_output.get("tokens", {}) or {},
                        "latency_ms": lead_output.get("latency_ms", 0) or 0,
                        "output_length": len(lead_text),
                        "is_real_execution": True,
                        "agent_role": lead_role,
                        "team_id": team_id,
                        "is_lead": True,
                    },
                    source_execution=loop_id,
                ))
                candidates[-1]["hypothesis_engagement"] = eng_norm

        return candidates

    # ── Helper methods ───────────────────────────────────────────

    @staticmethod
    def _assess_quality(exp: dict) -> dict:
        """Heuristic quality assessment for an ExperienceRecord."""
        scores = {}

        # Completeness: based on how many extraction dimensions are filled
        comp = 0
        if exp.get("title"): comp += 1
        if exp.get("lesson"): comp += 1
        if exp.get("context"): comp += 1
        if len(exp.get("technical_patterns", [])) > 0: comp += 1
        if len(exp.get("problem_patterns", [])) > 0: comp += 1
        scores["completeness"] = min(comp, 5)

        # Accuracy: based on confidence and output quality
        acc = 0
        conf = exp.get("confidence", 0)
        if conf >= 0.6: acc += 1
        if conf >= 0.7: acc += 1
        if conf >= 0.8: acc += 1
        if exp["evidence"].get("output_length", 0) > 2000: acc += 1
        if exp["evidence"].get("token_usage", {}).get("total", 0) > 20000: acc += 1
        scores["accuracy"] = min(acc, 5)

        # Structure: role-based and team-based
        struct = 0
        if exp.get("is_lead"): struct += 2
        if exp["evidence"].get("output_length", 0) > 1000: struct += 1
        if exp["evidence"].get("output_length", 0) > 5000: struct += 1
        if exp.get("team_status") == "success": struct += 1
        scores["structure"] = min(struct, 5)

        # Actionability: solutions extracted
        act = 0
        if len(exp.get("solutions", [])) > 0: act += 2
        if len(exp.get("solutions", [])) > 2: act += 1
        if len(exp.get("problem_patterns", [])) > 0: act += 1
        if exp.get("is_lead"): act += 1
        scores["actionability"] = min(act, 5)

        # Novelty: based on pattern diversity
        nov = 0
        all_patterns = (exp.get("technical_patterns", []) +
                        exp.get("problem_patterns", []) +
                        exp.get("solutions", []))
        if len(all_patterns) >= 3: nov += 1
        if len(all_patterns) >= 5: nov += 1
        if len(all_patterns) >= 7: nov += 1
        if exp.get("confidence", 0) >= 0.8: nov += 1
        if exp.get("is_lead"): nov += 1
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

    @staticmethod
    def _pattern_to_memory_id(pattern: str) -> str:
        """Convert a pattern name to a memory ID format."""
        # Remove special chars and capitalize
        clean = re.sub(r'[^a-zA-Z0-9]', '-', pattern).upper()
        # Truncate to reasonable length
        if len(clean) > 30:
            clean = clean[:30]
        return f"P8-{clean}"

    # ── Utility: scan for available team results ──────────────────

    def list_available(self) -> list[str]:
        """List all available team-result loop IDs."""
        if not os.path.isdir(self.validation_dir):
            return []
        ids = []
        for fname in sorted(os.listdir(self.validation_dir)):
            if fname.startswith("team-result-") and fname.endswith(".yaml"):
                # Extract loop_id: team-result-LOOP-20260901054901.yaml → LOOP-20260901054901
                middle = fname.replace("team-result-", "").replace(".yaml", "")
                ids.append(middle)
        return ids


def collect_from_team_results(loop_ids: list[str] = None, quiet: bool = False) -> list[dict]:
    """
    Convenience function: collect candidates from team-result files.

    Args:
        loop_ids: specific loop IDs to collect from. If None, scans all available.
        quiet: suppress console output

    Returns:
        list of MemoryCandidate dicts
    """
    collector = TeamResultCollector()

    if loop_ids is None:
        loop_ids = collector.list_available()

    if not loop_ids:
        if not quiet:
            print("  No team-result files found.")
        return []

    if not quiet:
        print(f"  Scanning {len(loop_ids)} team-result(s): {loop_ids}")

    return collector.collect(loop_ids, quiet=quiet)