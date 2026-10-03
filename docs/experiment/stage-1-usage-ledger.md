# Stage 1 · 使用账本 —— Agent OS 是否值得作为日常工具存在（2026-10-01 → 2026-10-08）

Stage 0 已答"能不能跑通"。本阶段只答一个不同的问题：**日常开发里带它，值不值。**
不改 `aos/**`、`integrations/opencode/plugin/**`、`content/policies/**`；不建 exp-v2；不换模型。

## 1. 三个问题，各自的可计算定义

| | 问题 | 用什么数回答（全部只读） |
|---|---|---|
| **Q1** | 经验会不会自然积累 | 窗口内由**真实会话**产生且当前仍 `active` 的记忆条数：`memories where ifnull(source_loop_id,'')<>'' and created_at>=窗口起 and status='active'`，按 `type` 分组 |
| **Q2** | 会不会在未来的相似任务里被召回 | `retrieval_log` 里 `memory_id` 属于 Q1 集合、且 `l.created_at > m.created_at` 的命中次数，按 `source_project` 分组 |
| **Q3** | 召回之后我的开发过程有没有变好 | **只能 owner 标**。我只记录标记与原话；不推断，不代填 |

三问不得互顶：Q1 为 0 时不能用"注入块里 seed 命中了"来答 Q2；Q3 无标记时不能写成"看起来更顺"。

## 2. 最重要的一条读数规则：seed 不算经验

正式库里 14 条记忆（10-03 复测仍 14：`active 13 / deprecated 1`），**13 条是 2026-09-30 手工植入的
`M-SEED-*` 演示种子**，剩下 1 条 `M-7B113D99`（真实会话产生）已于 2026-10-01 08:17 被 owner 退役。
`retrieval_log` 10-01 基线 13 次命中；10-03 复测 51 次，其中 **50 次落在 seed 上**、1 次落在那条已退役的。
⇒ 10-02 之后新增的 38 次命中**全部是 seed**，Q2 仍为 0：召回一直在发生，但没有任何一条日常经验被再次找到。

所以：`doctor` 在 10-01 基线时报 `recall: 5 runs · 5 拿到记忆 · 0 空手`，**几乎全部是种子在起作用**。
Q1/Q2 的统计一律加 `memory_id not like 'M-SEED%'` 与 `status='active'` 两个条件，否则本阶段会自欺。
现值不写在这里，一律 §6 的命令现取（10-03 复测见 §4bis）。

**Stage 1 的起点因此是：日常可召回的真实经验 = 0 条。** 后面每一个数都从这里算。

## 3. 边界（本阶段的禁止与允许）

禁止：人为制造失败任务、rig 模拟、probe、benchmark、改提示词制造优势、为了正结果挑任务、
提前优化人门、动冻结面。

允许：① 明显影响使用的 bug 修复（要能单笔回滚，且先有会红的具名测试）；② 只读分析工具；③ 文档。
**采集能力的任何改动一律先写成 exp-v2 提案，不在本阶段实现** —— 已知盲区见 §7。

**这条边界本阶段已被 owner 两次点名越过，两次都是加能力**（记在这里，免得这张账本读起来像"规则一直守着"）：
2026-10-02 加了 basic-memory 的**只读召回**（`82c9aa3`），2026-10-03 加了**批准后单向写回 bm**（本轮）。
两者的共同点：都不改召回/门禁的判定语义，都由 owner 直接下令，都留了单笔可回滚提交与两条 off-switch
（策略文件 `enabled: false` 或 `AOS_BM_BIN=""`）。它们对 Q1/Q2 的口径**没有**影响：写回不产生新记忆，
也不改变哪条被召回 —— 它只改变"批准过的东西人能不能看见"。

实验数据隔离：Stage 0 的臂 E 库留在 `<rig>/E/store`（`M-F8993E1D`、`M-21AE3B79`），
**不迁进正式库**。理由：那两条是实验票面产生的，混进日常积累就等于把实验产物当使用证据。
代价照写：日常暂时用不到那两条。要迁也得 owner 明确决定，并单独标注来源。

人门那 2 条 `outcome_label` pending（`#24`、`#25`）属于 owner 自己的会话，**不由我代标**（AGENTS.md）。

## 4. 基线快照（2026-10-01 实测，不是承诺）

