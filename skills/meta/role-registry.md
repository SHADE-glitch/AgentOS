# Role Registry

This file is the single source of truth for roles eligible to join orchestrated multi-agent teams.

It is the reference used by `agent-orchestrator` for team formation and task delegation.

## Derivation

Each entry is derived from:

- the skill's SKILL.md frontmatter (`name` must match exactly)
- `memory/skill-routing-matrix.md` (lead/support and keyword signals)
- `skills/version.json` (existence and version state)

Validation state: entries are **not yet team-validated**. They describe today's single-agent behavior. The `status` field moves to `team-validated` only after a role passes real multi-agent collaboration scenarios (Phase 4.2).

## Field semantics

```yaml
role:
  name: <skill name; must equal the SKILL.md frontmatter name>
  domain: <architecture | backend | database | distributed | frontend | ai | quality | engineering | devops>
  responsibility: <what this role owns, and only this role>
  input: <upstream artifacts required before execution>
  output: <the artifact this role produces>
  dependencies: [<upstream roles that must complete first; empty means lead-capable>]
  consumers: [<downstream roles that require this role's output>]
  activation_keywords: [<routing keywords compatible with agent-router; derived from the routing matrix and benchmark scenarios>]
  status: <active | team-validated>
```

## Roles

```yaml
role:
  name: system-architect
  domain: architecture
  responsibility: Own system-level architecture direction and cross-domain trade-off decisions.
  input: Business requirements, user goal
  output: Architecture proposal
  dependencies: []
  consumers: [backend-architect, database-engineer, distributed-system, frontend-architect, llm-engineer, devops-engineer]
  activation_keywords: [system design, architecture, 系统设计, 架构设计, 技术选型, full-system design, cross-domain]
  status: active
```

```yaml
role:
  name: backend-architect
  domain: backend
  responsibility: Own service decomposition, API contracts, and backend platform design.
  input: Architecture proposal, business requirements
  output: Service design
  dependencies: [system-architect]
  consumers: [database-engineer, security-engineer, code-reviewer, testing-engineer]
  activation_keywords: [Spring Boot, microservices, 微服务, API design, 服务治理, backend architecture, Java]
  status: active
```

```yaml
role:
  name: database-engineer
  domain: database
  responsibility: Own data model, cache strategy, and SQL/consistency decisions.
  input: Architecture proposal, service design
  output: Data model and cache strategy
  dependencies: [system-architect, backend-architect]
  consumers: [code-reviewer]
  activation_keywords: [SQL, MySQL, cache, 缓存, 索引, 慢查询, data model, Redis]
  status: active
```

```yaml
role:
  name: distributed-system
  domain: distributed
  responsibility: Own concurrency, consistency, and high-throughput distributed design.
  input: Architecture proposal
  output: Distributed design (consistency model, messaging, scaling)
  dependencies: [system-architect]
  consumers: [code-reviewer, testing-engineer]
  activation_keywords: [高并发, 秒杀, distributed transaction, 分布式事务, consistency, message queue, 消息队列]
  status: active
```

```yaml
role:
  name: frontend-architect
  domain: frontend
  responsibility: Own frontend ecosystem architecture and engineering system design.
  input: Architecture proposal, product requirements
  output: Frontend architecture
  dependencies: [system-architect]
  consumers: [frontend-performance, code-reviewer]
  activation_keywords: [React, Vue, 前端架构, frontend architecture, 工程体系, UI architecture]
  status: active
```

```yaml
role:
  name: llm-engineer
  domain: ai
  responsibility: Own LLM application design: model selection, prompt flow, and API integration.
  input: Business requirements, architecture proposal
  output: LLM application design
  dependencies: [system-architect]
  consumers: [rag-engineer, prompt-engineer, agent-engineer, code-reviewer]
  activation_keywords: [LLM, 大模型, model selection, 模型选型, prompt flow, fine-tuning]
  status: active
```

