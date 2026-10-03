# Agent OS 定位裁决（2026-09-30）

输入：`docs/audit/current-state.md`（仓库现状）、`docs/research/*`（四项目 + 本机基线 + 8 条借鉴记录）、
本轮补读的上游仓库（用于钉死"独立采用"次数，见 §2）。
输出：定位推荐 + 六个张力的裁决 + 停止/降级判据。Phase 归类与剩余计划在 `docs/plan/final-plan.md`。

**推理纪律**：不以已有投入（339 测试、迁移机制、契约）作为继续的理由 —— 那是沉没成本。
允许结论是"大幅收缩"或"停止"，事实上 §4 给 C 的分数并不低。所有判断标
`[Verified]`（带 `path:line` 或可复现命令）/`[Inferred]`/`[Judgment]`/`[Unconfirmed]`。

---

## 0. 裁决摘要（一句话 + 推荐）

**Agent OS 现在最大的问题不是"做少了"，而是它的闭环从未吃过一次真实数据**：
`store/aos.db` 实测 `observations=0`、`candidates=0`、`learning_reviews=0`，13 条 memories 全是我与手写的种子；
与此同时本机 opencode 有 199 个会话、61,790 个 part、16,374 次工具调用（其中 235 次 error 状态）
—— **100% 的真实证据都在 Agent OS 之外**。 `[Verified]`

因此推荐 **候选 D：证据与治理层（evidence/governance layer）**，
不是候选 A（自有引擎 + 自建 skill/记忆/遥测生态）：

- **保留并做完**：真实运行 → 合成结论 → 人门 → 晋升/降级 → 下次召回改变行为，这一段目前
  **没有任何一个上游为 opencode 做成**（§2 会说明为什么 okdk 没做成）。它是 Agent OS 存在的唯一充分理由。
- **收缩或删**：一切"别人已经做得更好"的部分 —— 遥测（本机 skill-tracker 五表 + 单调状态修正）、
  通用笔记与决策知识（basic-memory + 52 篇人工 md）、skill 生命周期自动化（UniM0cha/Hermes 家族）、
  会话检索（opencode 自带）、代码理解（opencore 的 chunk 索引、或 LSP）。
- **必须先做的前置**（否则 D 仍然是零真实数据）：`loop/pending.py`（session→loop 反查）+ 插件最小骨架，
  或者一条**只读回读**历史的最小通路（`R-007`，本机已实测哪些字段取得到）。二者择一即可通电，
  回读甚至不需要装插件。

---

## 1. 六个维度（打分口径，先定义再打分）

1. **闭环必要性**：缺了它，"下一次执行变好"这条链是否断。
2. **外部是否已有可靠实现**：有可靠实现 ⇒ Agent OS 自研的边际价值低。
3. **非干扰风险**：为生效是否需要写别人的地盘（配置/共享状态/排序）。用户硬约束「停用不影响其他组件、启用只是增强」。
4. **零依赖可行性**：Python 标准库内是否做得了。
5. **可演示性**：能不能在终端上敲出来看见，而不是表格在长。
6. **维护面积**：需要长期维护的代码面。

---

## 2. 血统钉定（这决定"多少项目独立采用"这件事的算法）

| 上游 | 实况 `[Verified]` | 血统含义 |
|---|---|---|
| `NousResearch/hermes-agent` | 存在，MIT，**1.1GB / 250,226 stars**，今天还在推（`2026-09-30T12:17`） | 概念源，体量大到只能读不能搬 |
| `NousResearch/hermes-agent-self-evolution` | 存在，**license: None**，32KB，`pushed 2026-06-17` | okdk README 引它作为"奖励信号"来源 ⇒ **又一处不可复制代码**，且是 GEPA 那半边的正源 |
| `UniM0cha/self-improving-skills` | 由 `claude-self-improving-skills` **改名而来**（API 301 重定向），MIT，124 文件，同一循环已有 **四个环境端口**（Claude Code / Cowork / Codex / ChatGPT Work） | okdk 自述的上游 ⇒ **okdk 是这套循环的第五个端口**，不是独立设计 |
| `okdk7788/skill-evolution` | MIT，14 文件，README 自述是"companion half"，补的是"skill 到底有没有用"这条轴 | 与上一行同属一个家族 |

