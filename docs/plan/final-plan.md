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
1. 通电后 4 周内真实 observations（**只数 `source='hot'`**）< 30 条 ⇒ 停止新功能，仓库降级为
   `outcome.py` + 契约层 + `migrations.py` 三个可独立存活件 + 文档。
   （P7 修正：原文写 `source∈{hot,backfill}`，但一次回读就产出 174 条 `[Verified]`，按字面已被伪满足 ——
   回读是"读来的历史"，不是"这套层通电后收到过运行"的证据。`doctor --json` 按来源分项计数正是为了让人数得对。）
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
  **P7 执行时的纠正**：这条写反了 —— 回读条数达标并不"允许评估判据 1"，它使判据 1 **失去意义**，
  因为 174 条读来的历史会把它 trivially 满足。验收改成看两条屏幕：回读落库但不进人门、不改召回；
  判据 1 只数 `source='hot'`（见 §1 同一处修正）。
- 白名单（P7 开工时本节未列，补在这里以说明改动面）：`aos/backfill.py`（新）、
  `aos/core/memory/migrations.py`（v5，纯追加）、`aos/core/memory/store.py`（水位读写 + 按来源过滤/计数）、
  `aos/cli/main.py`（`backfill plan|run` + `doctor --json` 的 observations 分项）、
  `tests/test_backfill.py`（新）、`tests/test_migrations.py`。
- 回滚点：单 commit revert。v5 是追加式 ⇒ 旧代码在同一库上仍可读写（`source` 有默认值 `hot`）。
  **但**回滚后库里已有的 `source='backfill'` 行会被旧版当成待标注运行灌进人门，
  所以回滚的正确顺序是先 `DELETE FROM observations WHERE source='backfill'`（或保持 `AOS_BACKFILL_DB` 不设，
  它本来就是默认）。

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
  **实际**：P7 需要 v5（`observations.source` 列 + `backfill_state` 表，纯追加），它**没有单独成 commit**，
  与 P7 其余改动同批 —— 记在这里作为偏离；分开提交会造出一个"schema 有、代码没有"的中间态。
  开发库 `store/aos.db` 至今仍是 **v4**：P7 的屏幕全部写在临时库里，它会在第一次真实运行时自己升到 v5。
- `R-002`（派生计数）的迁移前置：**先去重，才能建唯一索引**。P3 的 `uq_mem_dedupe` 生效前，
  库里若已有同事实不同 id 的条目必须先合并或让人裁决 —— 现在只有 13 条种子，人工核一遍即可，这是顺序上把 P3 放在通电之前的又一个理由。
- 已知不可逆：v2 的 `memory_lifecycle` 是破坏性重建。**退回代码不等于退回数据库**；对外文档必须写明
  （已写进 `agent-os-v2.md §14`）。
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
P7 只给它读到**历史**，判据 1 仍然要等 `source='hot'` 的运行长出来才有资格被检验
（见 §1 的 P7 修正）。**任何 Phase 结束时如果 §6 的三性 fixture 或 §1 的四条判据不通过，
该 Phase 不算完成**，即使测试全绿 —— 测试数不是成功标准，屏幕上那条链才是。

```bash
# 全部 Phase 完成后，最终演示（一条命令序列，人敲得动，终端可见）
./bin/aos preflight  --payload '{"task":"…"}'                 # 看到 <agent_os>
./bin/aos postflight --payload-stdin < run.json               # needs_review=true
./bin/aos review list                                         # 信号 + 缺席 + 下一步
./bin/aos review label N --outcome failure --skill bugfix      # 结论 + 归因；立刻看到候选与提案
./bin/aos review approve M --as shade                          # 人批准提案
./bin/aos preflight  --payload '{"task":"…同类…"}'            # 看到"不要…因为…"
./bin/aos review approve K --as shade                          # 批准 weaken（rank 下降）
./bin/aos preflight  --payload '{"task":"…"}'                 # 该条**不再出现**
```

