# Exp-v1 · Stage 0 —— ledgerd 项目、两栏判据与测量现场（2026-10-01）

本文件只改**测量**。Agent OS 的冻结面一个字节都没动，AL/AM/AN 三条在本轮只登记（§5）。

## 0. 这份文件要拆开一个混淆

Stage 0 的第一条出口判据原来写成一句话："项目是否产生可记录的失败"。LGD-02 给了它两个相反的答案：

- 项目侧：真的产生了失败、修复、再验证（独立证据见 §4）。
- Agent OS 侧：它的 `tool_trace` 里 **0 个** `ok=false`，42 步全部读成"通过"。

所以"项目有"与"系统看得见"必须分栏报告，否则同一份数据既能判过又能判不过。
判据 ① 自本文件起拆成 **①-A（项目侧摩擦）** 与 **①-B（Agent OS 可见性）**。

## 1. 实验设置

| 项 | 值 |
|---|---|
| 项目 | `ledgerd` @ `/home/shade/Public/test`（流水导入与月度对账，Python 3.14 标准库 + pytest） |
| 当前基线 | `d5bf7773fff32feb87c82767a7ffab3be5ff59c6`（LGD-02 完成后；种子 base 为 `70c935f`） |
| 票与顺序 | LGD-02 → LGD-06 → LGD-07 → LGD-11，一任务一会话、一任务一 commit，项目不 reset |
| 臂 | Stage 0 只跑臂 E（+Agent OS）；对照臂用 `AOS_RIG_INERT=1`，**不用 `--pure`** |
| **脚手架位置** | **一律在被试项目之外**：`/home/shade/stage0/`（`tickets/`、`E/store`、`E/rig`、`E/inflight`、`E/manifest.tsv`）。原先放在 `<project>/.arms/` 导致了 AO（§5bis），已整体搬出并由 `run.sh` 的放置守卫禁止再犯 |
| store 隔离 | `AOS_STORE_DIR=/home/shade/stage0/E/store`（真库 `store/aos.db` 一字未动，见 §7） |
| 模型 | `opencode/space-bunny-free`（exp-v1 冻结不变量，未改） |
| 权限 | `--auto`，owner 2026-10-01 授权，批准范围逐轮记录在 `$RIG/logs/<label>.txt` 首行 |

## 2. 判据 ① 的正式拆栏

### ①-A 项目侧真实摩擦

> 项目开发过程中是否真的发生了失败、修复、重新验证？

证据**只能来自 Agent OS 之外**：

- friction oracle 从宿主会话库读到的逐步 `status` / `exit` / `observed_test_results`（§3）；
- 项目自身测试结果的变化（pytest 计数前后对比）；
- `git log` / `git diff --stat`（新增模块、行数、提交点）；
- 票面验收命令的实际退出码。

**不得**把下列任何一项当唯一证据：`tool_trace.ok`、`build_exit_code`、`test_exit_code`、
`needs_review`、`confidence`、memory / proposal / review 的状态。它们是**被试**，不是**尺子**。

### ①-B Agent OS 可见性

> Agent OS 自己的 trace / observation 是否看到了上述失败与方法转向？

这项**允许为 Failed**，且 Failed 不是实验失败，而是本轮要产出的结论之一。

### 出口规则（替换原 §6 的判据①）

| A（项目有摩擦） | B（系统看得见） | 结论怎么写 |
|---|---|---|
| 是 | 是 | 采集形状够用，继续按原计划累积 |
| 是 | 否 | **"项目存在摩擦，但 Agent OS 当前观测能力未捕获"** —— 禁止写成"没有摩擦"，也禁止写成"实验无效" |
| 否 | — | 按原规格换任务设计或换项目，不硬跑 Stage 1 |

①-A 与 ①-B 不得互相顶替；两栏各自的证据要能单独复算。

## 3. 测量工具：friction oracle（measurement-only）

