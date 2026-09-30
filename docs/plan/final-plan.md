# Agent OS 收尾计划（final plan）

产出者：Stage 3。输入：`docs/decision/positioning.md`（裁决）、`docs/audit/current-state.md`（现状）、
`docs/architecture/agent-os-v2.md`（as-is 与缺陷登记 A–M）、`docs/research/*`（外部证据 R-001…R-008）。
本文是**执行契约**：每个 Phase 给验收屏幕、回滚点、文件白名单；不在表里的文件，该 Phase 不许碰。
标签沿用 `[Verified]/[Inferred]/[Judgment]/[Unconfirmed]`。

---

## 1. 裁决摘要与判据

**定位**：证据与治理层（候选 D）。Agent OS 只做四家都没做成的那一段 ——
`真实运行 → 合成结论 → 人门 → 晋升/降级 → 下次召回改变行为`；其余全部复用。 `[Judgment]`

**四条停止/降级判据**（原文 `positioning.md §6`，此处只重列编号，执行时每 Phase 末检查一次）：
1. 通电后 4 周内真实 observations（`source∈{hot,backfill}`）**< 30 条** ⇒ 停止新功能，仓库降级为
   `outcome.py` + 契约层 + `migrations.py` 三个可独立存活件 + 文档。
2. `review` 队列周均待标注 > 50，或连续两周标注数 = 0 ⇒ 主路径改成"回读 + 退出码"，人门只处理 `conflict/create`。
3. 任何能力若必须写 `~/.config/opencode/**`、或必须编辑他人写入的 `output.system` 元素才生效 ⇒ **直接放弃**，
   优先级高于 1 与 2。
4. 新增模块前必须在 `docs/research/open-source-capability-matrix.md` 指到一列"无人实现"；
   指到"已有更成熟实现"的 ⇒ 转只读适配或不做。

**推理纪律**：339 个测试与 v1→v4 迁移不构成继续的理由。本文之所以仍然有 KEEP 项，
依据是 `positioning §4` 的"三段无可替代物"，不是"已经写了"。

---

## 2. 归类表

### 2.1 现有模块

| 处置 | 对象（LOC `[Verified]`） | 依据 |
|---|---|---|
| **KEEP** | `core/outcome.py`(320)、`core/memory/{store,evolve,record,inject,migrations,policy,authoring}.py`、`contract/{schema,preflight,postflight}.py`、`cli/main.py`(715)、`core/loop/{lifecycle,stages,state}.py`、`core/evidence/*`(568)、`core/validation/*`(633)、`adapters/{base,host_delegate,test_provider}.py` | 它们就是那三段无可替代物的载体；`migrations.py` 的 append-only + 备份机制可独立存活（`positioning §5`） |
| **KEEP，但改实现** | `core/memory/retrieve.py`(403)、`core/memory/conflict.py`(122)、`core/memory/evaluate.py`(187) | retrieve 缺 status/scope 过滤（缺陷 A，实测）；conflict 是 O(n³) 全表重扫；evaluate 的排版打分必须保持 0.00 权重且不得进 verdict |
| **MERGE** | `store.set_observation_count` 的派生计数 → 统一由查询派生；`memories.observation_count` 与 `usage_stats` → 由 `retrieval_log`(linkage) 派生；`evidence.provenance` 的来源链 → 复用 memories 已有 6 个 source 列，不新建模块 | `R-002`（派生而非自增，4 家里有 3 家把计数器写成第二真相源）；`audit §5.2` 的同一病根 |
| **MERGE** | `routing/decision.py` 的 `memory_influence/memory_retrieved` 假字段 → 删除；`skill.skills_loaded`（恒 `[]` 却被校验）→ **从契约删掉**，将来要感知再说 | 缺陷 H、I；`R-006` 的"linkage 不是 outcome"同样适用于"字段不是数据" |
| **REMOVE** | `core/orchestration/*`(793) + `core/loop/team.py`(64) + `tests/test_orchestration.py`(286) + `core/orchestration/rules.json`；`adapters/opencode.py`(90) 及其在 `base.py:88` 的注册、`lifecycle/state` 的默认 `provider="opencode"` | 用户 2026-09-30 同意移除编排；结构性不可达（`router.py:384` 恒 ≤1 domain、`:396` 写死 medium，唯一读者就是编排）；opencode provider 是墙 3 的反方向通路且**无测试执行**（`grep OpenCodeProvider tests` 空） |
| **REMOVE（装饰品）** | `REVIEW_KINDS` 里零写入者的 `policy` / `skill_improvement`；`config.py:100` 的 `skills_dir`（`content/skills/` 根本不存在） | "预留但恒空"是研究里出现频率最高的失效类（`findings §12`、`audit §4.2/§5`） |
| **DEFER** | `routing/semantic_reader.py`(1157) 的精简；`before/after` 集合差；`evaluate.compute_quality_score` 的重新设计；trust 评分体系 | 1,157 行启发式的**唯一调用点**是 `router.py:324`，其输出（lures/contradiction）确实进 `_score_candidates`/`rules_applied` ⇒ 精简属于"为漂亮"，与"保架构、不做目录改名"的约束同级，排在闭环通电之后 |
| **NEW** | `aos/core/loop/pending.py`（session→loop 反查）；`aos/core/learning/{identity,dedupe}.py`（只装新逻辑，`memory/evolve.py` 不搬家）；`integrations/opencode/plugin/agent-os.js`；`content/policies/*.json`(6)；`aos/backfill.py`（只读） | 缺陷 B/C/D/E/G/K 的修复载体 + 通电的两条路 |
| **NEW，但只是命令** | `aos review sync`（或让 `label` 立刻跑门）、`aos doctor --json`、`aos memory refresh` | 缺陷 K/M 与"闭环必须人敲得动" |

### 2.2 旧计划的剩余项 → 本计划 Phase 映射

