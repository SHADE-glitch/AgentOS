# Phase 4.1 Tests

Infrastructure validation for the multi-agent core: orchestrator activation, team plan generation, and registry conformance.

## Test 1: Orchestrator triggering

### 1.1 Positive — complex cross-domain task triggers the orchestrator

## Input
帮我设计一个 AI 电商推荐系统，包含推荐算法、后端服务和数据库

## Expected
agent-orchestrator activates and produces a team plan.

## Reason
domain >= 2 (ai + backend + database) and required_roles >= 3, so the activation conditions hold.

### 1.2 Negative boundary — single-domain task stays single-agent

## Input
MySQL 慢查询优化

## Expected
Single-agent mode: database-engineer is the lead. agent-orchestrator does NOT activate.

## Reason
One domain, one required role, no task dependencies. Forming a team would be agent waste.

## Test 2: Team plan generation

## Input
设计完整 AI 商城系统（用户、商品、订单、推荐）

## Expected
The team plan contains all required sections:
- Task Summary
- Trigger Justification
- Selected Roles with owners
- Dependency Order (layered)
- Task Cards

## Reason
The orchestrator output contract requires a complete plan before the human review gate.

## Test 3: Registry conformance

## Input
Any team plan produced by agent-orchestrator.

## Expected
- Every selected role exists in `skills/meta/role-registry.md`.
- No learning role (interview-coach, project-mentor, learning-strategist) appears as a team member.
- No meta maintenance role (agent-router, evolution-engine, agent-evolution-engineer, collaboration-protocol) appears as a team member.

## Reason
The registry is the single source of truth for team-eligible roles. Infrastructure roles must not leak into teams.
