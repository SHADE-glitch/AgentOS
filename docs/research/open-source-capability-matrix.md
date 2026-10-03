# 开源能力矩阵 · 18 项能力 × 5 个来源

列：**A** = `ericmjl/agent-autolearn`、**S** = `Svtter/opencode-self-improve`、
**K** = `okdk7788/opencode-self-improving-skills`、**O** = `asphyksia/opencore`、
**本机** = 已在运行的组件（`skill-tracker.js` / `@tarquinen/opencode-dcp@3.2.0` / `notifier` / `conductor` / `basic-memory` MCP）、
**O（opencore）无 LICENSE 文件**（API `license: None`）⇒ 本矩阵中所有 O 列一律「设计可读、代码不可复制」；A/S/K 均为 MIT。
**AOS** = Agent OS 现状（只引 `path:line`）。

标签含义见 `findings.md §0.1`；血统计数规则见 `§0.2`（**svtter 与 okdk 同源，合计算 1 次**）。

---

## 一. 速览表

| 能力 | A | S | K | O | 本机 | AOS | 血统数 |
|---|---|---|---|---|---|---|---|
| Observation | 3 层：`observations.jsonl` + `tool_outcome` 索引 + 记忆 | 无（直接进 skill） | 半：`skill_outcomes.json` | 2 层：`facts` 表 + `MEMORY.md` 导出 | `skill_usage`/`mcp_usage`/`plugin_usage` 三表 append | `observations`（含 loop 级 + `signals_json`） | **4**（A、K、O、本机） |
| Conversation Review | reviewer 子进程（`opencode run --agent`，隐藏 agent、`steps:20`、`edit:deny`） | **stub，承认无 LLM** | **100% 模型自评**，代码只回一段静态 prompt | LLM 抽取 `importance`，每 5 轮节流 + transcript hash 去重 | 无（纯遥测） | 无 LLM 复盘；`outcome.synthesize` 合成 | **3**（A、K/O 的 LLM 抽取、AOS 的确定性合成） |
| Persistent Memory | `memories.jsonl` 无界 + retention tier | 无（只有 skill 表） | SKILL.md 文件本身 | `facts(id,text,type,importance,access_count,source)` + FTS5 + 向量 | 无（写 stats 不写记忆） | `memories` 29 列 + `scope/lane/status/version/supersedes` | **3**（A、O、AOS） |
| User Profile | `user-profile.md` + `type:"user"` 记忆条目，salience 0.80 | 无 | 无 | 无 | 无 | 无 | **1** → 单血统，暂不作通用 |
| Skill Creation | 复发≥3 聚类 + **证伪通过**才自动晋升 | 格式启发即创建 | 模型自愿调 `distill_skill` | 无（不创建 skill） | 不创建，只登记已知 skill | 无（skill 属 host，AOS 不创建） | **2**（A 与 S/K 的两条不同路线） |
| Skill Update | patch 插入 + `patch_count`；归档=rename | **同内容原地覆盖 + version+1** | agent 直接 edit + 轮转备份≤10 | n/a | n/a | 不适用（host 拥有 skill） | **3** |
| Skill Scoring | **无 LLM 分**：`gt_strength` + pass/fail/inconclusive | 4 维启发式 0–1，权重 0.3/0.25/0.25/0.2 | 无（rubric 交给模型） | `importance` 0–1 单值 | 无 | `evidence_level` 6 档 + `quality_score` | **3**（三种互不相同的路线） |
| Skill Dedup | 名字/slug 相等 + Jaccard 矛盾检测（部分） | `LIKE '%trigger%' LIMIT 3` | **无算法**，prompt 让模型查碰撞 | LLM `ADD/UPDATE/DELETE/SKIP`，解析失败→ADD | 无 | **未实现（Phase 3.3）** | **4 尝试 / 0 可靠解** |
| Skill Injection | **改 `opencode.json` 的 `instructions`** | `system.transform` push delta，top-3，无字符预算 | `system.transform` 一整块 evergreen 文本 **＋ 合成 user 消息** | `system.transform` 一行 `[opencore mem]`，**并在 compaction 时保活** | DCP `append 到 [-1]`（裁剪提示） | `system.transform` push 新元素，1400 字符/6 条预算，唯一标签幂等 | **5** |
| Skill Pruning | 30/90 天 + 60 天零使用；pinned/非自建豁免；**从不 delete** | 分数 <0.5 **硬删**；相似 ≥0.85 合并 | 人删目录后标 `archived`（插件永不删） | `unused_days` 只列清单，**无动作** | registry `status/last_seen` | `deprecated/superseded/invalidated` 状态 + decay；召回过滤未做（3.4） | **4** |
| Session Search | 自建 `search.db` FTS5 external-content，增量高水位 | 无 | 无（提示词引用不存在的工具） | 自建 `sessions.db`，数据来自 SDK `client.session.messages` | 无 | 无（Phase 未列） | **2**（两条不同数据来源） |
| Codebase Memory | 无（有 wiki 层，不是代码索引） | 无 | 无 | `chunks(path,startLine,endLine,content)` 60 行窗口/10 重叠，`file.edited` 增量替换，**删除文件不清理** | 无 | `evidence/collector.py` git 集合差（before 时序待修，3.7） | **2** |
| Skill Telemetry | `use_count` **从索引派生**（`GROUP BY`），repair 回写 | `skill_usage_log` 表 + 函数 **零调用方** | `use_count/view_count` 自增 JSON | `use_count` 自增；**`view_count` 声明/展示但从不自增** | 5 表 + `status` 单调修正 + `UNIQUE(session_id,call_id)` | `observations` + `retrieval_log`（后者写而不读，3.4 待接） | **4**，其中 **3 个是死字段样本** |
| Evaluation | 证伪 + 复发 + 时间三线，无混合分 | 4 维加权启发式 | GEPA 式 0–5 交给模型 | importance × recency × log(access) 排序 | 统计/TUI 展示 | `evaluate.py` 已降级为权重 0.00 的可选输入 | **3** |
| Evolution Proposal | `proposals.json` + 聚类 + `verify:` 块 | 无（直接改库） | `[진화 후보]` 排序行，`priority=use*(fail+1)/(total+2)` | 无（无进化概念） | 无 | `candidates` + `consumed_at/consumed_by` + 3.3 未做 | **2**（A、K） |
| Human Approval | `--dry-run` 全家桶 + Inspector 只有 strengthen/confirm/dismiss 两个写操作 | **无** | 文档写"Never auto-commit"，**代码不强制**（未注册 `permission.ask`） | **无** | 无 | `learning_reviews` 两类 + 代码强制 + CAS 拒绝（`stale`） | **1 真强制**（AOS 自己） |
| Plugin Integration | `event` 单钩子（v1）/ v2 事件流 / pi 钩子；spawn `uv run` 分离进程，无超时 | 3 钩子 + 9 tools；注入钩子 **无 try/catch** | 5 钩子 + 5 tools；**导出形状有静默不加载风险** | 4 个插件各注册 2–4 钩子；`bun:sqlite`；SDK 调用 | `8 钩子`；`export default {id,server}`；`safe()` 包裹；**有失败历史并被写成注释** | 契约 stdin/stdout；插件**未实现**（Phase 4） | **4** |
| Storage | 每 persona 一个目录，JSONL + 多个 `.db`（含 `verdicts.json`、`outcomes.db`、`search.db`） | 单一 `skills.db`（bun:sqlite）+ **未被加载的 schema.sql** | 全 JSON 平面文件 + `tmp+fsync+rename` 原子写 | `~/.opencore/{memory,codebase,sessions,budget,skills}/` 多库 + `try{ALTER}catch` 迁移 | `~/.local/share/opencode/skill-usage.db` + JSON registry | 单 SQLite + `PRAGMA user_version` 迁移链 v2/v3/v4 + 破坏性步骤先备份 | **5 种互不相同的组织方式** |