| 旧项 | 裁决 | 去处 |
|---|---|---|
| §4.3 去重/冲突/过期/来源 | KEEP，来源链 MERGE 进已有列 | P2（过期）、P3（去重/冲突/身份） |
| §4.4 使用反馈闭环 + status/scope 过滤 + Laplace 先验 | KEEP，计数改派生 | P2 |
| §4.5 路由/编排可达性六项（difficulty 派生、词汇翻译、rules 换血、task_cards 进 prompt、`--team`） | **REMOVE**（用户同意移除编排）；`difficulty` 列保留为元数据，契约键冻结并标 deprecated | P1 |
| §4.6 Skill governance（`sensing/skills.py`、`skill_versions`、白名单、`AOS_ALLOW_SKILL_EVOLUTION`） | **REMOVE**，只留"host 上报 skill 用了什么"这一条只读观测（走 `skill_used` 字段，已存在） | P1（删）/ P6（只读观测） |
| §4.7 证据时序 + pending + stage 卫生 | KEEP 三件（collect_before 上移、pending、fail/complete 与 recall 异常） | P5、P6 |
| §4.8 三个仓库级守卫测试 | **优先级升高** | P5 |
| Phase 4 插件 | KEEP，但第一版只有 ~20 行 | P6 |
| `aos skill report` 自建采集 | **REMOVE（取消）** | — |
| `--team` 命名问题 | **自动消解**（编排已删） | — |

---

## 3. MVP：一条人敲得动的链

今天（`b9dd2d6`）我实测跑到 **步骤 4 就断**，断因是缺陷 K。完整目标链与当前真实输出如下
（全部在 `AOS_STORE_DIR=<tmp>` 的临时库里跑，未触碰 `store/aos.db`）：

```
# 1) 召回不为空 —— 今天已经能看见
$ ./bin/aos preflight --payload '{"schema_version":"1.1","task_id":"T-2",
      "task":"修复 cache key 碰撞导致命中率下降的 bug","cwd":"/tmp/demo-project",
      "provider":"host_delegate"}'
  router.lead_skill: bugfix | category: bugfix
  retrieved: 3 | injection chars: 1274
  <agent_os> … - [M-SEED-CACHEKEY02 · failure · real_project_validated · high] 不要：…

# 2) 无 verdict 的运行 —— 已实现
$ ./bin/aos postflight --payload '{"…","loop_id":"LOOP-20260930123635-FD72"}'
  learning: {"candidates_recorded":0,"hypotheses_pending_review":1,"promoted":0,"needs_review":true}

# 3) 队列把信号与缺席都渲染出来，并告诉你下一步敲什么 —— 已实现
$ ./bin/aos review list
  #1 label loop=LOOP-…FD72 engine said=partial confidence=0.0 mass=0
     缺席: test_exit_code, build_exit_code, validation_status, tool_errors, todos_unfinished, diff, …
     -> aos review label 1 --outcome success|partial|failure

# 4) 人给出结论 —— 已实现，但归因过宽（缺陷 L：3 条 weaken 全给"在场"的记忆）
$ ./bin/aos review label 1 --outcome failure
  {"status":"labelled","candidates_created":3,"proposal_created":1,"observations_updated":4}

# 5) ★ 今天断在这里：标注之后队列里仍然 0 pending（缺陷 K）
#    必须再跑一次 postflight 才把上一步的候选扫进门 —— 实测出现
  #2 pending promotion M-6CC273A6   runs=1 quality=0.0
  #3 pending promotion M-E1051096   runs=1 quality=0.0

# 6) 人批准提案 —— 已实现（CAS + stale 保护）
$ ./bin/aos review approve 3 --as shade

# 7) ★ 今天也不成立：负向结论降级后，召回照旧（缺陷 A：retrieve 无 status/scope 过滤）
$ ./bin/aos preflight --payload '{"task":"…同一类任务…"}'
```

**MVP 的增量 = 让第 5 与第 7 步变成人眼可见的事实**，具体就是 P1→P4 的四件事：
门在标注后立即结算（K）、降级在召回侧生效（A）、同一任务重复失败只堆一条而不是 N 条（B/L）、
被召回不再自动等于被归因（L）。

**验收屏幕（MVP 完成定义，全部终端可见）**：
```
同任务失败 3 次 ⇒ `aos review list` 恰好 1 条 create 提案 pending（今天：3 条不同 id）
批准一条 weaken ⇒ 该记忆的 status/证据/decay 变化（今天已可见），**且下一次 preflight 的
                   <agent_os> 里不再出现它**（今天：仍然出现）
含 `</agent_os>` 的记忆 ⇒ 注入块闭合标签计数 = 1（今天：2）
```

---

## 4. Phase 划分

约定：每 Phase 一个 commit；`python3 -m pytest` 必须全绿才可提交；汇报固定五项
（修改文件 / 测试结果前后计数 / 行为变化 before→after / 风险与回滚 / 是否破坏既有契约）。
"Phase 未做完"的判据是**验收屏幕没跑出来**，不是代码写完。

### P1 · 收缩（只减不加）
删：编排 1,143 行 + `adapters/opencode.py`(90) + 两个预留 review kind + `config.py:100 skills_dir`
+ 两个假 DecisionContext 字段 + 契约里的 `skill.skills_loaded`（走 1.2 版本谈判：accept 1.0/1.1 时忽略该键）。
改：默认 provider `opencode → host_delegate`（`lifecycle.py:60,172,409`、`state.py:63,85,160`）；
`test_config.py` 的缓存回归测试改挂到 `policy.py`/`taxonomy.py`（**不能随编排消失**，它是 Phase 3.0 的唯一守卫）。
README §Multi-agent orchestration 与目录树同步删（删完 grep 名字，不留指向已删文件的 prose）。
- 验收屏幕：`grep -rn "orchestration\|OpenCodeProvider\|skills_loaded" aos tests README.md` = 0；
  `find aos -name '*.py'|xargs wc -l` 少 ≥1,230；`./bin/aos doctor` READY；测试数变化可被"删掉的用例数"逐条解释。
- 回滚点：单 commit revert（无 schema 变更 ⇒ 数据库不受影响）。
- 白名单：上面列出者 + `aos/contract/{schema,preflight}.py` + `tests/{test_orchestration,test_config,test_loop_lifecycle,test_contract,test_cli_contract}.py`。
- 契约影响：**破坏性**（删 `skill.skills_loaded`）。今日零已部署消费者 ⇒ 现在做成本最低，P6 之后不可做。