| 项 | 值 |
|---|---|
| exp-v1 tag | `f56f0aaa0db1a881792a0f514b6fc1c8c0290314`（本阶段不动） |
| 冻结代码点 | `53de1adc5fb5ff92877ae11e37606e2f9e8f6dbc`；`git diff 53de1ad..HEAD -- aos content tests integrations/opencode/plugin` = **0 文件** |
| AgentOS HEAD / 工作树 | `bcfb703` / 干净 |
| schema · contract | v5 · 1.2 |
| 模型 / 宿主 | `opencode/space-bunny-free` · `1.18.34`（不换） |
| formal DB | `store/aos.db` sha256 `c3907554319a0fe3…`；`memories 14（active 13 / deprecated 1）`、`observations hot 5`、`recall 5 runs / 5 拿到 / 0 空手`、`gate 2 pending · 0 candidates`、`pending_postflight outstanding 0` |
| 真实日常会话 | **0 条已记录**（今天这 5 轮是开发与验证过程本身，不计入 Q1/Q2 的经验来源） |
| 测试基线 | `447 passed` + `27 pass` + rig `15 passed`。原句是"本阶段不应变；变了就是有人在动代码"—— **它已经变了两次，两次都是 owner 下令的代码改动**（见 §4bis），所以这条读数规则作废，改成"每次复测时记录 HEAD 与计数" |
| 日常接线 | 零配置已在跑：`~/.zshrc:90` `export AGENT_OS_ROOT=…`，`opencode` alias 内联一份，环境里没有 `AOS_STORE_DIR`/`AOS_DB_PATH` 泄漏 ⇒ 正常会话写正式库 |

## 4bis. 2026-10-03 复测（全部 §6 命令现取，逐条可重跑）

| 项 | 10-01 基线 | 10-03 现读 | 差异归因 |
|---|---|---|---|
| AgentOS HEAD | `bcfb703` | `82c9aa3` | 中间 4 笔（`git rev-list --count bcfb703..HEAD`）：`fad30d3`（开本账本）、`6e57548`（AGENTS）、`5d34aba`（插件：慢 postflight 不再被杀、DCP 横幅不再当任务）、`82c9aa3`（basic-memory 只读召回，owner 令）。**动代码的是后两笔** |
| 测试计数 | 447 / 27 / 15 | **464 / 29 / 15** | +13 external、+4 inject（`82c9aa3`）；JS +2（`5d34aba`）。冻结面因此已移动：`git diff 53de1ad..HEAD -- aos content tests integrations/opencode/plugin` **不再是 0 文件**，exp-v1 的两个 tag 未动 ⇒ 跨这些点的读数不是同一条基线（`agent-os-v2.md §16`） |
| formal DB | sha `c3907554319a0fe3…` | sha `5ce6e590733844e0…` | **由 owner 的 live 会话写入**，不是本轮：10-02 新增 72 条 loop、10-03 新增 6 条（`cwd` 只有 `<subject-project>` 与 `<repo>`） |
| observations · recall | hot 5 · 5 runs / 5 拿到 / 0 空手 | hot **11** · 11 runs / 6 拿到 / **5 空手** | 有 postflight 的 loop 数 = 11 = `observations.hot`（交叉核对相等）；10-02 那 72 条 `final_status=pending`、`postflight=null`，贡献 0 条 observation |
| 人门 | 2 pending · 0 candidates | **8 pending**（`outcome_label` #24/#25 + #30–#35）· 1 promotion approved | 10-03 的 6 次宿主会话各产生 1 条待标注（"是不是真实开发会话"待 owner 标，§5）；**promotion 增量为 0** |
| Q1 / Q2 | 0 / 0 | **0 / 0** | `retrieval_log` 从 13 次涨到 51 次，10-02 之后的 38 次**全部落在 seed 上** ⇒ 召回一直发生，日常经验从没被再次找到 |
| pending_postflight | outstanding 0 · oldest 0 | outstanding **3** · oldest **20.4 h** | 三条 `since` 最晚 `2026-10-02T15:01:48Z`，修复提交在 `15:18:01Z` ⇒ 全部早于修复的存量；`store/` 无删除路径，也不该补发 postflight 去清（那是伪造一次没发生的回报） |

**这一行是本阶段目前最有用的一条事实**：`值不值得每天用` 在今天**仍不可判**，而卡住它的是两件不同的事 ——
① Q1/Q2 为 0 的直接原因是**人门没人标**（8 条 pending，窗口内 0 条 promotion），不是链路断；
② "谁在用"这一半**主机根本不暴露**（缺陷 AR，见 `agent-os-v2.md §12`）：`OPENCODE_CLIENT` 只有 `"acp"` 一处赋值、
TUI 不写它，人在 TUI 敲与我用 tmux 驱动 TUI 读出来同为 `cli` ⇒ 任何"来源"字段现在写进去都是假的。
可计算的部分照实给：**上界 11**（真实宿主会话产生的 observation），**可证"由人敲"的下界 0**；
差的这一段只能由 owner 在 §5 的 owner 列里标。"rig 不计"这一半目前由构造保证（rig 只写 `<rig>/E/store`，
正式库 83 条 loop 里 0 条 `cwd` 在 <rig> 下），不需要新字段。

