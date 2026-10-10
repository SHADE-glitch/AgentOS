# MAINTENANCE.md — AgentOS

维护流程文件。本文件是**路由**：本仓的工作规则在 [`AGENTS.md`](AGENTS.md)，长篇设计、计划与证据在
[`docs/`](docs/) 下。不要把它们的表格抄到这里——被抄写的事实正是会漂移的东西。

唯一要紧的维护风险是 **opencode 改变宿主契约**：插件只经 `bin/aos` + stdin/stdout JSON 契约进入，
且只 push 自己的 `output.system` 元素；若宿主改名某个钩子、改变 `output.system` 的形状，或开始写
`OPENCODE_CLIENT`，插件可能静默 no-op 或行为异常，而 CI 依旧全绿（CI 只跑离线层，从不跑真宿主）。
规则与红线见 [`AGENTS.md`](AGENTS.md) 的「Non-interference」与「Real-machine testing」两节。

## 验证层级
- **L0** —— `python3 -m pytest` 与 `node --test tests/js/plugin.test.mjs`（临时 store，不碰宿主）。
- **L1** —— 完整引擎路径打 scratch store（`AOS_STORE_DIR` / `AOS_DB_PATH` / `AOS_BM_DB` 三个都指 scratch）。
- **L2** —— 真宿主（opencode TUI）与真 store；需要本机所有者同意并记录批准范围。

## CI
`.github/workflows/ci.yml` 在 Python 3.11 / 3.14 矩阵上跑离线层，外加 Node 20 上的 JS 插件测试。见 `AGENTS.md` § CI。

## 资产
| 文档 | 什么时候读 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | 动手前 —— 不可协商的检查 |
| [`docs/architecture/agent-os-v2.md`](docs/architecture/agent-os-v2.md) | 判定行为、缺陷编号（§12）或某事证到哪一层（§15） |
| [`docs/plan/final-plan.md`](docs/plan/final-plan.md) | 回顾最近几轮怎么错的、怎么修的（§11） |
| [`integrations/opencode/live/README.md`](integrations/opencode/live/README.md) | 在真机上跑，或核对隐私线 |
