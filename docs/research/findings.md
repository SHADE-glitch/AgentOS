# 四个开源项目能力研究 · findings

研究日期 2026-09-30。对象：`ericmjl/agent-autolearn`、`Svtter/opencode-self-improve`、
`okdk7788/opencode-self-improving-skills`、`asphyksia/opencore`，外加本机已在运行的
四个注入/采集组件作为第五基线，以及 Agent OS 自身现状。

**这一轮不做定位决策。** 结论允许（并且确实）包含「Agent OS 现有某一环不该存在」。

---

## 0. 怎么读这份文档

### 0.1 标签

| 标签 | 含义 |
|---|---|
| `[Verified]` | 源码或本机文件可直接读到，带 `path:line` |
| `[Verified·一手]` | 我在本次会话中亲自打开该文件核对过该行 |
| `[Verified·代理读源]` | 由我派出的读源代理逐行摘录，引用为原文；承重结论我另做了一手复核，未复核的在此标注 |
| `[Inferred]` | 由结构、命名或调用关系推得，无直接断言 |
| `[Judgment]` | 我的判断，可以被争论 |
| `[Unconfirmed]` | 需要安装/运行/外部仓库才能确认，本轮明确没做 |

四个项目共 102/32/7/48 个文件，全部只读下载后静态阅读；**没有 install、没有运行、没有执行任何脚本**。

### 0.2 血统规则（这条规则会削减可借鉴清单，所以先说）

「多个项目独立采用同一机制」是本研究唯一承认的强度证据。但**仓库数量 ≠ 独立次数**，必须按血统计数：

| 项目 | 自述来源 | 引用 |
|---|---|---|
| svtter | 「brings **Hermes Agent** (NousResearch/hermes-agent)-style self-improvement capabilities to OpenCode」 | `svtter/README.md:3`、`svtter/package.json:4`、差异表 `svtter/README.md:120-128` `[Verified·一手]` |
| okdk | 「**Hermes-style** self-improvement loop — the opencode port of `UniM0cha/claude-self-improving-skills` + `okdk7788/skill-evolution`」；「Modeled on Nous Research's Hermes Agent」 | `okdk/README.md:3`、`:5`、`:137`、`:139` `[Verified·一手]` |
| autolearn | 不提 Hermes，反而与它对立：「**Hermes** uses a separate LLM call … Our reviewer IS the LLM」；自述来源是 Schema harness、WikiSkill(arXiv)、AgentMemory | `autolearn/docs/designs/session-search/LLD.md:28`、`docs/high-level-design.md:17-26`、`scripts/wiki.py:5-7` `[Verified·代理读源]` |
| opencore | 记忆整合「**OpenClaw-inspired** dreaming」 | `opencore/README.md:28` `[Verified·一手]` |

⇒ **svtter 与 okdk 是同一个上游想法（Hermes）的两次落地**（一次直译、一次经两个 Claude Code 端转口）。
它们共同具备的东西（markdown 文件当 skill、rubric 打分、curator 修剪、system prompt 注入）**只算 1 次采用**，
不是 2 次。真正达到「≥2 血统」的东西必须同时出现在 {svtter 或 okdk} 与 {autolearn, opencore} 之中。

### 0.3 一句话结论（细节见 Q1–Q10）

四个项目里**只有一个实现了确定性成败判定**（autolearn 的 `falsify.py`）。其余三个：svtter 明确承认它的
"subagent" 是占位桩，okdk 的证据探针对着错误的字段类型写、永不触发，opencore 全系统没有任何 verdict。
⇒ 「从真实执行结果产生经验」这件事，在四个项目里 3 次失败、1 次成功。Agent OS 现有的 `outcome.py`
（把置信度定义为**信号覆盖率**而非同意度，无信号即 `needs_review`）属于那 1 次成功之外的第二条路，
且它解决的正是三个失败样本共同的失效模式：**证据通道静默失效，系统照常写入"成功"**。

---

## Q1 成败判断：各项目怎么得到"这次任务成没成"

### svtter —— 没有 verdict，且自己承认
`svtter/src/subagent-runner.ts:13-17` 的注释原文：*「Stub subagent runner. In a real implementation this would spawn a background LLM call to analyse conversations. For now it uses heuristics」*。
实际判据在 `:22-32`：消息必须是 `role === 'assistant'`、`content.length ≥ 50`、
`/\n\d+\.\s/.test(content)`（有编号步骤）**且** `content.includes('```')`（有代码块）——满足就"提取为一个 pattern"。
配置项 `model: 'haiku'|'sonnet'|'opus'`（`src/config/schema.ts:5,14`）**在代码里从没被读取**。
`[Verified·一手]`

⇒ 判据是**回答的排版形状**，与"事情是否办成"零相关。`[Judgment]` 这正是 Agent OS 上一轮删掉的东西：
`evaluate.compute_quality_score` 给 markdown 标题、bullet、中文虚词加分，被降级为权重 `0.00`
（`AgentOS/aos/core/memory/policy.py:88`、`aos/core/memory/evaluate.py:10-19`）。

### okdk —— 名义上有证据通道，实际两个探针都打不到
`okdk/index.ts:937` 读 `client.session.messages({limit:30})`，然后：
```
const err = p?.error || p?.metadata?.error        // index.ts:941
if (p?.state === "error") { … }                    // index.ts:944-945
```
而本机 SDK 的真实形状是 `ToolPart.state: ToolState`，错误在 **`state.error`**、判据是 **`state.status === "error"`**
（`@opencode-ai/sdk/dist/gen/types.gen.d.ts` 的 `ToolPart` / `ToolStateError` / `ToolStateCompleted`）`[Verified·一手]`。
⇒ `p.error` 恒 undefined（那是 `state` 上的字段），`p.state` 是**对象**，与字符串 `"error"` 比较恒 false。
两条探针都不可能触发。于是唯一活着的信号退化为 `:947-949` 的 `looksLikeCorrection(text)` —— 三个正则嗅探用户是否改口。
**且它不会报错，只会永远记成 `ok`。** `[Verified·一手]`

### opencore —— 根本没有这个概念
唯一处在能看见结果的位置上的 hook 是 `skill-telemetry.ts:186-193` 的 `tool.execute.after`，
它从 `output.title` 里正则抠出 skill 名（`:156-160`）然后 `bumpUsage(…, "use_count", …)`，
**从不检查 `output` 的状态或错误**。整个插件目录里 `output.output|exit|isError|state.status` 的匹配只有这几行 title 读取 `[Verified·一手]`。
它记录的是 LLM 自报的 `importance: 0.0-1.0`（`memory.ts:234`）和 `source: manual|auto-extract`；
最接近"判定"的是 mem0 式冗余裁决 `ADD|UPDATE|DELETE|SKIP`（`memory.ts:163`）—— 判的是**文本重不重复**，不是**事情成没成**。
`session.idle` 无论结果都会触发写入（`memory.ts:390`）。`[Verified·一手]`

### autolearn —— 唯一真做了确定性判定的那个
三层，且分工清楚：

1. **ground-truth strength 阶梯**（`scripts/outcomes.py:110-133`）`[Verified·一手]`
   `4 = 测试命令 | 3 = 退出码 | 2 = 用户纠正 | 1 = 原始工具输出 | 0 = 无`。
   两处细节值得抄：
   - `2 correction` **显式标注 RESERVED 且从不赋值**，函数注释解释原因：把工具调用关联到其后的用户纠正需要文本窗口化，这个索引不做，所以"本函数封顶 3"。
   - `if tool == "skill": return 0  # a skill load is linkage, not an outcome` —— **加载过 skill 不等于 skill 起作用**。
2. **确定性证伪**（`scripts/falsify.py:150-178`）`[Verified·一手]`
   优先跑 skill 自带的 `verify:` 声明块，否则跑 `scripts/test_*.py`；
   pytest 退出码 `0=pass / 1=fail / ≥2=inconclusive`，声明命令比对 `expect_exit`；
   超时与 OSError ⇒ **inconclusive，而不是 fail**。
3. **后果**（`scripts/falsify.py:293-328`）`[Verified·一手]`
   连续 `fail_count ≥ falsify_fail_demote_after`（默认 1）→ skill `state="stale"`；
   **pinned 只标记不降级**；不在 `.usage.json` 里的 skill 只报告不接管；
   函数 docstring 明写「nothing here acts on weak evidence」「demote never deletes」。
   递归防护用 `AUTOLEARN_REVIEWER=1` 在每个 shell 早退（`plugin/autolearn.js:23`）。