### P2 · 让学习作用到召回（生效化，缺陷 A/L）
`retrieve()` 加过滤：`status ∈ {active, verified}` 才进候选，`candidate` 只进 hypothesis lane 提示位；
`scope` 过滤（`global` + 当前 `project:<cwd 名>`，`session:` 只在同 session）；
`revalidate_after` 到期 ⇒ `verified→active→deprecated` 逐级降，注入行首标 `· 可能已过期`；
**归因分层**：`observations` 只记 loop 级；"在场"由 `retrieval_log`(memory_id, loop_id, score, rank) 派生；
`weaken` 候选必须来自"人标注的失败 + 该记忆被点名"或后续 `verify:` 证据，而不是"它被召回了"。
`usage_stats` 的 `success_rate/quality_bonus` 改读派生结果。 `[Judgment]` 本 Phase 无需迁移
（`retrieval_log` 列已齐：`schema.sql:102-113`）。
- 验收屏幕：`memory add` 一条 → `preflight` 能看到 → `UPDATE … status='deprecated'` → `preflight` **不再出现**；
  `scope=project:other` 的条目在本项目 preflight 中不出现；一次失败标注 ⇒ 不再产生 3 条无差别 weaken。
- 回滚点：单 commit；`retrieve.py` 的行为改变有固定输入回归测试对拍。
- 白名单：`memory/{retrieve,store,record,inject,policy}.py`、`tests/{test_memory,test_inject,test_learning_gate}.py`、`content/policies/retrieval.json`（可提前建，与 P4 一致）。
- 风险：改排序 = 改行为（中）。缓解：固定输入回归 + 一条"记录顺序改变后排序改变"的闭环存在性测试。
  第二个风险是**语义改名**：`memories.observation_count` 从"被召回且成功的次数"变成"被点名的次数"，
  而 `review list`/`memory list` 都在显示它 ⇒ 同一 commit 里必须把标签文字一起改，
  否则库里存的是新语义、屏幕上读的是旧语义（这正是 `R-002` 记的那类病）。

### P3 · 提案身份与判重（缺陷 B/C）
`aos/core/learning/identity.py`：create 提案的 `memory_id` 由
`sha1(scope + category + 规范化标题)[:8]` **确定** ⇒ `_create_review` 已有的
`pending_review_id(memory_id, kind="promotion")` 复用路径（`evolve.py:552-555`）立刻生效，不需要新机制。
`aos/core/learning/dedupe.py`：三层（fact-key 规范化 ⇒ `dedupe_key` 生成并落入已有 UNIQUE 索引
`uq_mem_dedupe(scope, dedupe_key)`；`difflib.SequenceMatcher` ratio ≥0.86 + tag/role Jaccard ⇒ reinforce 而非新建；
0.6–0.86 灰区 ⇒ 开 review）。冲突检测按 `scope+category` 分桶（把 `conflict.py` 从 O(n³) 降到桶内）。
冲突解决写 `supersedes` + 旧条目 `superseded`（与 P2 的过滤联动）。 `[Verified]` 无需迁移：列与索引都在 v2 建好了。
- 验收屏幕：同任务失败 3 次 ⇒ 队列 1 条 pending（今天实测 3 条不同 id）；
  手工插两条 `dedupe_key` 相同的记忆 ⇒ 第二条被 UNIQUE 挡；ratio 落在灰区 ⇒ `kind=conflict` 的 review。
- 白名单：`memory/{record,evolve,conflict,store}.py`、新 `core/learning/__init__.py|identity.py|dedupe.py`、`tests/test_dedupe.py`(新)、`tests/test_learning_gate.py`。

### P4 · 人门可用（缺陷 K/M）
`review label` 之后**立刻**跑一次学习结算（或提供 `aos review sync`），使"标完就看到下一步"；
`review list` 按 status 渲染（已标注的行不再提示 `aos review label`）；CLI 返回的 status 字面量与库里一致；
批量标注（`label --outcome` 接多个 id）；`aos doctor --json`（P6 的版本谈判靠它）；
`aos memory refresh`（派生计数与 decay 的手动重算入口）；`content/policies/` 落 6 个 JSON
（retrieval / decay / promotion / rejection / injection / outcome，键名与 `policy.py` 内置默认逐一对齐）。
- 验收屏幕：§3 的第 5 步不再需要"再跑一次 postflight"；`./bin/aos doctor --json | python3 -m json.tool` 通过；
  改一个 `content/policies/outcome.json` 里的阈值 ⇒ 不碰代码就改变 `needs_review`（这是 54 个叶子键第一次真的可调）。
- 白名单：`cli/main.py`、`memory/{evolve,policy}.py`、`content/policies/*.json`、`tests/test_cli_contract.py`。

### P5 · 证据时序、注入卫生与守卫网（缺陷 D/E/F/G）
`collect_before` 上移到 preflight（否则 `files_changed` 永远是脏树自 diff ⇒ Evidence 名不副实）；
`stages.py:191-193` 的 `fail`→`complete` 擦除改为保留失败事实；`recall_stage` 补 try/except 且失败可见；
`inject.py` 清洗正文中的 `<agent_os>`/`</agent_os>`（连同 `_render_item` 的转义）；
三个守卫测试：`test_no_third_party_imports`（零依赖的唯一可维持执行方式）、
`test_reachability`（写了不读 / 读了不写的自动拦截 —— 本轮新发现 3 个这种缺陷）、
`test_skill_boundary`（墙 1：`content/skills/` 不得回来、不得出现 skill 写路径）。
- 验收屏幕：三个守卫测试**先红后绿**，红的输出贴在汇报里（这是它们存在的意义）；
  含闭合标签的记忆 ⇒ `open=1 close=1`；`evidence.files_changed` 来自 preflight 快照。
- 白名单：`core/loop/{stages,lifecycle}.py`、`core/evidence/collector.py`、`core/memory/inject.py`、`tests/{test_evidence,test_inject}.py` + 3 个新测试文件。

### P6 · 通电：pending + 最小插件
`aos/core/loop/pending.py`：`preflight` 时写 `store/pending-postflight/<session_id>.json`（loop_id + 摘要），
`postflight` 成功后删除 ⇒ 同时补上 opencode 缺的两件事（session→loop 反查、崩溃后补记）。
`bin/aos preflight --session` 契约侧加 session 字段（additive，1.2 内）。
插件 `integrations/opencode/plugin/agent-os.js`：**只做三个钩子** ——
`chat.message`(或 preflight 触发点) → `experimental.chat.system.transform`(push 自己的元素) → `event/session.idle` → postflight。
`export default { id, server }`、每钩子 `safe()`、短超时、fail-open、**不阻塞 prompt**。
- 验收：见 §5 的开工门与 §6 的三性 fixture。**安装本身需要单独批准**（判据 3 + 本轮约定全程 fixture）。