**血统判定要点（会削减借鉴清单）**
- 达到「≥2 独立血统」的能力：Observation、Injection、Pruning、Telemetry、Plugin Integration、Storage、Scoring、Evaluation、Session Search、Codebase Memory、Evolution Proposal。
- **只有 1 个血统**：User Profile（仅 A）、真正的强制人门（仅 AOS）、反漂移速率/单飞锁（仅 A）、inconclusive 第三态（仅 A）、Ebbinghaus 衰减公式（A，且自述 adapted from AgentMemory）。
- **4 家都试、0 家有可靠解**：写入前判重（dedup）。⇒ 见 `findings.md §14`，这是 Agent OS 唯一无先例可抄的一环。

---

## 二. 每能力七字段详情

约定：**输入 → 变换 → 输出**；状态 = 存到哪；触发 = 什么唤起它；调用者 = 谁执行；边界 = 与相邻能力不做什么。

### 1. Observation
- **解决什么问题**：把"发生过什么"与"这意味着什么"分开，否则结论无法重算、审计不能回溯。
- **为什么这样设计**：A 用 append-only JSONL + 可重算索引，因为它的证伪需要"每条 tool part 一行"才能算 `gt_strength`；O 用 `facts` 表是因为它的目标是检索而非重算；S/K 跳过这层，直接写结论，于是都出现了"派生态无法重算"的死字段（S 的 `skill_usage_log`、O 的 `view_count`）。
- **输入 / 输出**：A 输入 opencode.db 的 `part` 行 → 输出 `tool_outcome(skill_name,tool,status,gt_strength,…)`；AOS 输入合并后的 signals + 引擎证据 → 输出 loop 级与 per-memory 级两行观测，带 `confidence/signals_json/needs_review/synthesised`。
- **状态存在哪**：A `outcomes.db`；O `~/.opencore/memory/memory.db`；本机 `~/.local/share/opencode/skill-usage.db`；AOS `store/aos.db:observations`。
- **何时触发**：A 显式 `curator run` 的 index 步（手动/评审自愈合）；O 每次 `session.idle`；AOS 每次 postflight 的 `record_stage`。
- **谁调用**：A `outcomes.py:224-240`；AOS `aos/core/loop/stages.py:367` + `aos/core/memory/record.py:113`。
- **边界**：Observation 不含质量判断（A 的 `gt_strength` 是**证据强度**不是评价）；Evaluation 才做评价。S 把两者合一，是其判据退化的直接原因。

