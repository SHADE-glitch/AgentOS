#!/usr/bin/env python3
"""
Phase 8.2.1 — Base Collector Interface

Abstract base class for all collectors (TraceCollector, TeamResultCollector).
Defines the common interface for: read sources → validate → extract → generate candidates.

Architecture:
  Collector (ABC)
    ├── TraceCollector: reads runtime/traces/*.yaml → memory candidates
    └── TeamResultCollector: reads team-result-*.yaml → memory candidates

Both produce the same output format (memory candidates) compatible with Validator/Promoter.
"""

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional


class Collector(ABC):
    """Abstract base for all collectors. Does NOT duplicate logic."""

    @abstractmethod
    def load_source(self, source_id: str) -> Optional[dict]:
        """Load a single source artifact by ID. Returns dict or None."""
        ...

    @abstractmethod
    def validate_source(self, source: dict) -> tuple[bool, list[str]]:
        """Validate required fields. Returns (is_valid, reasons)."""
        ...

    @abstractmethod
    def extract_experiences(self, source: dict) -> list[dict]:
        """
        Extract ExperienceRecords from a validated source.

        Each ExperienceRecord contains:
          - experience_id, source_id, type, title, context, lesson
          - confidence, evidence, tokens, latency
          - agent_role, team_id, domain
        """
        ...

    @abstractmethod
    def generate_candidates(self, experiences: list[dict], source: dict) -> list[dict]:
        """Convert ExperienceRecords into MemoryCandidate dicts compatible with Validator."""
        ...

    def collect(self, source_ids: list[str], quiet: bool = False) -> list[dict]:
        """
        Full collection pipeline: load → validate → extract → generate candidates.

        Args:
            source_ids: list of source IDs (trace IDs or team-result IDs)
            quiet: suppress console output

        Returns:
            list of MemoryCandidate dicts
        """
        all_candidates = []

        for sid in source_ids:
            if not quiet:
                print(f"  Processing: {sid}")

            source = self.load_source(sid)
            if source is None:
                if not quiet:
                    print(f"    SKIP: source not found")
                continue

            valid, reasons = self.validate_source(source)
            if not valid:
                if not quiet:
                    print(f"    SKIP: {reasons}")
                continue

            experiences = self.extract_experiences(source)
            if not quiet:
                print(f"    Experiences: {len(experiences)}")

            candidates = self.generate_candidates(experiences, source)
            if not quiet:
                print(f"    Candidates:  {len(candidates)}")

            all_candidates.extend(candidates)

        return all_candidates

    @staticmethod
    def compute_output_hash(response: str) -> str:
        return hashlib.sha256(response.encode()).hexdigest()[:16]

    @staticmethod
    def make_candidate(candidate_id: str, target_memory: str, candidate_type: str,
                       outcome: str, reasoning: str, quality_score: float,
                       quality_breakdown: dict, evidence: dict,
                       source_execution: str) -> dict:
        """Standard candidate dict factory — same format as TraceCollector."""
        return {
            "candidate_id": candidate_id,
            "source_execution": source_execution,
            "target_memory": target_memory,
            "candidate_type": candidate_type,
            "quality_score": quality_score,
            "quality_breakdown": quality_breakdown,
            "reasoning": reasoning,
            "evidence": evidence,
            "outcome": outcome,
        }