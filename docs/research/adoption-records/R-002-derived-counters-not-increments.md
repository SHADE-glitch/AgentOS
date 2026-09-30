# R-002 · 计数由 append-only 观察派生，绝不就地自增

**来源项目与组件**
- `ericmjl/agent-autolearn`：`skills/autolearn/scripts/outcomes.py:388-414`（`skill_use_signals`，`GROUP BY skill_name` 从
  `tool='skill'` 的 part 行派生 count + last_seen）→ `skills/autolearn/scripts/autolearn.py:272-348`
  （`repair_skill_use_counts` 把派生值**抄回** `.usage.json`，且 docstring 明写「`created_by` is never modified」）。
- 本机 `skill-tracker.js`（正在运行）：`:119-136` `skill_usage` 表的 `UNIQUE(session_id, call_id)` +
  `:278-300` 的 UPSERT —— 一条事实一行，聚合靠 `:204/:229/:255` 的 `SUM(status='success')` 现算，
  **没有 `use_count` 这种会被自增的列**。

**观察到的设计**
输入：原始事件（每条 tool part / 每次调用）。变换：`INSERT` 一行（幂等键防止重复），
统计永远是查询期的 `COUNT/GROUP BY/SUM`。输出：可重算的派生视图（A 额外把派生值 repair 回人类可读的
`.usage.json`，但**方向永远是索引→视图，不反向**）。状态：append-only 表 + 一个可丢弃的派生缓存。
上面两处 autolearn 代码位置（`outcomes.py:388-414`、`autolearn.py:272-348`）与本机 `skill-tracker.js:119-136,278-300`
我逐行读过 `[Verified·一手]`；下面三个反面样本（S 的零调用方、O 的 `view_count`、A 的 `topics.jsonl`）
中前两个经我一手 grep/阅读确认 `[Verified·一手]`，第三个为代理读源 `[Verified·代理读源]`。

**解决的问题**
就地自增计数器在任何一个"重放/崩溃恢复/重复触发"的世界里都会漂。三个样本正好演示了漂移的三种形态：
- `svtter/src/skill-store.ts:86,115`：`incrementUsage`/`logUsage` 定义了，`skill_usage_log` 表建了，**调用者为 0** ⇒ 表永远空。
- `opencore/.opencode/plugins/skill-telemetry.ts:41,116,193`：`view_count` 在类型里、在 `bumpUsage` 的参数联合里、
  在三处展示串里（`:212/:221/:252`），**但只有 `"use_count"` 被传进去** ⇒ 一个永远为 0 却被呈现给用户的字段。
- `autolearn` 自己的反面教材：`shift.record_sightings` 无生产调用方（`shift.py:81`）⇒ `topics.jsonl` 从不被写 ⇒
  依赖它的人门"Remember it"实际是死的。
⇒ 「写了不读」和「读了但没人写」是同一种病的两个方向，两个方向都在四个项目里出现了。

**为何适用于此处**
1. **≥2 独立血统采用**：成立（autolearn 独立血统；本机 skill-tracker 独立血统，且它是**在这台机器上真在跑的实现**）。
   另有 3 个反面样本证明不做这件事的后果，属于同一共同问题。
2. **共同问题**：重复事件导致计数虚高；崩溃/重放导致计数与事实不符；没人再计算就没有人发现字段已死。
3. **Agent OS 也有**：**已核实**。
   - `aos/core/memory/store.py` 的 `set_observation_count` 是"数一遍再写回"（派生），这一处是对的；
   - 但重构计划 §4.4（Phase 3.4 归属记账）打算写的是一条**自增**语句：
     `UPDATE memories SET use_count=use_count+1, success_count=success_count+(outcome='success')` ⇒ 正是要避免的形态；
   - `retrieval_log` 已是 append-only 事实表且**写而不读**（计划 §1.4 断点 5，`retrieve.py` 内无读者）；
   - `memories.observation_count` 与 `observations` 已经是"派生值 + 源"并存，方向目前正确。

**需要的改造**
- Phase 3.4 的实现方式改为：**不加 `use_count/success_count` 的自增语句**，改为
  `store.py` 增加 `usage_from_observations()`（`SELECT memory_id, COUNT(*), SUM(outcome='success') FROM observations
  WHERE memory_id IS NOT NULL GROUP BY memory_id`），`memories.use_count/success_count` 降级为
  **可重算缓存**，由 `aos memory refresh` 与 `evolve_stage` 调用同一个函数刷；
  与 `use_count` 已有的 `earned` 保护一致（`upsert_memory` 不把这几个列当作者内容覆盖，已核实 `store.py` 的 `earned` 元组）。
- 幂等：为 `observations` 加 `UNIQUE(loop_id, memory_id)`（一个 loop 对一条记忆只记一次），
  这样 postflight 重放不会把 `use_count` 抬高 —— 直接借本机插件 `UNIQUE(session_id, call_id)` 的思路。
  迁移影响：v5 additive + 唯一索引；若现存库有重复行，索引创建会失败 ⇒ 迁移步骤必须先做一次去重（可解释、可测试）。
- 死字段守卫（这是这次研究给 Agent OS 的额外一条纪律）：
  `tests/test_reachability.py` 应断言"每一张表的每一列，要么有写入者要么有读取者"，
  至少对 `observations/retrieval_log/candidates/memories` 的关键列做覆盖 —— 否则 `view_count` 那种事一定会在这里重现。
- 零依赖：纯 SQL，无成本。

**为何不直接复制**
- autolearn 的实现在 SQLite + 一个它自己的 `outcomes.db`（独立库 + JSONL 双存储）；Agent OS 已决定
  SQLite 为唯一真源（`store/aos.db`），复制会把存储拓扑换成两库 + JSONL 混合（findings §18：A 与 AOS 存储哲学相反）。
- 本机插件是 JS/Bun，且它面向的是"skill 使用"，不是"记忆使用"；能借的只有**形状**（幂等键 + 查询期聚合）。

**建议去向**
**Memory（存储层）+ Learning（归属记账）**。`Plugin` 层不需要改：插件只上报事件，不计数。

**风险**
- 失效模式：`GROUP BY` 派生在观察量增长后退化（1.7GB 级别的表上每次 postflight 全表聚合会变慢）；
  以及"唯一索引创建时存量重复"会让迁移直接失败。
- **如何证伪（一条会失败的断言）**：
  同一 `(loop_id, memory_id)` 写两次 observation 后，`aos memory refresh --json` 报告的 `use_count` 必须是 **1**，
  不是 2；且 `tests/test_reachability.py` 里必须有一条断言 `retrieval_log` 有读者
  （今天它会**失败** —— 失败即正确暴露断点 5 仍在）。
