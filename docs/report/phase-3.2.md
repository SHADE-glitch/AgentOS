# Phase 3.2 汇报（补交）

单提交 `bf0fa6e`。目标：**把门修对** —— 让 Observation → Candidate → 晋升这条线在两个方向上都能走，
并且把"没人给结论的运行"变成人门的主路径而不是被当作成功。

计划里的说法是"Phase 3.2 中途被叫停"；**实际是 3.2 的 a–g 七个子项全部落地并已提交**
（`docs/audit/current-state.md §2` 逐条给证据）。这份汇报因此覆盖完整阶段。

---

## 一、修改文件（真实 diff，`git show bf0fa6e --stat`）

| 文件 | 变化 | 作用 |
|---|---|---|
| **`aos/core/outcome.py`** | 新增 320 行 | 结果合成：`confidence = 到场信号的权重覆盖率`，不是同意度；`mass < min_verdict_mass` 时**加权平均无权命名结论**；硬失败（中断/session_error/非零退出码）压倒平均；`response_summary` 被读但权重 0.00 |
| `aos/core/memory/policy.py` | +49 | 新增 `outcome` 段（权重表、`weight_overrides`、`thresholds`、`error_cap`、`min_auto_confidence 0.60`、**`min_verdict_mass 0.45`（计划里没有的新键）**、三档 quality 兜底） |
| `aos/core/memory/record.py` | +204/− | `candidate_type_for`（partial **不发**候选）、`should_propose`（零召回或失败才提案，未标注运行什么都不发）、`proposal_for_loop`（把一次运行起草成一条 episodic/failure 记忆，id 在提案时就预留）、`add_candidates_for_memories`、`memories_of_loop` |
| `aos/core/loop/stages.py` | +190/− | `record_stage` 不再自己判成败：合成 → 观测（带 `signals/present/absent/mass/score/reasons/task/cwd/memories_used` 快照）→ 候选；`finalize_stage` 由 `outcome` **派生** `final_status`（废除第二套结论计算）；删 `_outcome_for`；`source_hash` 改为按"运行"而不是按"回答文本"计算 |
| `aos/core/loop/lifecycle.py` | +51 | postflight 收 `signals`，与引擎自证（validator 的 test/build 退出码、`files_changed`）**合并成一份**再交给合成器 |
| `aos/core/memory/evolve.py` | +694/− | `decide_promotion`（晋升效果**算一次、以数据形式给出**）、`apply_effect`（逐字执行 + 对 `before` 的 compare-and-set，不符即 `stale`）、`label_review`、`_sweep_outcome_labels`、候选消费（含被拒组）、`max_promotions` 上限、create/weaken 永不自动 |
| `aos/core/memory/store.py` | +250 | `list_open_candidates`/`consume_candidates`/`pending_review_id`/`list_loops_needing_review`/`clear_loop_review_flag`；`set_observation_outcome` 改按 loop 整体改写；`REVIEW_KINDS`+`REVIEW_STATUSES`（含 `stale`）；`upsert_memory` 不再清零已赚计数器、不再丢弃行内 tags |
| `aos/contract/{schema,postflight}.py` | +38/+35 | `SIGNAL_FIELDS`、`VERDICT_FIELDS`、`PLUGIN_POSTFLIGHT_REQUEST_FIELDS`（钉住**host 能发什么**）、`collect_signals`（嵌套 `signals` 与扁平键两种形状）、`learning.needs_review` |
| `aos/cli/main.py` | +119 | `review list` 渲染每条评审的**后果**或一次运行的**信号快照**；`review label <id> --outcome`；`review reject --as`；`--payload` 告警 |
| `aos/core/memory/migrations.py` | +51 | **v4 `review_loop_link`**：`learning_reviews.loop_id`（计划 §五 只列了 kind/outcome） |
| `content/memory/seed/agentos.json` | +28 | 两条种子：`M-SEED-SIGNAL11`（不给未标注运行记默认结论）、`M-SEED-CWD12`（项目根由调用方命名） |

## 二、测试结果

| 起点 | 结束 | 净增 |
|---|---|---|
| `f108c84` = 279 passed | `bf0fa6e` = **339 passed** | **+60 用例**（`git diff` 口径 54 个新 `def test_`） |

**一处我自己的错要记**：`bf0fa6e` 的提交信息写「Tests: 337 passing」，实测 **339** —— 起草信息后我又加了两个
CAS 测试（`test_approval_is_refused_when_the_memory_moved_first`、`test_a_stale_approval_recovers_by_rerunning_learning`），
计数忘了改。提交信息未 amend（历史不改写，除非你要求）。

**既有断言被改写的三条**（都是行为变更，不是修测试让它通过）：
`test_run_with_test_provider_completes` → `test_run_without_evidence_is_partial_and_asks`（completed → partial+needs_review）、
`test_run_failing_tests_marks_partial` → `..._marks_failure`、
`test_failing_validation_marks_partial` → `test_failing_build_marks_failure`；
另 `test_approve_review_applies_promotion` 的 `observation_count == 1` 改为 `== 0`（晋升不再写使用计数，见下）。