### 本机基线（skill-tracker.js，正在运行）—— "乐观写、只可向下修正"
`~/.config/opencode/plugin/skill-tracker.js:278-300` 的 UPSERT：`tool.execute.after` 先乐观写 `success`，
事件通道观察到的 `error` **可以**把 success 改成 error，反向永不允许（代码注释原文：
*「A genuine error observed on the event path may correct a success that tool.execute.after optimistically wrote.
The reverse never happens: success cannot downgrade a recorded error/denied.»*）`[Verified·一手]`。
幂等键是 `UNIQUE(session_id, call_id)`（`:133`），`status` 有 CHECK 枚举 `success|error|denied|ask|unknown`（`:128`），
聚合用 `SUM(status='success')`（`:204,:229,:255`）。

### Agent OS 现状
`aos/core/outcome.py`：`mass = Σ 实际到场信号的权重`（`:256`）→ `confidence = min(1, mass)`（`:262`）→
`mass < min_verdict_mass(0.45)` 时**加权平均无权命名结论**，落 `no_signal_outcome="partial"`（`:268,:274`）→
`needs_review = confidence < min_auto_confidence(0.60)`（`:311`）。host 显式 `outcome` 是决定性的、跳过合成。
`response_summary` 被读但权重 `0.00`（`policy.py:88`）。

### 共同点与结论
1. **没有任何项目能从 opencode 拿到 verdict。** 四个项目 + 本机插件全部走"合成"路线：工具错误计数、
   退出码、diff 规模、用户措辞、或干脆不判。这与本机 SDK 事实一致：`Hooks` 类型里**没有返回成败的钩子**，
   只有 20 个钩子键与一个 `event` 通道（`@opencode-ai/plugin/dist/index.d.ts`，见 Q9）。
2. 判据可信度排序（`[Judgment]`）：**真跑声明命令 > 测试退出码 > 工具错误计数 > 用户措辞正则 > 回答排版形状**。
   四个项目分别停在第 2、3、4、5 档：autolearn 到第 2/1 档；本机 skill-tracker 到第 3 档；
   okdk 名义第 3 实际第 4；svtter 在第 5；opencore 不判。
3. **"由 Evidence 驱动"在其他项目里怎么落实**：只有 autolearn 落成了代码 —— 证据不是"我观察到一次失败"，
   而是"**我有一条 skill 自带的、可执行、可失败的 verify 命令**"。其余项目把 evidence 实现成了计数器。
4. `inconclusive` 这一档只有 autolearn 有。Agent OS 目前把"部分成功"和"不知道"都塞进 `partial`
   （`outcome.py:274`），这是一个真实的信息损失：`review label` 的 `partial` 与"零信号"在观测上不可区分。
   → 见 `R-001`。
5. `[Judgment]` 三个失败样本的共性不是"想法差"，而是**探针写错了对端形状后静默退化**。
   这给 Agent OS 的不是想法，是一条纪律：**每个信号必须能自证在场** ——
   `outcome.synthesize` 已经在返回 `present/absent` 清单（`outcome.py` 返回值），
   但没有任何断言检查"某信号长期缺席"是否本身就该报警。

---

## Q2 经验去向：Observation 与 Experience 有没有必要分层

| 项目 | 是否分层 | 证据 |
|---|---|---|
| autolearn | **是，且分三层**：`observations.jsonl`（事件日志，`plugin/autolearn-core.mjs:466-479`，裁剪到 1000 行）/ `tool_outcome` 索引（`outcomes.db`，`outcomes.py:156-190`）/ `memories.jsonl`（经验，`registry.py:115-140`） | `[Verified·代理读源]` |
| svtter | 否。conversation → 直接 `skills` 表；`skill_usage_log` 表存在但**无写入者**（`incrementUsage`/`logUsage` 零调用方，`src/skill-store.ts:86,115`） | `[Verified·一手]` |
| okdk | 半：`skill_outcomes.json`（ok/fail/fail_signals）与 SKILL.md 正文分离；但 distillation 的输入不是 outcome | `[Verified·代理读源]` |
| opencore | **是，两层**：`facts` 表（可检索）与 `MEMORY.md`（人读导出）。但代码注释明确「the DB remains the source of truth」（`lib/memory-store.ts:480-484`），注入用 `topConsolidated()` 从 DB 取；`README.md:28` 的措辞会让人以为 `MEMORY.md` 是回路一环 | `[Verified·一手]` |

**观察事实：分层的项目都有"原始事件 append-only + 派生态可重算"这个结构；不分层的项目出现了死字段。**
`skill_usage_log`（svtter，无写入者）、`view_count`（opencore，声明于 `skill-telemetry.ts:41`、
`bumpUsage` 支持但只在 `:193` 传 `"use_count"`，`:212/:221/:252` 只读展示）`[Verified·一手]`、
autolearn 的 `topics.jsonl`（`shift.record_sightings` 无生产调用方 ⇒ 人门"Remember it"实际是死的）都是同一件事。

⇒ `[Judgment]` 分层是必要的，但**必要条件是"派生态能被重算"**，不是"多存一份"。
Agent OS 现状已具备该结构：`observations`（append-only）+ `retrieval_log`（append-only）+ `memories.observation_count`（派生，由 `set_observation_count` 维护）。
缺口是 `retrieval_log` 目前**写而不读**（三个 Phase 前的旧账）—— 这恰好是把 `use_count` 改成派生的前提，见 `R-002`。

**一条经验何时进入 memory / skill / policy / 丢弃：**
- autolearn：跨 ≥3 会话复发（`proposer.py:31-35,139-146`，0.5 overlap 系数聚类）→ proposal；
  **只有 `common_resolution` 证伪为 `pass` 才自动晋升**（`proposer.py:302-330`）→ 生成的 skill 携带 `verify:` 块（`autolearn.py:428-499`）；
  行为规则走另一条：重复计数 → `improve.py:304-325` 决策树 → 写进 `AGENTS.md`（见 Q8）。
- svtter/okdk：判据是"格式/自我叙述"，不是复发。
- opencore：LLM 自报 `importance` + 每 5 轮节流 + transcript hash 去重（`memory.ts:36,194-210`）。

`[Judgment]` 只有 autolearn 的"复发 + 可证伪"值得作为经验准入条件；其余三种准入都能被一次排版良好的错误回答满足。

---

## Q3 Skill 生命周期：创建 / 更新 / 删除；"高频但差"与"低频但重要"

| 阶段 | svtter | okdk | opencore | autolearn | 本机基线 |
|---|---|---|---|---|---|
| 创建 | 格式启发（`subagent-runner.ts:22-32`）+ `autoCreate`（`skill-forge.ts:41`），**无人在环** | agent 自愿调 `distill_skill`，判据 100% 是模型自述（`index.ts:577-606`） | LLM 自报 importance（`memory.ts:234`） | 跨会话复发 + **证伪通过才自动晋升**（`proposer.py:302-330`） | 不创建 skill，只登记（registry `status/last_seen`） |
| 打分 | 4 维启发式 rubric 0–1（`rubric-scorer.ts:39-97`），证据是 skill 自身文本 | 无（`JUDGE` 评分是交给模型的 rubric，代码里不存在打分） | 无质量分，只有 importance | **无 LLM 分**，只有 `use_count/patch_count` + 证伪 verdict | 无 |
| 修剪 | 删除 `<0.5`（`curator.ts:55`）；合并 ≥0.85 相似（`:76-79`）；**`use_count` 完全不参与** | `archived` 只在人删目录后由 `forgetMissingUsage`（`index.ts:242-260`）标记；插件永不删 | `unused_days` 只列清单（`skill-telemetry.ts:227-241`），无动作 | 30 天→stale、90 天→archived（`autolearn.py:1100-1143`）、60 天零使用清理（`:503-542`）、pinned/非 autolearn 创建者豁免 | `status: active` + `last_seen`（`skill-stats-registry.json`） |
| 版本/回滚 | `version` 整数自增，**内容原地覆盖** | 轮转备份 ≤10（`index.ts:467`），仅用于格式非法回滚，**无法回滚一次合法退步** | 无 | 归档用 rename 进 `.archive/`，从不 delete | n/a |