⇒ **Hermes 家族 = 1 个血统**（hermes-agent → hermes-agent-self-evolution + UniM0cha 四端口 → okdk 移植 → svtter 自称同族但明确偏离：`svtter/README.md:120-128` 的差异表写着「Scoring: Hermes=LLM-based / 本插件=Heuristic」）。
加上 autolearn（自称源自 Schema harness / WikiSkill / AgentMemory，且**明确与 Hermes 对立**：
`docs/designs/session-search/LLD.md:28`「Hermes uses a separate LLM call … Our reviewer IS the LLM」）、
opencore（OpenClaw-inspired）、本机 skill-tracker、Agent OS 自身 ⇒
**整份样本实际只有 5 条血统，不是"四个项目 + 基线"那么多数**。
所有 §3 的裁决都按这个口径计独立次数。

**顺带一条对上轮研究的更正**：`docs/research/findings.md` 把 svtter 与 okdk 判为同源（正确），
但它没有预见到 UniM0cha 一侧比 okdk 移植版成熟得多。okdk 的移植**丢掉了上游的三件强制机制**：

| 上游有（`UniM0cha/README.md` 自述） | okdk 移植后 |
|---|---|
| 「plan first, **apply only after approval**」+ 备份/校验/回滚钩子 | 人门只剩 prose，**未注册 `permission.ask`**，格式合法的 edit 一律接受（`R-006`/findings Q8） |
| 「Distillation **prefers patching** existing skills over creating new ones」 | 判重只在 prompt 里提醒（`index.ts:583`） |
| 「use/view/**a patch a person made** counts as activity; **the distiller's own patches do not**」 | `view_count` 实际在编辑时自增（`index.ts:811`），且遥测从不出自增以外的判断 |
| 「Skills proven by repeated use (`use_count>=3`) age at half speed」 | 无对应机制 |
| 「Fenced distillation session: reduced tool set (no Bash), deny rules that survive `bypassPermissions`, per-job budget cap, post-run skill guard」 | 无 |
| 「Fail-safe hooks: hook errors approve the original action instead of breaking your session」 | 部分（多数 try/catch，但 system.transform 有未包的路径） |

⇒ `[Judgment]` 这是裁决里最硬的一条外部证据：**"学习回路 + 安全强制"这件事已经被一个 MIT 项目想透并实现了六个机制**，
Agent OS 若要在 skill 侧做，正确动作是**移植/复用这些纪律**（或直接把需求交给这个家族的一个 opencode 端口），
而不是自创第七套；而 Agent OS 真正没有对手的那一段在 **memory/经验的生命周期与结论合成**，
因为这一整个家族的"学习单位"都是 SKILL.md 文件，没有任何一家有：证据阶梯、结论置信=覆盖率、
人门在代码里强制、批准时 compare-and-set、可解释迁移（`docs/research/findings.md §13` 的 AOS 领先项清单）。

---

## 3. 六个张力的逐条裁决

### 张力 1 —— Basic Memory 边界
**事实**：已启用（`mcp.basic-memory.enabled=true`，`uvx basic-memory mcp`），其后端是
`<bm-vault>` 下 **52 个手写 md / 9 个编号目录 / 今天还在编辑**；
另有 `command/supermemory-*.md` 四条按需命令（`bunx opencode-supermemory`）与一个 9-05 后无人写的孤儿 `memory.jsonl`。
旧计划 §十一"enabled:false ⇒ 边界零成本"**双重过期**（不仅启用了，而且是活跃的人工地基）。

**裁决 `[Judgment]`**：
- Basic Memory 应成为 **AOS 的"知识侧邻居"，只读、单向、不合并**。AOS Memory 装的是
  *agent 经验*（有证据阶梯、生命周期、会被降级），basic-memory 装的是*人写的知识*（52 篇 md，人负责其真假）。
  两者单位不同、信任模型不同、写入者不同 ⇒ 不做同步、不做互调、不做统一检索。
- 双重注入的处置：边界必须是**一小段代码接缝 + 一条 fixture 断言**，不是文档宣言。
  接缝的具体形状（Stage 3 落进 Plugin 边界）：只 `push` 自己的元素、绝不编辑/删除他人元素、
  不占 `output.system[0]`（DCP 实测靠 `[0]` 判内部调用而整轮跳过裁剪：
  `opencode-dcp/lib/hooks.ts:49-56,101-105` `[Verified]`），并且**清洗正文里的边界标签**
  （现存缺陷：`docs/audit/current-state.md §5.1`，含 `</agent_os>` 的记忆可提前关自己的区块）。
- **不引入 MemoryProvider 抽象**。研究里唯一同名单元（opencore）的向量+FTS 混合检索需要 embedding/网络，
  与零依赖冲突，且它自己不解决"经验是否可信"这个问题（`findings.md` Q1：opencore 无 verdict）。
  预留空壳仍是装饰物。

### 张力 2 —— Skill 演化
**裁决 `[Judgment]`：不做。Agent OS 不建 skill 生命周期，也不做 personal-skills 的自动改进。**
理由三条，逐条有证据：
1. 血统计数：这件事只有 1 条血统（Hermes 家族），且该家族在**安全强制**上比 opencode 移植版成熟得多（§2 的六行表）。
   Agent OS 若做，是在第 6 个端口上重做第 5 个端口已经做错的部分。
2. 用户现有流程已经在产出关键结构：`skills/personal-skills/*/SKILL.md` 的 frontmatter 已写成
   `Use when: / Avoid when:`（实测 `resume-evidence-chain/SKILL.md:1-7`），即 AOS 为记忆发明的 `when_to_apply`
   在人工蒸馏里已存在 ⇒ 自动化只剩"从真实运行里发现缺口"这一小段有增量，而那一段**属于 AOS 的经验层，
   不属于 skill 层**：AOS 该产出的是"某 skill 在 N 次运行后失败率 X，建议人复核"这种**证据**，
   写不写 skill 由人决定（原硬墙不变）。
3. 本机 `permission.edit=allow` ⇒ 任何"自动改 skill 文件"的保护只能 AOS 自己实现，
   而它一旦实现就是在做 UniM0cha 的 skill guard 的第六次重写。

**保留**：Phase 3.6 里的**只读感知 + 有效性观测**（`skills_loaded` 填真值、成功率报告），
且遥测写入者是本机 skill-tracker —— AOS 只读它的表（张力 4）。
**删除计划**：`aos/core/skill_evolution.py`、`skill_versions` 表、`REVIEW_KINDS` 里的 `skill_improvement` 枚举。
（`REVIEW_KINDS` 现含 `policy`/`skill_improvement` 两个**零写入者**的预留值 —— 同一类装饰品，见 `audit §5`。）

### 张力 3 —— 评估模型（加权合成 vs rubric / LLM 打分）
**裁决**：**不合并，共存但分层**。哪些算 evidence、哪些算 judgment：
- **evidence**：能独立复核的事件 —— 测试/构建退出码、`part.state.status=='error'`、diff/patch 规模、
  `todo.status`、用户显式 `outcome`、显式声明并跑过的 `verify:` 命令（`R-005`）。
  共同点：不需要模型的意见即可重放。
- **judgment**：模型或人给的看法 —— svtter 的 4 维启发式、okdk/Hermes 的 LLM-as-judge rubric、
  opencore 的 `importance`、AOS 未来的 LLM 复盘。
- **合成规则**：judgment 可以决定"**要不要处理**"（排序、候选优先级，如 okdk 的 `use*(fail+1)/(total+2)`），
  **永远不能决定"能不能生效"**（晋升/降级只由 evidence + 人门决定）。
  这条是 `R-001`（第三态）、`R-006`（linkage≠outcome）与 §2 上游"nothing acts on weak evidence"的合并表述。
**后果**：`evaluate.compute_quality_score`（按排版打分）保持权重 0.00 的 host 可选输入地位；
`outcome.py` 需要补第三态（现在 `partial` 同时表示"办成一半"和"没被告知"，`R-001`）；
`evidence_level` 的 `runtime_validated/independent_validated` 两档目前由**在场次数**决定，名实不符（`R-006`）⇒ 必须重定义或降格。

### 张力 4 —— 遥测重复
**裁决**：**本机 skill-tracker 是遥测的唯一写入者，AOS 只读并做"遥测→证据"的推导。**
证据：它的实现比 AOS 计划的 `aos skill report` 完整得多 —— 五表（`skills/skill_usage/mcp_usage/plugin_usage/plugin_inventory`）、
`status∈success|error|denied|ask|unknown` 的**单调修正**（实测 `skill-tracker.js:278-300`：观察到的 error 可覆盖乐观写的 success，反向永不）、
`UNIQUE(session_id,call_id)` 幂等键、`metadata.model/agent/branch` 归属、`skill-stats-registry.json` 的 `status/last_seen` 生命周期。 `[Verified]`
`[Judgment]` 因此：
- **取消** `aos skill report` 的自建采集，改为 `aos skill report` = 只读聚合（或干脆删，用它的 `skill-stats.py`/TUI）；
- AOS 的 `telemetry_events` 只记**引擎自己的决定**（learning.run / review_* / lifecycle.fail_open），不记 host 行为 ⇒ 两类事件不再混在一张表；
- 版本耦合护栏照 `R-007`：列白名单 + 读不到就降级为"没有遥测"，并把"字段层级写错 ⇒ 静默永不触发"作为回归测试的必查项
  （okdk 是现成的反面教材）。

### 张力 5 —— 成败信号缺口，主路径是哪条
四条路的实测代价与可信度：

| 路 | 可信度 | 成本 | 本机现实 |
|---|---|---|---|
| 测试结果 / 退出码 | 最高（无歧义） | 要真跑，且需项目有测试 | AOS 只在 host 显式传或 `validate_stage` 真跑时才知道；`permission.bash=ask` ⇒ 多数时候不会自动跑 |
| **人标注（`review label`）** | 高（人就是标准） | **每次一次人工动作** | 已实现，且是唯一现在就能用的路 |
| LLM reviewer | 中低（会自我确认，见 §2 okdk/svtter 两例失效） | 一次子会话 + token | 上游 Hermes 家族用它做**候选生成**，但**批准仍是人**；AOS 目前完全没有这一路 |
| 历史回读（`R-007`） | 中（只能补 tool error/patch/todo 三类，摘要与成本大面积缺失：实测 `summary_files>0` 仅 1/199） | 一次性工程，零持续成本 | 可行且不需要插件在场 |

**裁决**：**主路径 = 人标注 + 测试/退出码；历史回读作为"冷启动加速器"，LLM reviewer 暂缓。**
`[Judgment]` 三条理由：
① 上游全部把"要不要改"交给 LLM，但把"生效"留给人 —— AOS 已有的人门与之同构，不需要再加一层不确定的判官；
② LLM reviewer 引入网络/token/提示注入面三件新成本，而它相对人门的增益未被任何一份样本证明；
③ 真正的瓶颈不是"判得不够聪明"，而是"没有输入"（`observations=0`）。回读能在不装插件的前提下
立刻让系统有真实数据可判，这是当前最短缺的东西。

### 张力 6 —— 计划的重量（剩余 Phase 3.3–3.8 每项过闸）
`[Judgment]` 按"闭环必需性 × 外部是否已有"预判（最终归类在 `final-plan.md`）：

| 计划项 | 裁决预判 | 理由 |
|---|---|---|
| §4.3 去重/冲突/过期/来源 | **KEEP（拆成两块）** | 判重是 4 家都试、0 家可靠，AOS 的索引还是装饰品（`R-003`）；但"来源链"里 provenance 一半已有列，不必新模块 |
| §4.4 使用反馈闭环 + status/scope 过滤 | **KEEP，且改实现方式** | 降级现在"记下了但不生效"（`retrieve.py:142-143` 只回显）；计数改派生（`R-002`），并借上游两条规则：人的使用算活跃、蒸馏器自己的 patch 不算；`use_count>=3` 者老化减半 |
| §4.5 路由/编排可达性六项 | **REMOVE / DEFER 大半** | 与"外置大脑"定位无因果：`difficulty` 硬编码只服务多智能体编排，而编排的产出「无人消费」是原审计自己的结论；`rules.json` 词汇换血是修一个不该用的系统 |
| §4.6 Skill governance | **收缩为只读感知** | 见张力 2；删 `skill_versions`/`skill_evolution.py`/预留枚举 |
| §4.7 证据时序 + pending + stage 卫生 | **KEEP 的三件** | `collect_before` 上移（Evidence 定义的一部分）、`pending.py`（**插件硬前置**）、`execute` 的 fail→complete 擦除与 `recall_stage` 无 try/except（静默吞失败类）|
| §4.8 三个守卫测试 | **优先级升高** | `audit §5` 的三个现存缺陷恰好全在它们的射程内；`test_no_third_party_imports` 是"零依赖"唯一可维持的执行方式 |
| `doctor --json` | **KEEP** | 版本谈判 + 让闭环不查 SQL 就可见 |
| `content/policies/*.json` | **KEEP，成本极低** | 54 个叶子键全部有读者但无一可调 ⇒ Policy Evolution 目前没有地基（`audit §4.1`，该处数字已更正）|
| Phase 4 插件 | **KEEP，但先做 20 行** | 只为通电：`chat.message`→preflight、`system.transform`→push、`session.idle`+`pending`→postflight。其余信号一律后置 |

---

## 4. A/B/C/D 打分与为什么不是 A / 不是 C

| 维度（1 最好） | A 自有引擎+插件 | B 薄治理层+适配 | C 停止自研 | **D 证据与治理层** |
|---|---|---|---|---|
| 闭环必要性 | 5（做满） | 4 | **1**（C 放弃结论合成与人门 ⇒ 环断） | 5 |
| 外部是否已有可靠实现 | 1（skill/记忆/遥测/检索都有更强的） | 4 | 5 | 4（经验生命周期确无对手） |
| 非干扰风险 | 2（生态越做越大，容易伸手进别人地盘） | 4 | 5 | 5（只 push 一个元素 + 只读） |
| 零依赖可行性 | 3（越做越想引入网络/embedding） | 4 | 5 | 5 |
| 可演示性 | 2（大面难以端到端） | 4 | 2（无演示物） | 5（MVP 就是那条链） |
| 维护面积 | 1 | 4 | 5 | 4 |
| **合计** | 14 | 24 | **18** | **28** |

**为什么不是 A**：外部五条线上，A 要重做的每一段都有更强的实现（UniM0cha 家族之于 skill、
skill-tracker 之于遥测、opencore 之于检索、basic-memory 之于知识、opencode 之于会话检索）。
"我们有 339 个测试和 v1→v4 迁移"不构成对 A 的支持 —— 那是已完成工作的度量，不是必要性的度量。

**为什么不是 C**：`[Verified]` 三段无可替代物 —— 结论合成（置信=覆盖率 + 硬失败压倒 + 覆盖率不足时**拒绝命名**）、
代码强制的人门（含 create/weaken 永不自动）、批准时的 compare-and-set。
Hermes 家族把第一条做成了粗粒度"用完之后有没有报错"，第二条**在 opencode 端口里丢了**，第三条谁都没有。
C 的实质是把这三段一起丢掉，而它们恰是"下一次执行变好"唯一的机制来源。
**但 C 的合理内核被吸收进 D**：D 的成立条件正是"除此之外全部复用"，且 §5 的判据允许它随时降级成 C。

---

## 5. 两个附加问题的回答

**Q：Basic Memory 应成为 Agent OS 的什么？**
`[Judgment]` **只读的邻居，人负责其真假；AOS 不导入、不镜像、不做适配层抽象、不与它双向同步。**
2026-10-02 owner 决定加一条接缝：**注入时把 basic-memory 的笔记作为"指针"带一句**（标题 + permalink + 文件路径），
并因此把当年那句"不统一检索"**收窄**为"不做统一索引/统一排序"——两个系统各自检索自己那一份，
输出在同一个块里但**分节、带标签、排在所有 Agent OS 记忆之后**，且不进 `memory_ids`、不进归因、不参与成败。
原来的第二半照旧生效：引用 id 而不是复制内容 —— 默认预算 `max_body_chars: 0` 就是把这句话写成了代码。
读它仍是只读（`mode=ro` + `PRAGMA query_only=ON`，测试钉住源码无写语句、跑完文件字节不变），
邻居库不在 ⇒ 静默降级，一次 preflight 绝不因为别人不在而失败。

2026-10-03 owner 加了**反方向的第二条接缝**，并把它收窄到只剩一种情形：**人门批准一条教训的那一刻，AOS 单向把
那一条发布成一篇笔记**（`agent-os/<memory_id>.md`，frontmatter 带 `agent_os: true` 与全部 `aos_*` 归属字段）。
边界仍然守住的那几条：**人写的笔记仍是只读指针**（引擎从不导入、从不回读自己发出去的那篇来决定什么）；
**发布只经 bm 自己的 CLI**，绝不打开它的 SQLite、绝不以写模式打开它的文件；同名但**没有我们标记**的文件 ⇒ 拒绝写
（`conflict`），所以这篇东西永远只有一个归属；发布失败只改变一次 `stderr` 提示与一条事件，
**不改变批准、不丢教训**（先写 store 再写 bm）。这不叫同步：没有反向数据流，也没有共享状态；
若将来要做"bm 当唯一记忆源"，那是 `agent-os-v2.md §16` 里写明的 Phase 2，不是这里已经做到的事。

**Q：如果 Agent OS 本身没有必要，哪些部分可以独立存在？**
按可独立存活程度排序（都在 `bf0fa6e`）：
1. **`docs/research/` + `docs/audit/`**：与 Agent OS 无关的独立价值（血统分析、四家失效模式清单，对任何 opencode 使用者可用）。
2. **`aos/core/outcome.py`（320 行，零依赖纯函数）**：可直接搬进任何 opencode 插件/CI 做"从信号合成结论 + 报覆盖率"。它不需要库、不需要引擎。
3. **契约层（`aos/contract/*`，stdin/stdout JSON + 版本谈判 + `validate_request` + `unread_request_fields`）**：可作为"任何外部工具向 opencode 注入上下文"的通用协议骨架。
4. **`aos/core/memory/migrations.py`（`PRAGMA user_version` 权威 + 镜像交叉校验 + append-only 步骤 + 备份）**：与学习无关，任何 SQLite 小工具都需要。
5. **门与 CAS（`evolve.decide_promotion`/`apply_effect`）**：形状可复用（"评审展示什么，写入就做什么，基线变了拒写"），但绑定在 memories 表上。
6. **`inject.py` + `retrieve.py` + `store.py` 的记忆层**：离开"经验"这个前提就没有意义 —— **若要停，先停这里**（13 条种子记忆是文档不是引擎，可平移到 basic-memory 或 `personal-skills`）。

---

## 6. 停止 / 降级判据（以后随时可套，不依赖感觉）

1. **真实数据判据**：装插件或开回读后 4 周内，`observations` 中 `source='hot|backfill'` 的真实运行数
   **< 30 条** ⇒ 停做新功能，仓库降级为 §5 的 2/3/4 三个可独立存活件 + 文档。
   （数字不写在这里：`AGENT_OS_ROOT=$PWD ./bin/aos doctor --json` 现取 `observations.hot`。
   2026-10-03 实测 11，其中 5 条是 10-01 的开发/验证轮（账本 §4 已注明不计）。
   且这条判据的"owner 的交互会话"那一半今天**不可机器判定**（缺陷 AR）⇒ 交出去的读数一律是
   "上界 / 可证下界"两个数，见 `docs/experiment/stage-1-usage-ledger.md §4bis`。
   这条判据存在的唯一理由就是防止再次出现"表格在长、能力没长"。）
2. **人门成本判据**：`review` 队列的周均待标注数 > 50，或连续两周标注数为 0 ⇒ 说明"人门是主路径"
   在这个工作流里不成立 ⇒ 把主路径改成"回读 + 测试退出码"，人门退回只处理 `conflict/create`。
   （研究里 okdk 的 24h 冷却与 autolearn 的日配额就是这个信号触发的产物，`R-004`。）
3. **非干扰判据**：任何能力若必须写 `~/.config/opencode/**`、或必须编辑他人写入的 `output.system` 元素才能生效
   ⇒ **该能力直接放弃**，不讨论收益。这条优先级高于 1、2。
4. **重复判据**：新增模块前必须在 `docs/research/open-source-capability-matrix.md` 里指到一列"无人实现"；
   若指到的是"已有更成熟实现"（skill 生命周期、遥测、检索），则该需求转为**只读适配**或直接不做。

---

## 7. 交给 Stage 3 的输入

- 归类预判见张力 6 的表；`REMOVE/MERGE` 必须真出现在 final plan 里（`rules.json` 词汇换血、`intent_role_map`、
  `skill_versions`、`aos/core/sensing/`、两个预留 review kind、`aos skill report` 的自建采集、`performance` 类装饰项）。
- MVP 定义：一条**人敲得动**的演示链（`preflight` → 无 verdict postflight → `review list` → `label failure` →
  提案晋升 → 下次 preflight 看到"不要…因为…"），且必须先解决 `R-003` 的提案身份稳定化（同任务重复失败堆 N 条评审，实演已见）。
- Phase 4 开工门需逐条重校（`audit §3` 的必需项：`pending.py`、`doctor --json`、三个守卫测试、契约校验恒真两处）。
- 待用户决定：`--team` 命名（**若张力 6 的 REMOVE 成立则此问自动消失**）、`policy_versions` 进不进、
  `R-005` 的 `verify:` 执行面（默认关）、历史回读开关的默认值（默认关）、真实装载验证何时批准（当前约定：全程 fixture）。
