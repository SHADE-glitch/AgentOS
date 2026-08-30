# Router Benchmark

This benchmark evaluates whether the router selects the correct lead skill and supporting skills for realistic engineering tasks.

## Benchmark objective

The router should be able to identify:

- task intent
- lead skill
- supporting skills
- fallback path
- collaboration needed

## Scenario format

```text
## Input
<user request>

## Expected Skill
<primary skill>

## Supporting Skills
<assistant skills>

## Reason
<why this is the correct route>
```

## Backend scenarios

### 1
## Input
Spring Boot 项目架构设计
## Expected Skill
backend-architect
## Supporting Skills
system-architect, database-engineer
## Reason
Requires service boundaries, infra decision, and persistence planning.

### 2
## Input
Redis 缓存击穿排查
## Expected Skill
database-engineer
## Supporting Skills
backend-architect
## Reason
This is fundamentally a cache and storage issue.

### 3
## Input
高并发秒杀系统设计
## Expected Skill
distributed-system
## Supporting Skills
system-architect, database-engineer, backend-architect
## Reason
Concurrency, consistency, and storage constraints dominate.

### 4
## Input
MySQL SQL 慢查询优化
## Expected Skill
database-engineer
## Supporting Skills
backend-architect
## Reason
Requires SQL and index tuning rather than top-level service design.

### 5
## Input
订单服务拆分方案
## Expected Skill
backend-architect
## Supporting Skills
system-architect, database-engineer
## Reason
This is about service boundaries and domain split.

### 6
## Input
分布式事务设计
## Expected Skill
distributed-system
## Supporting Skills
system-architect, database-engineer
## Reason
Transaction consistency and distributed failure modes are central.

### 7
## Input
支付系统接口设计
## Expected Skill
backend-architect
## Supporting Skills
security-engineer, database-engineer
## Reason
Needs API design, risks, and persistence modeling.

### 8
## Input
Redis 缓存和数据库一致性设计
## Expected Skill
database-engineer
## Supporting Skills
backend-architect, distributed-system
## Reason
Consistency model and cache strategy are key.

### 9
## Input
微服务治理方案
## Expected Skill
backend-architect
## Supporting Skills
system-architect, devops-engineer
## Reason
Service governance, boundaries, and system-level operations matter.

### 10
## Input
JVM 性能诊断
## Expected Skill
backend-architect
## Supporting Skills
database-engineer
## Reason
This is a service runtime optimization issue, not pure DB tuning.

## AI scenarios

### 11
## Input
RAG 系统设计
## Expected Skill
rag-engineer
## Supporting Skills
llm-engineer, prompt-engineer
## Reason
Retrieval, embedding, and retrieval quality are the main concerns.

### 12
## Input
Agent 工作流设计
## Expected Skill
agent-engineer
## Supporting Skills
prompt-engineer, llm-engineer
## Reason
Tool calling, orchestration, and workflow structure dominate.

### 13
## Input
Prompt 优化
## Expected Skill
prompt-engineer
## Supporting Skills
llm-engineer
## Reason
Main issue is prompt quality and evaluation.

### 14
## Input
构建 LLM 应用接入层
## Expected Skill
llm-engineer
## Supporting Skills
agent-engineer, prompt-engineer
## Reason
The focus is on model integration, API behavior, and application design.

### 15
## Input
向量库选型与召回策略
## Expected Skill
rag-engineer
## Supporting Skills
llm-engineer, database-engineer
## Reason
Requires retrieval quality and storage strategy knowledge.

### 16
## Input
AI 应用安全评审
## Expected Skill
security-engineer
## Supporting Skills
llm-engineer, prompt-engineer
## Reason
Security concerns exceed general AI app design.

### 17
## Input
LLM 评估方案设计
## Expected Skill
llm-engineer
## Supporting Skills
prompt-engineer, rag-engineer
## Reason
Evaluation and benchmark strategy are primary.

### 18
## Input
MCP 协议集成设计
## Expected Skill
agent-engineer
## Supporting Skills
llm-engineer, system-architect
## Reason
This is orchestration and protocol integration work.

### 19
## Input
AI 编码助手方案评审
## Expected Skill
prompt-engineer
## Supporting Skills
llm-engineer, agent-engineer
## Reason
Prompt behavior and LLM execution quality are central.

### 20
## Input
RAG 召回失败排查
## Expected Skill
rag-engineer
## Supporting Skills
llm-engineer, database-engineer
## Reason
This is retrieval-quality debugging.

## Frontend scenarios

### 21
## Input
React 性能优化
## Expected Skill
frontend-performance
## Supporting Skills
frontend-architect
## Reason
Covers rendering, memoization, and UI performance.

### 22
## Input
前端工程化方案设计
## Expected Skill
frontend-architect
## Supporting Skills
devops-engineer
## Reason
Architecture and tooling setup are primary.

### 23
## Input
Vue 组件设计与状态管理
## Expected Skill
frontend-architect
## Supporting Skills
frontend-performance
## Reason
Component architecture and state flow matter most.

### 24
## Input
页面加载性能优化
## Expected Skill
frontend-performance
## Supporting Skills
frontend-architect
## Reason
This is about runtime performance and rendering behavior.

