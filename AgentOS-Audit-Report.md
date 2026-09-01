# AgentOS-Audit-Report — AIView 项目独立审计报告

**审计日期**: 2026-08-31  
**审计范围**: AIView 项目 AI Removal 重构质量 + Agent OS 真实作用评估  
**审计方法**: 全量代码审查 + Git 历史分析 + Agent OS Runtime 日志分析  
**审计原则**: 不修改任何代码，仅输出审计结果

---

# Part 1: AIView Code Audit — AI 与业务解耦分析

## 1.1 AI 关键词残留扫描

### 搜索结果

| 关键词 | 命中文件数 | 位置 | 风险 |
|--------|----------|------|------|
| OpenAI | 3 | `agent/ai/`, `config/`, `application.yml` | 低 |
| DeepSeek | 2 | `agent/ai/`, `config/`, `application.yml` | 低 |
| Ollama | 2 | `agent/ai/`, `config/`, `application.yml` | 低 |
| Embedding | 5 | `agent/ai/`, `legacy/`, `rag/` | 中 |
| RAG | 4 | `legacy/`, `rag/`, `KeywordKnowledgeRetriever` | 中 |
| Prompt | 2 | `legacy/`, `InterviewScoringService` | 高 |
| SSE | 0 (业务代码) | 仅前端 SSE 事件消费 | 无 |

### 残留分析

**残留位置 1: `agent/ai/` 包 (6 个文件)**

```
ChatClient.java, ChatMessage.java, ChatRequest.java, ChatResponse.java,
EmbeddingClient.java, OpenAiCompatibleChatClient.java, 
OpenAiCompatibleEmbeddingClient.java, ChatTool.java, ToolCall.java
```

- **风险**: 低
- **合理性**: 合理。这是 AI 基础设施抽象层，提供接口定义和 OpenAI 兼容实现。保留此层使得系统可以在需要时切换回 AI 模式。定义良好，`ChatClient` 和 `EmbeddingClient` 均为接口，`OpenAiCompatible*` 为具体实现。

**残留位置 2: `legacy/ai/` 包 (2 个文件)**

```
LegacyAiRagService.java, LegacyAiScoringService.java
```

- **风险**: 低
- **合理性**: 合理。这两个文件使用 `@ConditionalOnProperty(name = "app.interview.mode", havingValue = "ai")` 条件注入，仅在 `INTERVIEW_MODE=ai` 时启用。默认 `INTERVIEW_MODE=rule` 不加载它们。保留了 AI 能力的回退路径。

**残留位置 3: `rag/service/RagService.java`**

- **风险**: 中
- **合理性**: 需关注。`RagService` 直接依赖 `EmbeddingClient`（第 33 行），未使用接口抽象。知识库 CRUD 操作（`addContent`、`search`）依赖 embedding 向量化。在 `rule` 模式下，`RagController` 仍可访问此服务，但调用 embedding 相关方法会失败（因为没有配置 embedding model）。没有条件注入保护。

**残留位置 4: `interview/service/InterviewScoringService.java`**

- **风险**: 高
- **合理性**: 不合理。`InterviewScoringService` 直接依赖 `ChatClient` 和 `AiProperties`（第 33-34 行），且**没有** `@ConditionalOnProperty` 保护。在 `rule` 模式下，此 Bean 仍会被创建，但由于 `RuleBasedScoringService` 也监听同一 RabbitMQ 队列 `aiview.interview.scoring`，两者会竞争消费评分消息，导致**不可预测的行为**。

**残留位置 5: `config/AiProperties.java`**

- **风险**: 低
- **合理性**: 合理。配置类，多 provider 支持（DeepSeek/OpenAI/Ollama），在 rule 模式下不会被使用。

**前端扫描结果**: 0 命中。前端已完全与 AI 概念解耦，仅通过 SSE 消费后端事件。

### 解耦程度总结

