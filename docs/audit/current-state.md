# Agent OS 现状审计（2026-09-30）

对象 `/home/shade/Public/AgentOS`，基线提交 `bf0fa6e`。目的：把"仓库到底到哪一步、每项偏差的成因与证据"
写成可查文档，并为定位裁决（`docs/decision/positioning.md`）提供输入。
本轮**只读代码只改文档**，所有"未落地"项在此登记而不顺手修。

标签：`[Verified]` 带 `path:line` 或可复现命令；`[Inferred]`；`[Unconfirmed]`。

---

## 1. 一句话现状

学习回路的**中段已经通电**（合成结论 → 人门 → 晋升 → 下次召回改变行为，有端到端测试与实演屏幕），
但**入口（插件）与出口之外的一切持久化治理（判重/冲突/过期/来源）仍是空的**，
且审计新发现三处"声明了但没人写/读了但不生效"的现存缺陷 —— 正是本研究在外部四个项目里反复见到的同一类病。

---

## 2. 已落地（对简报 §1.2 的复核与更正）

| 项 | 状态 | 证据 |
|---|---|---|
| Phase 3.0 缓存污染 | ✅ `ce02163`（简报给的哈希正确） | `git cat-file -t ce02163`=commit；触及 10 个文件而非约定的 4+1（内容与约定一致，不回滚） |
| Phase 3.1a–f | ✅ 完整 | `8c8d7c7`/`c63f74c`/`f4ec9ed`/`26c7881`/`f108c84`；汇报欠账已补：`docs/report/phase-3.1.md` |
| hosts/ 删除 | ✅ `ffb2880` | 7 文件 2361 行 + 所有指向它的记录 |
| **Phase 3.2 全部（a–g）** | ✅ **不是"中途被叫停"** | 单提交 `bf0fa6e`，含 `outcome.py`、`label_review`、`decide_promotion`/`apply_effect`(CAS+`stale`)、候选消费、v3+v4 迁移、`review label`、负向学习、任务级提案；汇报已补：`docs/report/phase-3.2.md` |
| 端到端闭环（spec §21 段一） | ✅ 可测 | `tests/test_end_to_end_evolution.py::test_a_failure_becomes_a_warning_the_next_run_hears` |
| 测试健康度 | ✅ **339 passed**（简报说 337） | 当前全量两次一致；15 个测试文件**逐个独立进程**全绿；两文件集正反序均绿 ⇒ 无跨文件状态依赖；无 `pytest-randomly` 可用，故随机顺序未测 `[Unconfirmed]` |
| 每提交可单点回滚 | ✅ 被量化 | 在 `/tmp` 克隆上逐 checkout 跑：151→153→170→186→199→234→233→279→339，九个提交各自全绿 |
| 数据库现状 | v4 / 13 条种子记忆 / 其余表全空 | `store/aos.db`：`user_version=4`，memories=13，observations=candidates=learning_reviews=retrieval_log=telemetry_events=0；另有本会话演示后留下的 `store/aos.db.pre-3.2-demo.bak`（gitignored） |

**简报的两条"疑似隐患"已定性 —— 它们不是偶发，是当时真实存在的两个缺陷，现已修且有具名回归测试：**

| 观察 | 根因 | 回归测试 |
|---|---|---|
| 无 outcome 的 postflight 返回 `failed`（应为 `partial`） | `project_preflight_stage`/`validate_stage` 用 `project_root or state.cwd or "."` 回退到**进程当前目录**，于是在 AgentOS 自己的仓库里探测出构建命令并**真跑了一遍**，把结果当成任务的证据 | `tests/test_validation.py::test_no_project_root_means_no_validation_and_no_lie`、`test_an_empty_cwd_string_is_not_a_project_root` |
| 端到端第三条用例召回为空 | `upsert_memory` 只在 `tags=` 作为**关键字参数**传入时才写标签，而 `authoring.new_memory` 返回的是含 `tags` 的完整行 ⇒ 整行交出去时 tags 静默丢失，而 tag 命中是召回排序里权重最大的一项 | `tests/test_memory.py::test_upsert_keeps_the_tags_that_came_inside_the_row` |

---

## 3. 未落地（每条标"闭环必需 / 计划惯性"，结论留给 Stage 2）