### 2. Conversation Review
- **解决什么问题**：从一次对话里提取"值得留下的东西"。
- **为什么这样设计**：A 用**分离的子进程**（`opencode run --agent autolearn-reviewer`，`AUTOLEARN_REVIEWER=1` 防递归，`stdio:"ignore"`，agent 配 `edit:deny`/`steps:20`）——评审能读能写但被限制破坏面；K/S 要么用占位桩要么把判据交给主模型自己，导致"评审"等于"自述"。
- **输入 / 输出**：A 输入缓冲区里的对话（user ≤1000、assistant ≤2000 字符，先脱敏 `:90-97`）→ 输出 `reviews/review-<ms>.md` + 评审自己写的文件改动；AOS 无对话复盘（只见信号不见对话）。
- **状态存在哪**：A `reviews/` + `observations.jsonl` 的 `review-complete` 自报；AOS `learning_reviews` 表存的是**决定**不是复盘。
- **何时触发**：A 三层节流（内容哈希 + 180s + 60/天）+ 进程退出前 flush；AOS `evolve_stage` 每轮 postflight。
- **谁调用**：A `plugin/autolearn-core.mjs:725-769`；AOS `evolve.py` 的 `run_learning`。
- **边界**：Review 不应同时充当 verdict 来源（A 分开了：评审写文件，`falsify` 才判成败）；AOS 目前**完全没有**对话复盘这一环，是相对别家的缺口，但它的 `outcome_label` 人门把这一职责交给了人而非模型。`[Judgment]` 两者可以共存，不必修。

### 3. Persistent Memory
- **解决什么问题**：跨会话保留事实，并且**在预算内可检索**。
- **为什么这样设计**：A 用无界 JSONL + 保留分 tier 决定"谁进注入"（用淘汰代替截断）；O 用 FTS5 + 向量 + `importance`，把检索质量放在查询期；AOS 用一行一记忆的 SQLite 表 + 生命周期状态，把可信度放在写期。
- **输入 / 输出**：A `memory add/strengthen/weaken` → `memories.jsonl` → 组合器 → `memory.context.md`；AOS `authoring.new_memory` / 提案晋升 → `memories` → `inject.render()` → `<agent_os>` 块。
- **状态存在哪**：见 §Storage。
- **何时触发**：A 加载插件时 fire-and-forget 重新生成；AOS 每次 preflight 渲染一次。
- **谁调用**：A `composer.py:32-82`；AOS `aos/core/memory/inject.py:149-172`。
- **边界**：Memory ≠ Skill（知道什么 vs 知道怎么做）；A 还多一层 `type:"user"`（用户画像），AOS 无画像。`[Judgment]` 画像在四个项目里只有 1 个实现且没有消费方，**不建议进核心**。