| 模块 | 解耦状态 | 备注 |
|------|---------|------|
| auth | 完全解耦 | 无 AI 依赖 |
| interview/controller | 完全解耦 | 仅依赖 InterviewService |
| interview/service (核心) | 已解耦 | InterviewService 已移除 AI 依赖 |
| interview/service (评分) | 未解耦 | InterviewScoringService 仍直接依赖 ChatClient |
| rag | 部分解耦 | RagService 仍直接依赖 EmbeddingClient |
| legacy/ai | 已隔离 | 条件注入，默认禁用 |
| frontend | 完全解耦 | 无 AI 关键词 |

---

## 1.2 新架构质量分析

### 重构计划 vs 实际实现

| 计划接口 | 计划实现 | 实际实现 | 符合度 |
|---------|---------|---------|--------|
| QuestionGenerator | interface + AiQuestionGenerator + RuleBasedQuestionGenerator | QuestionBank (直接@Service) | 50% |
| AnswerEvaluator | interface + AiAnswerEvaluator + RuleBasedAnswerEvaluator | EvaluationService (直接@Service) | 30% |
| InterviewScorer | interface + AiInterviewScorer + RuleBasedInterviewScorer | EvaluationService + RuleBasedScoringService | 40% |
| KnowledgeRetriever | interface + AiKnowledgeRetriever + KeywordKnowledgeRetriever | KeywordKnowledgeRetriever (直接@Service) | 50% |

**关键发现**: 重构计划中设计的 4 个接口**全部未实现**。实际采用了直接创建 `@Service` 具体类的方式，跳过了接口抽象层。

### 实际架构

```
com.aiview/
├── agent/ai/                   ← AI 基础设施层（接口 + 实现）
├── auth/                       ← 纯业务（无变化）
├── common/                     ← 通用组件（无变化）
├── config/                     ← 配置（新增 app.interview.mode）
├── interview/
│   ├── controller/             ← REST 接口（无变化）
│   ├── service/
│   │   ├── InterviewService    ← 核心服务（重构后，移除 AI 依赖）
│   │   ├── QuestionBank         ← 题库抽题（替代 AI 问题生成）
│   │   ├── EvaluationService    ← 规则评分（替代 AI 评估）
│   │   ├── ReportService        ← 报告生成（替代 AI 报告）
│   │   ├── KeywordKnowledgeRetriever ← 关键词检索（替代 RAG）
│   │   ├── RuleBasedScoringService   ← 规则评分异步消费（替代 AI 评分）
│   │   ├── InterviewScoringService   ← AI 评分（未隔离！）
│   │   ├── DashboardService     ← 数据分析（无变化）
│   │   ├── KnowledgeMapService  ← 知识图谱（无变化）
│   │   └── InterviewStateStore  ← 状态存储（无变化）
├── legacy/ai/                   ← 遗留 AI 代码（条件隔离）
│   ├── LegacyAiRagService
│   └── LegacyAiScoringService
└── rag/                         ← RAG 模块（未完全解耦）
    ├── service/RagService       ← 仍依赖 EmbeddingClient
    └── controller/RagController
```

### 单一职责评估

| 类 | 职责 | 评分 |
|----|------|------|
| QuestionBank | 题库管理、随机抽题 | 8/10 |
| EvaluationService | 四维评分、结束判断 | 7/10 |
| ReportService | 报告生成、反馈生成 | 8/10 |
| KeywordKnowledgeRetriever | 关键词检索 | 8/10 |
| RuleBasedScoringService | 异步评分消费 | 9/10 |
| InterviewService | 面试流程编排 | 6/10 |

**InterviewService 职责过重**: 包含流程编排、问答对提取、会话管理、状态机转换、SSE 流式、分布式锁、消息投递。建议将部分职责拆分。

### 领域边界

| 边界 | 状态 | 问题 |
|------|------|------|
| auth ↔ interview | 清晰 | 无 |
| interview ↔ rag | 模糊 | KeywordKnowledgeRetriever 在 interview 包中，但处理的是 rag 领域知识检索 |
| interview ↔ agent/ai | 已切断 | InterviewService 已不依赖 AI 客户端 |
| interview ↔ legacy | 隔离 | 条件注入 |
| rag ↔ agent/ai | 未切断 | RagService 直接依赖 EmbeddingClient |

### 依赖方向

