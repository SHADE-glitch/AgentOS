# exp-v1 基线冻结记录（2026-10-01）

目的只有一个：让后续 Stage 0 / 1 / 2 有一个**可重复、可审计**的起点。本文件不新增能力、不改逻辑，
它记录"冻结在哪、冻结了什么、哪些已经证明、哪些还没有"。

## 1. 基线身份

被冻结的**代码状态**是 `53de1ad`；`exp-v1` 这个 tag 落在紧随其后的一笔**只含文档**的提交上
（因为冻结记录本身必须进仓库）。两者**在冻结面上逐字节相同**，自证命令见下面最后一条 ——
注意比较范围必须限定成 §2 的冻结面：本文件与 §2 列的文件之外还有两份文档会被这笔提交改动，
其中一份按仓库惯例放在 `integrations/opencode/README.md`（接缝说明，属文字不是代码）。
所以"整个 diff 只含 `docs/`"这种断言一上手就是假的（我第一次就写错了它），必须按范围断言。

```
被冻结的代码 commit:  53de1adc5fb5ff92877ae11e37606e2f9e8f6dbc  (= 53de1ad)
tag exp-v1 指向:      本文件与另两份文档的提交（git rev-parse exp-v1 的短哈希见 §5 复核输出）
schema:               v5（`sqlite3 store/aos.db "PRAGMA user_version"` 实测 = 5；migrations 未新增版本）
python tests:         447 passed（`python3 -m pytest`）
javascript tests:     27 pass / 0 fail（`node --test tests/js/plugin.test.mjs`）
工作树:              `git status --short` 空
```

复核这三件事的命令（冻结前后各跑一次，输出必须一致）：

```bash
cd <repo>
git rev-parse HEAD; git status --short
python3 -m pytest                                   # 期望 447 passed
node --test tests/js/plugin.test.mjs                # 期望 # pass 27 / # fail 0
sqlite3 "file:store/aos.db?mode=ro" "PRAGMA user_version"   # 期望 5
git diff --name-only 53de1ad..exp-v1 -- \
    aos/ content/ tests/ integrations/opencode/plugin/     # 期望：空（冻结面零差异）
```

**不允许回退到的旧点**：`4e9bfec`。它早于第十六轮，缺 `tool_trace`/`tool_calls` 这条采集链
（契约、合成回显、插件轨迹、身份与轨迹分离、人门可见性都在 `c698094..53de1ad` 之间落地），
用它打基线会把"经验形成"这一格当成已经存在。

## Model（实验模型，冻结不变量）

```
model:      opencode/space-bunny-free
provider:   opencode
决定日期:    2026-10-01（owner）
禁止:       实验期间修改模型 id —— 它是本文 §2 冻结不变量清单里的第一项
```

`space-bunny-free` 在本机目录缓存 `~/.cache/opencode/models.json` 里确实存在（provider `opencode` 与
`opencode-go` 各一份，`cost` 四项均为 0）。为什么是它，三条：

1. `huoshan/ark-code-latest` 当前不可用：shell rc 里导出的该 provider API key 环境变量值是空串
   （长度 2，即一对引号），不是"我没配上"，是"配了空的"。
2. 采集链已经在它身上真跑通过一次：五个 bash 步骤全部落成 method trace，`session.idle → postflight`
   在无头 `run` 模式首答即中，`AOS_TIMEOUT_MS` 保持默认 1200（见 `integrations/opencode/README.md`
   的 exp-v1 real-host probe 一节）。
3. 实验目标不是比较模型能力，而是"固定模型 + 长期经验层"是否让轨迹发生变化 ⇒ **换模型就是换被解释的对象**。

这条决定的代价一起记，别把它写成普适结论：**全部结果只在这个免费模型上有效**。换成任何别的模型都算
一次新实验，需要重新打基线，`exp-v1` 不覆盖它们。

已有的硬约束（不是本节新立的规矩）：`integrations/opencode/live/run.sh:70` 与 `live/README.md:69` 的
recipe 把这个 id 写死在 `-m` 上 ⇒ 凡经 rig 跑的运行天然落在冻结模型上；绕过 rig 直接调用宿主时必须显式
带 `-m opencode/space-bunny-free`（上面那次探针就是这么做的）。