### 4. User Profile
- 只有 A 有（`user-profile.md` + `type=="user"` 条目，salience 0.80 高于普通记忆 0.85 之下的加权）。`[Verified·代理读源]`
- **边界**：它是"注入排序的另一个权重"，不是独立存储。**单血统 → 不借鉴**（`findings.md §12`）。

### 5. Skill Creation
- **输入 → 输出**：A：`candidates/topics` 的跨会话复发（0.5 overlap 聚类）+ `common_resolution` 证伪 → 新 `SKILL.md` + `verify:` 块；S：assistant 消息的排版特征 → 立即入库（`autoCreate`）；K：模型自愿调用 → 模型自己写文件。
- **为什么这样设计**：A 把创建门槛绑在"重复 + 可验证"，因为它的下游要自动执行 `verify:`；S/K 的门槛是"看起来像经验"，因为它们的下游只是注入。
- **状态**：A `.usage.json` + skill 目录符号链；S `skills` 表；K `~/.config/opencode/skills/<name>/SKILL.md`。
- **触发**：A curator；S `skill_forge_review` 工具（**自动路径未接线**）；K 无（靠 agent 自觉）。
- **调用者**：A `autolearn.py:905-967`；S `skill-forge.ts:17-53`；K `index.ts:577-606`。
- **边界**：**Agent OS 不创建 skill 是既定约束**（skill 属 host）。这项能力对 AOS 的用处只有"评价别人创建的 skill"，不是自己创建。

### 6. Skill Update
- A：section 内插入 bullet + `patch_count` 自增；命中 pinned / `created_by!="autolearn"` 时**不动**。
- S：命中相似 → **覆盖第一个匹配的全部字段** + `version+1`，即 last-write-wins，没有 diff、没有回滚点。
- K：agent 直接 `edit`；插件只在写前做备份、写后做 frontmatter 校验，非法则回滚到最新备份。
- **共同问题**：**三家的"版本"都不能回滚一次合法的退步**（K 只能回滚格式非法）。
- **边界**：AOS 对应物是 `memories.version` + `supersedes`（Phase 3.3 的冲突落点），别家没有谱系概念 ⇒ 这是 AOS 的领先项，不是借鉴项。

### 7. Skill Scoring
- **输入 → 输出**：S 输入 skill 文本 → 4 维加权和；K 输入"当前 skill + 20 条 ≤200 字符的 fail_signals"→ **模型输出 0–5**；A 输入"声明的 verify 命令的退出码"→ pass/fail/inconclusive；O 输入对话 → 模型自报 `importance`。
- **为什么不同**：取决于他们相信什么。只有 A 相信可执行命令；其余相信模型判断或字符串形状。
- **状态**：S `skills.quality_score`；O `facts.importance`；A 不是分数，是 `verdicts.json{verdict,fail_count,evidence}`。
- **触发**：S 创建/更新时 + 每次 curator 扫；A 每次 curator 的 falsify 步。
- **调用者**：`rubric-scorer.ts:39-97` / `falsify.py:131-178`。
- **边界**：分数**不该同时充当"要不要处理"和"能不能生效"**（okdk 用 priority 只决定前者，A 用证伪决定后者——这两条各对一半，可叠加）。

### 8. Skill Dedup / Memory Dedup
- 四家实现：slug 相等（A）、`LIKE` 前 3 条（S）、prompt 提醒（K）、LLM 四值裁决（O）。
- **共同症状**：重复堆积、互相覆盖、或每次写多付一次 LLM 成本，且 O 的解析失败 **fail-open 到新增**。
- **AOS 现状**：`dedupe_key` 列 + `uq_mem_dedupe` 唯一索引已在 schema（v2），但**没有任何生成/命中代码**（`grep dedupe_key aos/core/memory/retrieve.py` 无匹配）⇒ Phase 3.3 未开工。
- **边界**：判重属于写入路径（learning），不属于检索排序；判重的结果必须是"合并/强化已有条目"而不是"丢弃新证据"（这条四家都没做对）。

### 9. Skill / Memory Injection
- 见 `findings.md §6`（含 DCP `[-1]` 冲突、autolearn 改 config 的反例、预算对比、`messages.transform` 第二通道）。
- **七字段**：输入=查询/系统提示；变换=相关性排序 + 预算裁剪；输出=一段 system 文本或一条 instructions 文件路径；状态=无（注入是读路径）；触发=每次 LLM 调用（A 例外：加载时生成文件）；调用者=`*.transform` 钩子或 opencode 的 `instructions` 解析；边界=**不得改写别人写的数组元素**（DCP 违反了这一点，AOS 的 push 新元素 + 唯一标签是正解）。

