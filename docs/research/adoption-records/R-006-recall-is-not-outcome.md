# R-006 · 被召回 ≠ 起作用：归属必须区分"linkage"与"outcome"（AOS 现有的一处名实不符）

**来源项目与组件**
- `ericmjl/agent-autolearn`（MIT）`skills/autolearn/scripts/outcomes.py:110-133`（`classify_gt`）：
  `4=测试命令 / 3=退出码 / 2=用户纠正(RESERVED，从不赋值) / 1=原始工具输出 / 0=无`，其中
  ```python
  if tool == "skill":
      return 0  # a skill load is linkage, not an outcome
  ```
  `[Verified·一手]`
- 同仓库 `proposer.py:31-35,139-146`：把"值得记"建立在**跨 ≥3 会话复发**上，而不是"出现过"。`[Verified·代理读源]`
- 反面（同源但做法相反）：`okdk/index.ts:847-860` 把 `use_count` 定义为"skill 工具被调用过"
  （docstring 自己承认 `view_count` 其实是在**编辑文件**时自增的，`:811`）`[Verified·代理读源]`；
  `opencore/skill-telemetry.ts:186-193` 同样把"加载"当"使用"，且 `use_count` 是唯一被写的字段。`[Verified·一手]`

**观察到的设计**
autolearn 把两类事件严格分成两列：`tool='skill'` 的行只用于**关联**（哪个 skill 在这段对话里出现过），
`gt_strength` 只由**结果性**事件（测试、退出码、错误状态）赋值；因此"某 skill 被加载了 100 次"永远不会
变成"这个 skill 有效 100 次"。状态位置：`outcomes.db:tool_outcome(tool, status, gt_strength, skill_name)`。
触发：curator 的 index 步；调用者：`falsify`（读 gt 才降级）、`repair_skill_use_counts`（读 count 只更新使用视图）。

**解决的问题**
自我改进系统最常见的错误归因：**把"在场"当"有用"**。它的后果是正反馈回路 ——
被召回 ⇒ 所在运行成功 ⇒ 记一次功 ⇒ 排名更高 ⇒ 更容易被召回。这个回路不需要任何 bug 就能把
一组平庸记忆推上顶端，并把"记忆越来越自信但越来越差"变成常态。

**为何适用于此处**
1. **独立血统数**：正面做法 1（autolearn）；反面做法 2（okdk、opencore，与 AOS 当前做法同形）。
   ⇒ 按本研究规则，这不算"多血统验证的正确设计"，**但它是"共同问题"的强证据**（三家犯同一个错）。
2. **共同问题存在**：是，且上面正是它的表现。
3. **Agent OS 现在就是这个问题的实例 —— 逐行核实**：
   - `aos/core/memory/record.py:186`：对**每一条被召回的记忆**写一行 observation，携带的是**整个 run 的 outcome**；
   - `aos/core/memory/store.py:266-298 usage_stats()`：就从这些行算 `usage_count` / `successful_uses` / `success_rate` ——
     **没有任何"这条记忆是否真的被采纳"的判据**；
   - `aos/core/memory/retrieve.py:287,345`：`usage_stats` 喂给 `quality_bonus` ⇒ 成功运行里被召回过的记忆
     **在自己被检索时加分** ⇒ 闭环正反馈成立；
   - `aos/core/memory/record.py:208` + `:109`：一次高质量成功运行为**每条被召回记忆**发一个 `reinforce` 候选；
   - `evolve.py:196-201 _next_evidence_level`：升档只看 `runs` 计数。
   ⇒ `[Judgment]` AOS 的 `evidence_level` 名字（`runtime_validated` / `independent_validated`）目前**没有**
   对应"验证"语义，只有"在场次数"语义。这是名实不符，且与用户既定的"Evidence 是事实依据"定位句直接冲突。

