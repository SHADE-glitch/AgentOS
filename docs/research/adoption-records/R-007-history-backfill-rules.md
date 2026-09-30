# R-007 · 历史回读：SDK 优先，若直连 SQLite 必须复合高水位 + 源缺失不得清空索引

**来源项目与组件**
两条**互相独立**的实现（这是本条强度来源：同一需求、两种做法、作者互不知情）：
- `ericmjl/agent-autolearn`（MIT）SQLite 路线 `[Verified·一手]`：
  - `skills/autolearn/scripts/outcomes.py:219` `sqlite3.connect(f"file:{db}?mode=ro", uri=True)`；
  - `:196-213` 高水位用**复合键** `(last_time, last_part_id)`，注释说明原因：同一时间戳的多个 part 会被
    `time > mark` 型游标跳过；
  - `:224-240` **顺序即数据保护**：先检查源库存在再执行 `--full` 的清空，注释原文
    「Hoist the source-DB check ABOVE any --full truncation so a missing/moved opencode.db can never wipe an existing index」；
  - `:388-414` 派生统计用 `GROUP BY`；`autolearn.py:1398-1425` 全文索引只取 `pdata["type"] == "text"`、增量 `p.time_created > ?`；
  - 索引写进**自己的** `outcomes.db` / `search.db`（FTS5 external-content），**从不写 opencode.db**。