`integrations/opencode/live/friction_oracle.py`。**它是仪器，不是能力**：

1. 只读宿主会话库（`~/.local/share/opencode/opencode.db`，`file:…?mode=ro`），写不进去（有测试钉住）；
2. 不修改宿主库、不修改 Agent OS；
3. 不参与 memory / outcome / proposal / review 的任何一条路径；
4. 输出不进 prompt、不给模型、不进引擎环境；
5. 只作为实验清单与 Stage 0 ①-A 的证据；
6. 探项目 git 状态时带 `GIT_OPTIONAL_LOCKS=0` —— 否则 `git status` 会刷新**被测量项目**的 index，
   仪器碰到被测量对象就等于没测（`test_the_git_probe_does_not_take_optional_locks` 钉住）。

用法（`run.sh` 每次运行结束后自动调用，输出到 `$RIG/oracle/<label>.json`）：

```bash
python3 integrations/opencode/live/friction_oracle.py \
  --from-log "$RIG/logs/<label>.txt" --project <cwd> --out "$RIG/oracle/<label>.json"
python3 -m pytest integrations/opencode/live/tests -q      # rig 自己的测试结构，不在冻结的 tests/ 里
```

三态规则（不许把"没测到"写成"成功"）：

```text
exit == 0            → success
exit != 0            → failure
没有 exit / 非 int    → unknown     ← 不是 success
宿主 status 非 completed/running/pending → failure
```

字段形状：

| 字段 | 含义 | 为什么这样 |
|---|---|---|
| `command_classes` | 一次 shell 调用的**每个**片段的名称形状（≤3 token、无路径/无 `=`/无非 ASCII） | 与插件指纹**故意不同**：插件取首段（缺陷 AN），oracle 要能指出插件漏了什么 |
| `test_command` | 识别出的测试命令类别（pytest/unittest/go test/cargo test/ctest/npm test/make test），否则 `null` | 认不出就是 `null`，不是"没跑测试" |
| `observed_test_results` | **列表**：从宿主记录的输出里按 `in <n>s` 边界逐条抽出 `{failed, passed, errors}`；识别不到 = `null` | 单独标记，绝不伪装成退出码；一次调用里"改坏→红→改回→绿"是两条记录 |
| `masked_test_failures` | `observed_test_results` 里有失败而 `verdict != failure` 的步 | 这就是 AL 的可测量定义 |

隐私线：命令原文与工具输出在本进程里被读完即丢，落盘的只有名称形状、整数与摘要哈希。
`--out` 落在 `$RIG/oracle/`（Stage 0 用 `/home/shade/stage0/E/rig`，在被试项目之外，且不入库）。

## 4. LGD-02 = 校准样本（不是 Stage 1 数据）

```text
Stage 0 calibration / instrument finding
Project friction:               Verified
Agent OS method-level visibility: Failed
Independent oracle evidence:   Verified
```

同一张票的两栏读数（全部由命令产出，可重算）：

| 来源 | 读数 |
|---|---|
| oracle（宿主库） | 42 tool part：`success=19 / failure=0 / unknown=23`；pytest 步 5 次（#17 43 passed、**#23 8 failed, 35 passed**、#28 47 passed、#36 47 passed、**#39 8 failed, 39 passed → 47 passed**）；`masked_test_failures = 2` |
| bash 形状普查 | 19 次 bash 调用，**18 次复合**（`&&` 或 `;`），9 次含管道，宿主记录的**非零退出码 0 个** |
| Agent OS observation | `tool_calls=42`、`tool_trace` 16 步（`n=1–8` + `n=35–42`）、其中 **`ok=false` 0 个** |
| 人门 | `review label 1 --outcome success` → `proposal_created=1` → promotion `M-F8993E1D`（`tags=reconcile,monthly`，因果由人补） |
| 项目侧独立结果 | `43 passed → 47 passed`、新模块 `ledgerd/periods.py`、提交 `d5bf777`、报表与对账同月条数一致（`report 2026-03`=3、`2026-04`=1、`reconcile scanned=3`） |