2026-10-01 这条链在真实形状的数据上跑通了（写在 `/tmp/aos-chain/store` 副本库，真库未被这些运行污染）：
同一任务 3 次运行 ⇒ 3 条 `outcome_label`；`--skill bugfix` 标注 2 次 ⇒ 每条被召回记忆 2 个 weaken 候选
⇒ 门排队 3 条 promotion；批准后 `M-SEED-CACHEKEY02` 的 rank 1→3、分数 0.387→0.262；
**第 5 次**批准才 `active → deprecated` 并从注入块里消失（每秩只降一档，见 §12 Z 行）。
最后一行原话"今天的仓库做不到这一步"到此作废。

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
- 守卫网三条，每条都做了**反向验证**（先让它红，再让它绿），红法记在架构文档 §13 表里：
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

### P7 · 真实数据：只读历史回读 — 已完成（**默认关**，本机未启用）

- 测试：Python 382 → **396**（+14：`tests/test_backfill.py` 13 例 + `doctor` 的按来源分项 1 例），
  JS 仍 13 例。schema v4 → **v5**（追加式：`observations.source` 列 + `backfill_state` 表 + 索引）。
  迁移用例进 `tests/test_migrations.py`：断言 v5 纯追加、不改动既有行。
- 屏幕（源库 = 真实 `~/.local/share/opencode/opencode.db` 1.7GB / 199 会话 / 61,790 part，
  写入的是 `/tmp` 临时库；跑完源库与开发库 md5 逐字节相等 `[Verified]`）：
  1. `aos backfill plan` ⇒ `sessions_total: 199, with_evidence: 174`，且**临时库里连 db 文件都没被创建**
     （plan 零写入是屏幕证明的，不是断言声明的）。
  2. `backfill run --apply` ⇒ `written: 174, skipped_without_evidence: 25`，
     水位 `(1790762360092, ses_f0e43306dffehgI0IQwfd3K6Q2)`。
  3. 紧接着第二次同一命令 ⇒ `sessions_seen: 0, written: 0` —— 增量走水位，不重读。
  4. `doctor --json` ⇒ `observations: {"backfill": 174}`（**没有 total**）、`reviews.pending: 0`、
     `candidates.open: 0`、`retrieval_log`/`memories` 均 0 —— 174 条历史没有灌满人门，也没有假装成记忆。
  5. `AOS_BACKFILL_DB` 指向一个不存在的库 + `run --apply --reset` ⇒ `ok:false` 且**174 行仍在**：
     "先开源、后清空"这条顺序是屏幕可见的，它才是 `--reset` 的唯一保护。
  6. `AOS_BACKFILL_DB` 不设 ⇒ `{"enabled": false}` + exit 0 —— 默认关不是注释里的承诺。
- 落库内容的形状（隐私边的可核对形式）：信号只有 8 个键
  `agent, diff, files_changed, model, origin, project, todos_unfinished, tool_errors`；
  174 行共 1,392 个值，**最长 41 字符**（一个项目名 `AI-Interview-Practice-and-Feedback-System`），
  >60 字符者 0 个、含 `/` 者 0 个、含中文正文标记者 0 个。每行 `outcome='partial'`、`needs_review=1`、
  `memory_id IS NULL`、`source='backfill'`。其中 56 个会话带工具错误、27 个有 patch 证据 —— 这就是
  计划里预判的"可反推证据只有 error/patch/todo 状态"，实测吻合 `[Verified]`。
- 实施中被测出来（且都进了测试）的真实缺陷：
  1. **`session.model` 是 JSON 对象**（`{id, providerID, variant}`），原样搬运等于把别人的完整模型配置
     抄进我们的库。改成 `COALESCE(json_extract(model,'$.id'), model)`，并在 `plan` 的 probe 里报告该
     表达式是否可用（json1 缺席时降解而不是失败）。
  2. **同一毫秒内的兄弟行会被单时间戳游标静默跳过** ⇒ 水位改成 `(time_updated, id)` 复合比较；
     `test_sessions_sharing_a_timestamp_are_not_skipped` 钉住它。
  3. **一个畸形 part JSON 会让整条 SELECT 崩掉**（解析发生在 Python 侧）⇒ 按会话隔离解析并计
     `parts_unreadable`，坏数据降解为"未知"，不降解为"干净"。
  4. **`Path("")` 等于 `PosixPath(".")`** ⇒ "没配置源"看起来像"源文件不存在"，报错文案因此是假的。
     改成 `Optional[Path]`，未设置为 `None`。
  5. **回读一次就伪满足判据 1**（174 ≥ 30）。这是判据的缺陷不是代码的缺陷，登记为架构文档缺陷 P，
     修法是计数按来源分开 + 判据只数 `source='hot'`（§1 与 §4 已就地改正并注明）。