- `asphyksia/opencore`（**无 LICENSE**）SDK 路线 `[Verified·代理读源]`：
  `lib/session-store.ts:8-10` 明确声明「opencore maintains its OWN session index (not opencode's internal DB)」；
  数据全部来自 `client.session.messages`（`session-search.ts:69`、`memory.ts:199`）、`client.session.get`（`:84`）；
  自己的库 `~/.opencore/sessions/sessions.db`。

**观察到的设计**
两条路线的共同形状：**源库只读 → 自建派生库 → 增量高水位 → 派生统计在查询期现算**。
差别只在证据取处（直接读 SQLite 表 vs 走 SDK 调用）。输出是可重算的派生索引；状态落在自己的库里；
触发是显式 curator 步（autolearn）或首次工具调用时的惰性构建（opencore）；调用者是自己写的索引器。
**两家都不写回源库** —— 这条纪律比它的实现更值得抄。

**本机可行性实测（`mode=ro`，未使用 `immutable=1`，因为存在活跃 WAL）`[Verified·一手]`**
`~/.local/share/opencode/opencode.db` = 1.7GB / 21 表。可用证据：
`part` 61,790 行，type 分布 `tool 16,374 / step-start 13,541 / step-finish 13,264 / reasoning 10,940 /
text 6,517 / patch 1,109 / file 26 / compaction 14 / agent 5`；
`part.state.status ∈ completed 16,137 / error 235 / running 2` ⇒ **工具错误可反推**；
`todo` 305 行（`completed 263 / pending 27 / in_progress 14 / cancelled 1`）⇒ `todos_unfinished` 可反推；
`session` 199 行，`agent` 8 种、`model` 18 种 ⇒ 归属维度可用。
**不可用的部分**：`event` 表 369,500 行但只有 5 种 type（`message.part.updated.1 / message.updated.1 /
session.updated.1 / session.created.1 / message.removed.1`）—— **没有 session.idle / session.diff /
session.error / todo.updated**；`session.summary_files > 0` 只有 **1/199**、`cost > 0` 只有 **5/199**
⇒ 「历史里有会话摘要与成本，可直接当结果证据」这个假设在本机**基本不成立**。

**解决的问题**
学习回路只有两条进料口：热路径（会话进行中插件上报）与冷路径（回读历史）。
外部四家都在热路径上撞到同一个洞（没有任何钩子返回 verdict，见 findings Q9），
于是"能回读历史"就成为唯一能把**过去已发生的经验**一次性喂进系统的机制 ——
也恰好是 okdk 失败的地方：它让模型去调 `session_search`/`session_read`
（`index.ts:611,980`；`skills/optimize-skill/SKILL.md:27-30`、`skill-distiller/SKILL.md:19-20`），
而**这两个工具在本插件里从未注册**，`[Verified·一手]`（本机是否有同名工具属 `[Unconfirmed]`，见 findings §16.4-6）。

**为何适用于此处**
1. **≥2 独立血统**：成立（autolearn 与 opencore，路线不同、需求相同）。
2. **共同问题**：热路径证据不足 ⇒ 需要冷路径补证据；两者都实现了冷路径。
3. **Agent OS 有这个问题**：是。它现在**只有热路径**，且热路径依赖尚未实现的插件（Phase 4）。
   `store.py` 有 `observations/retrieval_log`，但对历史一无所知；引擎里没有任何 opencode.db 读取（已核实零引用）。
   ⇒ 意味着 Phase 3.3 的去重、Phase 3.4 的使用反馈、Phase 3.6 的 skill 有效性观测，
   在插件装上之前**都没有数据可学**。冷路径能把这段时间差补上。

**需要的改造**
- 去向明确为**新模块 + 显式命令**，不进热路径：`aos/core/learning/backfill.py` + `aos memory backfill [--since] [--dry-run]`。
- **两条路线都实现，但默认走 SDK 不可行**（引擎零依赖，不能依赖 node SDK）⇒ 实际只能走 SQLite 只读，
  于是这三条必须照搬 autolearn 的做法（都是标准库能力）：
  ① `file:...?mode=ro` URI 连接；② 高水位用 `(time_created, part_id)` **复合键**；
  ③ **先判源库存在，再做任何清空**；④ 派生数据只写进 `store/aos.db` 自己的表，**永不写 opencode.db**。
- 路径必须可配置并且**默认关闭**：`AOS_OPENCODE_DB`（不设则 backfill 直接拒绝并说明原因），
  这样隐私默认成立；文档要写明它读的是含私人对话的库、以及只读列的白名单。
- 读什么：只要 `part.type=='tool'` 的 `tool`、`state.status`、`state.title`，`part.type=='patch'` 的文件路径，
  `todo.status`，`session.agent/model/directory`。**不读 `text`/`reasoning` 正文**（避免把对话内容写进记忆库），
  这一条与"文档里不引用原文"的用户要求一致。
- 映射到现有信号：`tool_errors` ← `state.status=='error'` 计数；`files_changed/diff` ← patch parts；
  `todos_unfinished` ← `todo.status in ('pending','in_progress')`；`cwd/scope` ← `session.directory`。
  然后交给**同一个** `outcome.synthesize`，不另建判据（避免第二套结论逻辑）。
- 迁移：`observations` 增加 `source TEXT DEFAULT 'hot'`（`hot|backfill`），v5/v6 additive；
  回读出来的观测必须可辨识、可整体撤销（`DELETE WHERE source='backfill'`），
  否则一次错误回读会永久污染 `use_count`（R-002 之后 `use_count` 是派生的，因此撤销只需删行 —— 这是选派生的又一个理由）。

**为何不直接复制**
- autolearn：MIT，但它的索引器绑在自己的 `outcomes.db` + persona 目录 + `uv run` 环境上；
  可移植的是那四条纪律，约 20 行 Python。
- opencore：**无许可 ⇒ 不可复制代码**，只能读设计；且它的路线（SDK）在 AOS 的零依赖约束下用不了。

**建议去向**
**Learning**（新模块，人发起）；契约与插件层不受影响。
`[Judgment]` 它不属于"闭环的必需环节"，属于**闭环的启动加速器** —— 裁决时不应把它当成 Memory/Learning 的架构件。

**风险**
- **隐私**：读的是含私人对话的 1.7GB 库。列白名单 + 默认关闭 + 不落正文，三条都必须在代码里而不是文档里。
- 版本耦合：opencode 的表结构（`part.data` 的 JSON 形状）随版本变化，且本机是 1.18.33、
  两个参考实现分别对 1.17.11/1.14.33 说话。okdk 已经演示过"字段猜错 ⇒ 静默永不触发"的后果。
- 规模：全量回扫 61,790 个 part 是可行的；但 `event` 表 369,500 行、库 1.7GB，任何"全表重扫"都该有分页与上限。
- **如何证伪（一条会失败的断言）**：
  `tests/test_backfill.py`：
  ① 造一个假 opencode.db（临时目录 fixture，**绝不碰真实库**），插入两个**同一 `time_created`** 的 part，
     跑两次 backfill ⇒ 第二个 part 必须在第二次运行中被收进（复合键断言，
     若实现用 `time > mark` 游标这条会**失败** —— 正是 autolearn 注释警告的坑）；
  ② 把源库文件改名后再跑 `--full` ⇒ 必须**拒绝执行并且现有行还在**（数据保护顺序断言）；
  ③ 断言 `aos` 源码中不存在任何对 opencode.db 的写模式连接（`grep "mode=ro"` 之外不得出现该路径的 `connect`）。