结论形状要说准：**摩擦存在且被第三方尺子量到了；被试看不见它。**
这条样本不删除、不重跑、不改写，也不得混进 Stage 1 的统计。

## 5. AL / AM / AN —— 只登记，不修

| 编号 | 形状 | 实测证据（LGD-02） | 后果 | 本轮为什么不修 |
|---|---|---|---|---|
| **AL** | 插件用**整条 shell 调用**的退出码判 `ok`。`pytest \| tail` 取 `tail` 的 0；`a && b` / `a ; b` 取最后一条的状态 | 18/19 bash 步是复合、9 步含管道；2 次真实 pytest 红；`tool_trace` 里 `ok=false` 为 0 | `ok` **不能**当作项目真实失败的可靠测量；审核材料会把有失败的运行显示成"一次通过" | 修它要改 `integrations/opencode/plugin/agent-os.js`（冻结面）⇒ 属 exp-v2 |
| **AM** | 引擎自己的 validate 会**进入实验项目执行**自动探测出的构建命令 | `plan.project_preflight`：`build_system=pip`、`compile_command="python3 -m compileall -q ."`；`stages.validate`：`build_status=PASS`、`test_status=SKIPPED`；observation：`build_exit_code=0` 进 `present`，`mass=0.4`（门限 0.45），正文打出"可证：构建退出码 0" | ①"Agent OS 在实验项目里只观测不执行"这句话是**假的**，准确版本见下；②Agent OS 自己跑出来的结果**不能**当独立项目摩擦证据，也不能拿来替 Agent 的成绩说话（缺陷 AI 的实体化） | 改 validate 归属 = 改 `aos/**`（冻结面）⇒ 属 exp-v2 |
| **AN** | `methodOf` 对复合命令只取**第一个**存活片段 | `#38 printf`、`#39 cp`（那两条里真正的动作是 pytest）；`#2 find f`（`find . -maxdepth 1 -type f`） | 方法身份保真度低，"用了什么方法验证"经常丢失 | 改指纹 = 改插件（冻结面）⇒ 属 exp-v2 |

**AM 的准确表述（替代任何"不执行项目代码"的说法）**：

> Agent OS 在 postflight 会按自动探测到的构建系统在**被观测项目**里运行构建类命令（本机实测为
> `python3 -m compileall -q .`）。因此它的自证结果不是独立证据；实验文档中任何"Agent OS 不进项目执行
> 代码"的表述一律作废。本仓库现有的 `docs/research/**` 里那句"Agent OS 不执行任何来自记忆的指令"
> 仍然成立 —— 它讲的是"不执行记忆里的命令"，与"不执行自探测的构建"是两件事。

另外，`exp-v1-baseline.md` §3.3 的"轨迹上限 16 步会丢中部"这一条要降级为**次要**：LGD-02 里真正的
失败步（`#23`、`#39`）分别是"被位置裁掉"和"**已被保留但记成了成功**"。上限不是瓶颈，`ok` 的语义才是。

## 5bis. AO —— 仪器泄漏：脚手架一度住在被试项目里

这不是 Agent OS 的能力问题，是我把尺子放错了地方。**LGD-06 因此作废两次**：

| 次 | 标签 | 会话 | 怎么作废的 | 计不计数 |
|---|---|---|---|---|
| 1 | `LGD-06` | `ses_f088b5508ffedHbNJtJfNrfFJF` 之后的 `…153B` loop | 我在中途掐掉（当时 `3 failed, 44 passed`、未提交） | **不计** |
| 2 | `LGD-06-R2` | `ses_f085d3748ffeUK8ZmoD0fcqFtU` | 25 步、**零失败、唯一一次 pytest 直接 49 passed** —— 因为它先读了答案（见下） | **不计** |

