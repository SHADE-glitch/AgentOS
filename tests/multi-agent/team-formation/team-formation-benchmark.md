# Team Formation Benchmark Cases

Three cases validate that the pattern library + selection rules form the right team.

## Case 1: AI e-commerce system

## Input
帮我设计一个 AI 电商系统，包含推荐功能和后端服务

## Expected
- Lead: system-architect
- Team: system-architect, backend-architect, rag-engineer, database-engineer, quality-evaluator
- Rejected: llm-engineer, prompt-engineer, agent-engineer

## Reason
Domains ai + backend + database match the ai-application pattern. Recommendation implies retrieval, so R4 keeps rag-engineer. No LLM application/model design signal, so R5 prunes llm-engineer. Optional roles stay out.

## Case 2: Plain CRUD admin system

## Input
做一个普通的订单管理后台，包含用户、商品、订单的增删改查

## Expected
- Lead: backend-architect
- Team: backend-architect, database-engineer, testing-engineer
- Rejected: rag-engineer, llm-engineer, quality-evaluator

## Reason
Single backend + database scope matches the backend-project pattern. Its avoid_roles exclude AI roles, so a full AI team must not be started.

## Case 3: System performance optimization

## Input
系统性能优化，线上接口很慢，需要分析瓶颈

## Expected
- Lead: distributed-system
- Team: distributed-system, backend-architect, database-engineer

## Reason
Performance is the dominant domain, matching the system-optimization pattern. R6 makes distributed-system the lead.
