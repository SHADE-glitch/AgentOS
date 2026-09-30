# R-005 · 经验可携带 `verify:` 声明（存而不自动执行），作为升级置信的证据源

**来源项目与组件**
`ericmjl/agent-autolearn`（MIT）：
- `skills/autolearn/scripts/falsify.py:100-118`（`claims_of`：**声明的 `verify:` 块 > 自带的 `scripts/test_*.py` > 无**；
  docstring 原文「A declared `verify:` block wins because the author specified the exact command (deps, ignores, etc.)」）
- `scripts/outcomes.py:43-50`（`SAFE_DECLARED_DENY` 正则：`rm|sudo|curl|wget|nc|ssh|scp|dd|mkfs|chmod|os.system|subprocess|eval(|exec(|__import__|urllib|requests|socket|python -c` 等一律拒绝，
  注释写明「is refused and the claim comes back **inconclusive rather than executed**」）
- `scripts/proposer.py:302-330`（`verify_pending`：只对 `verified is None` 的 pending 提案跑一次，
  `verified = True only on a clean pass; False on fail; null on inconclusive/unsafe (stays pending)`；
  **自动晋升只消费 `verified=True`**）
- `autolearn.py:428-499`（晋升生成的 skill **携带 `verify:` 块**）

**观察到的设计**
输入：一条经验的正文 + 它自带的可执行验证声明。变换：安全白名单/黑名单过滤 → 带超时的子进程 → 三值裁决。
输出：`verdicts.json{verdict, fail_count, evidence}`，并驱动降级（`apply_consequences`）或解锁自动晋升（`proposer`）。
状态：与被评价对象分离存放（可重算、可审计）。触发：curator 步、手动 `falsify run --dry-run`。
调用者：`falsify.run_claim`（唯一执行点）。边界：**证伪只改状态，永不删除**。
上列 `claims_of`（`falsify.py:100-118`）、`SAFE_DECLARED_DENY`（`outcomes.py:43-50`）、
`verify_pending`（`proposer.py:302-330`）三处我逐行读过，其 docstring 原文已引在上节 `[Verified·一手]`。

**解决的问题**
"这条经验是不是对的"这件事，用模型自评不可靠（见 R-006 与 findings Q1 的三个失败样本），
用"它在成功的运行里出现过"是循环论证。唯一非循环的证据是**让它自己给出可失败的检验**。
同时 `SAFE_DECLARED_DENY` + 「拒绝即 inconclusive」处理了这条路的最大风险：**经验内容里带的命令是攻击面**。

**为何适用于此处**
1. **独立血统数 = 1**（只有 autolearn）。⇒ 按本研究自立的规则，这条**不构成"共同问题"的证据**，
   因此不进入"必须借鉴"清单，只进入"值得评估的方向"。我仍然记录它，理由有二：
   - 它是四份代码里唯一给出"经验级可验证性"的机制，而 Agent OS 的 `evidence_level` 6 档 ladder
     名字就叫 `benchmark_evaluated / runtime_validated / independent_validated`
     （`aos/core/memory/evolve.py:33-39`）——**这些档位目前没有任何可执行证据来源**，
     只能靠作者 `--verified` 或人工 approve 来跳档（`authoring.py:105-116`、`evolve.py` 的 `apply_promotion`）。
     也就是说 AOS 的证据等级现在是**声明的**，不是**验证的**。这是一处名实不符，本条是它唯一的已知解法。
   - 反面：`opencore` 用 LLM 自报 `importance`（`memory.ts:234`）、`svtter` 用文本启发式打分
     （`rubric-scorer.ts:50-97`），两者都是 AOS 应当避开的替代物。
2. **共同问题存在**：所有自称"验证过"的记忆等级都需要一个证据生产者；四个项目里只有一个提供了生产者。
3. **Agent OS 有这个问题**：`evidence_level` 的升档路径 `evolve.py:196-201`（`_next_evidence_level`）
   只看 **runs 次数**，即"被召回且所在运行成功"，不看任何直接验证 —— 与 R-006 是同一个根。

**需要的改造**
- 数据形状：给 `memories` 增加 `verify_command TEXT DEFAULT ''` 与 `verify_expect_exit INTEGER`
  （v6 additive；不需要备份）。**只存不跑**：引擎里**不出现任何执行该字符串的代码路径**。
- 呈现：`inject.render()` 对带 `verify_command` 的条目加一行「可验证：`<命令>`」
  （`aos/core/memory/inject.py`），让**人**在 `aos memory inspect` / review 时看得见。
  `[Judgment]` 这一句的价值在于它把"我怎么知道这条是对的"从模型的印象变成人眼可查的一件事。
- 消费方：`aos review` 增加显式 `verify <id>` 子命令 —— **人发起**、执行前套用 `SAFE_DECLARED_DENY` 同等黑名单
  （纯正则，零依赖）、要求二次确认（`--apply` 才写库），成功才允许 `evidence_level` 升一档。
  这样 `runtime_validated` 才第一次有了非声明的入口。
- 策略：`policy.py` 增加 `verification` 段（`timeout_s`, `deny_pattern`, `auto_run: false`），
  `auto_run` **默认 false 且代码里没有 true 分支的执行权**（用 `test_skill_boundary.py` 同类的守卫测试断言
  "执行 verify 的代码路径必须同时满足人批准 + 白名单"）。
- 与用户既有约束的关系：不改 `auto_modify_code=False`（执行只读命令不等于改代码，但仍属副作用 ⇒ 必须人发起）；
  不与"不安装插件、不写全局配置"冲突。

**为何不直接复制**
- MIT 允许复制，但 `falsify.py` 与 `uv run --with pytest`、shell 命令拼装、persona 目录布局耦合；
  AOS 若复制就引入"引擎会自动跑外部命令"这一条当前不存在的执行面，属于**净增风险**。
- 本条只取两件可分离的东西：**数据形状（verify 字段）** 与 **安全拒绝清单的思路**；
  执行器如果要建，必须是显式人门命令，不是 curator 后台步。

**建议去向**
**Memory（字段）+ Evolution（人发起的验证动作）**；**不进 Plugin、不进自动循环**。

**风险**
- 主要风险是**提示注入 → 命令执行**：一条被污染的记忆若携带 `verify_command`，任何自动执行都会把
  记忆库变成 RCE 通道。次风险：拒绝清单是正则，必然可绕（autolearn 的清单也只挡常见形态）。
- **如何证伪（一条会失败的断言）**：
  `tests/test_no_third_party_imports.py` 之外新增守卫 `tests/test_verify_boundary.py`：
  遍历 `aos/**/*.py`，断言**不存在**对 `verify_command` 列值的 `subprocess`/`os.system`/`eval` 调用；
  且 `verification.auto_run` 为 `true` 时 CLI 仍拒绝执行（今天它根本没有该子命令 ⇒ 这条断言应先失败，
  实现后转绿）。若将来加入执行路径，此测试就是必须显式改动的地方 —— 这正是我要的"改动会被看见"。