R2 的实际行为（宿主 `resolved path` + 权限评估记录，全部只读取证）：第 1–7 步正常侦察，
其中读了 **`.gitignore`**；第 8 步 `cat .arms/tickets/LGD-06.md`；第 11 步 `tail -40 .arms/E/rig/logs/LGD-06.txt`
（上一次中止运行的宿主日志）；第 12 步 `cat .arms/E/manifest.tsv`（我的实验清单，列名写着
`trace_retained`/`recall_ids`，还有"LGD-06 killed mid-run"）；第 13–14 步 `head -60` / `sed -n '60,200p'`
读了 `.arms/E/inflight/LGD-06.diff`，并 `cat` 了 `inflight/backfill.py`、`0004_amount_cents.sql`、
`pytest-at-abort.txt`。然后它写出**同名的两个文件**，一次测试就绿。

泄漏机制：我把 tickets、rig 日志、实验清单和"上一次尝试的完整答案"放在 `<project>/.arms/`，
而这个目录同时被写进 `.gitignore` —— 被试只要 `ls` 加读 `.gitignore` 就能发现它。**答案放在被测量对象
读得到的地方，实验就不再测量任何东西**：R2 的"零摩擦"是泄漏的产物，不是开发的样子（对照 LGD-02：
42 步、2 次真实红、43→47）。

处置（全在允许面内，不改 `aos/**`）：

1. 脚手架整体搬出项目树 ⇒ `/home/shade/stage0/{tickets,E/store,E/rig,E/inflight,E/manifest.tsv}`；
   项目内不再有 `.arms/`（空壳用 `rmdir` 收掉，搬移前后 md5 核对一致）。
2. `run.sh` 加两条**放置守卫**，在任何模型调用之前拒绝开跑：被试目录内存在 `.arms/`、
   或 `$RIG`/`$STORE` 落在被试目录内 ⇒ `exit 1`。测试：`live/tests/test_run_guard.py`（4 条，先红 ——
   红屏是 `missing placement guard`，两条拒绝路径的断言失败不是因为消息不存在就是因为守卫不存在，
   都由第 4 条按源码顺序钉住"两条守卫必须早于宿主启动行"）。
3. oracle 的 `command_classes` 顺手修掉同一类噪声：shell 控制词（`for`/`do`/`done`/`in`…）与
   单字母 flag 值不再当命令名 —— `for f in …; do cat …; done` 现在是 `cat`，`find . -maxdepth 1 -type f`
   现在是 `find`（`test_shell_control_words_and_flag_values_are_not_command_names` 先红后绿）。
4. R2 现场：4 项改动按字节抓到 `/home/shade/stage0-void/LGD-06-R2/`，再 `git stash push -u` 封存为
   `stash@{0}`（`LGD-06-R2 contaminated-run 2026-10-01 …`）；第 1 次的 stash 顺位下移为 `stash@{1}`（`64a7e98d…`）。
   两次都不 apply、不 drop、不进统计。

我自己在这轮还犯过一次同类错误：**在运行进行中的项目里跑了 `python3 -m pytest`**（仪器动了被测量对象，
当时那份 `3 failed` 读数因此不可用）。R3 起，运行期间不碰项目目录，取证只读日志、宿主库与 oracle。

## 6. 本轮明确没做的事

- 未改 `aos/**`、`content/**`、`tests/**`、`integrations/opencode/plugin/agent-os.js`；
- 未重打 tag、未改模型 id、未改 schema、未改权重、未改 memory 行为、未改 validate 逻辑、未改轨迹上限或指纹；
- 未运行新的实验任务、未进入 Stage 1、未补跑 LGD-06；
- `~/.config/opencode/**` 零写入；真库 `store/aos.db` 见 §7 的哈希自证。

**AL/AM/AN 是 exp-v1 的已知测量限制，不是本轮要修的代码。**

## 7. 现场与恢复

