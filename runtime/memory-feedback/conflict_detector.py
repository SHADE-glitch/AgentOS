#!/usr/bin/env python3
"""
Memory Conflict Detector — Phase 5.11.1
Detects potential conflicts between memories using rule-based logic.

No AI models used. Checks:
- Memory category conflicts
- Tags conflicts
- Recommendation polarity conflicts
- Contradiction keywords

Input:  memory/retrieval-index.yaml
Output: runtime/memory-feedback/conflict_candidates.yaml
"""

import yaml
import os
from datetime import datetime, timezone
from typing import List, Dict, Tuple

BASE = "/home/shade/.agents/runtime/memory-feedback"
MEMORY_INDEX_FILE = "/home/shade/.agents/memory/retrieval-index.yaml"
OUTPUT_FILE = os.path.join(BASE, "conflict_candidates.yaml")

# Contradiction keyword pairs
CONTRADICTION_KEYWORDS = {
    "isolation": ["shared", "multi-tenant"],
    "single": ["multi", "distributed"],
    "centralized": ["decentralized", "distributed"],
    "synchronous": ["asynchronous", "async"],
    "strong-consistency": ["eventual-consistency"],
    "monolith": ["microservice"],
    "single-database": ["multi-database"],
    "lock": ["lock-free", "optimistic"],
    "scale-up": ["scale-out"],
    "tight-coupling": ["loose-coupling"],
    "security": ["convenience"],
    "performance": ["correctness"],
}

# Polarity keywords - only strong opposites
POLARITY_KEYWORDS = {
    "positive": ["recommend", "best", "optimal", "effective"],
    "negative": ["avoid", "reject", "anti-pattern", "harmful"],
}

# Category conflict rules - only truly opposing categories
CATEGORY_CONFLICTS = {}  # Backend/frontend are not conflicts, just different domains

def load_memory_index() -> Dict:
    """Load the memory retrieval index."""
    if not os.path.exists(MEMORY_INDEX_FILE):
        return {"memories": []}
    with open(MEMORY_INDEX_FILE) as f:
        return yaml.safe_load(f) or {"memories": []}

def detect_tag_conflicts(memory1: Dict, memory2: Dict) -> List[str]:
    """Detect conflicts based on tags."""
    conflicts = []
    tags1 = set(memory1.get("tags", []))
    tags2 = set(memory2.get("tags", []))
    
    for tag_pair, keywords in CONTRADICTION_KEYWORDS.items():
        if tag_pair in tags1:
            for kw in keywords:
                if kw in tags2:
                    conflicts.append(f"tag:{tag_pair}↔{kw}")
        if tag_pair in tags2:
            for kw in keywords:
                if kw in tags1:
                    conflicts.append(f"tag:{kw}↔{tag_pair}")
    
    return conflicts

def detect_polarity_conflicts(memory1: Dict, memory2: Dict) -> List[str]:
    """Detect conflicts based on recommendation polarity."""
    conflicts = []
    tags1 = set(memory1.get("tags", []))
    tags2 = set(memory2.get("tags", []))
    
    for pos_kw in POLARITY_KEYWORDS["positive"]:
        for neg_kw in POLARITY_KEYWORDS["negative"]:
            if pos_kw in tags1 and neg_kw in tags2:
                conflicts.append(f"polarity:{pos_kw}↔{neg_kw}")
            if neg_kw in tags1 and pos_kw in tags2:
                conflicts.append(f"polarity:{neg_kw}↔{pos_kw}")
    
    return conflicts

def detect_category_conflicts(memory1: Dict, memory2: Dict) -> List[str]:
    """Detect conflicts based on category rules."""
    conflicts = []
    cat1 = memory1.get("category", "")
    cat2 = memory2.get("category", "")
    
    for cat_pair, incompatible in CATEGORY_CONFLICTS.items():
        if cat1 == cat_pair and cat2 in incompatible:
            conflicts.append(f"category:{cat_pair}↔{incompatible}")
        if cat2 == cat_pair and cat1 in incompatible:
            conflicts.append(f"category:{incompatible}↔{cat_pair}")
    
    return conflicts

