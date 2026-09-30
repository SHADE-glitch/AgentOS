# R-001 · verdict 必须有第三态：pass / fail / **inconclusive**

**来源项目与组件**
`ericmjl/agent-autolearn`（MIT），`skills/autolearn/scripts/falsify.py:150-178`（`run_claim`）与 `:293-328`（`apply_consequences`）。
本地副本 `commit: main @ 2026-09-27`，实测取回 codeload tar.gz，文件数 102。

**观察到的设计**
- 输入：一条经验自带的 `verify:` 声明块，或仓库里的 `scripts/test_*.py`。
- 变换：真跑命令，按退出码映射三值 —— pytest `0=pass / 1=fail / ≥2=inconclusive`；声明命令比对 `expect_exit`；
  超时与 `OSError` **一律 inconclusive**，注释与代码都把"跑不了"与"跑挂了"分开（`falsify.py:150-154`）。
- 输出：`verdicts.json{skill: {verdict, fail_count, evidence}}`；只有 `verdict=="fail"` 且
  `fail_count >= falsify_fail_demote_after` 才降级；**inconclusive 不产生任何后果**。
- 状态位置：persona 目录下的 `verdicts.json`（与被评价对象分离，可重算）。
  以上三行所述代码我逐行读过 `[Verified·一手]`。

**解决的问题**
把"没有证据"折叠成"失败"或"成功"都会污染学习：折叠成失败会削弱只是没被验证过的记忆；折叠成成功会让
无关的失败积累成信任。autolearn 用第三态把"证据不可用"从证据轴上摘出去。它的 docstring 还写明
「nothing here acts on weak evidence」——即第三态不只是标签，而是**动作闸**。

**为何适用于此处**
1. **多项目独立采用**：不成立 —— 只有 autolearn 有显式第三态（血统数 1）。
   但反向证据很强：**其余三家 + 本机**都是二值的（`opencore` `source:manual|auto-extract`、`okdk` `result:"ok"|"fail"`、
   `svtter` 无结果概念、本机 `status ∈ success|error|denied|ask|unknown`）。
   ⇒ **本机 skill-tracker 的 `unknown` 是同一意图的第二独立实现**（`skill-tracker.js:128` 的 CHECK 枚举，`[Verified·一手]`）⇒ 血统数 = 2。
2. **存在共同问题**：是的 —— 二值 verdict 会把"未观测"折叠成一种结论，四个项目里三个因此产生错误累积
   （见 findings Q1：okdk 的探针永不触发 ⇒ 永远记 `ok`；opencore `session.idle` 无论结果都写）。
3. **Agent OS 也有这个问题**：**已核实存在**。`aos/core/outcome.py:274` 在无信号或覆盖率不足时落
   `no_signal_outcome="partial"`，而 `partial` 同时被用于"部分成功"（`outcome.py` 阈值梯间的 `score>=0.40`）
   ⇒ 「一次办成一半」与「完全没被告知」在存储层不可区分；`aos review label` 的人工标注也是同一个 `partial`。`[Verified·一手]`

**需要的改造**
- `aos/core/outcome.py`：`OUTCOMES` 增加 `"unknown"`（或保留 `partial` 语义、新增 `evidence_state` 字段——**取后者更小**）；
  建议实现为：`report["outcome"]` 保持三值不变，新增 `report["decidable"] = bool(score is not None and mass >= verdict_mass)`，
  并把 `no_signal_outcome` 的默认值从 `partial` 改为 `unknown`。
- 存储：`observations` 已有 `synthesised/needs_review`；再走一次 additive 迁移（`migrations.py` 追加 v5）加
  `decidable INTEGER NOT NULL DEFAULT 1`，或直接把 `outcome` 的取值域扩到含 `unknown`（无 CHECK 约束在 outcome 列上，已核实）。
- 契约：`aos/contract/schema.py` 的 `OUTCOME` 枚举是**已发布 1.0/1.1 字段取值域**，扩值域是破坏性变更
  （同 MEMORY_TYPE 那次）；建议走 `learning.evidence_state` 新字段而不是改 `outcome` 枚举。
- 门：`evolve.py:158-181` 的 `validate_group` 目前靠 `quality_threshold` 把无质量的东西拒掉；应改为
  `decidable==False ⇒ 不产候选且不记 observation 之外的效果`，理由与 autolearn 一致：不可用证据不产生后果。
- 零依赖可行性：纯 Python，无新依赖。迁移影响：+1 个 additive 步骤（v5），不需要备份。

**为何不直接复制**
- 许可上可以（MIT），但没有可复制的单位：`falsify.py` 的三态是嵌在"真跑命令 + safe-command 拒绝清单 +
  `uv run pytest`"这套 Python 运行时里，而 Agent OS 目前**不执行任何来自记忆的**命令（用户硬约束
  `auto_modify_code=False` + 零依赖）。复制文件等于引入它的执行模型（见 `R-005`）。
- `verdicts.json` 的 JSON 文件存储与 Agent OS 的 SQLite + 迁移权威冲突（findings §18）。

**建议去向**
**Learning**（`outcome.py` 与 `evolve.py`），并在 postflight 契约里以新字段暴露给 host。
不是 Memory（它描述的是这次运行可不可判，不是长期事实）。

**风险**
- 失效模式：值域扩张后，历史数据里 `partial` 的语义漂移 —— 旧的 `partial` 里混着两种含义，
  新数据只有 `unknown`，导致跨时间统计不一致。
- **如何证伪（一条会失败的断言）**：
  `tests/test_outcome.py` 新增一例：`synthesize({})` 必须返回 `decidable is False` 且 outcome 与
  `synthesize({"test_exit_code": 0, "build_exit_code": 1})`（真·部分成功）返回的 outcome **不同名**；
  并且 `tests/test_learning_gate.py` 新增一例：一条 `decidable=False` 的运行**不得**产生任何
  `reinforce/weaken` 候选（当前 3.2 已由 `needs_review` 挡住，但断言要落在 `decidable` 上而不是 `needs_review` 上，
  因为 host 可以显式给 `outcome="partial"` 从而绕过 `needs_review`）。
- 若该断言在实现后仍通过旧路径（显式 `outcome=partial` + `needs_review=False`）产生候选，就是本条要防的污染回归。