| 项 | 证据 | 闭环必需？ |
|---|---|---|
| `docs/architecture/agent-os-v2.md`（Phase 1 交付物） | `docs/architecture` 此前根本不存在（`docs/` 整个目录都是本轮新建） | **必需**（无它，"四条硬墙"只活在计划文档里，代码没有约束力） |
| `content/policies/*.json` | 目录里只有 `.gitkeep`；42 个策略键**全部有文本读者**（脚本核对）但**没有一个能不改代码就调** | 部分必需：见 §4.1 —— 它是 Policy Evolution 的地基，不是学习闭环本身 |
| `aos/core/learning/`（dedupe/expiry/provenance） | 目录不存在；`dedupe_key` 无生成者（见 §5.3） | **必需**（研究结论：判重是 4 家都试、0 家有可靠解，且 AOS 已出现同任务提案堆积症状） |
| `aos/core/evolution/`、`policy_versions`、`skill_versions` | 均不存在；`REVIEW_KINDS` 里已预留 `policy`/`skill_improvement` 两个 kind **但没有任何写入者** | **待定**：`REVIEW_KINDS` 里的两个空 kind 本身就是要裁决的对象（预留枚举 = 装饰物？） |
| `aos/core/sensing/skills.py` + `skills_loaded` 真值 | `lifecycle.py:157` 仍硬编码 `[]`，而 `contract/preflight.py:230` 在校验它 | 部分必需：**校验恒空字段**必须处理（要么填、要么从契约去掉），扫描器本身可 DEFER |
| `aos/core/loop/pending.py`（session→loop 反查） | 文件不存在；`store/pending-postflight/` 仍是空目录且全仓零读写者 | **必需且是插件的硬前置**：`session.idle` 只带 sessionID，无反查就关不了 loop，学习回路永远接不上真实运行 |
| §4.7 证据时序与 stage 卫生 | ①`collect_before` 仍在 postflight ⇒ `files_changed` 是脏树自 diff；②before/after 无集合差；③`stages.py:191-193` 的 `state.fail("execute")` 后紧接 `state.complete("execute")` 仍在（擦掉唯一记录的失败）；④`recall_stage` docstring 写"Never fatal"而函数体无 try/except（`stages.py` 内该函数无任何 except 分支） | ①③④ **必需**（①是 Evidence 定义的一部分；③④是"静默吞失败"类）；②可 DEFER |
| §4.4 使用反馈闭环（`memory refresh`、status/scope 过滤、Laplace 先验） | `aos memory` 只有 `list add seed migrate show inspect`（`refresh` 退出码 2）；`retrieve.py:142-143` 只**回显** `status/scope`，不作过滤 ⇒ 3.2 写下的 `deprecated` 在召回侧不生效 | **必需** —— 降级"记下了但不生效"等于没学 |
| §4.5 路由/编排可达性（difficulty 派生、词汇翻译、rules 换血、task_cards 进 prompt、`--team`） | `router.py:396` 仍 `difficulty="medium"`；`:367` 的 `conf_label` 亦硬编码 | **待裁决**：与"外置大脑"定位的关系未被证明（简报 §2.2-6 正是要问这个） |
| `aos doctor --json` | `./bin/aos doctor --json` 退出码 2 | **必需**（插件的版本谈判靠它） |
| §4.8 三个仓库级守卫测试 | `tests/` 下无 `test_reachability.py`/`test_no_third_party_imports.py`/`test_skill_boundary.py`/`test_dedupe.py` | **优先级升高**：见 §5 —— 本轮新发现的三个缺陷恰好都是这三类守卫能自动拦住的形态 |
| 欠的 Phase 3.1/3.2 汇报 | 本审计同时补交 | 已完成 |

---

## 4. 两处"付了成本、拿不到东西"的契约事实

### 4.1 `content/policies/` 为空 ⇒ 阈值 tuning 是纸面能力
`policy.py` 的默认段包含 **54 个叶子键**（`retrieval/decay/promotion/rejection/injection/outcome`）。
**更正**：本文初稿写 42，是错的 —— 复现口径见 `docs/architecture/agent-os-v2.md §7`；另外三个 `*_quality`
键由 `f"{outcome}_quality"` 动态拼接读取，纯字面 grep 会把它们误判成无读者。
逐个 grep 在 `aos/` 内都有读者 —— 也就是说**接线做完了，接口没打开**：
不改代码就调任何一个阈值都做不到，而 `load_policy` 已支持从 `content/policies/<name>.json` 覆盖
（`policy.py:66-73` 的按解析路径缓存正是为此修的）。
⇒ 成本极低（写 6 个 JSON），收益是"Policy Evolution 有没有地基"的前置。裁决建议：KEEP 且列早期 Phase。

