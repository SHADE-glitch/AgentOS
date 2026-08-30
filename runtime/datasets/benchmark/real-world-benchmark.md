# Real World Benchmark

This benchmark is based on real task samples instead of synthetic-only scenarios.

## Goal

Establish the first valid operational baseline for:

- router accuracy
- skill effectiveness
- evolution usefulness

## Minimum standard

- at least 50 real tasks sampled
- at least 3 real failure cases analyzed
- at least 1 before/after quality comparison

## Benchmark Summary

- Sample Count: 58 real task executions
- Correct Routing: 53
- Wrong Routing: 5
- Accuracy: 91.4%
- Main Failure Pattern: RAG and distributed-system tasks were over-weighted toward general LLM or backend routing; support-role omissions were the second most common issue
- Improvement Observed: router precision improved from 84.5% in the first audit to 91.4% after applying explicit routing rules and support-skill checks

## Evidence

- Dataset source: `runtime/datasets/raw/tasks.md`
- Failure analysis source: `runtime/feedback/failures/analyzed/`
- Benchmark review: `runtime/feedback/review/`
- Decision basis: benchmark evidence, not elapsed time