**"使用次数高 ≠ 质量高"处理得怎样：**
- svtter：`use_count` 进入**注入排序**（`skill-injector.ts:30-44` 里 `min(usage/10, 0.1)` 一项），但**不进修剪** ⇒ 高频低质会被删，低频关键不受保护也不被提升。`[Verified·一手]`
- okdk：`priority = use*(fail+1)/(total+2)`（`index.ts:359`）—— 用频次当**爆炸半径权重**（高频且失败优先处理），这个方向是对的；但 `use<2` 直接排除候选（`:350`），**低频关键 skill 永远不进改进队列**。`[Verified·代理读源]`
- autolearn：把"加载"与"结果"分开（`gt=0 for tool='skill'`），频次只用于生命周期时间线，不用来证明质量。`[Verified·一手]`

**结论 `[Judgment]`**：五个实现里没有一个同时做到"高频低效要降级"和"低频关键要保留"。
最接近可用的是 autolearn 的两条正交设计：**(a) 时间/使用只管可见性与退役，(b) 证伪结果只管降级**；
以及 okdk 的 `use*(fail+1)/(total+2)` 排序思路（作为"改进优先级"而非"质量分"）。
Agent OS 现在的 `evidence_level`（6 档，只由验证升）+ `decay_factor`/`use_count`（由使用降）已经是这个正交结构，
所以这一项**不需要借鉴，需要的是把 Phase 3.4 的归属记账按"派生不来自增"实现**（`R-002`）。

---

## Q4 质量与漂移：去重、合并、修剪、冲突、过期、防无限漂移

### 去重/合并/冲突：四种实现，只有一种是可判定的
| 项目 | 去重机制 | 判定性 |
|---|---|---|
| svtter | SQL `LIKE '%triggers[0]%' OR LIKE '%name%' LIMIT 3`（`skill-store.ts:106-113`）；命中即**覆盖首个匹配并把 version+1**（`:90-104`）| 极弱；last-write-wins，无冲突概念 `[Verified·一手]` |
| okdk | **无算法**，只有 prompt 里让模型"先查碰撞"（`index.ts:583`；`skills/skill-distiller/SKILL.md:35`）；`absorbed_into` 字段存在（`:179`）但只被写成字面量 `"(deleted)"`（`:253`） | 无 `[Verified·代理读源]` |
| opencore | LLM 四值裁决 `ADD|UPDATE|DELETE|SKIP`（`memory.ts:144-187`），解析失败**fail open 到 ADD**（`:175,178,181`） | 每次写多一次 LLM 成本；且"失败即新增"正是漂移源 `[Verified·代理读源]` |
| autolearn | 名字/slug 相等判重（`registry.py:189`；promote 时存在即跳过 `:446`）；矛盾检测借用 AgentMemory 的 Jaccard（`docs/designs/memory-insight/LLD.md:191`）；**合并/整合是 prompt-only**（`references/curator.md:60-72`，无代码） | 部分 `[Verified·代理读源]` |

⇒ **没有任何一个项目实现了"同一事实不同表述"的可靠去重。**
这正是 Agent OS 的 Phase 3.3（fact-key 规范化 + `difflib.SequenceMatcher` + Jaccard 三层）**尚未开工**的那一项。
研究结论：这一项**无外部可抄，只能自研**；反面证据是四种弱实现各产生一种污染模式（覆盖、跳过、fail-open、只查名字）。

### 过期：只有两处真的有
1. autolearn 记忆层：`retention = min(1, salience·e^(−0.03·age_days) + 0.3·Σ1/d_days)`，
   分 tier `hot≥0.7/warm≥0.4/cold≥0.15/evictable`，**淘汰要求 evictable 且距上次强化 ≥90 天，且只改 status 不删**（`scripts/retention.py:58-132`）。`[Verified·代理读源]`
2. autolearn skill 层：30/90 天 + 60 天零使用宽限（`autolearn.py:1100-1143,:503-542`）。
3. okdk：24h 进化冷却（`index.ts:348`）。
svtter 靠 `setInterval(intervalDays)`（`index.ts:40`）——**进程内计时器，不持久化**，进程不活满 7 天就永不触发 `[Verified·一手]`；
opencore 无 TTL，且**删掉的文件不会从索引清除**（`codebase.ts:53-55` 只在 `chunkFile` 返回空时处理）`[Verified·代理读源]`。

### 防无限漂移：唯一成体系的是 autolearn
- 三层节流：内容哈希去重（只对 `## Conversation` 切片）+ `min_interval_ms=180000` + `max_reviews_per_day=60`（`plugin/autolearn-core.mjs:581-647`）；
- 生成一个**自重写、每次加载重写成只读 0o544** 的 shell wrapper，wrapper 内部再跑一遍同样的门 + `mkdir` 原子单飞锁（15 分钟过期回收），并且**在运行前就记录开始时间**（`:219-392,:301-335,:379-392`）；
- curator 独立 gate + 1h 机器级冷却（`:658-714`）；
- reviewer agent 被 `steps: 20` 限步、`edit: deny`（`install.sh:145-163`）；
- 递归：`AUTOLEARN_REVIEWER=1` 早退 + `Symbol.for` 目录级 primary guard（`autolearn.js:23,38-40`）。
okdk 有阈值/冷却/证据下限（`index.ts:337-376`）但**无速率限制、无写配额**，且 `logs/plugin-debug.log` 无界追加（`:793-799,821-831`）。
svtter / opencore **没有任何反漂移门**：opencore 的 `DELETE` 静默销毁事实（`memory.ts:271-273`），无审批、无回滚、无冷却 `[Verified·代理读源]`。

`[Judgment]` autolearn 的"每一层都自己再判一次，且闸门文件不可被旧实例回滚"是三家里唯一考虑了**攻击者是自己进程**的设计。
Agent OS 的对应物目前只有：`_can_auto_promote`（`evolve.py:504-522`：create/weaken 永不自动）、
`max_promotions` 每轮节流（`evolve.py:601-632`）、`apply_effect` 的 compare-and-set 拒绝（`evolve.py:407,470`）。
**缺的是速率与配额**（没有"每小时最多写多少条记忆"这类闸门）。

---

## Q5 共同的 Evaluation 原则（抽原则，不抄评分表）

各家的评分维度：

| 项目 | 维度 | 权重 | 证据来源 |
|---|---|---|---|
| svtter | accuracy / completeness / actionability / uniqueness → overall | 0.3/0.25/0.25/0.2（`config/loader.ts:37-42`；`rubric-scorer.ts:39`） | skill 自身文本的字符串特征 |
| okdk | `failure_coverage` 等 0–5 rubric | 交给模型 | **模型自评**，无打分代码 |
| opencore | `importance` 0–1 单值 + `access_count` | 无 | 模型自报 + 检索频次 |
| autolearn | 不用分数；用 `pass/fail/inconclusive` + `gt_strength` + 复发计数 | — | 可执行命令 + 索引 |

**归纳出四条共同原则 `[Judgment]`（每条都能在上面找到至少两次独立落地）：**

1. **准确性/可执行性优先于完整性。** svtter 的四维里有两维（actionability、accuracy）实际在问"它说清了怎么做吗"；
   autolearn 干脆把它变成"`verify:` 命令跑得绿吗"。凡是用文本形状代替可执行性检验的，都在 svtter 那一档退化。
2. **独特性/覆盖必须显式判。** svtter 把 uniqueness 做成一维；okdk/opencore 用"写入前先比对已有条目"实现同一意图
   （`SKILL.md:35` 的"先查碰撞"、`memory.ts:163` 的 `SKIP`）。⇒ **判重在 Evaluation 里是必要维度，不是 dedup 的附加品。**
3. **分数必须由独立证据锚定，否则只配决定"要不要处理"，不配决定"能不能生效"。**
   autolearn 的分数（无 LLM 分）与 okdk 的 priority 分别是从两端印证这条的：
   okdk 用频次+失败数排序**候选**（不动生效与否），autolearn 用证伪决定**降级**。
