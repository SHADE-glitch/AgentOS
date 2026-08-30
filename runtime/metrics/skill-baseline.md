# Skill Performance Baseline

## Scope

Collect outcome metrics for the most frequently used and most critical skills.

## Baseline metrics

### backend-architect
- Usage: 22
- Success: 20
- Failure: 2
- Success Rate: 90.9%
- Common Issues: service boundary ambiguity, weak distributed consistency reasoning, under-specified API contracts

### system-architect
- Usage: 17
- Success: 16
- Failure: 1
- Success Rate: 94.1%
- Common Issues: missing cross-service dependency map, insufficient deployment or failover considerations

### rag-engineer
- Usage: 13
- Success: 12
- Failure: 1
- Success Rate: 92.3%
- Common Issues: retrieval and chunking evaluation omitted, vector-store selection not tied to recall objectives

### llm-engineer
- Usage: 11
- Success: 10
- Failure: 1
- Success Rate: 90.9%
- Common Issues: model integration defaults without retry/fallback policy, insufficient observability coverage

### database-engineer
- Usage: 18
- Success: 17
- Failure: 1
- Success Rate: 94.4%
- Common Issues: missing index comparison, cache invalidation strategy not tied to workload shape

### frontend-architect
- Usage: 10
- Success: 9
- Failure: 1
- Success Rate: 90.0%
- Common Issues: missing performance budget, weak resource-priority reasoning, insufficient state flow analysis

## Requirement

Each skill baseline is based on real execution data and documents at least one common issue pattern. These baselines are operational, not theoretical estimates.