## 2. 冻结文件列表（实验期间不得修改）

路径全部实测存在（`aos/core/loop/` 与 `aos/contract/` 是整目录）。

```
aos/contract/schema.py
aos/contract/**                     # 含 preflight.py、postflight.py、__init__.py

aos/core/memory/retrieve.py         # 检索与排序
aos/core/memory/record.py           # 观察记录与提案起草
aos/core/memory/evolve.py           # 人门 / 晋升 / 结算
aos/core/memory/inject.py           # 注入渲染
aos/core/memory/policy.py           # 阈值与默认策略
aos/core/memory/store.py            # 存储层
aos/core/memory/authoring.py        # 作者面
aos/core/memory/conflict.py         # 冲突分桶
aos/core/memory/evaluate.py         # 评估
aos/core/memory/migrations.py       # schema

aos/core/outcome.py                 # verdict 合成

aos/core/loop/                      # lifecycle.py、stages.py、state.py、pending.py

integrations/opencode/plugin/agent-os.js          # 采集与注入的那一侧接缝
```

另外两份属于"配置而非代码"，同样视为冻结面（改了它们等于改了判据）：

```
content/policies/*.json             # 六个阈值文件：decay/injection/outcome/promotion/rejection/retrieval
```

**违反任一冻结项 ⇒ 实验作废**：重新打基线、从 Stage 1 重跑，不在旧数据上继续累计。
允许修改的面只有：`docs/**`、`integrations/opencode/live/**`（rig/脚本）、以及实验项目本体所在目录。

冻结不变量（这些一旦变了，前后两组数字就不可比）：**模型 id**（已固定，见上文 Model 一节）、
插件符号链接指向、backlog 内容与顺序、被测项目的 base commit、`AOS_STORE_DIR` 指向哪个库。

## 3. 已验证能力边界

分三栏写，**不合并**。Verified 的那一栏每一条都有可复跑的取法；Unverified 的一条都没有。

### 3.1 Verified `[Verified]`

| 主张 | 证据与复跑方法 |
|---|---|
| 经验可以形成（含"试 A 败 → 换 B 成"这类方法级经验）——**条件是轨迹里真的带有失败位** | 第十六轮 CLI 屏幕（手工喂入含 `ok=false` 的轨迹）+ 第十七轮真宿主：`_attempts` 判出 `changed=True`。形状已证；**真实宿主自己产出失败位这一段在 Stage 0 被判为 Failed**（见 §3.3 的 AL 与 `docs/experiment/stage-0-ledgerd.md` §4），所以这一行不能读成"实盘上已经能长出方法级经验" |
| 经验可以保存 | `review approve` 后 `memories` 出现 `procedural` 行，body 含 `过程：…`，`dedupe_key` 由不含轨迹的正文算出 |
| 一次教训只对应一次决定 | 同一任务第二次带不同轨迹 ⇒ 同一 `memory_id`、库里 1 行；`test_two_traces_of_one_task_leave_one_review_not_two` |
| 经验可以检索 | 批准并给 `--tags` 后，同主题提问召回该条（真库只读实测：路由命中 0.15、tag 命中 0.16/0.24/0.39 两条入口） |
| 经验可以注入 | 引擎 `recall.injection_chars` == 插件日志 `len=`（第十一轮 511==511、第十四轮 TUI 323==323、第十五轮 1122→1359 且 +237 为跑前预测） |
| 人门的一次决定会改变下一次召回 | 真库闭合：注入块从 1122 字符/3 条变 1359 字符/4 条，两处 `len` 一致 |
| 真实宿主能产生 method trace | 第十七轮一次 `opencode run --auto`：5 个 bash 步全部落库，指纹 `ls` / `pytest tests` / `python3 -m pytest probe_tests` / `cat` / `grep`。**但 Stage 0 的 LGD-02（42 步真任务）里 `ok=false` 出现 0 次，而项目确实红了两次** ⇒ 轨迹能落库，失败位不能可靠落库，见 AL |
| `session.idle → postflight` 在无头 `run` 模式成立 | `agent-os: postflight sent … answered=true`，且 `doctor.pending_postflight.outstanding=0`（默认 1200ms 未改） |
| `args.command` 真存在 | 宿主自身库里本次会话 5 个 bash tool part 的 `state.input` 键名均为 `command`（只读查键名） |
| 原命令不出宿主 | canary 在 `observations`/`learning_reviews`/`$store`/我方日志/`review list` 输出/仓库六处计数全 0；`grep` 那步的指纹恰为 `grep` |
| 轨迹不买到判决权重 | 三臂对照：有轨迹 2 臂与无轨迹 1 臂的 `mass` 同为 0.0、`outcome` 同为 `partial`、`needs_review` 同为 1 |

