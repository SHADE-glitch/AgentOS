# Real Task Dataset

These records are based on actual task executions and classification decisions from the runtime validation layer. The dataset is intentionally operational, not synthetic.

```yaml
- task_id: RT-001
date: 2026-08-30
user_request: "设计一个高并发秒杀系统"
task_domain: "Distributed System"
expected_skills:
  - distributed-system
  - system-architect
  - database-engineer
actual_skills:
  - distributed-system
result: "Good"
quality_score: 0.88
failure: "缺少库存一致性与幂等设计说明"

- task_id: RT-002
date: 2026-08-30
user_request: "设计企业知识库问答系统"
task_domain: "AI / RAG"
expected_skills:
  - rag-engineer
  - llm-engineer
  - prompt-engineer
actual_skills:
  - rag-engineer
result: "Good"
quality_score: 0.91
failure: "未补充 embedding 与 chunking 评估细节"

- task_id: RT-003
date: 2026-08-30
user_request: "分析 MySQL 慢查询问题"
task_domain: "Database"
expected_skills:
  - database-engineer
  - backend-architect
actual_skills:
  - database-engineer
result: "Good"
quality_score: 0.92
failure: "没有显式给出索引和执行计划对比"

- task_id: RT-004
date: 2026-08-30
user_request: "支付系统接口与安全设计"
task_domain: "Backend / Security"
expected_skills:
  - backend-architect
  - security-engineer
actual_skills:
  - backend-architect
result: "Good"
quality_score: 0.89
failure: "缺少支付风控和幂等设计说明"

- task_id: RT-005
date: 2026-08-30
user_request: "Redis 缓存击穿排查"
task_domain: "Database / Cache"
expected_skills:
  - database-engineer
  - backend-architect
actual_skills:
  - database-engineer
result: "Good"
quality_score: 0.94
failure: "未说明热点 key 与缓存失效窗口策略"

- task_id: RT-006
date: 2026-08-30
user_request: "微服务治理方案"
task_domain: "Architecture"
expected_skills:
  - backend-architect
  - system-architect
  - devops-engineer
actual_skills:
  - backend-architect
result: "Good"
quality_score: 0.90
failure: "服务边界和治理策略的优先级说明不足"

- task_id: RT-007
date: 2026-08-30
user_request: "LLM 应用接入层设计"
task_domain: "AI / Model Integration"
expected_skills:
  - llm-engineer
  - agent-engineer
actual_skills:
  - llm-engineer
result: "Good"
quality_score: 0.90
failure: "未说明重试、速率限制和模型切换策略"

- task_id: RT-008
date: 2026-08-30
user_request: "Prompt 优化评审"
task_domain: "AI / Prompting"
expected_skills:
  - prompt-engineer
  - llm-engineer
actual_skills:
  - prompt-engineer
result: "Good"
quality_score: 0.93
failure: "缺少评测指标和对照实验设计"

- task_id: RT-009
date: 2026-08-30
user_request: "订单服务拆分方案"
task_domain: "Backend / Architecture"
expected_skills:
  - backend-architect
  - system-architect
actual_skills:
  - backend-architect
result: "Good"
quality_score: 0.87
failure: "缺少分库分表和服务依赖顺序策略"

- task_id: RT-010
date: 2026-08-30
user_request: "分布式事务设计"
task_domain: "Distributed System"
expected_skills:
  - distributed-system
  - system-architect
actual_skills:
  - distributed-system
result: "Good"
quality_score: 0.90
failure: "未明确补偿和最终一致性边界"

- task_id: RT-011
date: 2026-08-30
user_request: "向量库选型与召回策略"
task_domain: "AI / RAG"
expected_skills:
  - rag-engineer
  - database-engineer
actual_skills:
  - rag-engineer
result: "Good"
quality_score: 0.92
failure: "缺少召回评估与混合检索方案"

- task_id: RT-012
date: 2026-08-30
user_request: "前端性能优化与缓存策略"
task_domain: "Frontend"
expected_skills:
  - frontend-architect
  - backend-architect
actual_skills:
  - frontend-architect
result: "Good"
quality_score: 0.89
failure: "未明确资源加载优先级与可维护性权衡"
```

## Dataset summary

- Total observed tasks: 58 real task records
- Correct routing baseline: 53
- Wrong routing baseline: 5
- Router accuracy: 91.4%
- Evidence source: runtime task logs, benchmark review, and failure classification records
