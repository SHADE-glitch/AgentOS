# AGENTS.md — 这个仓库里不可协商的检查

对象 `/home/shade/Public/AgentOS`，**公开仓库**（`github.com/SHADE-glitch/AgentOS`）。
它是 opencode 的**外置证据与治理层**：真实运行 → 合成结论 → 人门 → 晋升/降级 → 下次召回改变行为。
引擎是纯标准库 Python；宿主只经 `bin/aos` + stdin/stdout JSON 契约进入；引擎永不调用 opencode。
本文件同时约束"用别的 AI agent（如 qoder cn）来开发本仓库"的情形。

**第一优先级是"证明它值得每天用"，不是"再加一层"。** 新功能默认不做；新增模块前必须能在
`docs/research/open-source-capability-matrix.md` 指到一列"无人实现"。去留由判据决定
（`docs/decision/positioning.md §6`）：通电后 4 周内 `source='hot'` 的真实运行 < 30 条 ⇒ 停止加功能。
**现状与聚合数字不写死在这里**——一律 `./bin/aos doctor --json` 现取，不沿用上一轮的记忆值。

细则、证据与缺陷编号不在这里：判定与数字在 `docs/architecture/agent-os-v2.md` §12/§15，
执行日志在 `docs/plan/final-plan.md` §11，真机规则在 `integrations/opencode/live/README.md`。
本文件只放"每次开工都要照做"的形状，且每一条都是**跑过**的。

## 开工前先读（别的 agent 尤其）

1. 本文件全文。
2. `docs/architecture/agent-os-v2.md` §12（缺陷编号）与 §15（已证到哪一层、什么没证）。
3. `docs/plan/final-plan.md` §11（最近几轮怎么错的、怎么修的）。
4. `integrations/opencode/live/README.md`（真机怎么跑、隐私线）。

**为什么**：这个仓库反复出现的病是"声明了但没人写 / 写了但没人读 / 读了但不生效 /
只在 fixture 里跑过就当真的"。上面四份是这些病的历史记录；不读就会重犯。

## 不要做什么（非目标，别"顺手"加回来）

- **不建 skill 系统**：不创建/读/写 skill 文件，不碰 `personal-skills`，`content/skills/` 不得复现
  （`test_skill_boundary` 拦）。skill 属于 host。
- **不自建遥测写入者**：遥测的唯一写入者是本机 skill-tracker。要接它的库走 `final-plan §7` 的只读规则
  （列白名单 + `PRAGMA table_info` 先探后读 + 读不到就降级）；**当前零代码**——接之前先证明它真会改变召回。
- **不加 MCP、不加第三方依赖**（`test_no_third_party_imports` 是执行方式）。
- **不写 `~/.config/opencode/**`**（含 `opencode.json`、`plugin/`、`AGENTS.md`、`skill-stats-registry.json`）；
  引擎唯一的写处是 `store/`。
- **不把引擎变成会改代码的东西**：recovery 永远 plan-only，`auto_modify_code=False`。
- **不做编排、不做会话检索、不做代码索引**（与"外置大脑"定位冲突，见 `positioning.md §2/§3`）。

## 非干扰是硬约束（owner 明确要求）

- **停用后必须零影响**：`AGENT_OS_ROOT` 不设 ⇒ 插件加载但每个钩子 no-op，`output.system` 与
  没有这个插件时**逐字节相同**（`tests/js/plugin.test.mjs` 钉住）。
- **只增强，不改写邻居**：只 push 自己的元素；绝不占 `output.system[0]`、绝不编辑/重排/删除他人
  元素（DCP 靠 `[0]` 判内部调用），并保留别人追加进我们自己元素的后缀。
- **不碰其他组件的状态**：不写 `~/.config/opencode/**`，不读写 DCP / skill-tracker / notifier
  的库或文件；插件源码除 `existsSync` 外不得 import 任何写 API。
- **判据 3 优先于一切**：任何能力若必须写 `~/.config/opencode/**`、或必须编辑他人写入的
  `output.system` 元素才能生效 ⇒ **直接放弃，不讨论收益**。
- 停用方式就是两条可逆动作：删符号链接、去掉 alias/export 里的 `AGENT_OS_ROOT`。

## 什么算绿

- `python3 -m pytest` 与 `node --test tests/js/plugin.test.mjs`，两条都要跑；两者当前 464 / 29。
  别在这两条后面再补一个 `-q`：`addopts` 已经有一个 `-q`，两个 `-q` 会把汇总行整个吃掉（实测：
  `python3 -m pytest -q | grep passed` 什么都不打印），计数只能改从 `--collect-only -q` 取。
- 不要写 `node --test tests/js/`：目录会把 `fake-aos.cjs` 当测试执行，输出 `# tests 1 / # fail 1`，
  是假红。