### 3.2 未证明 `[Unconfirmed]` —— Stage 0/1/2 要回答的就是这些

- 经验是否**减少**未来试错（同类任务的失败尝试次数、到达可行方案的轮次/耗时是否下降）。
- 经验是否改变 Agent 的**首次动作**（默认路径偏移）。
- 注入是否让**模型本来不会答**的那类任务（项目特有事实、仓库内部约定）从错变对。
- 经验层相对 `AGENTS.md` 静态说明的**增量**（同一份知识写进 AGENTS.md 是否效果相同）。
- 经验层相对普通 memory/basic-memory 的**增量**（判据 4 要求先在能力矩阵指到"无人实现"那一列，仍未指到）。
- 旧问题复发率是否下降（需要先有可比的错误签名与"机会数"归一）。
- 跨轮/跨会话的经验**粘性**：第十四轮实测同一会话第二轮换话题后召回为 0，注入更像"每次提问重查一次字典"。

一句话：**"能形成、能存、能召回、能注入"已证；"因此 Agent 做得更对/更省"未证。** 不要把前者写成后者。

### 3.3 已知限制（本基线的固有形状，不在实验期间修）

| 限制 | 后果 |
|---|---|
| 非 shell 工具没有 exit（`glob` 的 metadata 只有 `count/truncated`），宿主 `output` 又无 `error` 键 | 编辑/读文件类工具的失败**不可见**，`tool_errors` 在本机恒缺席 ⇒ verdict 覆盖度低、多数运行进人门 |
| 被拒绝/未批准的调用根本不进 `tool.execute.after` | "这个方向被否决了"最有信息量的事件零痕迹 |
| 纯思考层的转向无法观察 | 只执行了的方法切换才记得到；想明白但没动手的记不到 |
| 跨 loop 的方法迁移不支持 | 每次提问开新 loop 并重置累加器 ⇒ 第 1 轮失败、第 3 轮成功是两个轨迹，永不相见 |
| `exit=0` ≠ "这一步才是对的方法" | 轨迹只给相邻性，不给因果；归因仍要人写（`review approve --body`） |
| 轨迹上限 16 步（去中间留两端） | 长会话中部丢失，但步号自带缺口，且 `tool_calls` 给真实总数。**Stage 0 实测：上限不是瓶颈** —— LGD-02 的失败步之一（`#39`）就在保留窗口里，仍被记成"通过"；瓶颈是下一行 AL |
| **AL**（Stage 0 新增，实测于 LGD-02）：`ok` 取的是**整条 shell 调用**的退出码 | `python3 -m pytest -q \| tail -30` 取 `tail` 的 0；`cp … && pytest … && git diff` 取 `git diff` 的 0。该票 19 次 bash 里 18 次复合、9 次含管道，宿主记录的非零退出码 **0 个**，而项目真实红了两次 ⇒ **`ok` 不能当项目失败的测量**，审核材料会把有失败的运行显示成一次通过。修它要动插件（冻结面）⇒ 归 exp-v2；Stage 0 用 `live/friction_oracle.py` 从宿主库独立量摩擦 |
| **AM**（Stage 0 新增）：引擎的 validate 会在被观测项目里**执行**自动探测出的构建命令 | LGD-02 的 loop：`build_system=pip`、`compile_command="python3 -m compileall -q ."`、`build_status=PASS`；observation 里 `build_exit_code=0` 进了 `present`，`mass=0.4`（门限 0.45），提案正文打出"可证：构建退出码 0" ⇒ ①任何"Agent OS 不进项目执行代码"的表述作废；②自证结果**不是**独立项目摩擦证据，也不许替 Agent 的成绩说话（缺陷 AI 的实体化）。本轮不改 validate 归属 |
| **AN**（Stage 0 新增）：`methodOf` 对复合命令只取第一个存活片段 | 同一条票里 `#38 printf`、`#39 cp` 才是真名 `python3 -m pytest` 的两次运行；`find . -maxdepth 1 -type f` 被记成 `find f` ⇒ 方法身份保真度低，"用什么方法验证"经常丢失。只登记，改指纹归 exp-v2 |
| 回读（backfill）产生的行没有轨迹 | `source='backfill'` 与 `source='hot'` 形状不一致 |
| `user_interrupted` 读了没人写（缺陷 AK） | 中断这条硬否决对 opencode 实际从不生效 |
| 退出码→构建/测试的归属映射未获批准（缺陷 AI） | 轨迹里有 exit，但 `test_exit_code`/`build_exit_code` 仍为空，verdict 不因此变准 |
| `--auto` 是本次采集的前提 | 无头批量必须 `--auto`；它的批准范围必须逐轮记录（AGENTS.md 真机一节） |