- **偏离与诚实边界**：
  1. 白名单本节原本没写，实际改动面见上（`backfill.py`/`migrations.py`/`store.py`/`cli/main.py`/两个测试文件）；
     其中 `store.py` 与 `cli/main.py` 是为水位与计数通电的最小改动面，没有新能力。
  2. v5 没有按计划"单独提交"，随本 Phase 同批提交（理由记在 §8）。
  3. **开发库没有被回读**：`store/aos.db` 仍是 v4 / 13 条种子 / 其余表全空。回读是**可选**的入口，
     要不要开、开在哪个库上是用户的决定，不是本仓库的默认状态。`AOS_BACKFILL_DB` 未设 ⇒ 这条通路完全不存在。
  4. 源库结构仍是 `[Unconfirmed]` 意义上的"外部契约"：它没有版本号，opencode 一次升级就可能让
     `part.state.status` 换层级（okdk 犯过的错）。这里的对策是 probe + 降解，**不是**跟进适配。
- 回滚：单提交 revert。v5 纯追加 ⇒ 旧代码在同库上照跑；唯一残留是 `source='backfill'` 的行会被旧版当成
  待标注运行灌进人门，所以回滚顺序是先删这些行（或保持默认：不设 `AOS_BACKFILL_DB`）。

### 计划后 · 第一次把命令跑在真实库上（2026-10-01，用户批准执行 `memory refresh`）

P1–P7 的验收屏幕全部写在临时库里，所以"跑在开发库上"是这套层第一次接触**已有数据的真实状态**。
两个只有这时才暴露的东西：

1. **缺陷 Q**：`aos memory refresh` 把人门的降级撤销了。`M-SEED-EXPORT8` 三次 weaken 后
   `decay_factor=0.512`，一次 refresh 变回 `0.85` —— `decay_factor` 有两个写入者，衰减 pass 是**赋值**。
   正确规则当时就写在 `evolve.py` 的注释里，只是没变成代码。修法见架构文档 §12 Q 行
   （`min(重算, 库里)` + 只在变化时写入 + 报告值等于持久值 + 两条具名测试）。
   教训进本计划：**"屏幕跑过了"不等于"跑过了"**，跑的是 fixture 时，凡依赖既有数据状态的路径都还没被验证。
2. **本文 §3 第 1 步屏幕已经过期**：它写 `cwd=/tmp/demo-project`，而 P2 之后 scope 过滤会拒绝把
   `project:AgentOS` 的经验拿到别的项目去 ⇒ 从别处敲是 `retrieved: 0`，**这是设计而不是回归**。
   在项目目录里原样复现：`retrieved: 3 | injection chars: 1274`。
   另记一次自己的误判：中途我用结果里并不存在的 `score` 键读召回，读到 0 便怀疑召回被打断 ——
   那是探针错，引擎侧的 `final_score` 是 0.393/0.274。

refresh 本身在开发库上的净效果（改动前已备份 `store/aos.db.pre-refresh.bak`）：
schema v4→v5、13 条 `dedupe_key` 补齐、5 条 `observation_count` 从演示遗留（11/9）清账为 0
（开发库 `observations` 表是空的 ⇒ 计数必须为 0）、过期降级 0 条（`revalidate_after` 是 2027-03-31）、
第二次跑幂等。诊断过程中我自己产生的 3 条 pending + 4 个 loop 文件已删除，`doctor` 报 `outstanding: 0`。