### P7 · 真实数据：只读历史回读（默认关）
`aos/backfill.py`：`sqlite3.connect(f"file:{db}?mode=ro", uri=True)`（**不用 `immutable=1`**，存在活跃 WAL）；
复合高水位 `(time, part_id)`；**先检查源库存在，再执行任何 `--full` 清空**；列白名单；
不落任何对话正文（文档与库都不落）；`AOS_BACKFILL_DB` 未设置 ⇒ 完全不跑。
可反推的证据只有：`part.state.status='error'`(235)、`patch` parts(1,109)、`todo.status`(305)
—— 摘要类信号在本机大面积缺失（`summary_files>0` 仅 1/199）`[Verified]`，所以**回读不产出 verdict**，
只产出 linkage 与工具错误，仍需人标注或退出码来定结论。
- 验收：`observations` 出现 `source='backfill'` ≥30 条 ⇒ 此时才允许评估判据 1。

**顺序论证**：P1 必须第一（只减不加，把后面每一步的改动面缩小）；P2/P3 是"让已写的生命周期真的生效"，
先于任何新功能，否则新增的采集面接上的是一个不生效的下游；P4 让人门可被人类日常使用，先于 P6 通电
（通电带来队列，队列必须好标）；P5 在 P6 之前，因为插件一上，`files_changed` 与注入面的错误就会进入真实 prompt。

---

## 5. Phase 4（旧计划）开工门重校 = 本计划 P6 的开工门

| 旧门槛项 | 裁决 | 理由 |
|---|---|---|
| `test_reachability` | **保留，优先级升高** | 研究结论：这批项目的通病是"写了不读"；本轮仓库内新发现 3 个（A/C/K）。插件上线会把这类缺陷直接推进真实 prompt |
| `test_no_third_party_imports` | **保留** | 零依赖是共存性质的实现前提，不是风格 |
| `test_skill_boundary` | **保留，缩为两条断言** | 墙 1 已裁决不做 skill 侧 ⇒ 只需断言"无 skill 写路径""`content/skills` 不复现" |
| 全仓路径守卫（不写他人目录） | **保留并加严** | 判据 3；断言形式=fixture 里对 `~/.config/opencode/**` 的 mtime/内容零变化 |
| `aos doctor --json` | **保留，提到 P4** | 版本谈判靠它，但它是 CLI 项，不该等插件 |
| 契约校验恒真的两处（`skills_loaded`、`MEMORY_TYPE` 词汇换血） | **`skills_loaded` 在 P1 删字段；`MEMORY_TYPE` 保留新词汇并写进契约文档** | 前者是装饰品；后者 3.1f 已换完且有迁移，回退成本高于记账 |
| §4.5 路由/编排可达性六项 | **作废** | 用户 2026-09-30 同意移除编排 |
| `pending.py` 存在性 | **保留，P6 的第一件事** | `session.idle` 只有 sessionID，无反查就关不了 loop |
| 真实装载验证 | **默认不做，需单独批准** | 钩子执行顺序、`message.part.delta` 是否仍发等仍为 `[Unconfirmed]`（`audit §8`）；非干扰性质用 fixture 证明 |

---

## 6. Plugin 边界与共存

| 邻居 | 关系 | 约束 |
|---|---|---|
| `skill-tracker.js` | **共存，读它的表**（§7） | 不注册同名钩子之外的任何东西；不写它的 db |
| `@tarquinen/opencode-dcp@3.2.0` | 共存 | 它 `append` 到 `output.system[-1]`，并用 `systemPrompts[0]` 判内部调用而整轮跳过裁剪（`lib/hooks.ts:49-56,101-105` `[Verified]`）⇒ **AOS 只 push，绝不占 `[0]`、绝不编辑索引位、绝不重排数组** |
| `@mohak34/opencode-notifier`、`opencode-conductor-plugin` | 无关 | 不共享状态 |
| `basic-memory`（已启用，52 篇手写 md） | 只读邻居 | 不导入、不镜像、不统一检索、不做 `MemoryProvider` 抽象；将来引用某篇 ⇒ **引 id，不复制正文** |
| `supermemory-*`（四条按需命令）、`memory.jsonl`（孤儿） | 不算活跃面 | 不检测、不协调、不写入 |
| opencode 自带会话检索 | 复用 | AOS 不建会话索引 |

实现约束（P6 的硬门）：
1. **只用一个注入面** `experimental.chat.system.transform`；`messages.transform` 存在但架构上不用（可审计面只有一处）。
2. `export default { id, server }`；每钩子 `safe()`；Python 调用超时 ≤ 阈值且 fail-open；绝不阻塞 prompt。
3. **禁写清单**：`~/.config/opencode/**`（含 `opencode.json`、`plugin/`、`AGENTS.md`、`skill-stats-registry.json`）、
   任何 `personal-skills` 目录、任何项目源码。Agent OS 唯一的写处是 `store/` 与自己 `integrations/` 下的代码。
4. 注入块必须**清洗边界标签**（P5 的 D），使"host 幂等替换单个自标识元素"的前提成立。
5. 非干扰的证明形式：假 hooks 输入 ⇒ 断言其他组件的 `system` 数组、MCP 调用序列逐字节不变；
   停用后重启一次会话 ⇒ 与基线 diff 为空。真实装载行为一律标 `[Unconfirmed]`。

---

## 7. 与 skill-tracker 数据的整合