def detect_contradiction_keywords(memory1: Dict, memory2: Dict) -> List[str]:
    """Detect contradictions based on keywords in tags."""
    conflicts = []
    tags1 = " ".join(memory1.get("tags", []))
    tags2 = " ".join(memory2.get("tags", []))
    
    for keyword_pair, opposites in CONTRADICTION_KEYWORDS.items():
        if keyword_pair in tags1:
            for opp in opposites:
                if opp in tags2:
                    conflicts.append(f"keyword:{keyword_pair}↔{opp}")
        if keyword_pair in tags2:
            for opp in opposites:
                if opp in tags1:
                    conflicts.append(f"keyword:{opp}↔{keyword_pair}")
    
    return conflicts

def detect_conflicts(memory1: Dict, memory2: Dict) -> List[str]:
    """Detect all conflicts between two memories."""
    all_conflicts = []
    all_conflicts.extend(detect_tag_conflicts(memory1, memory2))
    all_conflicts.extend(detect_polarity_conflicts(memory1, memory2))
    all_conflicts.extend(detect_category_conflicts(memory1, memory2))
    all_conflicts.extend(detect_contradiction_keywords(memory1, memory2))
    return list(set(all_conflicts))  # Deduplicate

def find_all_conflicts() -> List[Dict]:
    """Find all potential conflicts in the memory index."""
    index = load_memory_index()
    memories = index.get("memories", [])
    conflicts = []
    
    # Compare each pair of memories
    for i, mem1 in enumerate(memories):
        for mem2 in memories[i+1:]:
            conflict_types = detect_conflicts(mem1, mem2)
            if conflict_types:
                conflicts.append({
                    "memory_a": mem1["memory_id"],
                    "memory_b": mem2["memory_id"],
                    "category_a": mem1.get("category", ""),
                    "category_b": mem2.get("category", ""),
                    "tags_a": mem1.get("tags", []),
                    "tags_b": mem2.get("tags", []),
                    "conflict_types": conflict_types,
                    "severity": "high" if len(conflict_types) >= 2 else "medium",
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                })
    
    return conflicts

def save_conflicts(conflicts: List[Dict]):
    """Save conflict candidates to file."""
    output = {
        "version": "1.0",
        "phase": "5.11.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "conflict_detector.py (Phase 5.11.1 Trust Hardening)",
        "source_file": MEMORY_INDEX_FILE,
        "summary": {
            "total_conflicts": len(conflicts),
            "high_severity": len([c for c in conflicts if c["severity"] == "high"]),
            "medium_severity": len([c for c in conflicts if c["severity"] == "medium"]),
        },
        "conflicts": conflicts,
    }
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        yaml.dump(output, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    return OUTPUT_FILE

def get_conflicting_memory_ids() -> set:
    """Get set of memory_ids that have conflicts."""
    if not os.path.exists(OUTPUT_FILE):
        return set()
    
    with open(OUTPUT_FILE) as f:
        data = yaml.safe_load(f) or {}
    
    conflicting_ids = set()
    for conflict in data.get("conflicts", []):
        conflicting_ids.add(conflict["memory_a"])
        conflicting_ids.add(conflict["memory_b"])
    
    return conflicting_ids

def is_memory_conflicted(memory_id: str) -> bool:
    """Check if a specific memory has conflicts."""
    conflicting = get_conflicting_memory_ids()
    return memory_id in conflicting

def main():
    print("=" * 60)
    print("Phase 5.11.1 — Memory Conflict Detector")
    print("=" * 60)
    
    index = load_memory_index()
    memories = index.get("memories", [])
    print(f"Loaded {len(memories)} memories from retrieval-index.yaml")
    
    conflicts = find_all_conflicts()
    
    print(f"\nFound {len(conflicts)} potential conflicts:")
    for c in conflicts:
        print(f"  {c['memory_a']} ↔ {c['memory_b']}: {', '.join(c['conflict_types'])} (severity: {c['severity']})")
    
    output_file = save_conflicts(conflicts)
    print(f"\nOutput written to: {output_file}")
    
    return conflicts

if __name__ == "__main__":
    main()