**插件装载（同日，用户批准）**：判据 1 只有 `source='hot'` 能检验，而 hot 的唯一来源是 host 在场的运行
⇒ 装。产物严格两件，都可单独撤销：

```
~/.config/opencode/plugin/agent-os.js -> <checkout>/integrations/opencode/plugin/agent-os.js
~/.zshrc:87  alias opencode='AGENT_OS_ROOT=/home/shade/Public/AgentOS opencode --auto'
```

**没有用 `opencode plugin <module>`** —— 它顺手改写 `opencode.json`，而那个文件不是这个仓库该动的；
装载后 `~/.config/opencode/**` 其余文件的 mtime 与装载前一致，唯一的例外是 `plugin/` 目录本身。
装载之后实测 `opencode serve --print-logs --log-level DEBUG` 的启动日志**没有任何 plugin 行**
⇒ 插件是按实例懒加载的，启动日志证明不了它被读到；于是 final-plan §5 里"真实装载验证"要确认的两项
（钩子顺序、`tool.execute.after` 真实形状）**仍未确认**，要等一次真实会话。
判据 1 的时钟从那一刻才开始走，今天 `observations.hot` 仍是 0。

上面那句"仍未确认"和"hot 仍是 0"随后就被下一节推翻了 —— 这两项正是
端到端循环要回答的问题，答案记在那里。

### 计划后 · 端到端测试-修复循环（2026-10-01，用户批准"你来进行测试"）

**目的**：把 `source='hot'` 从 0 变成 ≥1，并且只信屏幕。模型调用 8 次（预算 7–8），全免费非 contributor 的
`opencode/space-bunny-free`；除最后一次外全部写在 `/tmp/aos-rig/store` 副本库里。
测试：Python **398 → 401**，JS **13 → 20**（新增的每一条都先在修复前红过一次）。

**验收屏幕（真库那一次，`LOOP-20261001013518-F5D1`）** `[Verified]`：

```
aos doctor --json  → observations {"hot":1} · reviews {pending:1, by_kind:{outcome_label:1}}
                     candidates.open 0 · pending_postflight.outstanding 0
loop 文件          → recall.injection_chars 511 == 插件 stderr 的 len=511（数字配对，不依赖模型服从）
retrieval_log      → 该 loop 1 行（linkage）；注入的是 M-SEED-CACHEKEY02（scope=project:AgentOS，命中cwd）
review #23         → 缺席列表把 user_interrupted / tool_errors / session_error 等都列为"缺席"，等人标注
```

**修掉的 7 条**（每条一次提交、每条测试先红）：F1 成功也要可见、F2/F10 三种沉默各不相同、
F4 postflight 未答可重试三次、F6 保留邻居写进我们元素尾部的文本、F8 送出 `model`、
S 注入规模持久化、T 脏树不再被算作运行的产物。F5 把契约漂移守卫从手抄清单改成解析 JS 源码
（并用"塞一个 `invented_key` 就变红"证明它会红）。F7 由现场普查结论：**不修**，
`tool.execute.after` 里没有 `error` 键、被拒的调用根本不走 after 钩子 ⇒ `tool_errors` 只能缺席（设计上"缺席不是 0"）。
F3（`skill_used` 不发 ⇒ 真实运行不产候选）与 F9（`user_interrupted` headless 拿不到）**故意不动**，
理由分别写进 `record.py` 的反自我奖励约束与代码注释。

**判据 1 的状态**：时钟从今天开始，`hot=1`（那一次运行改了什么由 review #23 等人裁决 ——
它同时带着 T 修复**之前**采集的 `files_changed`，那条信号不可信，其余信号仍然成立）。

**两条计划里没料到的事**：

1. **只在 fixture 里跑过的东西，等于没跑过。** T（脏树 credited）与 Q（decay 覆盖）都是
   真实数据才暴露的形状；而"修了一半"的 T 比没修更危险 —— 它旁边就有一句 `preexisting_files`
   让人以为已经处理了。已写进架构文档 §12 的共性段。