```yaml
role:
  name: rag-engineer
  domain: ai
  responsibility: Own retrieval, vector storage, and RAG pipeline design.
  input: LLM application design, business requirements
  output: RAG pipeline design
  dependencies: [system-architect, llm-engineer]
  consumers: [quality-evaluator]
  activation_keywords: [RAG, retrieval, 检索, vector, 向量数据库, embedding, knowledge base, 知识库]
  status: active
```

```yaml
role:
  name: quality-evaluator
  domain: quality
  responsibility: Own quality evaluation of integrated multi-agent results against benchmarks and gates.
  input: Integrated results, final report
  output: Quality report (pass / hold / fail)
  dependencies: [code-reviewer]
  consumers: []
  activation_keywords: [quality evaluation, 质量评估, benchmark validation, quality gate, 质量门禁]
  status: active
```

```yaml
role:
  name: code-reviewer
  domain: engineering
  responsibility: Own design and code review for correctness, maintainability, and risk.
  input: Design artifacts and implementation produced upstream
  output: Review findings
  dependencies: [backend-architect, database-engineer, distributed-system, frontend-architect, llm-engineer]
  consumers: [testing-engineer, quality-evaluator]
  activation_keywords: [code review, 代码审查, review, 代码质量, PR review]
  status: active
```

```yaml
role:
  name: testing-engineer
  domain: engineering
  responsibility: Own test strategy, case design, and acceptance validation.
  input: Review findings, design artifacts
  output: Test strategy and cases
  dependencies: [code-reviewer]
  consumers: [quality-evaluator]
  activation_keywords: [testing, 测试, test strategy, 用例设计, acceptance, 验收]
  status: active
```

```yaml
role:
  name: devops-engineer
  domain: devops
  responsibility: Own deployment, CI/CD, and operational readiness design.
  input: Architecture proposal
  output: Deployment and CI/CD design
  dependencies: [system-architect]
  consumers: [testing-engineer]
  activation_keywords: [CI/CD, Docker, Kubernetes, deployment, 部署, monitoring, 监控]
  status: active
```

```yaml
role:
  name: security-engineer
  domain: engineering
  responsibility: Own security review: threats, access control, and data protection.
  input: Design artifacts
  output: Security review
  dependencies: [backend-architect]
  consumers: [code-reviewer]
  activation_keywords: [security, 安全, vulnerability, 漏洞, access control, 权限, encryption, 加密]
  status: active
```

```yaml
role:
  name: technical-reviewer
  domain: architecture
  responsibility: Own architecture-level technical review and trade-off validation.
  input: Architecture proposal
  output: Architecture review
  dependencies: [system-architect]
  consumers: [code-reviewer]
  activation_keywords: [architecture review, 架构评审, technical review, 技术评审]
  status: active
```

```yaml
role:
  name: frontend-performance
  domain: frontend
  responsibility: Own frontend runtime performance analysis and optimization.
  input: Frontend architecture
  output: Performance optimization plan
  dependencies: [frontend-architect]
  consumers: [code-reviewer]
  activation_keywords: [performance, 性能优化, page performance, 页面性能, rendering, 渲染]
  status: active
```

```yaml
role:
  name: prompt-engineer
  domain: ai
  responsibility: Own prompt design and evaluation sets for LLM applications.
  input: LLM application design
  output: Prompt and evaluation design
  dependencies: [llm-engineer]
  consumers: [quality-evaluator]
  activation_keywords: [prompt, 提示词, prompt engineering, evaluation set, 评估集]
  status: active
```

```yaml
role:
  name: agent-engineer
  domain: ai
  responsibility: Own agent workflow design: tool calling, orchestration, and multi-step reasoning.
  input: LLM application design, business requirements
  output: Agent workflow design
  dependencies: [llm-engineer]
  consumers: [code-reviewer]
  activation_keywords: [agent, 智能体, tool calling, 工具调用, agent workflow, multi-agent]
  status: active
```

## Not registered

The following existing skills are intentionally NOT registered as team members:

- Learning roles: interview-coach, project-mentor, learning-strategist
- Meta maintenance roles: agent-router, evolution-engine, agent-evolution-engineer, collaboration-protocol, collaboration-runtime

Meta roles remain infrastructure components and must not appear in team plans.