| 项 | 决定 |
|---|---|
| 写入者 | **skill-tracker，唯一**。AOS 不写任何遥测表 |
| AOS 读什么 | `skill_usage`（`skill`、`status`、`session_id`、`call_id`、`metadata.model/agent/branch`）、`mcp_usage`、`plugin_inventory`（`status/last_seen`）`[Verified] skill-tracker.js:107-204,278-300` |
| 怎么用 | 只做"遥测 → 证据"的推导：某 skill 在 N 次运行后 error 比率 ⇒ 生成**给人复核的候选/报告行**；永不据此自动改 skill（墙 1 + 张力 2） |
| 接口 | 环境变量 `AOS_SKILL_TRACKER_DB`（未设置 ⇒ 该证据源为"缺席"，与 `outcome.py` 的 mass 记账一致：缺席信号降覆盖率，不降结论） |
| 缺失/损坏 | 只读打开失败 ⇒ 记录 `telemetry.source_absent` 事件，行为退回"没有 skill 侧证据"，**绝不报错中断热路径** |
| 版本耦合护栏 | 列白名单 + `PRAGMA table_info` 先探后读；读不到预期列 ⇒ 降级而非猜。反面教材是现成的：okdk 用 `p?.error`/`p?.state==="error"` 读 `ToolPart`（真实字段 `state.status`/`state.error`）⇒ **探针静默永不触发**（`R-007`/findings Q1）。这条必须写成回归测试的必查项 |

---

## 8. 迁移与数据风险

- 现状：`store/aos.db` = **v4 / 13 条种子 memories / 其余表全空**，另有 `store/aos.db.pre-3.2-demo.bak`（gitignored）。
  ⇒ 没有历史数据，正是改 schema 唯一便宜的时机（旧风险表结论仍成立）。
- 纪律：`MIGRATIONS` **append-only**（即使步骤从未发布过，也加新步而不改旧步）；`PRAGMA user_version` 权威 +
  `schema_meta` 镜像交叉校验；破坏性步骤前 `Connection.backup()` 出 `.pre-v<k>.bak`。
- **本计划 P1–P5 预判不需要任何迁移**（缺陷 A/B/C/L 都能在既有列上解决：`dedupe_key`/`scope`/`status`/
  `supersedes`/`revalidate_after` 已在 v2 建好，`retrieval_log` 列已齐）。若实施中需要，走 v5 且单独提交。
- `R-002`（派生计数）的迁移前置：**先去重，才能建唯一索引**。P3 的 `uq_mem_dedupe` 生效前，
  库里若已有同事实不同 id 的条目必须先合并或让人裁决 —— 现在只有 13 条种子，人工核一遍即可，这是顺序上把 P3 放在通电之前的又一个理由。
- 已知不可逆：v2 的 `memory_lifecycle` 是破坏性重建。**退回代码不等于退回数据库**；对外文档必须写明
  （已写进 `agent-os-v2.md §12`）。
- 契约风险：P1 删 `skill.skills_loaded` 是破坏性变更。今日零已部署消费者 ⇒ 现在做；P6 之后不可做。
  其余 Phase 全 additive，`_TOP_LEVEL` 不动。
- 隐私：P7 只读 `~/.local/share/opencode/opencode.db`（1.7GB，含私人对话）。规则：列白名单、
  **不落正文**（库与文档都不落）、默认关、`mode=ro`。文档只引用聚合数字。

---

## 9. 仍待你决定的问题

1. `policy_versions` 进不进（`skill_versions` 已随张力 2 裁决删除，不再问）。`[Judgment]` 建议**不进**：
   Policy Evolution 现在缺的是那 6 个 JSON 文件（P4），不是版本表；先让人能调阈值。
2. `R-005` 的 `verify:` 执行面开不开（默认关）。建议保持默认关，直到 P7 有真实运行可对照。
3. 历史回读（P7）的默认值与开关命名：建议 `AOS_BACKFILL_DB`，未设置=不跑。
4. 真实装载验证何时批准（当前约定：全程 fixture；批准前插件代码只落仓库不 `ln` 进 `~/.config/opencode/plugin/`）。
5. P1 是否连同 `README.md` 的编排章节一起改写（我建议一起改，避免留下指向已删文件的 prose ——
   这条是你之前定的删除纪律）。
6. 已消解：`--team` 命名、personal-skills 自动改进（裁决为不做）、`aos skill report` 自建采集（取消）。

---

## 10. 完成定义

做到 P1–P5 后，"Agent OS 是什么"有了可演示的答案；做到 P6 后，它第一次接到真实运行；
做到 P7 后，判据 1 才有资格被检验。**任何 Phase 结束时如果 §6 的三性 fixture 或 §1 的四条判据不通过，
该 Phase 不算完成**，即使测试全绿 —— 测试数不是成功标准，屏幕上那条链才是。

```bash
# 全部 Phase 完成后，最终演示（一条命令序列，人敲得动，终端可见）
./bin/aos preflight  --payload '{"task":"…"}'        # 看到 <agent_os>
./bin/aos postflight --payload-stdin < run.json      # needs_review=true
./bin/aos review list                                # 信号 + 缺席 + 下一步
./bin/aos review label N --outcome failure           # 立刻出现提案
./bin/aos review approve M --as shade                # 人批准
./bin/aos preflight  --payload '{"task":"…同类…"}'   # 看到"不要…因为…"
./bin/aos review approve K --as shade                # 批准 weaken
./bin/aos preflight  --payload '{"task":"…"}'        # 该条**不再出现** ← 今天的仓库做不到这一步
```

---

## 11. Phase 执行日志

每 Phase 完成后在此追加：结果计数、验收屏幕是否达成、**偏离白名单/计划之处**。
这份日志是计划的一部分，不是额外文档 —— 它存在的理由是本仓库已经有过
"提交信息与实现不符"和"计划预测没兑现但没人记账"的前科（`docs/audit/current-state.md §6`）。

### P1 · 收缩 — 已完成

- 测试：339 → **313**（删 `tests/test_orchestration.py` 的 27 个用例，加 1 个守卫测试；
  逐项可解释，且逐文件计数之和与全量运行相等）。
- 面积：`aos/` 11,250 → **10,265** 行 Python。
- 契约：`CONTRACT_VERSION` **1.1 → 1.2**，`SUPPORTED_VERSIONS` = `("1.0","1.1","1.2")`。
  兼容性论证（写进 `schema.py:13-19` 的注释）：被删的 `skill.skills_loaded` 唯一取值一直是 `[]`，
  所以没有任何 host 能观察到行为差异；版本仍然要动，因为文档形状动了，
  而且这样"想把键要回来"的 host 有一个版本号可指。
- 行为对拍：同一 payload 在 P1 前后跑 `preflight`，`aos_status / lead_skill / lead_role / warnings / retrieved`
  逐项相同 ⇒ 删除没有改变外部行为（这是"只减不加"的验收形式）。