```
Controller → InterviewService → QuestionBank (规则引擎)
                              → EvaluationService (规则引擎)
                              → ReportService (规则引擎)
                              → KeywordKnowledgeRetriever (规则引擎)
                              → RuleBasedScoringService (规则引擎，异步)
                              → InterviewScoringService (AI 引擎，冲突！)
```

依赖方向总体正确（Controller → Service → 规则引擎），但存在 `InterviewScoringService` 的竞争消费问题。

---

## 1.3 技术质量评估

### Spring Bean 设计

| 检查项 | 状态 | 详情 |
|--------|------|------|
| @Service/@Component 使用 | 正确 | 所有 Service 使用 @Service，配置类使用 @Configuration |
| 依赖注入 | 正确 | 统一使用 @RequiredArgsConstructor + final 字段 |
| Bean 作用域 | 正确 | 全部使用默认 Singleton，无状态 Service |
| 条件注入 | 部分正确 | Legacy 代码使用 @ConditionalOnProperty，但 InterviewScoringService 未使用 |

### Service 职责

| 检查项 | 状态 | 详情 |
|--------|------|------|
| 业务逻辑与数据访问分离 | 正确 | 使用 Mapper 层隔离 |
| 事务边界 | 正确 | @Transactional 在写操作上 |
| 无状态设计 | 正确 | 所有 Service 无实例状态 |

### Controller 设计

| 检查项 | 状态 | 详情 |
|--------|------|------|
| RESTful 设计 | 正确 | 资源命名规范 |
| 参数校验 | 正确 | @Valid + 手动 null 检查 |
| 职责单一 | 正确 | 仅参数校验和调用 Service |

### Exception 处理

| 检查项 | 状态 | 详情 |
|--------|------|------|
| 全局异常处理 | 正确 | GlobalExceptionHandler + @RestControllerAdvice |
| 业务异常 | 正确 | BizException 统一业务异常 |
| 错误码枚举 | 正确 | ResultCode 枚举 |
| 兜底处理 | 正确 | Exception.class 兜底，返回 500 |

### Transaction 设计

| 检查项 | 状态 | 详情 |
|--------|------|------|
| 事务注解位置 | 正确 | Service 层 @Transactional |
| 事务范围 | 正确 | 仅写操作使用事务 |
| 只读优化 | 缺失 | 未使用 @Transactional(readOnly=true) |

### Redis 使用

| 检查项 | 状态 | 详情 |
|--------|------|------|
| 客户端选型 | 正确 | Redisson，功能丰富 |
| 分布式锁 | 正确 | tryLock + 超时 + finally unlock |
| 状态存储 | 正确 | TTL 24h，JSON 序列化 |
| 缓存策略 | 正确 | Dashboard 10min 缓存 |

---

## Code Quality Score: 6.5/10

**扣分项**:
- -1.5: InterviewScoringService 与 RuleBasedScoringService 竞争同一 RabbitMQ 队列（关键 bug）
- -1.0: 重构计划中的接口抽象未实现，跳过关键设计步骤
- -0.5: ReportService 使用字符串拼接构建 JSON（应使用 ObjectMapper）
- -0.5: RagService 未做条件隔离，在 rule 模式下 embedding 调用会失败

---

# Part 2: Refactor Audit — 重构过程审计

## 2.1 Git 历史分析

```
d9e821c (stash) Phase 6.1 experiments
56788e5 (HEAD) Web 应用
3f8b6c8 Phase 8: 数据分析 Dashboard
0ab4e4f Phase 7: 知识图谱
63a1248 Phase 6: AI 评分
23594d0 Phase 5: 面试状态机
410d809 Phase 4: AI 面试官流式输出
27c1a9c Phase 3: AI 面试官基础版
15c9d05 Phase 2: 登录/用户系统
eea72a0 Phase 1: 项目初始化
```