### 10. Skill Pruning
- A：时间 + 零使用 + pinned 豁免 + **rename 归档不删除**；S：分数阈值 + **硬删**；K：只跟人删的动作；O：只列清单；本机：`status/last_seen` 供人判断。
- **共同问题**：`usage_count` 高不等于质量好（S 完全不看使用量；K 把使用量当爆炸半径而非质量）。
- **AOS 现状**：`status: deprecated/superseded/invalidated/archived` + `decay_factor` 已由 weaken 写入（`evolve.py:363-379`），但 **`retrieve` 未按 status/scope 过滤**（`aos/core/memory/retrieve.py:142-143` 只回显字段）⇒ 降级"记下了但不生效"，这是 Phase 3.4 的活。
- **边界**：修剪 ≠ 删除（保留 provenance 是 A 与 AOS 的一致选择；S 的硬删是少数派）。

### 11. Session Search
- A：自建 FTS5 external-content 表，**增量高水位是复合键** `(time,id)`；只索引 `type=="text"`；查询用 `prefix*` + `bm25 rank` + ±2 条上下文回读；**无自动索引**（手动 `search init` 或评审自愈）。
- O：自建 `sessions.db`，来源是 SDK `client.session.messages`；`session-search.ts:22` 注释宣称 hook `session.idle` 但**并未注册该钩子**，索引在工具调用里惰性构建 ⇒ 注释与实现不一致。
- **AOS**：无此能力，且 Phase 计划里没有它。`[Judgment]` 对"外部大脑"定位而言，会话搜索是**证据取证工具**而非学习机制，可以不做，但若要做，走 SDK 而非读 opencode.db（版本耦合更低，见 Q10）。

### 12. Codebase Memory
- O 独有（在本研究内）：`chunks(id,path,start_line,end_line,content)` 60 行窗口 + 10 行重叠，`git ls-files` 或过滤遍历，`file.edited` 事件增量替换该路径的 chunk，**删除的文件不会清理**；混合检索 BM25 + 余弦 RRF（k=60），`ORDER BY bm25(facts_fts) - importance` 这个"重要性倾斜"是一行可移植技巧。
- AOS 对应物是 evidence 层的 git 事实（`files_changed`），不是代码索引：定位不同（AOS 记"改了什么"，O 记"代码长什么样"）。`[Judgment]` 不建议 AOS 做代码索引——那会把它变成第二个编码 agent，与"外置大脑"定位冲突。

### 13. Skill Telemetry
- 五方对比见 `findings.md Q7`。核心结论：**只有把观察存成 append-only 事实、计数派生，遥测才不会腐烂**；
  3 个样本（S 的空表、O 的 `view_count`、A 的 `topics.jsonl`）证明"声明了但没人写/没人读"是常态失效模式。
- AOS 的 `retrieval_log` 写而不读，属同一类，且已被 §1.4 断点 5 记录在案、Phase 3.4 待接。

### 14. Evaluation
- 原则性结论见 `findings.md Q5`（4 条）；**不建议照抄任何一家的维度与权重**。
- 可移植的具体做法只有一条：把评价拆成"是否可验证"（命令/退出码）与"是否值得处理"（排序权重），永不分处同一字段。

### 15. Evolution Proposal
- A：`proposals.json` + 复发聚类 + **证伪通过才自动晋升**；K：`priority=use*(fail+1)/(total+2)` + 24h 冷却 + `use≥2 & fail≥1` 才成候选；AOS：`candidates` + 三种类型（reinforce/weaken/create）+ 每组消费 + `max_promotions` 每轮上限。
- **缺口对照**：AOS 无"冷却时间"与"提案速率限制"（K/A 都有），也**没有 A 的 `verify:` 声明块**——后者让提案自带可验证性，见 `R-007`。
- **边界**：Proposal 不是 Memory（AOS 已实现：提案→review→人批准→写 memories）；S 直接把候选写进库，跳过了这一层。