4. **置信度要能被下游读到。** 只有 autolearn 把它做成了字段（`gt_strength`，`tool_outcome.gt_strength`）；
   其余项目把置信度隐含在阈值里，于是"低置信"与"零证据"不可区分。
   Agent OS 已用 `confidence`（覆盖率）+ `needs_review` + `present/absent` 落地，且比 autolearn 更细，
   但**同样不可区分的**是 inconclusive —— 见 `R-001`。

⇒ **不建议照抄任何一家的评分体系。** `[Judgment]` 数值权重是各家自调的产物，
唯一可迁移的是这四条原则与"维度必须能被代码或命令验证"的要求。

---

## Q6 注入：机制、预算、时机，以及与 basic-memory / DCP / Agent OS 的相互干扰

### 6.1 各项目的注入手段

| 项目 | 手段 | 预算 | 时机 | 一手/代理 |
|---|---|---|---|---|
| **Agent OS（未装）** | `experimental.chat.system.transform`，push 新元素，唯一标签 `<agent_os>` 幂等替换 | `max_chars=1400`、`max_items=6`、`max_body_chars=280`、`hypothesis_max_items=1`（`policy.py:63-71`，裁剪在 `inject.py:149-172`） | 每次 preflight | `[Verified·一手]` |
| svtter | 同一钩子，`output.system.push(injected.slice(context.length).trim())`（`index.ts:49-56`）—— 只推 delta | **top-3 条**，无字符预算；正文在创建时截 500 字符（`subagent-runner.ts:59`） | 每次 LLM 调用 | `[Verified·一手]` |
| okdk | 两个通道：同一 system 钩子推**一整块** evergreen 韩文文本（`index.ts:672-744`，无 item/字符预算、无相关性排序，每轮同文）；**外加合成一条 `role:"user"` 消息**（`experimental.chat.messages.transform`，`:749-787`，`synthetic: true`） | 无 | 每轮 | `[Verified·一手]` |
| autolearn | **不用钩子**：改写 `~/.config/opencode/opencode.json` 的 `instructions` 数组，指向生成的 `memory.context.md`（`plugin/autolearn-core.mjs:418-449` + `install.sh:108-127`，`writeFileSync` 整份重写） | 3000 字符 compose 预算，pinned 可超（`composer.py:67-77`） | 插件加载时 fire-and-forget 重新生成 | `[Verified·一手]` |
| opencore | 同一 system 钩子推一行 `[opencore mem] type:text | …`（`memory.ts:410-415`），**并在 `experimental.session.compacting` 里把它塞进 `output.context`，让它在压缩后存活**（`:419-426`） | 5 条常显（`memory.ts:54`）vs 整合取 8（`memory-store.ts:453`）**两处不一致**；无字符/无 token 预算 | 每轮 + 压缩时 | `[Verified·代理读源]` |
| 本机 DCP 3.2.0 | `output.system[length-1] += "\n\n" + newPrompt`（`lib/hooks.ts:101-105`），空数组时才 push | 按 `input.model.limit.context` 与 tokenizer 计 token | 每轮 | `[Verified·一手]` |

### 6.2 干扰判定（这是本轮唯一能拿本机实文件验证的部分）

事实：`~/.config/opencode/opencode.json` 里 `plugin: ["@tarquinen/opencode-dcp@3.2.0", "@mohak34/opencode-notifier@0.4.0", "opencode-conductor-plugin"]`，
`~/.config/opencode/plugin/skill-tracker.js`（软链，正在跑），`mcp.basic-memory.enabled: **true**`
（`command: ["uvx","basic-memory","mcp"]`，`BASIC_MEMORY_HOME=/home/shade/Documents/01-Learning/opencode-memory`）。
`[Verified·一手]`

⇒ **与已批准的重构计划 §十一冲突**：那里记的是 `"enabled": false`（原文第 681 行），今天不是。
"边界几乎零成本"的前提已不成立。

具体干扰点（按严重度）：

1. **DCP 追加到数组最后一个元素。** 若 Agent OS 的块先落进 `output.system`，它就成了最后一个元素，
   DCP 随后把它的运行时提示**拼进同一条字符串**（`lib/hooks.ts:101`）。后果：
   (a) 我们的 `<agent_os>…</agent_os>` 与 DCP 的裁剪提示在同一条 message 里，我们的"幂等替换整块"策略
   在下一轮无法按元素定位；(b) 谁先执行取决于插件加载顺序，本轮无法静态确定 `[Unconfirmed]`
   （要确认只需在 `system.transform` 里打印顺序跑一次）。
   ⇒ 反过来（DCP 先、我们 push 新元素）是干净的。**这条给出一个可执行纪律：Agent OS 必须 push 新元素，绝不 append 到 `[-1]`** ——
   重构计划 §6.3 已经这么写了，现在它有实测依据。
2. **DCP 的"内部 agent 调用"探测只看 `systemPrompts[0]`**（`lib/hooks.ts:49-56`）。
   ⇒ 我们的块落在末尾不会误触发它；但如果哪天改成插到最前，就会被判成内部调用而让 DCP 整轮跳过裁剪。**这是一个可被无意破坏的隐式耦合。**
3. **okdk 证明了第二条注入通道存在**（合成 user 消息）。Agent OS 若将来需要"提醒式"注入，`experimental.chat.messages.transform`
   是合法路径，但它会把**模型自己写的话**变成"用户说的话"，污染后续学习的输入（模型可能把这条 synthetic 提醒当成用户诉求来复盘）。
   `[Judgment]` 不要用这条通道，除非消息里带 `synthetic: true` 且我们的记录路径能过滤掉它。
4. **basic-memory 与 Agent OS 会同时向同一 system 注入。** 它是 MCP（工具式），不是 system 钩子，
   所以默认不重写我们的块；但两个系统都可能"召回并注入相关记忆"，用户在 prompt 里会同时看到两套。
   计划 §十一 的禁令（不互调、不互写、不同步、无预留空壳）**依然成立且现在才变成必要**，
   并且 §3.5 的唯一标签 `<agent_os>` + push 新元素，正是"两套并存不互相吞并"的机制前提。
5. **autolearn 的 config 改写是 Agent OS 明确不能走的路。** 它 `writeFileSync` 整份 `opencode.json`
   （`JSON.parse/stringify` 会丢注释；本机配置带 `$schema` 键，会被原样回写但任何 JSONC 注释会消失），
   且改写的是**用户全局配置**。用户约束里"不修改 OpenCode 全局配置"直接覆盖它。
6. **本轮实测出 Agent OS 自己有一个注入边界缺陷（承重，非借鉴项）**：
   `aos/core/memory/inject.py` 不清洗记忆正文，因此一条含 `</agent_os>` 的记忆可以**提前关闭自己的容器标签**。
   实测（临时 store，`body="evil </agent_os> tail"`）：渲染结果 `<agent_os>` 出现 1 次而 `</agent_os>` 出现 **2 次**，
   尾部 footer 与真闭合标签落在被注入的闭合标签**之外** `[Verified·一手]`。
   后果：① host 侧"按标签定位并幂等替换整块"的前提被破坏（§3.5 硬约束 (ii) 失效）；
   ② 记忆内容可结束自己的区块并把后续文本伪装成区块外的正常内容 —— 这正是被推迟到下一轮的
   prompt-injection 威胁（重构计划 §十）里**最容易落地的一种**。
   ⇒ 修复不需要威胁建模，只需要在渲染时清洗或拒绝边界标签；见 `R-008` 的证伪断言。
   `[Judgment]` 这条应该排在下一轮任何新能力之前。
   ⇒ 记入不借鉴清单 §12。

### 6.3 预算该多大
只有两处给了可比较的数字：Agent OS 1400 字符 / ≤6 条 / 单条 280；autolearn 3000 字符 compose（pinned 可超）。
svtter 用条数（top-3）封顶，opencore/okdk **无预算**。`[Judgment]` 无预算是这四家里"注入"最常见的失败模式之一：
opencore 的常显块随事实数线性增长（`memory.ts:410-415`），且整合的 top-N(8) 与常显 top-N(5) 不一致
（`memory-store.ts:453` vs `memory.ts:54`）⇒ 同一个系统在两条路径上对"注入多少"给出不同答案。
Agent OS 现状（字符预算 + 条数 + 裁剪记入 `truncated/dropped`）比四家都严；**不需要借鉴，需要保持**。

---

## Q7 遥测：数据如何变成进化证据

