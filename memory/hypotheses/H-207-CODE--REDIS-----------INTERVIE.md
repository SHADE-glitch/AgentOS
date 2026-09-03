```yaml
memory_id: H-207-CODE--REDIS-----------INTERVIE
type: hypothesis
category: engineering_pattern
domain: database
source_loop: LOOP-20260902091226
source_team: team-18087af2
source_agent: security-engineer
evidence_level: hypothesis
confidence: low
observation_count: 1
created_at: 2026-09-02T09:26:32.754096+00:00
tags:
  - auto-bootstrapped
  - code--redis-----------intervie
  - redis
  - cache
  - ttl
  - expiration
```

# Code  Redis           Intervie

## Pattern

Multi-agent team (team-18087af2) execution succeeded. Agent 'security-engineer' identified pattern: code: Redis 连接异常应直接抛 `INTERVIEW_STATE_ERROR`，**禁止**走 DB 重建；只有「确定 key 不存在」才允许回退。. Confidence: 0.74. Team: 7/7 completed.

## Context

Code  Redis           Intervie

## Domain

- Domain: database
- Technical Tags: redis, cache, ttl, expiration

## Source

- Loop: LOOP-20260902091226
- Team: team-18087af2
- Agent: security-engineer
- Bootstrapped: 2026-09-02T09:26:32.754130+00:00

## Status

This is an auto-bootstrapped hypothesis. It requires a second independent
observation before it can be elevated to a validated memory.