### 16. Human Approval
- 见 `findings.md Q8`。唯一值得记的强对比：**"文档里写了纪律"与"代码里有门"是两件事** —— K 写了 Never auto-commit 却没注册 `permission.ask`；A 的 HARD GATE 只在 prompt 里；只有 AOS 的门能被绕过时的后果是被 CAS 拦住。
- AOS 的门形态（两类 kind、`label` 日常命令、`--dry-run` 式 `migrate --dry-run`）比别家完备；**待补的是 `--dry-run` 的覆盖面**（A 几乎每个破坏性命令都有）。
- **2026-10-03 起矩阵里有一列"无人实现"**：四家（A/K/S/O）的人门批准都只写**自己**的存储（persona JSONL、`reviews/` 目录、`skills.db`、`~/.opencore/memory`），
  没有一家把"批准的结果"发布进**人自己日常维护的那个笔记库**。AOS 现在的形状：批准时经 `basic-memory tool write-note` 单向写一篇
  `agent-os/<memory_id>.md`，带 `agent_os` 归属标记、无标记的文件拒绝覆盖、失败不改变批准。
  判据 4 要求新模块能指到这样一列，这一条就是它指到的那一列（`positioning.md §6.4`）。

### 17. Plugin Integration
- 权威钩子清单与兼容性判定见 `findings.md Q9`。三条硬事实值得进设计：
  1. **导出形状必须是 `export default { id, server }`**：本机有因此**整插件静默不加载**的事故记录（`skill-tracker.js:1791-1796`），SDK 侧契约是 `PluginModule { id?, server }`，而 K 与 A v1 都写成了裸函数导出。
  2. **每个钩子必须包 `safe()`**：S 的注入钩子**没有 try/catch**，抛错就发生在 system prompt 变换路径上（可能挡住用户这一轮）；本机插件 40+ 处 catch 且每个钩子都包。
  3. **不要阻塞 prompt**：A 用分离进程 + 无超时的 spawn（有悬挂风险），本机/AOS 计划用短超时 + 放弃注入。
- AOS 现状：**插件未实现**（Phase 4），但 `collect_signals` / `PLUGIN_POSTFLIGHT_REQUEST_FIELDS` / `learning.needs_review` 已在契约里就位（`aos/contract/postflight.py:33,36,106`）。

### 18. Storage
- 五种组织：A `~/.autolearn/personas/<p>/`（多 JSONL + 多 `.db` + `verdicts.json` + `reviews/` + `wiki/`，机器级 `.review_gate/`、`.curator_cooldown`）；S 单 `skills.db`；K 纯 JSON 平面 + **`tmp+fsync+rename` 原子写**；O `~/.opencore/{memory,codebase,sessions,budget,skills}/` + 每库一 `.db`；AOS 单 `store/aos.db` + `store/{loops,evidence,pending-postflight}/`。
- **迁移策略对比（这是最有用的一列）**：
  - A：懒迁移 + 迁移后把旧文件改名 `.legacy`（`registry.py:276-376`）；
  - O：`try { ALTER } catch { /* already exists */ }`，无版本戳（`memory-store.ts:81`）；
  - S：`CREATE TABLE IF NOT EXISTS`，**且 `schema.sql` 与实际内联 SCHEMA 是两份**；
  - K：无（JSON，字段靠默认值）；
  - **AOS：`PRAGMA user_version` 为唯一权威 + `schema_meta` 镜像交叉校验 + 不一致即拒绝启动 + 破坏性步骤先 `Connection.backup()`**（`aos/core/memory/migrations.py:103,209,247,504-507`）。
- `[Judgment]` AOS 在这一点上是这批样本里唯一做到"迁移可解释"的，属于必须守住而非借鉴的能力。

---

## 三. lineage 附注行

| 列 | 自述来源 |
|---|---|
| A | Schema ARC-AGI-3 harness、WikiSkill(arXiv 2608.27454)、AgentMemory（retention/Jaccard）、self-improving-agent/improve.py；**明确与 Hermes 路线对立**（"Our reviewer IS the LLM"） |
| S | Hermes Agent（NousResearch） |
| K | Hermes Agent（概念源）+ UniM0cha/claude-self-improving-skills + okdk7788/skill-evolution（**代码是 port**） |
| O | OpenClaw-inspired dreaming；本体是 opencode 的产品封装 |
| 本机 | 用户自有；无外部声称来源 |
| AOS | 无外部来源；设计来自用户 spec + 本次审计 |

⇒ **S 与 K 合并计 1 个血统**；任何"S 和 K 都有"的机制，在矩阵里一律标 1 次采用。