- 验收屏幕：`grep -rn "orchestration|plan_executor|team_id|task_cards|OpenCodeProvider|skills_loaded|skills_dir|knowledge_dir" aos tests`
  ⇒ 只剩三处**刻意保留的说明性文字**（`schema.py` 的版本注释、两个具名守卫的 docstring）。
- 缺陷 H、I 关闭；新登记缺陷 **N**（`degraded` 可以不带任何 warning），排期 P4。
- **偏离之处（三条，如实记录）**：
  1. 白名单只写了 `skills_dir`，实际同时删了 `knowledge_dir` + `ENV_KNOWLEDGE_DIR`。
     理由是同一类缺陷（只有声明、零读者），留着就是刚删完一个又留一个。
  2. P1 声称"只减不加"，实际加了 1 个测试：
     `tests/test_contract.py::test_1_2_drops_the_field_no_producer_ever_filled`。
     它钉住的是**删除本身**（防止恒空字段作为装饰品回来），属于删除的收尾而非新功能。
  3. README 的「Multi-agent orchestration」章节没有直接删空，替换成一小节
     「What the engine deliberately does not do」，把四条边界（不编排、不驱动 host、不做第二套 skill、不写遥测）
     写成一处可指的文本，而不是只存在于没有文件的空白里。
- 回滚：单提交 revert 即可；无 schema 变更 ⇒ `store/aos.db` 不受影响。

### P2 · 让学习作用到召回 — 已完成

- 测试：313 → **323**（+6 个过滤/过期用例、+1 个"被召回不加分"用例、+1 条负向学习端到端；
  其余是既有用例改语义而非删除）。`./bin/aos doctor` READY。
- schema：**零迁移**，与计划预判一致 —— `status`/`scope`/`revalidate_after` 列与 `retrieval_log`
  在 v2/v4 就已建好，缺的一直是"没人过滤、没人生成"。
- 验收屏幕（临时库，同一 task 文本只换 cwd 与 status）：
  `[1] 同项目 warehouse -> retrieved 1 | chars 253` ／ `[2] 另一个项目 billing -> retrieved 0` ／
  `[3] 降级之后再问一次 -> retrieved 0`。第一段在 P2 之前是 `retrieved 1`，第三段之前**也是 1**（缺陷 A）。
- 策略地基提前：`content/policies/retrieval.json` 落地，与内置默认逐键相等 ⇒ 中性的；
  但把 `min_score` 改 0.99 ⇒ 召回 3→0，`top_k` 改 1 ⇒ 恰好 1，全程不改代码。
  42→**54**：审计与定位文档里的"42 个键"是错的，已按 `DEFAULT_POLICIES` 递归叶子计数更正（四处）。
- 行为变化的完整清单（不止屏幕上那三段）：
  ① `retrieve()` 只放行 `policy.recall_statuses`（默认 `active|verified`）；
  ② scope 过滤生效 ⇒ **`project:AgentOS` 的 8 条种子不再漏进别的项目**，host 实际看到的内容变少；
  ③ per-memory observation 停写 ⇒ 一次运行一条 loop 级观测；
  ④ `usage_stats` 拆成 linkage（`usage_count`）与 earned verdict（`success_rate`，只算 `needs_review=0`）；
  ⑤ 自动路径的候选要求归因（host 上报的 `skill_used` 对上记忆的 category/tags）；
  ⑥ `memories_used` 现在包含 hypothesis lane —— 提示行也是注入进 prompt 的内容，
     失败时同样可以被归因，否则负向学习对人能看到的 hint 永远无牙。
- 计划本身需要修正的一处：§3 的 MVP 屏幕写"批准 weaken ⇒ 下次不再出现"。实情更窄 ——
  `decide_promotion` 只在**已在证据阶梯底部或已 deprecated**时才写 `status='deprecated'`，
  所以对强证据记忆，weaken 的效果是"降一档证据 + decay"，不是消失。端到端用例因此用
  hypothesis-lane 记忆来证明"退役即不再出现"，并把强证据记忆的那一半留在 §4 的 decay 语义里。
- **偏离白名单之处（三处，都是被自己的改动逼出来的，不是顺手扩展）**：
  1. `aos/core/loop/stages.py`：把 `scope_project`/`scope_session` 放进 recall query、
     把 `skill_used` 的来源从"引擎自己的路由标签"改成"host 上报"、`memories_used` 并入 hypothesis ids。
     不放进去，scope 过滤就成了没人喂参数的死参数 —— 正是本 Phase 要消灭的形状。
  2. `aos/core/memory/evolve.py`：`group_candidates` 的"独立运行数"原来数的是 per-memory observation，
     停写之后它恒为 0 ⇒ 晋升路径会静默停止工作。改为数 `store.linkage_by_memory()`。
  3. `aos/core/memory/evaluate.py`：A/B 对比的 used_loops 同上改读 linkage；
     `evaluate_all` 的候选集也从"有 per-memory 观测的记忆"改成"有判定 linkage 的记忆"，
     否则它会返回空列表而不报错 —— 一个永远为空的报告比错误的报告更难发现。
  另：`skill_used` 来源的改变使 `observations.skill_used` 列的语义从"路由标签"变为"host 上报"，
  P5 的守卫测试与 P6 的插件必须按新语义对待它。
- 回滚：单提交 revert；`content/policies/retrieval.json` 与内置默认等值，删除它也不改变行为。
### P3 · 提案身份与判重 — 已完成

- 测试：323 → **338**（新增 `tests/test_dedupe.py` 15 例）。`doctor` READY。schema：**零迁移**（与预判一致）。
- 面积：`aos/core/learning/`（`identity.py` 78 + `dedupe.py` 164 + `__init__.py` 6）落地，
  只装新逻辑，`memory/evolve.py` 未搬家（P1 已裁决）。`aos/` 10,265 → 11,073 行。
- 三段验收屏幕全部在终端跑出来：
  ① 同任务失败三次 ⇒ **一条**评审：`#1 pending promotion M-9C4C248E runs=3（提案提出后又收集到 2 次）`；
  ② 同 scope 同事实第二次 ⇒ `同一事实已存在：M-0AC7CE6C 「Java 17 是本项目运行时」… 退出码 2`（不是 traceback）；
  ③ 灰区（实测 title ratio=0.604，tag 重叠 0.0）⇒ `pending conflict`，批准后
     `M-0245234C -> superseded` / `M-CEA71DED 取代它（active，evidence 仍 hypothesis）`。