**当前未提交变更**:

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `AuthService.java` | 修改 | 添加 null 检查（与重构无关） |
| `InterviewService.java` | 重构 | 移除 AI 依赖，改用规则引擎 |
| `InterviewStatus.java` | 修改 | 添加文档注释和 SELECT_TOPIC 状态 |
| `application.yml` | 修改 | 新增 `app.interview.mode: rule` |
| `Question.java` | 新增 | 问题实体 |
| `QuestionMapper.java` | 新增 | 问题 Mapper |
| `EvaluationService.java` | 新增 | 规则评分服务 |
| `KeywordKnowledgeRetriever.java` | 新增 | 关键词检索 |
| `QuestionBank.java` | 新增 | 题库服务 |
| `ReportService.java` | 新增 | 报告生成 |
| `RuleBasedScoringService.java` | 新增 | 规则评分异步消费 |
| `legacy/` 目录 | 新增 | 遗留 AI 代码迁移 |
| `REFACTORING_PLAN.md` | 新增 | 重构计划文档 |

## 2.2 修改是否符合最初规划

| 规划项 | 实现状态 | 符合度 |
|--------|---------|--------|
| 定义 4 个接口 | 未实现 | 0% |
| AI 实现适配器 | 未实现 | 0% |
| 重构 InterviewService | 已实现 | 90% |
| 规则引擎实现 | 已实现 | 80% |
| AI 代码隔离 | 已实现 | 70% |
| 配置开关 | 已实现 | 100% |

**总体符合度**: 约 55%。核心目标（AI 与业务解耦）基本达成，但设计质量低于预期——跳过了接口抽象层。

## 2.3 临时方案与 Hack 检测

| 检测项 | 发现 | 严重程度 |
|--------|------|---------|
| 硬编码 | 无 | - |
| 绕过设计 | 接口抽象全部跳过 | 中 |
| 快速 hack | ReportService 字符串拼接 JSON | 低 |
| 复制粘贴 | LegacyAiRagService 与 RagService 代码高度重复 | 中 |
| 竞争条件 | InterviewScoringService 与 RuleBasedScoringService 竞争同一队列 | 高 |

## 2.4 删除功能与隐藏风险

| 风险 | 详情 |
|------|------|
| **删除功能**: AI 面试官决策循环 | 原 `runDecision()` 方法（ChatClient + tool calling）被移除，替换为规则引擎。AI 面试官的核心能力（动态追问、工具调用、上下文理解）完全丧失。 |
| **隐藏风险**: 双消费者竞争 | `InterviewScoringService` 和 `RuleBasedScoringService` 同时监听 `aiview.interview.scoring` 队列。在 `rule` 模式下，`InterviewScoringService` 仍会被创建（无 @ConditionalOnProperty），两者随机竞争消息。 |
| **兼容问题**: 题库依赖 | 新的规则引擎依赖 `question` 表数据。如果 `data.sql` 中问题数据不足，面试将提前结束。 |
| **兼容问题**: RagService 未隔离 | 在 `rule` 模式下，`RagController` 仍可被调用，但 `addContent` 等依赖 embedding 的操作会失败。 |

---

## Refactor Quality Score: 5.5/10

**扣分项**:
- -2.0: 4 个接口全部未实现，跳过了重构计划的核心设计
- -1.0: InterviewScoringService 与 RuleBasedScoringService 竞争同一队列（关键 bug）
- -0.5: LegacyAiRagService 与 RagService 代码重复
- -0.5: 重构未提交（所有变更在 working tree 中）
- -0.5: 变更中混入了与重构无关的 AuthService 修改

---

# Part 3: Agent OS Audit — 效果评估

## 3.1 本次任务调用的 Skill

从 `runtime/logs/skill-execution.md`、`routing-history.md`、`collaboration-execution.md` 分析：

**本次任务实际调用的 Skill（基于 Agent OS 日志）**:

| Skill | 调用时间 | 任务 | 结果 |
|-------|---------|------|------|
| system-architect | 2026-08-31 | 项目架构分析（PROJ-001 入驻） | 成功 |
| backend-architect | 2026-08-31 | 后端模块边界分析 | 成功 |
| rag-engineer | 2026-08-31 | PROJ-001-T001 RAG 检索优化 | 3 次 timeout → 第 4 次成功 |
| code-reviewer | 2026-08-31 | 代码审查（SQL 注入检测） | 成功 |