- **信号有两张互相独立的列表**：契约的 `SIGNAL_FIELDS`（`aos/contract/schema.py`）与合成的
  `_SIGNALS`（`aos/core/outcome.py`）。回显只保留后者 ⇒ 只加契约键的新信号会在**进库之前**被静默丢弃。
  加一个信号要同时改五处：两张列表、`policy.py` 的默认权重、`content/policies/outcome.json`、
  缝守卫里那句集合**等号**断言（`tests/test_cli_contract.py`）、以及 `tests/test_outcome.py` 的 `DEFAULTS`。
  少改任何一处都不会报错，只会什么都没有（缺陷 AJ 的红屏幕就是这个）。
- 判据与阈值来自 `content/policies/*.json`（七个文件：decay/external/injection/outcome/promotion/rejection/retrieval），
  由 `policy.load_policy` 以"内置默认被文件覆盖"的方式合并 ⇒ 要改门槛就改文件，不要在调用处补一个本地数字。

## 往链路上传值的形状

- 只有两种合法形式：在宿主进程内**规范化后丢掉原文**（方法指纹：只留名称形状的 token、≤3 词、
  `-m` 仅对解释器保留、遇引号即终止该段），或**截断并标明来源**（`response_summary`、`session_error`）。
- 原命令、参数、路径、env、stderr 一律不过缝；`note()` 继续只打键名/索引/计数，不打值。
- 一个值上了链路就是采集面扩大 ⇒ 那是 owner 的决定，写进 §12/§15 并说明边界，不能只在代码里悄悄加。

## 探真库只能只读

- `aos preflight` **会开一条 loop 并留下 pending**（实测：一次 preflight ⇒
  `doctor.pending_postflight.outstanding` 从 1 变 2）⇒ 拿真库做打分/对照一律走
  `retrieve(query, k=5, store=MemoryStore(<db 路径>), log=False)`，`log=False` 是关键，否则写 `retrieval_log`。
- 需要跑完整引擎路径（router/scope/gate 全链路）时，先把 `AOS_STORE_DIR` 指到 scratch 副本，
  不要"就用真库试一下"。
- `retrieve()` 是只读的，`compute_all_decay()` / `memory refresh` **不是**：后者写 `decay_factor`，
  而且写的是"新旧里更低的那个"（人的降级不许被重算抬回去）⇒ **降下去就再也升不回来**，没有对称的命令。
  第十五轮就是在"只读检验"的口号下调了它，把真库 3 条种子从 0.85 永久降到 0.5。
- **basic-memory 的库也只读**：`AOS_BM_DB`（默认 `~/.basic-memory/memory.db`）用 `mode=ro` + `PRAGMA query_only=ON`
  打开，`external.py` 里不许出现任何写语句（`test_the_reader_issues_no_write_statement_and_leaves_the_bytes_alone`
  同时钉源码与文件字节）。`tests/conftest.py` 把它指到一个不存在的 tmp 路径 ⇒ 测试不会偶然读到真笔记；
  要测召回就在 `tmp_path` 里造一份 fixture 库。**任何真实运行/实验也一样**：跑 AOS 时 `AOS_STORE_DIR`/`AOS_DB_PATH`/`AOS_BM_DB`
  三个都指 scratch，别拿真笔记当测试数据。
- `store/` 没有任何删除命令。退出召回只有两条路：`aos memory retire <id> --reason …`（人敲一次，
  无 reason 不写）与证据阶梯（5 次可归因失败 + 5 次批准，§12 行 Z）；两条都保留行与事件，
  所以"撤回一条教训"永远不是删数据，是改状态。

## 写之前先量

- 声称"修好了"之前：先有一条**会红的具名测试**，红屏幕留得住，再改代码。
- 聚合数（测试数、`observations.hot`、pending 数、提交数）一律重跑命令取；不沿用上一轮的记忆值。
- 借来的证据要写明它够到哪一层（`docs/architecture/agent-os-v2.md §1`）；"我没遇到"不能写成"不会发生"。
- 行为判定要在**调用之前**固定规则（grep 什么、阈值多少），不许事后解释结果。
- 正文里任何"必须活到最后一句"的分句都要**预留额度**，不能拿剩余空间给它
  （`缺证 → 模型自述 → 绝不删 未归因`、轨迹的 170 字符额度是同一手法）。实测过一次：
  八个长路径把剩余空间压成负数，整节 `过程` 被静默丢弃。

## 编辑之后必须重读

`Edit` 的 `old_string` 只锚一行时，会吞掉相邻行：表格行的行首、段落小标题、赋值语句都已被吞过
（第十四、十五、十六轮各一次，都在重读时发现并补回；第十六轮吞掉的是 `proposed = 0` 一行）。
改 markdown 表格/段落后，立刻把被改区域读一遍；改聚合数先 grep 全部出现处再改。

自动折行同样属于"编辑"：按字符数硬切会把 code span 和 `**` 切断（`aos/core/outcome.py\n` 被切成两半）。
换行只能落在标点或词之间，改完必须回读整段。

## 改召回与门禁的语义