**需要的改造**
1. **归属分层**（Phase 3.4 的实现方式修正，不改架构）：
   `observations` 增加 `attribution TEXT`（`recalled` / `applied` / `cited`），
   默认 `recalled`；只有当 host 能证明应用时才升级为 `applied`。
   - 现实约束：**opencode 无法上报"模型真的用了这条记忆"**（`findings.md Q9`：没有任何钩子返回这种信息）
     ⇒ `applied` 只能由 ① 人在 `review label` 时指定，或 ② 注入块被引用/复述的可疑启发式（不建议）。
     所以默认状态就是 `recalled`，而 **`recalled` 不参与质量分**。
2. **排序去污染**：`retrieve.py` 的 `quality_bonus` 改为只从 `attribution != 'recalled'` 的行推导；
   `recalled` 计数只驱动**新鲜度/衰减**（time-based），不驱动 success_rate。
   这条改动会显著改变排序，必须按重构计划 §1.6 的"固定输入回归 + 记录顺序改变后排序改变"两条测试同时守。
3. **候选生成收紧**：`record.py:208` 的 `reinforce` 不再对"仅被召回"的记忆发放；
   改为：一次运行成功只为**其结果可归因的证据**（`test_exit_code==0` 之类 `gt_strength>=3` 的信号）
   升级"参与决策的记忆"，否则只写 `observations` 不写候选 —— 即 autolearn「nothing here acts on weak evidence」。
4. **引入 AOS 自己的 `gt_strength`**（`outcome.py` 已有全部原料）：
   把 `present` 信号映射成 0–4 的证据强度并写入 `observations`，
   让"这个结论建立在什么强度的证据上"成为可查询字段而不是隐藏在 `confidence` 里。
   零成本：`synthesize` 已经算了 `mass`。
5. 迁移：`observations.attribution` + `observations.gt_strength` 均 additive（v5 或 v6 一步）。

**为何不直接复制**
- `outcomes.py` 的 gt 阶梯绑定在"逐条 tool part 建索引"上，而 AOS 不索引 opencode.db（它收 postflight 信号）。
  可移植的是**语义分层**，不是那张索引表。
- MIT 许可无碍，但 AOS 需要的是 `outcome.py` 里的一个纯函数映射，不是 200 行 SQLite 索引器。

**建议去向**
**Learning（归属与候选生成）+ Memory 存储（两个新列）**；`retrieve.py` 的排序改动属 **Memory/检索**。
Plugin 层：契约应新增可选 `signals.applied_memory_ids`（host **能**给时给；不能给时 AOS 保持 `recalled`），
并且**不得**把这个字段设为必需 —— 它永远填不出来（findings Q9 的 loud gap 同类）。

**风险**
- 主要风险是**收紧后学习信号变稀**：如果 `recalled` 不再加分，很多从未被证明应用过的记忆会停在
  `hypothesis/benchmark` 档，`run_learning` 的自动晋升几乎不再有输入。
  `[Judgment]` 这是**正确结果而不是回归** —— 但必须让人门（`review label` 的"是否被采纳"）成为补上信号的通路，
  否则系统会从"过度自信"翻车到"什么都不学"。
- 次风险：改动排序会改变既有注入内容（行为变更），需要固定输入回归。
- **如何证伪（一条会失败的断言）**：
  `tests/test_memory.py` 或新文件里：构造 5 次**全部成功**的运行，每次都召回同一条记忆但**没有任何一次给出可归因证据**
  （无 `test_exit_code`、无 host verdict、无 `applied`），断言
  ① `store.usage_stats()[mid]["success_rate"]` **不因此上升**（今天它会上升 ⇒ 当前实现会让这条测试失败，
  这正是本记录要修的缺陷），
  ② 该记忆的 `final_score` 不因这些运行改变（`quality_bonus` 不含 `recalled`），
  ③ 且 `candidates` 表里没有为它生成的 `reinforce` 行。
  三条中任一条今天会失败即为缺陷确认；全部实现后必须绿。