| 事项 | 值 |
|---|---|
| 臂 E store | `/home/shade/stage0/E/store/aos.db`（1 条 active 记忆 `M-F8993E1D`、1 条 hot observation（LGD-02）、2 条 loop —— `LOOP-…-38B2` 已完整回报，`LOOP-…-153B` 属于作废的第 1 次 LGD-06，开着没回来） |
| 开发真库 | `store/aos.db` sha256 前缀 `c3907554319a0fe3`，本轮未变 |
| LGD-06 | **中止，不作实验数据**：中途被我掐断，未发 postflight，臂库里留下一条开着没回来的 loop（`LOOP-20261001124603-153B`） |
| LGD-06 现场捕获 | 第 1 次：`/home/shade/stage0/E/inflight/`（搬自原 `.arms/E/inflight`，md5 与原文件一致）；第 2 次：`/home/shade/stage0-void/LGD-06-R2/`（`state-and-diff.txt` + `files/` 四件，md5 核对过） |
| LGD-06 可恢复位 | `stash@{1}` = `64a7e98d0b91cdd7901170a96ef5990de4eed765`（第 1 次中止，消息 `LGD-06 aborted-run …`）；`stash@{0}`（第 2 次污染，消息 `LGD-06-R2 contaminated-run …`）。恢复一律用 `apply`，不 `pop`、不 drop，且**都不进 Stage 0 统计** |
| 中止点内容 | 第 1 次：`cli.py`（+`backfill-amount`）、`backfill.py`、`0004_amount_cents.sql`，`3 failed, 44 passed`；第 2 次：再加 `tests/test_migrations.py`，唯一一次 pytest 直接 `49 passed`（零失败，见 §5bis） |
| 恢复后 | 项目回到 `d5bf777`、工作树 0 项、`47 passed`；项目内已无 `.arms/` |

## 8. Stage 0 继续前的检查单

```bash
git -C /home/shade/Public/test status --porcelain          # 必须为空
git -C /home/shade/Public/test rev-parse HEAD              # 必须是 d5bf777…（LGD-02 之后）
test ! -e /home/shade/Public/test/.arms                    # 脚手架不得在被试项目内（AO）
cd /home/shade/Public/AgentOS
python3 -m pytest -q                                       # 447 passed（冻结面未动，计数不应变）
node --test tests/js/plugin.test.mjs                       # 27 pass —— 不要写 `node --test tests/js/`，那是假红
python3 -m pytest integrations/opencode/live/tests -q      # 15 passed（10 oracle + 4 放置守卫 + 1 控制词）
git status --porcelain                                     # 只允许 docs/experiment/** 与 integrations/opencode/live/**
```

跑票时（脚手架在项目外）：

```bash
export AOS_RIG=/home/shade/stage0/E/rig AOS_STORE_DIR=/home/shade/stage0/E/store
bash integrations/opencode/live/run.sh LGD-06-R3 /home/shade/Public/test --auto \
  "$(cat /home/shade/stage0/tickets/LGD-06.md)"
```

## 9. 逐票记录

### LGD-06-R3（干净重跑，计入 Stage 0）

**Ticket**：`amount_cents` 定点化第一步 —— 新迁移只加列（历史行留 NULL）、加可反复执行的
`backfill-amount` 子命令、读路径不动、不改已有三个脚本；验收含"migrate 连跑两次为 no-op"与
"回填后无 NULL、与 `CAST(ROUND(amount*100) AS INTEGER)` 全等"。

**①-A Project friction**

```text
Result: Verified
```

Evidence（一律不看 Agent OS 的产物）：