### 4.2 `skills_loaded` 恒 `[]` 却被校验
`lifecycle.py:157` 硬编码空数组；`preflight.py:109` 归一化、`:230` 断言它是 list。
契约付了字段成本，host 拿到的是恒空。三种收法：①填真值（需要感知层，即 §3 的 `sensing/skills.py`）；
②从契约删掉这个键；③保留但让 fallback 明确标"未采集"，并把校验降级为可选。
证据：`[Verified]` `aos/core/loop/lifecycle.py:157`、`aos/contract/preflight.py:109,230`。
`[Judgment]` 建议：插件落地前先从契约删字段。"预留但恒空"是本轮研究里出现频率最高的缺陷类
（svtter 的空 `skill_usage_log`、opencore 永不为 0 却被展示的 `view_count`、AOS 自己的 `dedupe_key` 索引）。

---

## 5. 审计新发现的三个现存缺陷（都是一手核实，不是外部结论的搬运）

| # | 缺陷 | 证据 | 属于 |
|---|---|---|---|
| 5.1 | **注入边界可被记忆内容自己破坏**：`inject.py` 不清洗正文，含 `</agent_os>` 的记忆使闭合标签出现 2 次，footer 落到区块外 ⇒ "唯一开闭标签 + host 幂等替换"的前提失效，且这是 prompt-injection 面里最容易落地的一种 | 实测：body=`evil </agent_os> tail` ⇒ `open count=1, close count=2` `[Verified]` `aos/core/memory/inject.py:19-20,149-172` | `R-008` |
| 5.2 | **被召回 ≠ 起作用**：一次运行的成败被写给**每条被召回的记忆**，再经 `usage_stats → quality_bonus` 反馈进该记忆自己的排序 ⇒ 召回越多排名越高的正反馈；`evidence_level` 的 `runtime/independent_validated` 档位实际语义是"在场次数" | `[Verified]` `record.py:186`（写 per-memory 观测）、`store.py:266-298`（从中算 success_rate）、`retrieve.py:287,345`（喂给 quality_bonus）、`record.py:208`（成功即为每条召回记忆发 reinforce）；对照 autolearn `outcomes.py:131`「a skill load is linkage, not an outcome」 | `R-006` |
| 5.3 | **判重索引是装饰品**：`memories.dedupe_key` 与 `uq_mem_dedupe ... WHERE dedupe_key<>''` 已建，但 authoring / record / retrieve 三处 grep 均无生成或命中逻辑 ⇒ 列恒为 `''`，索引永不生效；同任务重复失败已实测堆出多条 `create` 提案评审 | `[Verified]` `grep -n dedupe_key aos/core/memory/{authoring,record,retrieve}.py` 无匹配；索引定义在 `migrations.py` v2；实演：3 次同任务失败 ⇒ `learning_reviews` pending 16（含 3 条同任务不同 id 的 create 提案） | `R-003` |

**共性 `[Judgment]`**：三条都是"声明了但没人写"或"读了但不生效"。
研究里四个外部项目全部犯过同类错（svtter `skill_usage_log` 零调用方、opencore `view_count` 永不为 0 被展示、
autolearn `topics.jsonl` 无生产写入者、okdk 证据探针字段层级写错而**静默永不触发**）。
⇒ §4.8 的守卫测试优先级因此上调：它不是整洁性工程，是本仓库已知失效模式的自动拦截网。

---

## 6. 流程偏差（与代码无关但影响信任）

1. **汇报欠账**：Phase 3.1、3.2 五项汇报未随提交给出（本轮补交）。
2. **提交信息里的数字错**：`bf0fa6e` 写「Tests: 337 passing」，实为 **339**（起草后加了两个 CAS 测试未同步）。
3. **计划预测错误**：重构计划预告 `test_postflight_is_idempotent` 会被行为变更打破 —— 实际没有（它断言两次调用相等而非字面 `completed`）。
4. **计划内部偏离**：①`validated` 映射为 `verified`（计划写 `active`）；②`outcome.py` 新增计划里没有的策略键
   `min_verdict_mass`；③晋升不再写 `observation_count`（计划 §4.4 打算自增，现改为单一写入者）；
   ④v4 迁移（`loop_id`）不在计划 §五 的清单里；⑤计划 §4.2a 承诺的 `content/policies/outcome.json` 未创建。
5. 简报环境描述与实际不符之处：`@mohak34/opencode-notifier`（简报写 `@mohac34`）；另有 `opencode-conductor-plugin`；
   `permission:{"edit":"allow","bash":"ask"}` 未提及但关键（见 §7）。

---

## 7. 环境事实修正（比简报宽，直接影响裁决）