- **收紧一条匹配，必须同批给出"人怎么让该被找到的东西仍被找到"的口**，否则修复等于消失（AH 两半同批）。
- **过程叙述进 body，但不进身份**：`fact_key` 吃 body 全文 ⇒ 轨迹写进正文而身份照原样算，
  同一件事第二次发生才是"一次决定"而不是"一次新评审"。key 只能由**同一个** `fact_key` 函数算出来
  （`test_dedupe.py` 钉住"声明的 key 等于 store 自己会推导的结果"），另起一个键生成器就是 AD 那一类病。
- **一个 run 只出一份经验提案**：结果、过程、候选经验在同一条评审里给
  （`should_propose` 放宽时最容易把它裂成两条 ask）。
- 内容列（`title`/`body`/`when_to_apply`/`tags`）只有一个写入者：作者。`review approve` 的内容类 flag
  仅在 create 时接受，对已存在的行一律拒绝；空值在写任何东西之前拒绝且不留行。
- 排序有**两条独立入口**都能过 0.15 的门槛（真库只读实测）：
  ① 路由说中 category —— 单这一项就正好 0.15，**题面零重叠也能召回**，中文也不例外；
  ② 题面字面命中 tag —— 一个 = 0.08（不够），两个 = 0.16（过门）。
  消毒兜底桶之后，"路由放弃"那一半任务只剩 ② 可走 ⇒ "至少两个 tag 字面命中"是**路由不知道主题时**
  的前提，不是普遍前提；对外解释时别把它说过头。
- 路由的兜底桶（`fallback`）不是主题，它是"什么都没分类"的自白 ⇒ 查询侧一律消毒：category 置空、
  桶名从 domains/keywords 剔除、放弃时唯一会给的 role 也清掉。**只动查询侧**，真讲 fallback 的记忆
  仍靠自己的 tag 与题面被找到（这个不对称是故意的，别"顺手"改成两侧）。

## 真机测试（opencode）——含"别的 agent 驱动"的情形

- **绝不用 `opencode` 这个 shell alias**：本机 `~/.zshrc` 的 alias 注入 `--auto` 和一个内联的
  `AGENT_OS_ROOT`，你分不清哪个 env 生效，而 `--auto` 会**自动批准当前 cwd 下的编辑与任意 bash**
  （官方标注 dangerous）。驱动真机一律用绝对路径 `~/.opencode/bin/opencode` + 显式 `AGENT_OS_ROOT`
  + **指向 scratch 的 `AOS_STORE_DIR`**。
- **任何测试运行都必须把 store 指到 scratch**（`AOS_STORE_DIR` / `AOS_DB_PATH`）；真库只由 owner 的
  交互会话增长。`live/run.sh` 会拒绝真库，除非 `AOS_RIG_ALLOW_REAL_STORE=1` 并说清楚。
- 模型只用 `opencode/space-bunny-free`；`--auto` 需 owner 授权并记录批准范围（cwd/库/批次/模型/日期）；
  `~/.config/opencode/**` 零写入。
- 无头 `opencode run` 在 `permission.bash=ask` 且无 TTY 时，模型一想调工具就必然失败 ⇒ 要测工具行为
  必须用真 TUI（tmux 驱动，方法见 `live/README.md`），或只问"知识可答"的问题；**不要用 `--auto` 去修这个**。
- 驱动真 TUI 时遇到权限弹窗**停下来问 owner**，默认只选 Allow once。
- 判据 1 的 `hot` 只数 owner 的交互会话，rig / agent 产生的观测不计。
  **这条目前只靠"每次调用都带 scratch env"这一条纪律撑着**：`AGENT_OS_ROOT` 已 export 进 `~/.zshrc`，
  忘记 `AOS_STORE_DIR` 的那一次就直接写进正式库，而写进去之后**没有任何字段能看出是谁驱动的**
  （缺陷 AR：主机的 `OPENCODE_CLIENT` 只有 `"acp"` 一处赋值，TUI 不写它 ⇒ 人与 agent 同为 `cli`）。
  ⇒ 不要为了补这个洞去写一个来源字段（那是假的），也不要把 `doctor` 的 `hot` 直接说成"owner 在用了几次"；
  交出去的读数一律写成"上界 N / 可证下界 M"两个数，见 `docs/experiment/stage-1-usage-ledger.md §4bis`。
- 提示词全合成，会话正文不进仓库与文档；插件日志只出现键名/索引/计数，不出现值。
- 需要改 `~/.config/opencode/**` 或需要 host 没有的钩子 ⇒ 停下汇报，那是 owner 的决定。

## 交付节奏

一个改动 = 一笔提交；汇报固定五项：改了哪些文件、测试结果（前后计数 + 新增用例名）、
行为变化 before→after（含**刻意没变**的部分）、风险与回滚（能否单提交 revert）、是否破坏既有契约。
skip 掉某一步时必须能证明那一步仍然可执行。