## 5. 会话记录表

每行一次**真实开发会话**（不是实验）。`是否真实任务` 为 No 的行不进任何统计，只留痕。
标注 `owner` 的列由 owner 填，我不代填；标 `ro` 的列由 §6 命令读出，我抄数不改数。

| 日期 | 项目 | 任务（一句话） | 真实任务? | 任务类型 | 产生 observation | 进入 review | promotion | 经验类型 | 人工确认 | 未来是否召回 | 影响结果(owner) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| | | | | bugfix/feature/refactor/learning/maintenance | ro | ro | ro | ro | owner | ro | owner |
| 2026-10-01 | — | （尚无真实使用行） | — | — | — | — | — | — | — | — | — |
| 2026-10-03 | test | 题面只留在本机 `store/loops/`，不入仓库（隐私线 §6 末） | **待 owner 标** | — | 3（obs 79/81/82，全 success） | 3（#30/#32/#33） | 0 | 0 条新记忆 | 待标 | Q2 = 0 | 待标 |
| 2026-10-03 | test | 同上 | **待 owner 标** | — | 1（obs 80，failure） | 1（#31） | 0 | 0 条新记忆 | 待标 | Q2 = 0 | 待标 |
| 2026-10-03 | test | 同上 | **待 owner 标** | — | 2（obs 83/84，全 success） | 2（#34/#35） | 0 | 0 条新记忆 | 待标 | Q2 = 0 | 待标 |

三行的 `ro` 列按 session 分组，可由 §6 的第二段命令逐条对上（loop → session → observation）。
owner 列一律留空：这三行是不是"真实开发会话"、有没有帮上忙，只有 owner 能标；我只数不改。
窗口内 **promotion 增量 0**，所以 Q1 仍是 0 —— 不是链路没跑，是 8 条 `outcome_label` 还没人标。

`影响结果` 只允许三种值：`省了一次尝试` / `绕开了一个坑` / `没帮上`；空白 = 未标，未标不等于没影响。

## 6. 取数命令（已实测；只读，不改任何东西）

```bash
cd <repo>

# 快照（聚合数一律从这里取，不沿用上一轮记忆值）
AGENT_OS_ROOT=$PWD ./bin/aos doctor --json | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['memories'],d['observations'],d['recall'],d['reviews'],d['pending_postflight'])"

# 会话 → loop → 项目 → 召回了几条 → 有没有回报（不打 task_text：会话正文不进仓库）
python3 - <<'PY'
import json, glob
for path in sorted(glob.glob("store/loops/*.json")):
    d = json.load(open(path))
    print(d["created_at"][:16], d["loop_id"], (d["session_id"] or "-")[-8:], d["cwd"].split("/")[-1],
          "recalled", d["stages"]["recall"]["data"].get("retrieved"),
          "postflight", d.get("postflight") is not None, "status", d.get("final_status"))
PY

# Q1 / Q2 / 人门频率（sqlite 以 mode=ro 打开）
python3 - <<'PY'
import sqlite3
db = sqlite3.connect("file:<repo>/store/aos.db?mode=ro", uri=True)
W = "2026-10-01"                      # 窗口起日
# Q1 与 Q2 用同一套过滤：真实会话产生、仍 active、非 seed —— 少一条两问就会互相打脸
NEW = ("ifnull(m.source_loop_id,'')<>'' and m.created_at>=? and m.status='active' "
       "and m.memory_id not like 'M-SEED%'")
q1 = list(db.execute(f"select m.memory_id,m.type,m.category,m.source_project from memories m "
                     f"where {NEW}", (W,)))
print("Q1 日常产生的 active 经验:", len(q1), q1)
print("Q2 它们后来被召回:", db.execute(
    f"select count(*) from retrieval_log l join memories m on m.memory_id=l.memory_id "
    f"where {NEW} and l.created_at>m.created_at", (W,)).fetchone()[0])
print("  对照：落在已退役记忆上的召回（一般是「先召回后退役」，不是泄漏）:", db.execute(
    "select count(*) from retrieval_log l join memories m on m.memory_id=l.memory_id "
    "where m.status<>'active' and l.created_at>m.created_at").fetchone()[0])
print("人门:", list(db.execute(
    "select kind,status,count(*) from learning_reviews where created_at>=? group by 1,2", (W,))))
PY
```

基线日实测：`Q1 = 0`、`Q2 = 0`、落在已退役记忆上的召回 = 1（`M-7B113D99` 于 05:27 被召回、08:17 才被退役，
顺序正常，不是"退役了还在注入"）。人门那三行（`outcome_label approved 3` / `pending 2` / `promotion approved 1`）
是 10-01 开发轮的产物，不计入本阶段。