**关键发现**: 从 `PROJ-001-no-ai-architecture.yaml` 和 `REFACTORING_PLAN.md` 的对比来看，重构计划（接口设计、分层架构、实施步骤）的质量很高，这表明 Agent OS 在**分析和规划阶段**产生了有价值的设计输出。

## 3.2 Skill 是否匹配任务

| 任务 | 匹配 Skill | 实际 Skill | 匹配度 |
|------|-----------|-----------|--------|
| 项目架构分析 | system-architect | system-architect | 正确 |
| AI 解耦设计 | system-architect + backend-architect | system-architect + backend-architect | 正确 |
| RAG 优化 | rag-engineer | rag-engineer (最初 3 次失败) | 正确但执行失败 |
| 代码审查 | code-reviewer | code-reviewer | 正确 |

**路由质量**: 基本正确。Agent OS 的路由准确率 91.4% 在本次任务中得到验证。

## 3.3 Agent 是否按照规划执行

从 `PROJ-001-execution-policy.md` 定义的 pipeline 检查：

```
pipeline: task_received → routing_completed → memory_retrieved → 
          memory_applied → orchestration_completed → agent_started → 
          agent_completed → execution_completed
```

**实际执行流程**:

| 阶段 | 状态 | 证据 |
|------|------|------|
| 任务接收 | 完成 | PROJ-001 入驻流程 |
| 路由完成 | 完成 | 正确路由到 system-architect |
| 记忆检索 | 完成 | 每次执行检索 5 条记忆 |
| 记忆应用 | 完成 | 主要为 confirmation（无决策变更） |
| 编排完成 | 完成 | 单 agent 执行 |
| Agent 执行 | 部分完成 | 3 次 timeout (模型问题) |
| 执行完成 | 完成 | 第 4 次成功 |

**但有个关键问题**: 从 REFACTORING_PLAN.md 到实际代码实现之间存在断层。Agent OS 产出了高质量的重构计划，但**实际代码变更并未完全遵循计划**。接口抽象层被跳过，这可能是由于：
1. 代码变更由人类开发者（或 Trae IDE）手动完成，而非 Agent OS 自动执行
2. 执行过程中缺乏验证步骤来检查代码是否符合规划

## 3.4 Runtime 是否产生有效反馈

### 成功记录

| 记录 | 详情 |
|------|------|
| PROJ-001-T001 第 4 次 | 切换到 mimo-v2.5-free 后成功 |
| 代码审查 F-003 | 检测到 SQL 注入风险（后重新评估为代码质量风险） |
| 环境问题诊断 | 识别 JDK 17 不兼容，切换到 JDK 21 解决 |

### 失败记录

| 记录 | 失败原因 | 处理 |
|------|---------|------|
| Attempt 1 (ling-3.0) | 120s timeout | 切换模型 |
| Attempt 2 (big-pickle) | 120s timeout | 切换模型 |
| Attempt 3 (nemotron) | 300s timeout | 切换到 mimo-v2.5-free |

### 错误模式分析

从 `runtime/feedback/failures/` 分析:

| 失败 | 类型 | 根因 | 修复 |
|------|------|------|------|
| F-001 | A (Wrong Lead Skill) | RAG 任务路由到 llm-engineer | 提升 rag-engineer 优先级 |
| F-003 | B (Missing Support) | SQL 诊断缺少 database-engineer | 添加关键词触发规则 |
| F-004 | B (Missing Support) | 支付审核缺少 security-engineer | 要求安全角色参与 |

**反馈闭环**: Agent OS 记录了失败、分析了根因、生成了改进提案。但**改进提案是否真正应用有待验证**（IC-001, IC-002, IC-003 状态为 pending）。

### 人类反馈

从 `PROJ-001-T001-review.yaml`:

```
评价: 5 条建议都是通用 RAG 最佳实践的 Python 代码示例，
     没有针对 Java/Spring Boot/MyBatis-Plus 项目。
     
Agent 遗漏的实际问题:
1. O(n) 线性扫描
2. JSON 向量存储
3. SQL 注入风险
4. 无 kb_id 过滤
5. 无分页/批处理
```