2. **证明方式会自己推翻自己**：植入校验词想证明注入到达，而注入块的 preamble 明写"不要向用户复述本节"
   ⇒ 模型不听话恰恰是它对；`--pure` 也不是对照臂（它把所有外部插件一起摘掉）。到达证明改为
   引擎数字 == 插件数字 + 惰臂（只关我们）的 input-token 差值 +583 / 1,279 字符（U）。
   惰臂是这一轮才补进 rig 的，`--pure` 那两次调用因此只证明了"没有我们时也能答对" ⇒ 作废了行为证据。

**遗留（需人裁决，不在本轮动手）**：缺陷 V —— 纯中文措辞的任务基本召不出记忆，
`min_score=0.15` 对单个中文 tag 上限 0.080，且 `len(tag)>=3` 把两字词整体排除、keyword 要求等于 tag。
今天所有成功召回都靠路由器恰好吐出英文实体。本轮 8 次调用里有 3 次就是被这件事烧掉的（提示词怎么改都召不到）。

另记一次我自己的流程失误：F7普查那条提交是在它的测试仍红的时候打进去的（命令里 `grep` 吞掉了失败码），
下一轮立刻发现并单独修了测试模式 —— 已写在该提交的说明里，不做 amend。

### 计划后 · 第二轮：多轮会话、归因洞与链条闭合（2026-10-01，同批批准内）

2 次模型调用（`space-bunny-free`），其余全部零成本。真库当前 `observations` 回到 **0**，
因为第一 hot 那条（`LOOP-20261001013518-F5D1`）带着 T 修复之前采集的 `files_changed`
—— 它把操作者运行前留下的脏文件算成了运行的产物 ⇒ 用户裁决**删掉**，判据 1 的时钟重新从下一次干净运行开始。
删除前的库留在 `store/aos.db.pre-drop-obs73.bak`。

**多轮（同一 session 的第二条消息）是好的**：两条 turn 各开一个 loop、各进一条 `outcome_label`，
`pending` 不会被后一轮覆盖掉前一轮（先前担心的那点不成立）。

**V 在真实用法里又证实一次**：第一轮提示词带英文 token（`retrieve.py`、`cache`）⇒ 注入 394 字符；
第二轮纯中文追问 ⇒ `chars=0`，什么都没注入。同一个会话、同一个目录，差别只在措辞语言。

**缺陷 Y（本轮最大的一个，零模型调用复现）**：标注路径从来不查归因。一次 `failure` 标注给
**三条被召回记忆**都发了 weaken 候选，其中包括讲 sqlite 表重建与 postflight 默认值的两条。
P2 把这条洞在 record 路径上关掉了，label 路径一直敞着；今天没造成后果纯粹是因为
另一条不相干的守卫（`need >= 2 independent executions`）先挡住了。
修法是让人点名工种：`--skill`，不点名的结论照记、不怪任何记忆，CLI 打印下一步该怎么补。
顺带纠正我上一轮报告里的一句错话：我说"真实运行不产候选"——record 路径确实不产，
label 路径产，而且产得过头。

**链条闭合**（`/tmp/aos-chain/store` 副本，真库未动）：§10 那条"今天的仓库做不到这一步"已经作废 ——
rank 1→3、分数 0.387→0.262、第 5 次批准后 `active→deprecated` 并从注入里消失。
副作用是一条记账（§12 Z 行）：让一条既有记忆退出召回需要 5 次可归因的失败，不是一次点击。

### 计划后 · 第三轮：第一个可信的计数点（2026-10-01）

真库第一次带着修好的证据归因跑完（`LOOP-20261001022025-5282`，`AOS_RIG_ALLOW_REAL_STORE=1` 明确声明）：

```
doctor → observations {"hot":1} · reviews {pending:1, outcome_label} · candidates.open 0 · pending 0
loop   → evidence.files_changed=[] / working_tree_dirty=false / before_source=preflight   ← T 修好了的样子
         recall.retrieved=1 injection_chars=394 injected=['M-SEED-NORESORT3']
         record.outcome=partial needs_review=true confidence=0.4
stderr → preflight ok … / system appended index=1 len=394 / postflight sent … answered=true
```