- 顺带把 `conflict` 这个 review kind 从"预留枚举"变成**有写入者、有裁决语义**的东西 ——
  P1 删掉 `policy`/`skill_improvement` 而留下 `conflict` 的理由在这里兑现。
- 冲突扫描的复杂度：`run_learning` 原来对每个候选组重扫全表（O(组数 × n²)），
  现在每周期扫一次并用 `conflict.index_by_id` 建索引；`test_conflicts_are_scanned_once_per_cycle_with_the_same_results`
  钉住"结果集与逐 id 扫描一致"，所以这是性能修复而非语义收窄（分桶收窄只用在 dedupe 的候选集上，那里同 scope 是定义的一部分）。
- **实施中被测量推翻的两次自我设计（如实记录）**：
  1. 原打算让 tag 重叠把灰区提升为合并（`lifted`）。这与计划自己的"灰区交人"直接矛盾，
     且同一个主题下的两条不同主张（"输入要先归一化" vs "加命名空间前缀"，tag 全同）会被静默删掉一条 —— 删掉。
     tag 重叠改为**只报告不参与判决**。
  2. 相似面从 `title + body` 改成 `title`：提案 body 是模板句（`任务「…」的结果：failure。`），
     把同一事实的 ratio 压到最高 0.24，灰区与"新事实"因此不可分；只看 title 实测拉开 0.34 / 0.604 / 1.00。
     完全重复仍由 fact key 兜住（key 含 body）。
- **偏离白名单之处（一处）**：`aos/cli/main.py`。原因不是顺手扩展，而是我这个 Phase 自己造出的洞 ——
  通用评审渲染对 `kind="conflict"` 会打印 `批准后: nothing`，而批准实际会取代一条记忆；
  这违反本仓库最硬的那条性质（评审展示的与写入的必须是同一件事）。同一提交里还补了
  `runs_now`：确定 id 让同一提案跨运行复用同一条评审后，`validation_runs` 变成"开评审那次的快照"，
  人看到的 1 次可能是 3 次证据 —— 新增 `store.evidence_loops_by_review()` 把当前计数显示出来。
- 屏幕之外的一处诚实边界：`classify()` 的灰区在**自动提案 × 模板散文**的组合下仍可能落到 `new`
  （title 相似但被模板稀释），此时保护来自第①层 fact key 与人门，而不是相似度 ——
  所以 §3.4 的"三层"里，第②层是降噪手段而非安全边界，架构文档按这个口径写。
- 回滚：单提交 revert；零 schema 变更 ⇒ `store/aos.db` 不受影响。

### P4 · 人门可用 — 已完成

- 测试：338 → **349**（`tests/test_cli_contract.py` +9 条命令面用例、`tests/test_config.py` +1 条策略键守卫）。
  schema 仍 **v4**，零迁移。
- 缺陷 J、K、M、N 一次关闭。
- 验收屏幕：
  ```
  # 标完就看到下一步（K）
  $ ./bin/aos review label 1 --outcome failure
    {"status":"approved","learning":{"candidates":1,"reviews_created":1,...}}
  # 队列不再问已经答过的问题（M）
  $ ./bin/aos review list | grep 已标注
      已标注: failure（approved）
  # 一次答完整排（批量 + 拒绝说明）
  $ ./bin/aos review label 1 2 3 --outcome failure
    {"labelled":[1,2,3],"skipped":[]}
  # 握手文档（J，插件用）
  $ ./bin/aos doctor --json | python3 -m json.tool   → contract_version / supported_versions /
    schema.{expected,installed,pending} / paths / memories{total,recallable,without_dedupe_key} / reviews / candidates
  # 派生态对齐（J 的另一半 + P3 遗留的回填）
  $ ./bin/aos memory refresh
    补齐 dedupe_key: 13 条 ／ 重算判定计数: 5 条 ／ 衰减: degraded 13
  $ ./bin/aos doctor --json → without_dedupe_key: 0      （幂等：第二次全 0）
  # 过期逐级降级，不删（verified→active→deprecated，两次跑到位）
  # 阈值不调代码（P4 的存在理由）
  outcome.json 的 min_auto_confidence 0.6 → 0.0 ⇒ 同一无人判定的运行 needs_review True → False
  ```
- 反向验证做了一次：往 `content/policies/outcome.json` 塞拼错的 `min_auto_confidance` ⇒
  守卫测试转红；还原 ⇒ 绿。所以那条守卫不是装饰。
- **偏离与超出计划之处（四条，如实）**：
  1. `store.update_memory_fields` 原本**静默丢弃**白名单外的字段，现改为抛 `ValueError`。
     起因是我自己踩到：给某条记忆设 `revalidate_after` 时"成功"返回、字段却没写进去，
     于是过期阶梯整段不触发 —— 白名单是安全属性（学习不得改写 title/body），静默吞掉不是。
  2. 加了计划没点名的 `aos review sync`：`label` 已自带结算，但任何**其它**写入候选的路径
     （直接 `record_outcome`、导入历史、未来回读）仍需要一个手动结算口，否则缺陷 K 只是换了个入口。
  3. `doctor --json` 顺手把 `_schema_line` 重构为共用 `_schema_state()`：人类那行与 JSON 必须来自
     同一份事实，否则两个视图会各自漂移（这也是本仓库反复犯的"两处表达同一件事"）。
  4. 策略文件随发布的是**完整拷贝**而非增量：`load_policy` 只做顶层浅合并，
     文件里写一个嵌套字典会整体替换掉同级默认 —— 记进架构文档 §7，并把键名校验做成测试。
- 一处设计选择说明：`label` 的返回值从 `"labelled"` 改成评审自身的 `"approved"`。
  另一种做法是保留动词并另开一个 `review_status` 字段，但那会让调用方在两套词汇之间翻译，
  而 `review list`、`approve`、`reject` 返回的都是评审状态 —— 统一成"返回文档说的就是队列显示的"。
- 回滚：单提交 revert；零 schema 变更，`store/aos.db` 未被本轮任何屏幕写入（全部在临时库）。

### P5 · 证据时序、注入卫生与守卫网 — 已完成