## 三、行为变化（before → after，含实演屏幕）

**① 无 verdict 的运行不再被记成成功，也不再什么都不改。** 实演（CLI + 真 git 仓库，8 次同任务运行）：

```
run 1: final=partial  learning.needs_review=True  candidates_recorded=0   ← 合成不出结论 → 问人
run 4: final=failed  candidates=5  pending_reviews=10                     ← host 给了 outcome=failure
```

**② 门第一次能往下走。** 批准一条 weaken 评审的实测屏幕（这一屏就是计划 §4.2 的验收标准）：

```
$ ./bin/aos memory show M-SEED-EXPORT8
before: {'evidence_level':'real_project_validated','confidence':'high','status':'active','decay_factor':1.0,'observation_count':7}
$ ./bin/aos review approve 15
approve: applied kind=weaken evidence_level {'old':'real_project_validated','new':'independent_validated'}
                        confidence {'old':'high','new':'medium'} decay {'old':1.0,'new':0.8}
after:  {'evidence_level':'independent_validated','confidence':'medium','status':'active','decay_factor':0.8,'observation_count':7}
```
再两轮：`independent_validated → runtime_validated → benchmark_evaluated`，decay 1.0→0.8→0.64→0.512（floor 0.5），
`observation_count` 全程未被晋升改写（**它只有一个写入者**），并且该记忆已不在召回列表里。

**③ compare-and-set 真的挡住了一次批准。** 队列里那条评审开着时，后续三次运行把记忆推进了：

```
$ ./bin/aos review approve 5
stale {'observation_count': {'was': 2, 'now': 4}}     ← 什么都没写，评审转为 stale，让下一轮重新描述它
```

**④ 端到端闭环成为可测事实**：`tests/test_end_to_end_evolution.py::test_a_failure_becomes_a_warning_the_next_run_hears`
—— preflight（召回空）→ postflight 无 verdict → `outcome_label` 评审 → `label failure` → 提案 → 晋升 →
下一次 preflight 的 `<agent_os>` 里出现"不要…"与"适用："。这是 spec §二十二 D 的第一次可运行回答。

**⑤ 契约收紧**：`signals` 对象不再是"未知字段"而是被读；host 想报失败可以只报 `test_exit_code:1`（实测 mass 0.55 → `failed` + `needs_review`）。

**刻意没变**：注入仍只有 `inject.render` 一个出口；晋升仍需人门或强证据；候选仍走 SQLite；
`evidence_level` 六档未动；零依赖、未装插件、未写 `~/.config/opencode/**`。

## 四、风险与回滚

| 风险 | 说明与处置 |
|---|---|
| **改了学习门的安全属性** | 这是计划 §1.6 标"高风险、需单独立项"的那一项。做法是**先把测试改成"批准后的效果"**（`test_approving_a_weaken_review_lowers_the_memory` 等），再动 `apply_promotion`；测试先行这一点按计划执行了 |
| 评审可能永久不可批准 | CAS 的副作用：基线里放了 `observation_count` 会让任何被再次使用的记忆**永不可批准**。修法是把它从 `before`/`changes` 里移出（晋升只写它判定的字段），并留下 `test_approval_is_refused_when_the_memory_moved_first` 双向守住 |
| 行为收紧让 `aos run` 看起来"变差" | 无测试命令的引擎自述运行现在报 `partial`。`[Judgment]` 正确但**用户可见**，需要写进 README 与 final plan 的 MVP 说明 |
| v4 迁移 | 选择新增 v4 而不是改已应用的 v3（`MIGRATIONS` append-only）。代价是多一个版本号，收益是"已应用的步骤永不被悄悄改写"这条纪律不被破例 |
| 回滚 | `git revert bf0fa6e` 撤代码；**已迁到 v4 的库不会降级**，旧引擎读到 `user_version=4 > LATEST` 会拒绝启动 ⇒ 回滚代码必须同时人工 `PRAGMA user_version = 3`，或从 `store/aos.db.pre-3.2-demo.bak` 恢复。这条限制必须在 final plan 的迁移风险一节成为显式运维步骤 |

## 五、是否破坏既有契约

**否（全 additive），但有一处语义变更：**

1. `postflight` 请求新增 `signals` 对象与 8 个扁平信号键 —— 旧 host 不发也能跑，只是质量退化为"没被告知"。
2. `learning` 块新增 `needs_review`（嵌套 additive，旧键未删未变型）。
3. `review` 的 `proposed_change` JSON 形状变了（`kind/changes/before/reason`）—— **引擎内部结构，不在 host 契约面**，但它是人读的东西，改了要通知使用习惯。
4. **语义变更**：`final_status` 不再是"loop 机器自己算的第二套结论"，而是由记录到的 outcome 派生。
   同一 loop 在旧实现可能报 `completed`、新实现报 `partial`。这是有意的、且是本轮最重要的一次"少说谎"。