| 项目 | 遥测采什么 | 是否改变行为 |
|---|---|---|
| opencore | `use_count`、`view_count`（**声明 `:41`、支持 `:116`、只传 use_count `:193` ⇒ 永远 0，但 `:212/:221/:252` 会展示**）、`last_used_at`、`last_viewed_at` | **完全不改**。唯一消费者是 `skill_stats` 工具，返回文本摘要 + `unused_days` 清单（`:215-255`）。**遥测是惰性的。** `[Verified·一手]` |
| svtter | `skill_usage_log` 表 + `incrementUsage`/`logUsage` | **调用者为 0** ⇒ 表永远空；`use_count` 只进注入排序、不进修剪（Q3） `[Verified·一手]` |
| okdk | `skill_outcomes.json{ok,fail,fail_signals,sessions}` | **改**：决定 `[진화 후보]` 提醒与 `optimize_skill` 排序（`index.ts:337-376,1124`）。但见 Q1 —— 它的 fail 信号来自三个正则而非工具状态，因此实际只在用户改口时触发 `[Verified·一手]` |
| autolearn | `tool_outcome`（每条 tool part 一行，含 `gt_strength`）+ `step_cost` | **改，且改得最克制**：`use_count` 从索引 `GROUP BY` 派生（`outcomes.py:390-414`）再 `repair` 回 `.usage.json`（`autolearn.py:272-348`）；证伪失败才降级（Q1） `[Verified·一手]` |
| 本机基线 | `skill_usage`（含 `status ∈ success|error|denied|ask|unknown`、`trigger_type`、`duration_ms`、`session_id`、`project_path`、`metadata.model/agent/branch`）+ `mcp_usage`/`plugin_usage`/`plugin_inventory` | 目前到 **TUI/统计**（`skill-stats.py`、`skill-tui.py`）为止；状态单调修正使 success/error 计数可信，但**尚未反哺任何行为** `[Verified·一手]` |

**"某 MCP 零使用是修剪候选、某 skill 高频但反复失败是进化候选"** —— 用户提的这两种推断，在四个项目里：
- 前者：opencore 实现了**清单**（`unused_days`）但无动作；svtter 用 interval 删低分（与使用无关）。⇒ **无人做成闭环。**
- 后者：只有 okdk 形式上做了（`use*(fail+1)`），但它的 fail 是坏的（Q1）。

⇒ `[Judgment]` 遥测→证据的闭环**在这批代码里没有先例**，Agent OS 如果要做就是自己在开路。
但**闭环的前置件已被 autolearn 验证**：把每条遥测存成 append-only 事实（不是计数器），然后**派生**计数。
否则 `view_count` 这种事会一直发生。

---

## Q8 Human Approval：放在哪个环节、什么形式

| 项目 | 人门位置 | 形式 | 是否被代码强制 |
|---|---|---|---|
| autolearn | proposal → skill 晋升；memory 候选；淘汰 | Inspector（stdlib `ThreadingHTTPServer` 127.0.0.1:4321）只有两个写操作：`POST /api/memory/{id}/strengthen`、`POST /api/candidate/{id}/confirm|dismiss`（`inspector_server.py:229-258`）；CLI 侧 `proposals confirm/dismiss`、各命令 `--dry-run` | **自动晋升被证伪替代**（`proposer.py:302-330`），不是人；而"HARD GATE 必须先复发≥3"在 `cmd_skill_create` 里**没有调用 `is_recurrent`** —— 纯 prompt `[Verified·代理读源]` |
| svtter | 无 | 无 dry-run、无审批，`DELETE` 硬删 | 无 `[Verified·一手]` |
| okdk | 文档写"Never auto-commit / No data, no evolution"（`skills/optimize-skill/SKILL.md:86-91`） | 无 | **无强制**：插件没注册 `permission.ask`，格式合法的 edit 一律接受 `[Verified·一手]` |
| opencore | 无 | 无；`DELETE` 静默销毁 | 无 `[Verified·代理读源]` |
| Agent OS | `learning_reviews`：`promotion` / `outcome_label` 两类；`aos review list|label|approve|reject`；`apply_effect` 比对 `before` 失败即 `stale` 拒绝写 | CLI（`store.py:558,563`、`evolve.py:580,771,850`） | **是，代码强制**（`evolve.py:522` create/weaken 永不自动；`evolve.py:425,470` CAS） `[Verified·一手]` |

**结论 `[Judgment]`**：
1. 「人门写在 prompt 里、代码不强制」是这批项目最普遍的失效模式（okdk 最典型：它甚至在文档里写了纪律）。
   Agent OS 的 `review` 门是被代码强制的 —— 这是它相对整批样本的真实领先项，也是**不能因为"别人没有"就削弱**的项。
2. autolearn 给出的不是"要不要人门"，而是**人门的两种正确形态**：`--dry-run`（每个破坏性命令都有）
   与"确认/驳回"两个最小动词（Inspector 只有这两个写操作，其余全是只读）。
   ⇒ 值得借鉴的是**动词面极小**这件事，而不是 Inspector 这个 UI（它带 HTTP server，Agent OS 零依赖原则下不值得引入）。

---

## Q9 兼容性：这些项目依赖的 hook / API 在 opencode 1.18.33 上是否存在

权威来源不是任何 README，而是本机已安装的 SDK 类型（无需安装即可核对）`[Verified·一手]`：
`~/.config/opencode/node_modules/@opencode-ai/plugin/dist/index.d.ts`（`@opencode-ai/plugin@1.18.4`，被 `~/.config/opencode/package.json` 钉住）。

**`Hooks` 类型全部 20 个键：**
`chat.headers`、`chat.message`、`chat.params`、`command.execute.before`、`config`、`dispose`、`event`、
`experimental.chat.messages.transform`、`experimental.chat.system.transform`、`experimental.compaction.autocontinue`、
`experimental.provider.small_model`、`experimental.session.compacting`、`experimental.text.complete`、
`loader`、`models`、`permission.ask`、`shell.env`、`tool.definition`、`tool.execute.after`、`tool.execute.before`。

**事件名来自 `@opencode-ai/sdk` 的 `Event` 联合**，走单个 `event` 钩子（`index.d.ts:175`），包括：
`session.idle`、`session.diff`、`session.error`、`session.status`、`session.updated/created/deleted/compacted/…`、
`todo.updated`、`permission.replied`、`permission.updated`、`message.updated/removed`、`message.part.updated/removed`、`file.edited`、`installation.updated`、`server.connected` 等。

对 brief 的两处更正（重要）：
1. **`permission.replied` 是事件名，不是 hook 名**；钩子里存在的是 `permission.ask`（可改 `status: ask|deny|allow`）。
   已批准的重构计划 §1.5/§6.3 把它列进"钩子"清单，措辞要改。
2. **此前审计漏了一个可用注入面：`experimental.chat.messages.transform`**（改消息），
   以及 `chat.params` / `tool.definition` / `shell.env` / `config` / `models` / `loader` 六个从未在审计里出现过的钩子。

各项目的钩子需求核对：

| 项目 | 用到的钩子 | 在 1.18.33 上 |
|---|---|---|
| svtter | `experimental.chat.system.transform`、`tool.execute.after`、`tool` | 存在 `[Verified·一手]` |
| okdk | `experimental.chat.system.transform`、`experimental.chat.messages.transform`、`tool.execute.before/after`、`event` | 存在；但它**没注册 `permission.ask`**，所以其"人门"纪律无处落地 `[Verified·一手]` |
| opencore | `tool`、`event`、`experimental.chat.system.transform`、`experimental.session.compacting` | 存在 `[Verified·代理读源]` |
| autolearn v1 | 仅 `event`（`session.created`/`message.updated`/`message.part.updated`/`message.part.delta`/`session.idle`） | `message.part.delta` **不在本机 SDK 的事件联合里**（联合里有的是 `message.part.updated`）⇒ 该分支在 1.18.33 上可能永不触发 `[Inferred]`，需运行确认 `[Unconfirmed]` |
| autolearn v2 / pi | `ctx.event.subscribe` 上的 `session.step.started`、`session.text.ended`、`session.execution.succeeded\|failed\|interrupted`、`session.inbox.enqueued`；pi 的 `before_agent_start`/`agent_settled` | **这些是 opencode v2-beta / pi 的形状，不在 1.18.33 的 v1 钩子里** ⇒ 迁移成本主要落在这里 `[Verified·一手]` |
| 本机 skill-tracker | `tool.execute.before/after`、`permission.ask`、`command.execute.before`、`event`、`chat.message`、`chat.params`、`dispose` | 全部存在（它正在跑） `[Verified·一手]` |