| 事实 | 证据 | 影响 |
|---|---|---|
| **basic-memory 启用且是活跃使用中的知识库**：`/home/shade/Documents/01-Learning/opencode-memory` 下 **52 个 md / 256K / 9 个编号目录**（00-index…90-archive），最近编辑就是今天 | `stat` 与 `find -newermt` `[Verified]` | 旧计划 §十一 的"enabled:false ⇒ 边界零成本"**双重过期**：不仅启用了，而且里面是人写的结构化知识。AOS Memory 与它的关系必须重新定义，而不是沿用"邻居"结论 |
| **`permission.edit` 是 `allow`** | `opencode.json` `[Verified]` | "personal-skills 写入需人门"**不能靠 opencode 权限兜底** —— 计划 §4.6 的白名单+`AOS_ALLOW_SKILL_EVOLUTION=1` 是唯一防线，必须在 AOS 侧实现 |
| **本机还有 supermemory，但不是常驻插件**：`command/supermemory-{init,login,logout,status}.md` 四条自定义命令，运行时 `bunx opencode-supermemory@latest` | `[Verified]` | 第四个记忆系统以"按需命令"形式存在。裁决 §2.3「Basic Memory 应成为什么」必须把它一起算进去 |
| `~/.config/opencode/memory.jsonl` 是**孤儿**：最后写入 2026-09-05，313 字节 1 条 entity 记录；已安装的所有包与 command/agents 里都 grep 不到 `memory.jsonl` | `[Verified]`（否定性 grep，覆盖面=cache/packages、config/node_modules、opencode-skill-tracker） | 不能当"第四套活跃记忆面"计入；记为 `[Unconfirmed] 归属`（写入者当前不在机器上） |
| 你的 `personal-skills` frontmatter **已经带触发子句**：`description: \|` 里是 `Use when: …` / `Avoid when: …` | `[Verified]` `skills/personal-skills/resume-evidence-chain/SKILL.md:1-7` | 与 AOS 为记忆发明的 `when_to_apply` 形状同构 ⇒ 张力 §2.2-2（自动 skill 演化相对人工蒸馏的增量价值）的答案更窄：人工流程已在做"适用条件 + 边界"，自动化只剩"从真实运行里发现缺口"这一段可能有增量 |
| 本机 skill-tracker 的遥测明显比计划里的 `aos skill report` 完整：`skills/skill_usage/mcp_usage/plugin_usage/plugin_inventory` 五表、`status∈success/error/denied/ask/unknown` 的**单调修正**（error 可覆盖乐观写的 success，反向永不）、`UNIQUE(session_id,call_id)` 幂等键 | `[Verified]` `opencode-skill-tracker/plugin/skill-tracker.js:107-204,278-300` | 张力 §2.2-4 的事实基础：重复造遥测没有价值，AOS 应做"遥测→证据"的推导层 |
| 可用钩子权威清单（本机 `@opencode-ai/plugin@1.18.4` 的 d.ts）：20 个钩子键；`permission.replied` 是**事件名不是钩子名**；另有此前未记录的注入面 `experimental.chat.messages.transform`（okdk 用它合成 user 消息） | `[Verified]` `~/.config/opencode/node_modules/@opencode-ai/plugin/dist/index.d.ts` | 旧计划 §1.5/§6.3 的钩子清单需更正；Plugin 边界章节要说明第二条注入通道存在但**建议不用** |
| `~/.local/share/opencode/opencode.db` = 1.7GB，可回读 `part.state.status`（error 235/16137）、`patch` parts(1109)、`todo.status`；但 `session.summary_files>0` 仅 1/199、`cost>0` 仅 5/199，`event` 表只有 5 种类型且**不含 session.idle/diff/error** | `[Verified]` 只读 SQL 聚合，零正文读取 | R-007 的可行性边界：冷路径补得上工具错误/diff/todo 三类证据，补不上"会话摘要即结果"这种假设 |

---

## 8. 遗留 `[Unconfirmed]`（需要运行或装载才能确认，本轮刻意不做）

1. 多插件同时注册 `experimental.chat.system.transform` 时的**执行顺序**（决定 §5.1/`R-008` 的实际危害大小）。
2. `okdk` 那种裸函数 `export default` 是否真导致整插件静默不加载（本机 skill-tracker 的注释记录了同形事故，但那是一次已修的历史事故）。
3. `message.part.delta` 在 1.18.33 是否仍发（autolearn v1 依赖它）。
4. `~/.config/opencode/memory.jsonl` 的写入者。
5. opencode 是否内建 `session_search` / `session_read` 工具（okdk 的 GEPA 第一步依赖它们）。
6. 随机测试顺序下的稳定性（`pytest-randomly` 未安装，属新增 dev 依赖决策）。