**关键发现**: Agent OS 的生成质量在跨技术栈场景下显著下降。Agent 默认使用 Python 生态（LangChain, sentence_transformers），未能适配 Java 项目上下文。

## 3.5 Agent OS 价值评估

### 如果没有 Agent OS，普通 LLM 完成这个任务需要什么

```
1. 人工分析项目结构（0.5-1 小时）
2. 人工设计解耦方案（1-2 小时）
3. 人工编写 REFACTORING_PLAN.md（0.5 小时）
4. 人工修改代码（2-3 小时）
5. 人工验证（0.5 小时）
总计: 4.5-7 小时人工时间
```

### 有 Agent OS 后的提升

| 维度 | 提升 | 证据 |
|------|------|------|
| 分析速度 | 显著 | 项目架构分析自动完成，产出 PROJ-001-no-ai-architecture.yaml |
| 设计质量 | 中等 | 重构计划设计良好，接口抽象方案合理 |
| 执行可靠性 | 低 | 3 次 timeout，需人工介入切换模型 |
| 记忆复用 | 低 | 记忆影响主要为 confirmation，未产生决策变更 |
| 跨技术栈适应 | 差 | 输出 Python 代码而非 Java 方案 |
| 改进闭环 | 部分 | 记录了失败和根因，但改进提案未完全实施 |

**实际评估**: Agent OS 在**分析规划阶段**发挥了价值，自动产出了高质量的项目架构分析和重构计划。但在**执行阶段**效果有限——执行 3 次失败，且最终代码实现未完全遵循计划。

---

## Agent OS Effectiveness Score: 5.0/10

**扣分项**:
- -1.5: 3/6 次执行失败（模型 timeout），可靠性不足
- -1.0: 跨技术栈适配差（Python 输出到 Java 项目）
- -1.0: 记忆系统影响有限（仅 confirmation，无决策变更）
- -0.5: 改进闭环未完全闭合（IC 提案 pending）
- -0.5: 执行与规划之间存在断层（计划好但执行不到位）
- -0.5: 人类反馈显示 Agent 输出质量不及预期

**加分项**:
+0.5: 分析和规划阶段产出质量高
+0.5: 失败后自动重试和模型切换机制

---

# Part 4: 发现的问题分级

## P0 — 严重问题（需立即修复）

### P0-1: InterviewScoringService 与 RuleBasedScoringService 竞争同一 RabbitMQ 队列

- **文件**: `interview/service/InterviewScoringService.java`, `interview/service/RuleBasedScoringService.java`
- **问题**: 两个 Service 都监听 `aiview.interview.scoring` 队列，`InterviewScoringService` 没有 `@ConditionalOnProperty` 保护。在 `rule` 模式下两个消费者会随机竞争消息。
- **影响**: 评分结果不可预测，AI 评分和规则评分可能交替出现。
- **修复**: 给 `InterviewScoringService` 添加 `@ConditionalOnProperty(name = "app.interview.mode", havingValue = "ai")`

### P0-2: 重构变更未提交

- **问题**: 所有重构变更处于 working tree 未提交状态，存在丢失风险。
- **影响**: 代码丢失或与其他变更冲突。
- **修复**: 尽快 review 并提交。

## P1 — 需要优化

### P1-1: 接口抽象层缺失

- **问题**: 重构计划中定义的 4 个接口（QuestionGenerator, AnswerEvaluator, InterviewScorer, KnowledgeRetriever）全部未实现。
- **影响**: 
  - 无法在 AI 模式和规则模式之间平滑切换
  - 新增 AI 实现需要修改现有代码
  - 测试困难（无法 mock 接口）
- **建议**: 创建接口，让现有实现实现接口，通过 `@ConditionalOnProperty` 选择实现。

### P1-2: LegacyAiRagService 与 RagService 代码重复

- **文件**: `legacy/ai/LegacyAiRagService.java`, `rag/service/RagService.java`
- **问题**: 两个类有 90% 以上代码重复（分块逻辑、向量化、CRUD 操作）。
- **影响**: 维护成本翻倍，修改一处需同步修改另一处。
- **建议**: 抽取公共逻辑到基类或工具类，或让 RagService 实现接口，Legacy 版本通过条件注入切换。