| 来源 | 读数 |
|---|---|
| 宿主库只读（第 44 步） | 命令 `cd … && rm -f /tmp/lg6-old.db* && python3 - <<PY`，输出第一行 **`zsh:1: no matches found: /tmp/lg6-old.db*`**，而该步 `exit=0 / status=completed` |
| Agent 自己的叙述（日志 1192 行） | "The `rm -f /tmp/lg6-old.db*` glob failed in zsh (nomatch aborts the whole line), so the history DB was never created and **that check was invalid. Redoing it:**" |
| 返工（第 45、46 步） | 第 45 步把文件名写全（`rm -f a.db a.db.imported.json`）才真造出"只到 0003 的历史库"；第 46 步才验到 `version before 0004 = 3`、列里没有 `amount_cents`、历史行 2 → `apply 0004` → 回填前 NULL=2、`updated=2` → 再跑 `updated=0` |
| oracle | 51 parts：`success=20 / failure=0 / unknown=31`，`masked_test_failures=0` —— **oracle 也没抓到这次摩擦**（见 §10 AQ） |
| 项目测试数 | `47 passed → 51 passed`（新增 4 条用例，见 `git diff --stat d5bf777 HEAD`：5 个文件、+137/−5） |
| 我的独立验收复算 | `migrate` 连跑两次（第二次打印 `no pending migrations`）均 0；`ingest` 插入 4；`backfill-amount` `updated=4`；`amount_cents IS NULL` 计数 0；与 `CAST(ROUND(amount*100) AS INTEGER)` 不一致计数 0；`schema_version` = 1,2,3,4；`pytest -q` 51 passed |

摩擦的形状要说准：**这一票没有"测试红"，但有一次"验收静默失效 + 返工"** —— 通配符在 zsh 下无匹配会中断整行，
`rm` 根本没执行，而复合命令的退出码仍是最后一段给的 0。真实成本存在，只是它不长在 pytest 上。

**①-B Agent OS visibility**

```text
Result: Failed
```

| 项 | 读数 |
|---|---|
| observation | `LOOP-20261001133757-29E5`，`outcome=partial`（`mass=0.4` < 门限 0.45 ⇒ 交人标注），`tool_calls=51`，`tool_trace` 16 步（`n=1–8` + `n=44–51`），**`ok=false` 0 个** |
| 第 44 步在不在窗口里 | **在**。它被记成 `{"n":44,"tool":"bash","method":"rm","exit":0,"ok":true}` —— 这一次连"被截断"都不是借口，是 `ok` 的语义本身把它读成通过 |
| 提案正文的过程行 | `#1 find f 通过 → #2 ls 通过 → #3–6 read → #47 python3 -m pytest 通过 → #48 git log 通过 → #49 git add 通过 → #50 cat 通过 → #51 git log 通过（省略 5 步）`；唯一带摩擦的 44/45/46 在 170 字额度里被省掉 |
| Agent OS 观察到的 | 51 次调用的量、终局成功、构建退出码 0、路由 `data_model` |
| Agent OS 没观察到的 | 那次静默失效、它被判无效并返工、以及"用显式文件名替代 glob"这个方法级差异 —— **恰好是这张票上唯一值得记的经验** |

**关键事件**

| 问题 | 读数 |
|---|---|
| 是否发生失败 | 项目侧：是（第 44 步的检查无效）；测试层：否（4 次 pytest 全绿） |
| 是否发生方法变化 | 是：`rm -f <路径>*` → `rm -f <显式文件列表>`（同一目的两种做法，先后顺序真实存在） |
| 是否出现 compound / pipeline | 是：第 44/45/46 都是 `cd … && rm … && python3 - <<PY`；#47/#49/#51 带管道 |
| test result 与 shell exit 是否不一致 | 是，但**新增一种形状**：不是"pytest 红而 exit 0"，是"shell 自己报错而 exit 0" |
| AL / AM / AN | 三条全部复现，见下 |

**是否进入 Stage 0 统计**：**Yes**。票面未改、脚手架在被试项目之外、放置守卫先跑过；
宿主库只读复核 `resolved path` 与权限评估里**没有任何 `.arms` / `stage0` 命中**（对照 R2 的 6 次命中）。
人门：`review label 3 --outcome success`（不带 `--skill`，因为召回为 0，无从归因）⇒ 一份提案
⇒ `M-21AE3B79`（`tags=migrate,backfill,fixture`，因果句由人补）。