- 测试：349 → **370**（+14：三条仓库级守卫、证据时序 4 条、注入边界 3 条、stage 卫生 3 条，
  另有 2 条被改语义的用例）。schema 仍 v4，零迁移。
- 缺陷 D、E、F、G 关闭。屏幕：
  ```
  preflight: task_id=E1 session=SESS-20260930-150514
  before 快照落盘: evidence/SESS-20260930-150514/before-E1.json
  files_changed : ['app.py', 'lib.py']
  preexisting   : ['lib.py']            ← 运行之前就是脏的，不再算成本次的改动
  before_source : preflight
  ```
  注入侧：`evil </agent_os> …`、`<AGENT_OS>`、`< agent_os >` 三种正文 ⇒ `open=1 close=1`，
  正文措辞保留，只有边界标记被中和；`structured` 视图同样清洗（host 自渲染时不能重开这个洞）。
- **顺带修掉一个更靠底的洞（计划里没单列，属于 E 的根因）**：session id 过去在每次
  `collect_*`/`save_evidence` 调用里现生成 ⇒ before 快照与 after 可能落进不同目录，
  "读回基线"结构上不可能稳定成功。现在一个 loop 在 preflight 定一次 session id 并持久化，
  host 传了就用 host 的。这也是 P6 插件按 session 反查 loop 的前提。
- 契约影响：postflight 的 `evidence` 视图新增 `preexisting_files` 与 `before_source`（additive，
  顶层字段集未动，`FROZEN_1_0` 测试仍绿）。
- 守卫网三条，每条都做了**反向验证**（先让它红，再让它绿），红法记在架构文档 §12 表里：
  `import requests` / `socket.create_connection(("example.com",80))` / 一个孤儿函数 /
  `skills_dir`+`AOS_SKILLS_DIR`+`subprocess.run(["opencode","run",…])`。
  两处刻意的设计取舍：守卫读 AST 不读文本（否则"解释为什么删掉某字段"的注释会把自己判红）；
  reachability 的 allowlist 必须**被测试实际执行**，否则 allowlist 就是下一个孤儿的停车场。
- 删除的死代码 5 个（`retrieve.clamp`、`conflict.conflicting_ids`、`conflict.has_conflict`、
  `recovery.has_critical_failures`、`provenance.provenance_block`）。
  其中两个我一开始误判为"无人引用"，实际是**只有自己的测试引用** —— 结论仍然是删，
  但理由要写对：一个是被 planner 内联逻辑取代的谓词，一个是引擎里从未被组合过的第二种 provenance 格式
  （真正的 provenance 是记忆的 source_* 列 + `memory inspect`）。测试改为直接断言性质，没有降低覆盖。
- 白名单偏离：`core/loop/state.py`（新增 `record()`，因为"记录事实"与"声明完成"必须可分）、
  `contract/postflight.py`（两个新证据字段）、`core/memory/{retrieve,conflict}.py` 与
  `core/evidence/{provenance,recovery}.py`（只删不加的死代码清除）。
  三者都是被 P5 自己的修复逼出来的：before 快照需要 session 与"未完成也记数据"的原语，
  证据归属需要契约能说出"哪些不是本次改的"，守卫上线后孤儿必须真的清掉而不是加注释。
- 回滚：单提交 revert；零 schema 变更，dev `store/aos.db` 未被触碰。

### P6 · 通电：pending + 最小插件 — 已完成（**未安装**）

- 测试：Python 349 → **382**（+9 pending 语义、+3 插件接缝/契约漂移、+1 跑 node 的守卫），
  另有 JS **13** 例（`node --test tests/js/plugin.test.mjs`）。schema 仍 v4。
- `store/pending-postflight/` 第一次有了写入者与读取者（审计里那条"声明了但零读写"就此关闭）：
  preflight 落 `pending-<session>.json`、postflight 删除、`aos pending --session … --json` 是唯一的
  session→loop 反查接口、`doctor --json` 报 outstanding/unreadable/oldest_hours。
- 插件只有三个钩子 + `dispose`，`export default { id, server }`，每钩子 `safe()`，
  超时默认 1200ms，任何失败都"这一轮不注入"而不是拖住 prompt；
  没看到的信号保持**缺席**（不写 `tool_errors: 0` 这种假装干净的数字），缺席在 P2 的 mass 记账里
  就是覆盖率下降 ⇒ 交给人，这是两半设计对上的地方。
- 三性的证明形式（都是断言，不是宣言）：未配置 root 时 `output.system` 与基线**逐字节相等**且
  假引擎记录**零次调用**；启用时数组长度 +1、原元素原样、不占 `[0]`、同一段文本重复 transform 不叠加；
  重启后不猜文件格式而是 `aos pending`；测试夹具里插件自己不创建任何文件。
- 实施中被测出来的真实缺陷（值得记，因为它决定插件上线后是否会静默失效）：
  `execFile` 的 `input` 选项在本机不会把 EOF 送进子进程 ⇒ 每次调用都等到超时 ⇒ 表现是
  "插件在、什么都不注入、也不报错"。JS 测试先红在此，传输层改为显式 `spawn` + `stdin.end()` + 自管 kill。
- 契约漂移现在有守卫：`test_every_field_the_plugin_sends_is_one_the_engine_reads` 断言
  `warnings == []`（引擎不读的关键会点名返回），未知键那条用例断言它**被点名**。
  JS 与 Python 两半因此不能各自漂走。
- **偏离与诚实边界**：
  1. 白名单里原本只有插件与 `pending.py`，实际还改了 `cli/main.py`（`aos pending` 命令）与
     `contract/postflight` 无关；新增 `tests/js/`（13 例 + 一个假 `aos`）。
  2. 没有安装、没有链接、没写 `~/.config/opencode/**`、没有启动 opencode ⇒
     钩子执行顺序与 `tool.execute.after` 的真实 payload 形状仍是 `[Unconfirmed]`，
     这两项必须在真实装载时确认，装载需要单独批准（判据 3 优先于功能）。
  3. 插件**不**读 skill-tracker 的 db、不注册工具、不碰权限钩子、不使用
     `experimental.chat.messages.transform` —— P7 的"遥测→证据"若要做，也在引擎侧只读文件/命令，
     不给插件加第二块地盘。
- 回滚：单提交 revert；插件留在仓库里不构成"已启用"，删除它也不需要 host 侧任何动作。