review **#24 故意留着不标**：一条真实运行的成败是人的判断，不是测试脚本该替我填的字段。
`aos review label 24 --outcome X`（只记结论）或 `--outcome X --skill bugfix`（同时点名归因）由用户敲。
判据 1 的 4 周窗口从这一刻算起，此前那条被删的不算。

另记一次我自己的操作失误：这轮之前那次 `run.sh` 忘了带真库环境变量，屏幕上的 `store under test:`
写着 `/tmp/aos-rig/store` 而我没看，于是"验收"跑到了副本里 —— rig 的默认安全方向（写副本）是对的，
错在我没读它打印的那行。

### 计划后 · 第四轮：V 的止痛上限与 decay 的另一半（2026-10-01，用户指示"直接跑步骤 2 和 3"）

零模型调用，全部在副本库（`/tmp/aos-v`、`/tmp/aos-chain`），真库未动。

**② V 的止痛实验（只改数据）**：给 13 条种子各补 3 个中文 tag，同批 5 条纯中文提示词
从 **1/5 有召回变成 4/5**（401–499 字符注入）。仍然不够的那 1 条（P2）把机制量清楚了：
单个 tag 命中只值 0.08 静态分，`decay=0.85` 一乘 ⇒ 0.068，**要 3 个 tag 同时命中才越过 `min_score=0.15`**。
中文没有空格分词，"3 个 tag 同时出现"就是靠人工把词组猜对 —— 所以补 tag 是把沉默率从 5/5 降到 2/5，
不是解决；解决要么动阈值、要么动匹配（`len(tag)>=3` 与 keyword 必须等于 tag 这两条都是英文假设）。

**新发现 AA（同一批测量顺手撞出来的，比 V 更阴）**：`decay_factor` 乘在**相关性**上
（`final = static × (1+quality_bonus) × decay`），于是策略自己写的下限 0.5 拦不住"靠算术杀死召回"：
同一条提示词在 `decay=0.85` 召回 1 条，把 decay 设成 0.5 后 `retrieved=0`，而那条记忆的 `status`
仍然是 `active` —— 召不出来、队列里也没有任何痕迹。`evolve.py:269-270` 的注释明写着
"decay 只该让它更安静，不该靠算术杀死它"，这条注释又一次没变成代码（与 Q 同形）。**未修 ⇒ 等人裁决。**

**③ `review reject --as [--skill]` 这条路第一次被走**：不点名 ⇒ 结论改了、0 归因；点名 ⇒
只归因到 category 匹配的 2 条（第 3 条因已在副本里被退休而不在可打分集合内 —— 行为正确）。
撞出 AB：未归因提示让用户对**刚被批准的同一 id** 再跑一次 `review label` ⇒ `already_decided`，
两条路径都印这个坏提示。已修（具名测试先红：`assert 'label 1 --outcome' not in err`）。

测试：Python **402 → 403**，JS 20。提交：`7e645c0`（AB）。V / AA 留在裁决台上，
两者的共同点是"排序语义"，都不是这轮循环该顺手改的东西。

### 计划后 · 第五轮：V 的可修部分修掉了，剩下的三条杠杆量给了数字（2026-10-01，用户指示"继续"）

**V-1（改代码，已提交）**：`compute_static_relevance` 里 `len(tag) >= 3` 是一条拉丁假设 ——
中文的词通常是两个字（缓存、配置、排序），于是这些 tag 永远不参与命中，而 `id`、`to` 这种拉丁噪声
反倒被同一条规则保护着。现在按文字系统分流（`_is_matchable_tag`：含中日韩 ⇒ ≥2 字，否则 ≥3 字）。
新增具名测试先红：两字中文 tag 必须命中、两字母拉丁 token 仍然不算。测试 Python **403 → 404**。

**V-2（只测量，不改代码）**：同一条 5 提示词矩阵 + 8 条对照提示词，四种口径各测一遍：

| | 现在 | 阈值降到 0.12 | decay 不乘相关性 | 每命中 0.20→0.30 |
|---|---|---|---|---|
| 5 条纯中文提示词命中 | 4/5 | **5/5** | **5/5** | **5/5** |
| 8 条对照/近似提示词误召 | 0 | 0 | 0 | 0 |