**版本对齐风险**：opencore 钉 `opencode-ai` **1.17.11**、svtter 钉 `@opencode-ai/plugin ^1.14.19`（解析到 1.14.33），
本机是 **1.18.33 / plugin 1.18.4**。⇒ 它们对 payload 形状的假设（尤其 okdk 已证实在 `ToolPart` 上猜错）**不能默认在新版本上成立**。
`[Judgment]` Agent OS 若将来读这些事件，必须对本机 SDK 类型断言，而不是照抄某仓库的字段访问。

**插件导出契约（三家里两家踩坑）**：
- 本机 `skill-tracker.js:1791-1797` 的注释记录了**真实事故**：loader 会把模块里**每个**导出函数都当插件工厂调用，
  只有 default 是带 `server` 的对象时才停止；`export default skillTrackerPlugin`（裸函数）导致 `__selftest` 被当工厂调用、
  其隔离守卫抛错、**整个插件静默不加载、采集全停**。
- `okdk/index.ts:646,1251` 正是 `export const SelfImprovingSkills: Plugin = async …` + `export default SelfImprovingSkills` ⇒ 同形风险 `[Verified·一手]`；
  是否真的导致不加载属 `[Unconfirmed]`（需实际装载一次）。
- `autolearn` 三个 shell 三种形状：v1 `export const … + export default`（同样风险）、v2 `export default { id, async server… }` 形式（`autolearn-v2.js:38-40,306`）—— v2 是对的。
- SDK 侧契约：`PluginModule { id?, server: Plugin }`。⇒ **重构计划 §1.5 的硬规则得到第二方（本机事故）与第三方（v2 写法）印证，属高置信必守项。**

---

## Q10 本地可行性：回读 opencode 会话历史在本地 SQLite 上是否可行

**可行，但只对"部分证据"可行。** 以下全部是本机只读实测（`sqlite3 "file:…?mode=ro"`，未使用 `immutable=1`，因为存在活跃 WAL）：

`~/.local/share/opencode/opencode.db` = 1.7GB，21 张表：
`event`、`event_sequence`、`message`、`part`、`session`、`todo`、`project`、`project_directory`、`permission`、
`workspace`、`session_input`、`session_message`、`session_context_epoch`、`session_share`、`account*`、`credential`、
`migration`、`data_migration`、`__drizzle_migrations`。`[Verified·一手]`

计数与分布（只读聚合，无任何正文被读取）：

| 事实 | 数值 | 对 Agent OS 的意义 |
|---|---|---|
| `session` | 199 行，时间跨度 2026-07-23 → 09-30 | 历史足够长，能喂饱"复发≥3"这类判据 |
| `part` | 61,790 行；type 分布 `tool 16,374 / step-start 13,541 / step-finish 13,264 / reasoning 10,940 / text 6,517 / patch 1,109 / file 26 / compaction 14 / agent 5` | **tool part 与 patch part 都在**，diff 与工具错误可回读 |
| `part.state.status` | `completed 16,137 / error 235 / running 2` | `tool_errors` 信号**完全可以从历史反推**（这就是 okdk 想读而读错的那个字段） |
| `message` | 15,339 行 | 用户纠正/措辞类信号可读，但即受 Q1 里 okdk 的正则可靠性限制 |
| `todo` | 305 行，`status ∈ completed 263 / pending 27 / in_progress 14 / cancelled 1` | `todos_unfinished` 信号可回推 |
| `event` | 369,500 行，**只有 5 种 type**：`message.part.updated.1 (237,207)`、`message.updated.1 (99,994)`、`session.updated.1 (30,847)`、`session.created.1 (1,304)`、`message.removed.1 (148)` | **事件日志里没有 session.idle / session.error / session.diff / todo.updated** ⇒ 别指望从 event 表拿结果 |
| `session.summary_files > 0` | **只有 1 / 199** | brief 说"历史是现成的证据源"对 `summary_*` **基本不成立**；不能依赖会话摘要 |
| `session.cost > 0` | 5 / 199 | 同上，成本数据大面积缺失；预算类信号不可靠 |
| `session` 的 `agent`/`model` 去重数 | 8 / 18 | 归属维度可用（scope/agent/model） |

**先例（同一台机器上能用的正确做法，来自 autolearn）** `[Verified·一手]`：
- 只读 URI 连接：`sqlite3.connect(f"file:{db}?mode=ro", uri=True)`（`outcomes.py:219`）；
- **增量高水位用复合键** `(last_time, last_part_id)`，避免同一时间戳的 part 被跳过（`outcomes.py:196-213`）；
- **数据保护顺序**：先检查源库存在，**再**执行 `--full` 的清空 —— 注释原文
  「Hoist the source-DB check ABOVE any --full truncation so a missing/moved opencode.db can never wipe an existing index」（`outcomes.py:224-240`）；
- 索引进**自己的库**（`outcomes.db`、`search.db` 的 FTS5 external-content 表），从不写 opencode.db；
- 全文检索路径只取 `pdata.type == "text"`，增量条件 `p.time_created > ?`（`autolearn.py:1398-1425`）。

opencore 走的是另一条：完全不读 opencode.db，声明"维护自己的会话索引"（`lib/session-store.ts:8-10`），
数据全部来自 SDK `client.session.messages`（`session-search.ts:69`、`memory.ts:199`）`[Verified·代理读源]`。
⇒ `[Judgment]` 两条路都可行；SDK 路线不需要知道 opencode 的表结构（**版本耦合更弱**），SQLite 路线能拿到全量历史（**能力更强**）。
Agent OS 若回读，SDK 路线对"零依赖 + 契约稳定"更符合它的约束。

**okdk 的教训**：它的 GEPA 第一步要求模型调 `session_search` / `session_read`（`index.ts:611,980`；
`skills/optimize-skill/SKILL.md:27-30`、`skill-distiller/SKILL.md:19-20`），但**这两个工具在本插件里没注册**，
且在已安装的 opencode 里是否存在我也未能静态确认 `[Unconfirmed]`。
⇒ `[Judgment]` 给 agent 的提示词里出现的工具名，必须是已核实存在的；否则"证据驱动"的第一步直接落空。

---

## 11. 可以抽象成通用 Capability 的东西（按血统计数）

| 能力 | 独立血统数 | 证据 | 判断 |
|---|---|---|---|
| 事件型观察（append-only，一条事实一行）+ **派生**计数 | 2（autolearn `outcomes.py:390-414` + 本机 skill-tracker `:278-300` 的幂等 upsert；反面证据 3 家死字段） | `[Verified·一手]` | **通用**。这是本表里最强的一条 |
| 每轮向 `output.system` 注入一段自己负责的文本 | 4（svtter、okdk、opencore、本机 DCP） | `[Verified·一手]` | **通用**，且必须 push 新元素而非 append |
| 写入前判重（名字/相似/LLM 四值裁决都算） | 4 | `[Verified·一手]` | **通用需求，通用解法不存在**（见 Q4）→ Agent OS 自研 |
| 阈值化修剪（分数/时间/使用） | 3（svtter 分数、autolearn 时间+使用、okdk 状态标记） | `[Verified·一手]` | 通用；但"分数从哪来"决定它是否可信（Q5 原则 4） |
| 确定性证伪作为降级依据 | **1**（只有 autolearn） | `[Verified·一手]` | 单血统。但 Agent OS 的 `outcome` 合成是同问题的另一解 ⇒ **两条不同路线并存**，强度高于单血统 |
| 人门在代码里强制 | **1**（只有 Agent OS 自己） | `[Verified·一手]` | 别家都没有；不是借鉴来的，是要守住的 |
| 反漂移的速率/配额/单飞锁 | 1（autolearn） | `[Verified·代理读源]` | 单血统；Agent OS 目前完全没有 → 见 R-005 |
| 回读本地会话历史作为证据源 | 2（autolearn SQLite、opencore SDK） | `[Verified·一手]` | 通用可行，见 Q10 |
| 记忆衰减公式（Ebbinghaus 型） | 1（autolearn，自述 adapted from AgentMemory） | `[Verified·代理读源]` | 单血统，且 Agent OS 已有 `decay_factor` 的两写者待收敛问题 → 不急于引入新公式 |