### AL / AM / AN 在 R3 的复现

- **AL 复现（更强）**：LGD-02 那次还能说"失败步被位置裁掉"，R3 的失败步 `#44` **就在保留窗口内**，
  仍被记为 `ok=true`。所以 AL 与截断无关，是 `ok = (整条 shell 的 exit == 0)` 的语义问题；
  而且这次连 pytest 汇总都不存在（`no matches found` 不是测试失败），`test_exit_code` 依然缺席。
- **AM 复现**：observation 的 `present` 含 `build_exit_code` + `validation_status`，正文照例打
  "可证：构建退出码 0"（引擎自跑的 `compileall`），而真正跑的 4 次 pytest 只以 `observed_test_results`
  存在 my oracle 里，**在 Agent OS 侧 `test_exit_code` 仍是 absent**。
- **AN 复现**：`#44 rm`、`#45 rm` 的真实动作是"造历史库并验升级路径"，指纹只给第一个片段；
  `#1 find f` 再次出现。

### 10. AQ —— 我自己仪器的盲区（登记，本轮不改）

R3 证明 oracle 也会漏：`masked_test_failures` 的定义要求"解析出 pytest 汇总且有失败"，
而第 44 步的失败是 shell 自身的 `zsh:1: no matches found`，没有 pytest 汇总可解析 ⇒ 报成 `success`。

```text
observed_test_results = null  →  不代表这一步没问题
```

要补的形状（属于允许面，等下一轮再动，避免在看清样本前调仪器）：识别 shell 自己的报错前缀
（`zsh:`、`command not found`、`No such file or directory` 之类），单独记成
`observed_shell_error`，**仍然不得回写成 exit**。

### 11. 只读预检：R3 之后我对"下一票能不能召回这条经验"的预测（跑前写下，跑后核对）

用引擎自己的查询形状（`recall_stage`：`scope_project` 取 cwd 目录名，`keywords` 走 `_keywords`）做只读
`retrieve(log=False)`：

| 票面 | route | considered | 命中 | 分数 |
|---|---|---|---|---|
| LGD-07（退避） | `config` | 2 | 无 | 低于门限 |
| LGD-11（迁移幂等） | `data_model` | 2 | `M-21AE3B79` | **0.422** |

预测：**LGD-11 开跑时应召回 `M-21AE3B79`**（`injection_chars > 0` 且 `memory_ids` 含它）。
这条是判据 ④ 在 Stage 0 里第一次真正可检的点。

**同时纠正我自己**：上一轮我用同一方法"预检" LGD-06 召回为 0，但那次查询**漏了 `scope_project`**，
`total_considered` 因此是 0 —— 结论碰巧对了，方法是错的，当时那句"与预期一致"不该写。
用正确形状复算：R3 开跑时库内只有 `M-F8993E1D`（月度窗口，tag 在 06 票面命中 1 个 < 门限），
所以 R3 的真 `retrieved=0` 与打分一致，不是 scope 过滤掉了。

两点必须并写：

1. **R3 当时召回为 0 是真的**：那一刻库里只有 `M-F8993E1D`（月度口径那条，`tags=reconcile,monthly`，
   category `test`），对 LGD-06 的票面过不了 0.15 —— 用正确查询复算：`considered=2 / after_filter=1`，
   留下的那条是 R3 自己后来生成的 `M-21AE3B79`，`M-F8993E1D` 被过滤掉。
2. **我上一轮那次"只读预检"方法是错的**：查询里漏了 `scope_project`（引擎在 `recall_stage` 会带上，
   取 cwd 目录名），于是 `total_considered=0`，报出来的 `retrieved=0` 是"我什么都没给它比"而不是"比了不够"。
   结论蒙对、过程无效，因此那轮报告里"与预期一致"这句话不成立；本节表格才是可复算的版本。
