# Skill Routing Matrix

This matrix is the routing reference used by `agent-router`.

| Task | Lead | Support | Priority | Confidence | Fallback |
| --- | --- | --- | --- | --- | --- |
| Spring Boot 项目设计 | backend-architect | system-architect, database-engineer | High | 0.92 | system-architect |
| MySQL 慢查询优化 | database-engineer | backend-architect | High | 0.94 | backend-architect |
| 高并发秒杀系统 | distributed-system | system-architect, backend-architect | High | 0.90 | system-architect |
| RAG 系统设计 | rag-engineer | llm-engineer, prompt-engineer | High | 0.95 | system-architect |
| Agent 工作流设计 | agent-engineer | prompt-engineer, llm-engineer | High | 0.91 | system-architect |
| Prompt 优化 | prompt-engineer | llm-engineer | High | 0.93 | llm-engineer |
| React 页面性能优化 | frontend-performance | frontend-architect | High | 0.91 | frontend-architect |
| 前端工程体系设计 | frontend-architect | devops-engineer | Medium | 0.88 | system-architect |
| 大型互联网系统设计 | system-architect | distributed-system, backend-architect | High | 0.96 | agent-evolution-engineer |
| 学习路线规划 | learning-strategist | project-mentor | Medium | 0.90 | project-mentor |
| 项目陪练 | project-mentor | learning-strategist | High | 0.92 | learning-strategist |
| Java 后端面试准备 | interview-coach | backend-architect | Medium | 0.89 | backend-architect |
| 代码审查 | code-reviewer | security-engineer | Medium | 0.86 | system-architect |
| 安全问题审查 | security-engineer | code-reviewer | High | 0.97 | code-reviewer |
| SQL 优化 | database-engineer | backend-architect | High | 0.94 | backend-architect |
| 系统级架构评审 | technical-reviewer | system-architect, security-engineer | Medium | 0.88 | system-architect |
| 分布式事务设计 | distributed-system | system-architect, database-engineer | High | 0.92 | system-architect |
| 知识库问答系统 | rag-engineer | llm-engineer | High | 0.95 | llm-engineer |
| 缓存架构设计 | database-engineer | distributed-system, backend-architect | High | 0.90 | system-architect |
| 服务治理设计 | backend-architect | system-architect, devops-engineer | Medium | 0.87 | system-architect |

## Priority guidance

- High priority: tasks dominated by a single domain with a clear specialist boundary.
- Medium priority: tasks that require cross-domain coordination but still have a clear lead.
- Fallback: use `system-architect` when the task is underspecified or spans multiple uncertain domains.

## Confidence guidance

Confidence reflects how clear the lead skill is based on problem type and domain cues.

- above 0.9: strong specialist route
- 0.85-0.9: acceptable but needs support review
- below 0.85: ambiguous; route should be re-evaluated before final execution