---

## 12. 不该借鉴 / 不该进 Agent OS 核心（逐条给理由）

1. **改写 `~/.config/opencode/opencode.json` 来注入**（autolearn `autolearn-core.mjs:418-449` + `install.sh:108-127`）。
   理由：用户硬约束「不修改 OpenCode 全局配置」；且 `JSON.parse/stringify` 重写整份文件会丢注释、
   覆盖用户其它键的顺序，属于对他人配置的副作用型写。
2. **常驻 HTTP Inspector**（autolearn `inspector_server.py`，127.0.0.1:4321，内嵌 SPA）。
   理由：零三方依赖原则；Agent OS 的人门已经在 CLI（`aos review`）里，HTTP 面是新增攻击面与运维负担。
3. **云同步层 / 多端加密后端**（autolearn `sync-server/`+`sync-convex/`，opencore `gateway/` Telegram 桥）。
   理由：产品形态，不是能力；两者自身也声明核心不依赖它们（`autolearn.py:1903-1912` 的 `SYNC_FILES` 白名单，
   `gateway/src/*.ts` 里对 plugins 零引用）。
4. **embedding + 向量表**（opencore `vectors(fact_id,hash,model,dim,vec)` + `lib/embeddings.ts`）。
   理由：直接违反 Agent OS 的「无 embedding、无网络」硬约束；opencore 自己也做了"失败回落 BM25"（`memory-store.ts:276-295`），
   说明它并不认为向量是不可缺的。
5. **`bun:sqlite` / Bun 运行时**（svtter、opencore 全部 SQLite 访问点）。
   理由：Agent OS 引擎是 Python 标准库；移植意味着换语言或加运行时。借鉴其 schema 形状可以，代码不行。
6. **把"回答排版"当质量分**（svtter `rubric-scorer.ts:50-97`、`subagent-runner.ts:22-32`）。
   理由：这就是 Agent OS 上一轮修掉的断点 4，且 svtter 的 README:126 自己承认是 Heuristic。
7. **进程内 `setInterval` 当日程调度**（svtter `index.ts:40`）。
   理由：不持久化，进程不活满周期就永不执行；Agent OS 的对应需求应由显式命令 + postflight 内联完成（计划 §4.4 触发者三条）。
8. **`try { ALTER TABLE … } catch { /* already exists */ }` 当迁移机制**（opencore `memory-store.ts:81`；无 `PRAGMA user_version`）。
   理由：这正是 Agent OS §五 花大力气避免的东西，而且 opencore 已经为此付出了"删除文件不清索引"的代价。
9. **合成 user 消息作为提醒通道**（okdk `index.ts:749-787`）。
   理由：把模型自产内容伪装成用户输入，会污染"从对话里学"的输入分布；且它的 `pickNudgeTarget(…, null)`
   存在跨会话注入的缺陷（`index.ts:752,1196-1205`）`[Verified·一手]`。
10. **fail-open 的写入裁决**（opencore LLM 解析失败即 ADD，`memory.ts:175-181`）。
    理由：解析失败应"什么都不写 + 记一条告警"，与 Agent OS 的 fail-open 纪律（异常必须进 `warnings`/事件）一致。
11. **无界日志/无界注入块**（okdk `logs/plugin-debug.log` 永久追加；opencore 常显块随事实数线性增长）。
    理由：预算必须由代码封顶，Agent OS 现状 `inject` 的 1400/6/280/1 是正解。
12. **让 skill 正文携带 `verify:` 命令并自动执行它** —— 这条本身在 autolearn 里是好设计（有安全拒绝清单
    `SAFE_DECLARED_DENY`，`outcomes.py:45-50`），但对 Agent OS 需要单列风险：
    `[Judgment]` 一旦"经验里带命令、系统会跑它"，一条被污染的记忆就变成代码执行通道。
    用户已把 prompt-injection 威胁建模推迟到下一轮；因此 `R-007` 的建议是**存声明但不自动执行**，
    执行必须走人批准 + 白名单 + 显式 `--apply`。

---

## 13. 各项目核心区别，以及与 Agent OS 想验证的闭环对照

| 项目 | 它真正在解决的问题 | 闭环里覆盖了哪几环 | 缺了什么 |
|---|---|---|---|
| **autolearn** | 让"自我改进"有可证伪的地面真值，并把学到的东西分层（记忆 / skill / 行为规则 AGENTS.md） | 真实数据→观察（索引）→经验（记忆/候选）→评估（证伪）→提案→验证→沉淀；**人门最弱** | 无统一 verdict 契约（pass/fail/inconclusive 只作用于 skill 降级）；自动晋升靠证伪而不是证据等级；人门只在 CLI/Inspector 局部 |
| **svtter** | 最小可用的 skill 生命周期骨架（创建→打分→存储→修剪→注入），全部在进程内 | 观察→经验→沉淀（+注入） | **无 verdict、无人在环、无持久调度、遥测表无写入者、schema.sql 未被加载** |
| **okdk** | 把 Hermes/GEPA 式"进化循环"落到 opencode 的钩子上 | 触发→存储→度量→进化（形式齐全） | **Review 与 Evolve 的判据是模型自评；Measure 的证据通道结构性失效**；无强制人门 |
| **opencore** | 一个可用的编码 agent 产品：记忆 + 代码库检索 + 会话检索 + 预算观测 | 真实数据→观察→沉淀→注入 | **不判成败、不进化（遥测惰性）、无审批、无 TTL、无版本化** |
| **Agent OS（现状）** | 让"经验"有生命周期与门：合成 verdict + 覆盖率置信 + 人门 + CAS 写入 | 观察→经验→评估→提案→验证→人批准→沉淀 | 去重/冲突/过期（Phase 3.3）未做；使用反馈闭环与排序（3.4）未做；policy 版本化与路由可达性（3.5）未做；skill 感知/进化（3.6）只有设计；证据时序与崩溃补记（3.7）未做；**插件本身未实现** |

**Agent OS 相对领先处（不是借鉴来的，别在裁决时丢掉）`[Verified·一手]`：**
- verdict 合成 + 置信=覆盖率 + `min_verdict_mass` 下不命名结论（`outcome.py:256-311`）：五者里只有它把"不知道"做成显式状态并路由给人；
- 人门由代码强制，且 create/weaken 永不自动（`evolve.py:504-522`）；
- 批准写入带 compare-and-set，memory 变了就 `stale` 拒写（`evolve.py:407-483`）；
- 候选被消费记账（`consumed_at/consumed_by`，`evolve.py:699`）—— 三家都有"重复处理旧证据"的对应缺陷；
- 迁移机制以 `PRAGMA user_version` 为唯一权威、破坏性步骤先备份（`migrations.py:103-247,504-507`）；
- 注入有显式字符/条数预算与 `truncated/dropped` 记账（`inject.py:149-172`）。

---

## 14. 自我进化的最小闭环（从共同点归纳）

```
 [执行] opencode 的一次会话
   │  (a) 事件/钩子现场采：tool.execute.after 的 status、patch/diff 规模、todo 余量、中断/错误
   │  (b) 或事后回读：append-only 的 part/todo（本机实测 tool 状态可反推：error 235/16137）
   ▼
 [观察 · append-only 一条事实一行]  每条带来源、时间、会话、项目        ← 血统 2（autolearn, 本机）
   ▼
 [判据 · 确定性优先]  能跑命令就跑命令；不能就聚合信号并给出"覆盖率"    ← 血统 2（autolearn 证伪 / Agent OS 合成）
   │     必须有第三态：inconclusive / 未标注 —— 与 fail 分开             ← 血统 1（autolearn），但方向被 Agent OS 的 needs_review 印证
   ▼
 [候选 · 与结论分开存]  "值得记" ≠ "已生效"；复发或证据达标才成候选     ← 血统 3（autolearn recurrence, okdk 阈值, opencore importance）
   ▼
 [判重 · 必须先于写入]  同事实不同表述必须能合并；无通用解 → 自研        ← 血统 4（弱实现），无强实现
   ▼
 [门 · 代码强制]  人批准；且写入前比对基线，世界变了就拒绝               ← 血统 1（Agent OS），别家 0
   ▼
 [降级 · 也要能发生]  失败/过期使证据下降，而不是只上升                 ← 血统 1（autolearn demote），Agent OS 已实现
   ▼
 [下一次执行]  注入预算固定、可幂等替换、不吞别人写的块                 ← 血统 4（都注入；只有 DCP 会 append [-1]）
   ▲____________ 计数由观察派生，永不就地自增；否则必有死字段 _________|  ← 血统 2 + 3 个反面样本
```