10-03 整块照抄重跑（`bash` 退出 0）：`Q1 = 0`、`Q2 = 0`、已退役记忆上的召回仍 = 1、人门
`outcome_label pending 8`（原 2 条 + 10-03 新增 6 条）；第二段的逐行输出里 `postflight True` 11 行、
`False` 72 行 —— 与 §4bis 的两个读数一一对上。**这一块原先照抄是跑不了的**：Q1/Q2 片段里一个
Python 字符串套了成对直双引号，实测 `SyntaxError: invalid syntax. Is this intended to be part of the string?`，
所以"已实测"那句当时靠的不是文档里这份命令。内层引号已改为「」。

隐私线：`store/loops/*.json` 与 `observations.signals_json` 里含任务原文与工具轨迹，**只在本机读**，
仓库与本文只出现计数、id、项目名与日期。

## 7. 带进本阶段的已知盲区（只登记，不改）

Stage 0 已实测的四条，本阶段**同样成立且不去修**（细节见 `docs/experiment/stage-0-ledgerd.md` §5/§5bis/§10）：

- **AL**：`ok` 取整条 shell 调用的退出码 ⇒ 管道与复合命令把真实失败读成通过。
- **AM**：引擎的 validate 会在被观测项目里跑自探测的构建命令，其结果进 `present`/`可证` ⇒ **不是**独立证据。
- **AN**：`methodOf` 只取复合命令第一段 ⇒ 方法身份失真。
- **AQ**：我的 oracle 只解析 pytest 汇总 ⇒ shell 自身报错而 exit=0 时它也报 `success`。

本轮（10-03）新增两条，都属于"账本读数的口径"而非引擎错误，登记不修（细节与命令在 `agent-os-v2.md §12`）：

- **AR · 驱动者不可判定**：主机不给插件"这次运行是人敲的还是 agent 驱动的"。`PluginInput`/`Session`/`UserMessage`
  无此字段；二进制里 `OPENCODE_CLIENT` 仅一处赋值（`="acp"`），TUI 不写它 ⇒ 人与我驱动 TUI 读出来同为 `cli`。
  后果：判据 1 的"只数 owner 的交互会话"目前**没有机器可判的依据**，只能读成上界（11）；
  任何写进链路的"来源"字段在此刻都是假的。要闭合必须先由 owner 拍板方案（§12 行 AR 给了三条，都含契约/字段改动）。
- **AS · `outstanding` 是下界**：崩溃记录一个 session 一个文件（`aos/core/loop/pending.py:39`），
  同会话下一次 preflight 覆盖上一次，而 `clear()` 只有 `lifecycle.py:406` 一个调用点。
  实测：10-02 某会话 66 条未回报的 loop 只留下 1 条 `pending-*.json` ⇒
  `doctor.pending_postflight.outstanding = 3` 对应的未闭合 loop 其实是 **72** 条。
  读这张账时：`outstanding` 只能证明"至少这么多没闭"，不能证明"只有这么多"。

推论要写死：本阶段**不指望 trace 提供"失败—修正"证据**。Q1/Q2 的可信读数来自 `retrieval_log` 与
`learning_reviews`；`tool_trace` 只作旁证，出现"全通过"时不能当"确实没有摩擦"。

## 8. 收口（2026-10-08）

只出一张事实表，不出价值判断：

1. Q1 条数与类型分布（真实会话、active、非 seed）；
2. Q2 召回次数与"召回时所在项目 ≠ 产生时所在项目"的跨项目数；
3. 人门负担：窗口内产生的 review 总数、owner 标注的条数（我不代标）、owner 标"有价值"的条数、其中重复条数；
4. Q3：owner 标记的分布（含空白数）；
5. 期间是否发生过"明显影响使用的 bug 修复"（若有：单号、回滚方式）；
6. 代码不变量复核：tag、冻结面 diff、两套测试计数、formal DB 哈希增长路径；
7. AR 的状态：owner 是否已对"驱动者怎么标"拍板。未拍板则本阶段的"谁在用"一栏只能交上界，
   收口时必须写明"这一问没答"，不能用 hot 计数代替。

**"值不值得作为日常工具"由 owner 判**。我不从上面七项里推这个结论。
数据不足就说不足：例如 Q1 = 0 时结论只能是"7 天内没有自然积累"，不能改写成"链路没问题只是没数据"。
§4bis 那条"卡在 8 条未标的人门"只是**位置**判定（记录确实产出了、门确实没开），它不同步说明
"门开了以后那些经验有用"——那仍然是 Q1/Q3 要答的。