三条杠杆**在同一个地方等价**：今天唯一被卡住的是"命中 2 个 tag"（0.16 静态 → 0.136，差 0.014）。
1 个命中的情况在四种口径下都进不来（0.068 / 0.068 / 0.08 / 0.102 全都低于各自阈值），
所以这次改动不会把"碰巧共享一个词"变成召回 —— 这是那 8 条对照测出来的，不是我推的。

**留给你的选择**（三条都有效、误召都是 0，区别在语义）：
① `min_score` 是策略文件里的键，改它**不用动代码**，但它对所有记忆一视同仁地放低门槛；
② decay 不再乘在相关性上 —— 同时把 AA 一起解决（那条注释本来就是这么要求的），
但它改变的是"被削弱过的记忆该多安静"，是排序哲学；
③ 每命中 0.20→0.30 —— 只放大标签证据，作用面最窄，代价是两个 tag 就从 0.068 跳到 0.204。
默认我不动，等你点一条。

### 计划后 · 第六轮：②′ 落地，AA 关闭（2026-10-01，用户选"按 ② 实施 + 补回归用例"）

**改的代码**：`retrieve()` 的准入门槛从 `final_score` 改看 `adaptive_score`（decay 之前的相关性），
排序仍按 `final_score` ⇒ decay 保留"让它更安静"的作用，失去"判它死刑"的作用。这正是
`evolve.py:269-270` 那条注释一直要求、而代码从没做到的样子。

**两条具名测试，先红后绿**：
- `test_decay_orders_a_memory_but_does_not_ban_it_from_recall`：红的时候 `M-WEAK`（decay 0.5、
  两个标签命中）根本召不出来；修后它被召回且排在更新更干净的那条之后。
- `test_a_single_tag_coincidence_is_still_not_a_recall`：精度守卫（改前就已经绿，钉的是"放宽之后也不许把
  单标签巧合变成召回"），以后谁再动阈值/权重都会先被它拦。

**实测（副本库，含第五轮那 39 个中文 tag）**：

| | 修前 | 修后 |
|---|---|---|
| 5 条纯中文提示词命中期望记忆 | 4/5 | **5/5** |
| 8 条无关/近似提示词误召 | 0 | **0** |
| AA 屏幕：`decay=0.5` 的那条记忆 | `retrieved=0`，status 仍 `active`（静默退休） | 召回，且排在该任务其它命中之前/之后由 decay 决定 |

测试：Python **404 → 406**，JS 20；无回归。

**还留在你手上的两件**：① 真库那 13 条种子的 tag 仍全是英文 —— 本轮机制修好了，但"纯中文任务能召回"
在这份语料上仍要靠中文 tag（副本里那份 39 个 tag 的补丁要不要进 `content/memory/seed/agentos.json`，是你的决定）；
② 真库 `review #24` 还没人标注（判据 1 的第一个判决）。

### 计划后 · 第七轮：中文任务在真库里也能召回（2026-10-01，用户"继续"）

三件事，一次模型调用：

1. **AC 关闭**（`15e8458`）：`upsert_memory` 从不覆盖 standing ⇒ 作者路径与门路径按构造分离
   （不得写的列正好等于 `update_memory_fields` 可写的列）。红证据：`--force` 会把
   `M-SEED-EXPORT8` 从 `benchmark_evaluated/low` 抬回 `real_project_validated/high`。
2. **语料补齐**：`content/memory/seed/agentos.json` 每条加 3 个中文 tag（共 39 个），并把三条书写规矩写进
   note（含"tag 必须双语"这条，理由就是 V 的机制）。`aos memory seed --force` 应用后：tag 70 → 109、
   全部 standing 不动、热观测与队列不动 ⇒ 顺带在真实数据上验了 AC。