`[Judgment]` 五条硬要求，缺一条就不叫闭环：**append-only 观察、确定性判据（含第三态）、写入前判重、
代码强制的人门、由观察派生的计数**。
四个外部项目里没有一个同时满足三条以上（autolearn 满足 1、2、5；svtter 满足 1；okdk 满足 1 的形式；opencore 满足 1）。
Agent OS 目前满足 1、2、4、5，**唯独"写入前判重"（Phase 3.3）未落地**，而它正是外部四个项目全都撞过的墙。

---

## 15. License 与复用代价

| 项目 | License（实测） | 借设计 | 抄代码 |
|---|---|---|---|
| ericmjl/agent-autolearn | **MIT**（有 `LICENSE` 文件） | 可以 | 可以，须保留版权声明；但 Python 侧有 8 个三方依赖 + Bun/uv（`autolearn.py:15-25`），复制=引入依赖，违反零依赖 |
| Svtter/opencode-self-improve | **MIT** | 可以 | 不行（`bun:sqlite`），且体积虽小（32 文件）但 TS/bun 运行时不可移 |
| okdk7788/opencode-self-improving-skills | **MIT** | 可以 | 不行（单文件 53K TS，`main: ./index.ts` 需 Bun 直跑；且其证据通道实现是错的） |
| asphyksia/opencore | **无 LICENSE 文件**（`api.github.com` 返回 `license: None`；仓库 48 文件无 LICENSE） | 阅读与设计思想可用 | **不可复制**（默认保留所有权利）。Fork/复制需先取得作者许可 `[Unconfirmed：作者意图]` |
| 本机 skill-tracker（用户自有） | 用户自己的仓库 | 可 | 可，但它是 opencode 插件，不属 Agent OS 核心 |

`[Judgment]` 三家的实现语言/运行时（Bun、TS、uv、pyyaml、cryptography）与 Agent OS 的「纯标准库」结构性冲突 ⇒
**本研究没有一条建议是"复制文件"，全部是"移植机制并自己实现"。**

---

## 16. 采集与验证附录（诚实记录）

### 16.1 取回
- `git ls-remote` 对四个仓库全部超时（exit 124）⇒ 不能用 clone。
- 实际取回：`codeload.github.com/<repo>/tar.gz/refs/heads/<branch>`，Python `urllib` + 3 次重试，**四个都第 1 次成功**：
  243,856 / 19,722 / 26,545 / 76,440 字节；解包后文件数 102 / 32 / 7 / 48，与 `api.github.com` 树计数一致。
- 期间出现过整批 `curl: (35) TLS connect error … unexpected eof`，重试后成功 —— 网络不稳，非仓库问题。
- 落盘仅在 `/tmp/aos-research/{autolearn,svtter,okdk,opencore}`；**未 install、未运行任何脚本、未执行任何测试**。

### 16.2 我一手复核过的承重结论
| 结论 | 复核方式 |
|---|---|
| svtter 无 verdict、SubagentRunner 是 stub | 亲读 `src/subagent-runner.ts:1-35` |
| svtter `schema.sql` 从未被加载；`incrementUsage/logUsage` 零调用方 | 亲跑 grep：src 内 0 处引用；函数只有定义行 |
| okdk 的两个失败探针打不到真实字段 | 亲读 `index.ts:930-958` + 对照本机 SDK `ToolPart/ToolState*` 类型定义 |
| okdk 的合成 user 消息通道与 nudge 文本 | 亲读 `index.ts:749-790,1210-1216` |
| okdk/autolearn 的导出形状与 `session_search` 引用 | 亲读 `index.ts:644-650`、tail；`grep session_search/session_read` |
| autolearn 的 gt 阶梯、证伪映射、降级后果 | 亲读 `outcomes.py:108-135`、`falsify.py:150-180,293-330` |
| autolearn 的历史回读实现 | 亲读 `outcomes.py:196-240,388-415`、`autolearn.py:272-300,1398-1425` |
| autolearn 注入 = 改写 opencode.json | 亲读 `autolearn-core.mjs:415-455`、`install.sh:108-130`；并确认本机 `opencode.json` **没有** `instructions` 键（说明它未在此机运行，我只读未改） |
| opencore 无 verdict、`view_count` 写不读 | 亲读 `skill-telemetry.ts:182-200` + 全目录 outcome 相邻读取的 grep；`view_count` 三处引用核对 |
| DCP 追加到 `[-1]`、内部调用探测只看 `[0]` | 亲读 `lib/hooks.ts:49-56,101-105` |
| SDK 钩子/事件清单 | 亲查 `@opencode-ai/plugin/dist/index.d.ts` 与 `@opencode-ai/sdk/.../types.gen.d.ts` |
| 本机历史库可行性 | 亲跑只读 SQL：表清单、schema、计数、type 分布（无正文） |

### 16.3 未一手复核（来自代理逐行摘录，引用可信但未二次验证）
autolearn 的 retention 公式常数与 tier 阈值、三层节流的每个默认值、Inspector 的路由表、
`docs/designs/**` 的"文档 ≠ 代码"清单逐条、opencore 的 BM25/RRF 具体表达式与 budget.ts 常数、
svtter 的 curator 相似度权重分解、okdk 的 clustering 细节。
⇒ 这些在 capability-matrix 中一律标 `[Verified·代理读源]`，不做裁决依据。

### 16.4 `[Unconfirmed]` 清单（本轮明确没做、以及需要什么才能确认）
1. **插件加载顺序**（DCP 与 Agent OS 谁先跑 `system.transform`）⇒ 需要装一个探针插件实跑一次对话。
2. **okdk 的裸 `export default` 是否导致整个插件不加载** ⇒ 需要装载它（本机不允许装）。
3. **`message.part.delta` 在 1.18.33 是否仍发** ⇒ 需要订阅 `event` 打印实跑。
4. **opencore 钉的 1.17.11 与 1.18.33 的 hook 差异** ⇒ 需要两个版本并跑或读 opencode 变更日志。
5. **okdk 的 `looksLikeCorrection` 三个正则的真实精度** ⇒ 需要标注数据。
6. **`session_search`/`session_read` 工具是否由 opencode 1.18.33 提供** ⇒ 我在 `command -v opencode`（zsh alias）上 grep 未取得有效计数，判为未确认；需要 `opencode` 的真实可执行路径或运行时工具列表。
7. **上游 `UniM0cha/claude-self-improving-skills` 与 `okdk7788/skill-evolution` 的内容** ⇒ 影响血统判定精度，本轮按 §3 约定「先停下问用户」，未取。
8. **Hermes Agent（NousResearch）本体设计** ⇒ svtter/okdk 的概念来源，未读，因此"两家同源"的判断只依据它们的自述。
9. autolearn 文档里的经验数字（393/393 精确重放、106k tool parts、+15 ablation）⇒ 仓库内不可验证。

### 16.5 本机只读 SQL（可复现，全部 `mode=ro`）
```sql
SELECT name FROM sqlite_master WHERE type='table';
SELECT json_extract(data,'$.type') t, COUNT(*) FROM part GROUP BY t ORDER BY 2 DESC;
SELECT json_extract(data,'$.state.status') s, COUNT(*) FROM part WHERE json_extract(data,'$.type')='tool' GROUP BY s;
SELECT type, COUNT(*) FROM event GROUP BY type ORDER BY 2 DESC;
SELECT COUNT(*), SUM(cost>0), SUM(summary_files>0), SUM(time_archived IS NOT NULL), COUNT(DISTINCT agent), COUNT(DISTINCT model) FROM session;
SELECT status, COUNT(*) FROM todo GROUP BY status;
```
**没有任何查询读取 `part.data`/`message.data` 的正文值**，本文档不含任何会话内容。
