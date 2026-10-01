# Exp-v1 · Stage 0 —— ledgerd 项目、两栏判据与测量现场（2026-10-01）

本文件只改**测量**。Agent OS 的冻结面一个字节都没动，AL/AM/AN 三条在本轮只登记（§5）。

## 0. 这份文件要拆开一个混淆

Stage 0 的第一条出口判据原来写成一句话："项目是否产生可记录的失败"。LGD-02 给了它两个相反的答案：

- 项目侧：真的产生了失败、修复、再验证（独立证据见 §4）。
- Agent OS 侧：它的 `tool_trace` 里 **0 个** `ok=false`，42 步全部读成"通过"。

所以"项目有"与"系统看得见"必须分栏报告，否则同一份数据既能判过又能判不过。
判据 ① 自本文件起拆成 **①-A（项目侧摩擦）** 与 **①-B（Agent OS 可见性）**。

## 1. 实验设置（本轮未改）

| 项 | 值 |
|---|---|
| 项目 | `ledgerd` @ `/home/shade/Public/test`（流水导入与月度对账，Python 3.14 标准库 + pytest） |
| base commit | `70c935f93a6b811ba3cc848cae9fc1e341582f2f`（种子两笔：`e5f5921` 初始导入、`70c935f` README 用法） |
| 票与顺序 | LGD-02 → LGD-06 → LGD-07 → LGD-11，一任务一会话、一任务一 commit，项目不 reset |
| 臂 | Stage 0 只跑臂 E（+Agent OS）；对照臂用 `AOS_RIG_INERT=1`，**不用 `--pure`** |
| store 隔离 | `AOS_STORE_DIR=/home/shade/Public/test/.arms/E/store`（真库 `store/aos.db` 一字未动，见 §7） |
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
`--out` 落在 `$RIG`（`/tmp/aos-rig` 或项目的 `.arms/`，两者都不入库）。

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

## 6. 本轮明确没做的事

- 未改 `aos/**`、`content/**`、`tests/**`、`integrations/opencode/plugin/agent-os.js`；
- 未重打 tag、未改模型 id、未改 schema、未改权重、未改 memory 行为、未改 validate 逻辑、未改轨迹上限或指纹；
- 未运行新的实验任务、未进入 Stage 1、未补跑 LGD-06；
- `~/.config/opencode/**` 零写入；真库 `store/aos.db` 见 §7 的哈希自证。

**AL/AM/AN 是 exp-v1 的已知测量限制，不是本轮要修的代码。**

## 7. 现场与恢复

| 事项 | 值 |
|---|---|
| 臂 E store | `/home/shade/Public/test/.arms/E/store/aos.db`（1 条 active 记忆 `M-F8993E1D`、1 条 hot observation、2 条 loop） |
| 开发真库 | `store/aos.db` sha256 前缀 `c3907554319a0fe3`，本轮未变 |
| LGD-06 | **中止，不作实验数据**：中途被我掐断，未发 postflight，臂库里留下一条开着没回来的 loop（`LOOP-20261001124603-153B`） |
| LGD-06 现场捕获 | `/home/shade/Public/test/.arms/E/inflight/`（`LGD-06.diff` + `backfill.py` + `0004_amount_cents.sql` + `pytest-at-abort.txt`，md5 与原文件一致） |
| LGD-06 可恢复位 | `git stash` `stash@{0}` = `64a7e98d0b91cdd7901170a96ef5990de4eed765`，消息 `LGD-06 aborted-run 2026-10-01 (killed mid-flight; not experiment data)`；恢复用 `git stash apply 'stash@{0}'`（apply 而非 pop，本轮不 drop） |
| 中止点内容 | `ledgerd/cli.py`（+`backfill-amount` 注册）、`ledgerd/backfill.py`、`ledgerd/migrations/0004_amount_cents.sql`；`3 failed, 44 passed`（都是半张迁移网造成的） |
| 恢复后 | 项目回到 `d5bf777`、工作树 0 项、`47 passed` |

## 8. Stage 0 继续前的检查单

```bash
git -C /home/shade/Public/test status --porcelain          # 必须为空
git -C /home/shade/Public/test rev-parse HEAD              # 必须是 d5bf777…（LGD-02 之后）
cd /home/shade/Public/AgentOS
python3 -m pytest -q                                       # 447 passed（冻结面未动，计数不应变）
node --test tests/js/plugin.test.mjs                       # 27 pass —— 不要写 `node --test tests/js/`，那是假红
python3 -m pytest integrations/opencode/live/tests -q      # 9 passed（oracle，本轮新增）
git status --porcelain                                     # 只允许 docs/experiment/** 与 integrations/opencode/live/**
```