3. **真库第一次纯中文任务**（`LOOP-20261001030411-1D4E`，中文提示词里没有任何拉丁词）：
   `retrieved=2`、注入 755 字符（`M-SEED-PHASE010` + `M-SEED-CACHEKEY02`）、`observations {"hot":2}`、
   两条 `outcome_label` 待标注、`pending_postflight 0`。
   同时 T 在真库上再验一次：当时工作树是脏的（正在改种子），
   `files_changed=[]`、`preexisting_files=['content/memory/seed/agentos.json']` —— 引擎没把我的编辑算成运行的产物。

判据 1 的窗口里现在有 2 条 hot，其中 1 条是修好证据归因之后的第一条干净运行。

### 计划后 · 第八轮：召回命中率进 doctor（2026-10-01，用户选 ①）

`doctor --json` 多一节 `recall: {runs, recalled, zero_recall}`，只统计 `source='hot'` 的 loop 级运行
（回读来的历史不是"我们为它召回过什么"的证据），人读输出同时多两行：

```
observations:    hot 2
recall:          2 runs · 2 拿到记忆 · 0 空手
```

为什么这条值得存在：V 那类缺陷的症状是"跑得很欢、一条记忆都没回去"，而 `observations` 的计数在
这种状态下长得跟健康一模一样。有了 0，判据 1 的四周窗口里我第一次能直接看出**这套层是在沉默还是在学**。
三个分支都过屏幕：没有运行 ⇒ "还没有一次 loop 自己的运行"；有运行但空手 ⇒ 计数出来；真库 ⇒ 2/2/0。

测试 Python **407 → 408**（`test_doctor_reports_whether_recall_found_anything`，先红：`KeyError: 'recall'`）。

### 计划后 · 第九轮：判据 1 的计数前提被查出是半证的（2026-10-01，用户"继续"）

排三件待办时冒出来的问题：四周窗口数 `source='hot'`，而我们 8 次通电验证**全部是 `command opencode run`
无头形态**（`live/run.sh:70`），可 `live/README.md` 早就把"普通 TUI 使用也会写这个计数"当事实写了一句 ——
`[Judgment]` 混进了陈述句。若它不成立，窗口会收 0 条并因错误的理由触发降级，所以先不烧用户的会话，
改用机器上已有的东西查证（全部只读，`mode=ro`）：

1. **常驻插件的钩子在交互会话里真的被调用** `[Verified]`：`~/.config/opencode/plugin/skill-tracker.js`
   注册 `tool.execute.before/after`、`event`、`chat.message`、`dispose`（`:1401,1422,1561,1745,1768`），
   其库里由钩子路径写入的行是 `skill_usage` 21 条 `tool_call` + `plugin_usage` 39 条 `tool_call`
   + 9 条 `event_detected`，日期 2026-09-23…09-30 —— rig 那几天一次都没跑。
2. **`session.idle` 会送到插件，且 host 区分 CLI 与 TUI** `[Verified]`：`@mohak34/opencode-notifier@0.4.0`
   `dist/index.js:2319` 处理 `type === "session.idle"` 并调 `idle(sessionID, isCLI)`，`isCLI` 在 `:2293`
   算出 —— 这个判别式存在的唯一理由就是两种客户端都会走到这里。它的通知计数器
   （`opencode-notifier-state.json`，现值 `turn: 21277`，在 `:1846` 每次投递 +1）是这条路径跑过几千次的活记录。
3. **缺的那一环**：我们**开环用的 `chat.message`** 没有可借的旁证 —— skill-tracker 的同名处理器只写内存
   (`:1745-1757`，不落库)。所以"一次真机会话 ⇒ `observations: hot` +1"停在 `[Inferred]`。

处理：把 `live/README.md` 那句改写成分三条、各自带标签与出处的证据链；`agent-os-v2.md §9` 的
已确认/未确认清单加第三条（含结算方式：真会话前后各跑一次 `./bin/aos doctor`，`hot` 必须 +1）。
顺带排掉一条摘要里的旧尾巴 —— "V-2 那个 skill 文件待批准"不成立（`~/.config/opencode/skills/` 下只有
`open-source-skills`、`personal-skills`，仓库对 `ai-research-investment` 零引用）。

零代码改动，测试数 **410 不变**；本轮只做只读取证与文档校正，未向 `~/.config/opencode/**` 写任何东西。
