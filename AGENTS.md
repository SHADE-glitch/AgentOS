# AGENTS.md — 这个仓库里不可协商的检查

细则、证据与缺陷编号不在这里：判定与数字在 `docs/architecture/agent-os-v2.md` §12/§15，
执行日志在 `docs/plan/final-plan.md` §11，真机规则在 `integrations/opencode/live/README.md`。
本文件只放"每次开工都要照做"的形状，且每一条都是**跑过**的。

## 什么算绿

- `python3 -m pytest` 与 `node --test tests/js/plugin.test.mjs`，两条都要跑；两者当前 447 / 27。
- 不要写 `node --test tests/js/`：目录会把 `fake-aos.cjs` 当测试执行，输出 `# tests 1 / # fail 1`，
  是假红。
- **信号有两张互相独立的列表**：契约的 `SIGNAL_FIELDS`（`aos/contract/schema.py`）与合成的
  `_SIGNALS`（`aos/core/outcome.py`）。回显只保留后者 ⇒ 只加契约键的新信号会在**进库之前**被静默丢弃。
  加一个信号要同时改五处：两张列表、`policy.py` 的默认权重、`content/policies/outcome.json`、
  缝守卫里那句集合**等号**断言（`tests/test_cli_contract.py`）、以及 `tests/test_outcome.py` 的 `DEFAULTS`。
  少改任何一处都不会报错，只会什么都没有（缺陷 AJ 的红屏幕就是这个）。
- 判据与阈值来自 `content/policies/*.json`（六个文件：decay/injection/outcome/promotion/rejection/retrieval），
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

## 真机测试（opencode）

- 模型只用 `opencode/space-bunny-free`；`--auto` 需 owner 授权并记录批准范围（cwd/库/批次/模型/日期）；
  `~/.config/opencode/**` 零写入。（owner 于 2026-10-01 把"绝不传 `--auto`"改成这一条；
  `live/run.sh` 的头注释与 `live/README.md` 仍写着旧规则、且脚本尚未解析 `--auto` ——
  那属于 rig，等实验轮真正开工时一并改，不在开发轮顺手动。）
- 提示词全合成，会话正文不进仓库与文档；插件日志只出现键名/索引/计数，不出现值。
- 无头 `opencode run` 在 `permission.bash=ask` 且无 TTY 时，模型一想调工具就必然失败 ⇒
  判据 1 的 `hot` 只数 owner 的交互会话，rig 产生的观测不计。
- 驱动真 TUI 时遇到权限弹窗**停下来问 owner**，默认只选 Allow once；方法见 `live/README.md`。
- 需要改 `~/.config/opencode/**` 或需要 host 没有的钩子 ⇒ 停下汇报，那是 owner 的决定。

## 交付节奏

一个改动 = 一笔提交；汇报固定五项：改了哪些文件、测试结果（前后计数 + 新增用例名）、
行为变化 before→after（含**刻意没变**的部分）、风险与回滚（能否单提交 revert）、是否破坏既有契约。
skip 掉某一步时必须能证明那一步仍然可执行。