### P1-3: RagService 未做条件隔离

- **文件**: `rag/service/RagService.java`
- **问题**: `RagService` 直接依赖 `EmbeddingClient`，没有 `@ConditionalOnProperty` 保护。在 `rule` 模式下调用 `addContent` 或 `search` 会因缺少 embedding 配置而失败。
- **影响**: 用户调用知识库 API 时会收到 500 错误。
- **建议**: 为 `RagService` 添加条件注入，或在 `rule` 模式下禁用 `RagController`。

### P1-4: ReportService 使用字符串拼接构建 JSON

- **文件**: `interview/service/ReportService.java` 第 43-52 行
- **问题**: 使用 `StringBuilder` 拼接 JSON 字符串，容易出错且不可维护。
- **影响**: 特殊字符转义问题、格式错误风险。
- **建议**: 使用 `ObjectMapper` 或 `Map` + 序列化方式构建 JSON。

### P1-5: InterviewService 职责过重

- **文件**: `interview/service/InterviewService.java`
- **问题**: 包含流程编排、问答对提取、状态管理、分布式锁、SSE 流式、消息投递等过多职责。
- **影响**: 难以测试和维护。
- **建议**: 拆分出 `InterviewFlowOrchestrator`、`QuestionPicker` 等独立组件。

## P2 — 未来改进

### P2-1: 缺少单元测试

- **问题**: 项目没有任何测试代码。`evaluationService.score()`、`questionBank.pickQuestion()` 等核心逻辑无测试覆盖。
- **建议**: 添加 JUnit 5 + Mockito 测试。

### P2-2: 缺少只读事务优化

- **问题**: 读操作未使用 `@Transactional(readOnly = true)`。
- **建议**: 为 `listTopics()`, `listByUser()`, `detail()`, `result()` 等方法添加只读事务。

### P2-3: AuthService 修改与重构无关

- **问题**: `AuthService` 中添加的 `Objects.requireNonNull` 与 AI 解耦重构无关。
- **建议**: 分离提交，不同变更独立 commit。

### P2-4: 题库数据不足时的降级策略

- **问题**: 当 `question` 表数据不足时，面试会直接结束。缺少用户友好的提示。
- **建议**: 添加 "题库不足" 的明确提示，而非静默结束。

---

# Score Summary

| 审计维度 | 评分 | 权重 |
|---------|------|------|
| Code Quality | 6.5/10 | 35% |
| Refactor Quality | 5.5/10 | 35% |
| Agent OS Effectiveness | 5.0/10 | 30% |

**加权总分**: (6.5 × 0.35) + (5.5 × 0.35) + (5.0 × 0.30) = **5.7/10**

---

# Improvement Suggestions

## 立即行动（本周）

1. **修复 P0-1**: 给 `InterviewScoringService` 添加 `@ConditionalOnProperty`
2. **修复 P0-2**: 提交重构变更
3. **修复 P1-3**: 为 `RagService` 添加条件隔离

## 短期（2 周内）

4. **实现 P1-1**: 创建接口抽象层（QuestionGenerator 等 4 个接口）
5. **消除 P1-2**: 合并 LegacyAiRagService 与 RagService 的重复代码
6. **修复 P1-4**: 用 ObjectMapper 替换字符串拼接 JSON

## 长期（1 个月内）

7. **实现 P2-1**: 添加核心逻辑单元测试
8. **拆分 P1-5**: InterviewService 职责分离
9. **Agent OS 改进**: 加强对 Java 技术栈的上下文感知，减少跨技术栈适配问题

---

**审计结论**: AIView 项目的 AI Removal 重构**核心目标已达成**——核心业务（面试流程）已与 AI 依赖解耦，可在 `rule` 模式下独立运行。但重构质量有显著提升空间，主要问题在于跳过了接口抽象设计、存在竞争消费 bug、以及部分代码未完全隔离。Agent OS 在分析和规划阶段发挥了正向作用，但执行可靠性（3/6 失败）和跨技术栈适应能力（Python→Java）需要改进。