## 4. 判据仍按原样生效（本文件不改判据）

- **判据 1**：到 2026-10-29，`aos doctor` 的 `observations.hot` 是否 ≥ 30，且**只数 owner 的交互会话**；
  rig / 探针 / 手喂产生的观测一律不计（本轮探针写在隔离库，真库 `hot` 仍为 5）。
- **判据 2**：人门队列周均待标注数（现为 #24/#25，owner 自己的，实验期间也不代为标注）。
- **判据 4**：不新增采集面。本轮 `args` 的读取是 owner 明确批准的例外，其边界（只取 `command`/`cmd`、
  只上规范化指纹）写在 `integrations/opencode/README.md`。

## 5. 冻结与复核输出

冻结动作：文档提交进仓库后 `git tag exp-v1`。**tag 哈希故意不写进本文** —— 文档会在 tag 之后继续被订正，
每次重指都会让上一版记录过期；被冻结的东西只有一个：**代码点**。读法一律用命令，不用记忆：

```bash
git rev-parse exp-v1                          # tag 当前指向（文档提交，可随订正移动）
git rev-parse exp-v1^{commit}                 # 同上，解引用
git merge-base --is-ancestor 53de1ad exp-v1 && echo "代码基线在 tag 的祖先链里 ✓"
git diff --name-only 53de1ad..exp-v1 -- \
    aos/ content/ tests/ integrations/opencode/plugin/   # 必须为空：冻结面零差异
```

**"基线"= `53de1ad`（代码点）；tag 只是指向一份描述它的文档。** 复核输出见下。

### 冻结复核（实测输出，不是承诺）

```
被冻结代码点 (53de1ad)      = 53de1adc5fb5ff92877ae11e37606e2f9e8f6dbc
tag exp-v1 当时指向          = 见上面那条 git rev-parse（文档提交会移动，不写死）
git diff --name-only 53de1ad..exp-v1 -- aos/ content/ tests/ integrations/opencode/plugin/   = （空）
python3 -m pytest                 = 447 passed
node --test tests/js/plugin.test.mjs = # tests 27 / # pass 27 / # fail 0
sqlite3 "file:store/aos.db?mode=ro" "PRAGMA user_version" = 5
git status --short                = （空）
真库 store/aos.db sha256 前缀      = c3907554319a0fe3…（探针前后一致，实验数据未进真库）
```

一处本轮自我修正：本节最初写的是"`git diff --name-only 53de1ad..exp-v1` 只应出现 `docs/` 下的路径"，
实跑发现该提交还含 `integrations/opencode/README.md` ⇒ 断言按范围重写，tag 随之重指到修正提交。

第二处同类自我修正：本节原先把 tag 的提交哈希写成了文字。Model 一节（模型 id 冻结）落在 tag 之后的
一笔文档提交里，于是"基线文档不含模型决定"与"模型属于冻结不变量"互相矛盾 ⇒ 重指 tag 之后哈希又过期。
结论写在这里而不是留在提交说明里：**能随提交移动的引用，不要抄进文档；写命令和它应有的输出。**