### 25
## Input
大前端项目脚手架设计
## Expected Skill
frontend-architect
## Supporting Skills
devops-engineer
## Reason
Tooling, build, and architecture are the main concerns.

### 26
## Input
前端接口封装设计
## Expected Skill
frontend-architect
## Supporting Skills
backend-architect
## Reason
Need end-to-end API contract understanding.

### 27
## Input
前端布局和渲染问题排查
## Expected Skill
frontend-performance
## Supporting Skills
frontend-architect
## Reason
This is a rendering and client-side optimization problem.

### 28
## Input
前端代码审查
## Expected Skill
code-reviewer
## Supporting Skills
frontend-architect
## Reason
Review quality is more important than architecture generation here.

### 29
## Input
构建缓存优化方案
## Expected Skill
devops-engineer
## Supporting Skills
frontend-architect
## Reason
Build pipeline and CI speed are central.

### 30
## Input
前端错误边界设计
## Expected Skill
frontend-architect
## Supporting Skills
code-reviewer
## Reason
Architecture and resilience design dominate.

## Architecture scenarios

### 31
## Input
系统设计：电商平台
## Expected Skill
system-architect
## Supporting Skills
backend-architect, database-engineer, distributed-system
## Reason
Large-scale design with service boundaries and data concerns.

### 32
## Input
高并发日志系统设计
## Expected Skill
system-architect
## Supporting Skills
distributed-system, devops-engineer
## Reason
System throughput and platform concerns dominate.

### 33
## Input
技术方案评审
## Expected Skill
technical-reviewer
## Supporting Skills
system-architect, security-engineer
## Reason
Main need is judgment and risk review.

### 34
## Input
服务拆分评审
## Expected Skill
system-architect
## Supporting Skills
backend-architect
## Reason
Requires architecture judgment and service boundary reasoning.

### 35
## Input
消息队列选型
## Expected Skill
system-architect
## Supporting Skills
distributed-system, database-engineer
## Reason
Architecture and operational constraints are primary.

### 36
## Input
系统扩容方案
## Expected Skill
system-architect
## Supporting Skills
devops-engineer, distributed-system
## Reason
Scaling design and deployment operations are key.

### 37
## Input
服务熔断方案设计
## Expected Skill
system-architect
## Supporting Skills
devops-engineer, backend-architect
## Reason
Resilience and operational behavior matter.

### 38
## Input
架构设计评审
## Expected Skill
technical-reviewer
## Supporting Skills
system-architect, security-engineer
## Reason
This is primarily about review and risk assessment.

### 39
## Input
多租户系统架构
## Expected Skill
system-architect
## Supporting Skills
database-engineer, security-engineer
## Reason
Isolation and data placement are central.

### 40
## Input
缓存架构设计
## Expected Skill
system-architect
## Supporting Skills
database-engineer, distributed-system
## Reason
Storage strategy and scalability are central.

## Learning scenarios

### 41
## Input
学习路线规划
## Expected Skill
learning-strategist
## Supporting Skills
project-mentor
## Reason
This is a capability assessment and study plan task.

### 42
## Input
项目陪练
## Expected Skill
project-mentor
## Supporting Skills
learning-strategist
## Reason
Mentorship and guided reasoning are the main goal.

### 43
## Input
Java 后端面试准备
## Expected Skill
interview-coach
## Supporting Skills
backend-architect
## Reason
This is interview readiness and communication-focused.

### 44
## Input
我想提升后端架构能力
## Expected Skill
learning-strategist
## Supporting Skills
project-mentor
## Reason
Requires capability assessment and structured skill roadmap.

### 45
## Input
看懂项目结构和模块职责
## Expected Skill
project-mentor
## Supporting Skills
learning-strategist
## Reason
This is a guided understanding and learning exercise.

### 46
## Input
面试中被问到数据库索引原理
## Expected Skill
interview-coach
## Supporting Skills
database-engineer
## Reason
Interview response quality and domain depth matter.

### 47
## Input
我想做一个 Java 项目练习
## Expected Skill
learning-strategist
## Supporting Skills
project-mentor
## Reason
Need learning path and progression planning.

### 48
## Input
项目中我不懂为什么要这样设计
## Expected Skill
project-mentor
## Supporting Skills
learning-strategist
## Reason
Need reflective teaching, not direct code output.

### 49
## Input
服务拆分问题如何理解
## Expected Skill
project-mentor
## Supporting Skills
system-architect
## Reason
Learning and design reasoning are central.

### 50
## Input
准备系统设计面试
## Expected Skill
interview-coach
## Supporting Skills
system-architect
## Reason
This is interview communication and strong design articulation.

## Additional benchmark coverage

The list above is intentionally structured as a benchmark core. In real use, the benchmark should be expanded to at least 100 scenarios, but these entries already provide good coverage of routing intent and specialization boundaries.

## Benchmark rules

- score each route as correct / needs review / wrong
- record whether supporting skills were missing
- identify route ambiguity and fallback quality
- review repeated error patterns after each benchmark run

## Benchmark outcome

A sustainable router is not one that is perfect on day one.
It is one that steadily improves after each real task and each benchmark run.
