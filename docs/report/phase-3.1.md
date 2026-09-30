# Phase 3.1 汇报（补交）

**这份汇报是补交的。** 按批准的节奏它应当在 Phase 3.1 结束时随代码一起给出；实际是代码先提交
（`ce02163`…`f108c84`，2026-09-30），文档在此之后。这本身就是被审计的一项偏差
（见 `docs/audit/current-state.md §6`），此处不辩解，只把欠的内容补齐。

Phase 3.1 是"观测纵切面"：冷启动 → 召回 → 注入 → 标注 → 晋升，一次做成**能在屏幕上看见**的闭环，
允许信号来自人工、允许记忆由人写，但不允许任何一环缺失。

---

## 一、修改文件（真实 diff）

五个代码提交，按子项归组；`git show <sha> --stat` 可复现。

| 子项 | 提交 | 内容 |
|---|---|---|
| **3.0 缓存污染**（3.1 的硬前提） | `ce02163` | `aos/config.py`(+20 `reset_caches()`)、`memory/policy.py`、`orchestration/orchestrator.py`、`routing/taxonomy.py` 的缓存键改为**解析后的真实路径**；`tests/conftest.py` 在 hermetic fixture 前后各调一次；清掉 `test_learning_gate.py`/`test_routing.py`/`test_orchestration.py` 里手写的 `reload()` |
| **3.1a 注入渲染器** | `8c8d7c7` | 新增 `aos/core/memory/inject.py`（187 行，纯函数）；`stages.build_prompt` 改用它（此前自己拼英文标题 + 恒空的 `content` 字段，注入在观测上与"没接线"不可区分）；`policy.py` 加 `injection` 默认段；+`tests/test_inject.py` |
| **3.1b 契约 1.1** | `c63f74c` | `contract/schema.py`（`CONTRACT_VERSION="1.1"`、`SUPPORTED_VERSIONS=("1.0","1.1")`、`validate_request`）、`preflight.py`（`memory.injection{structured,text,…}`、`memory.status`）、`postflight.py`（`aos_error`、`recovery.final_status` 不再伪造）、`lifecycle.py`（渲染注入块）、README；+`tests/test_contract.py` 双向键集守卫 |
| **3.1c CLI 全字段转发** | `f4ec9ed` | `cli/main.py` 显式白名单转发 postflight 全字段（此前只转 `task_id/loop_id/session_id/cwd`，**静默丢弃 host 的 outcome —— 断点 3 的根因**）；`schema.py` 的 `REQUEST_FIELDS`/`unread_request_fields` ⇒ 未知键进 `warnings`；`_rejected()` + 退出码 3 |
| **3.1d/e 作者面与冷启动** | `26c7881` | 新增 `memory/authoring.py`（枚举校验、`verified` 门、`seed_from_dir`）、`content/memory/seed/agentos.json`（首批种子）；`cli/main.py` 的 `memory add|seed|show|inspect|list` |
| **3.1f 生命周期与迁移机制** | `f108c84` | 新增 `memory/migrations.py`（461 行，`PRAGMA user_version` 为唯一权威 + 镜像交叉校验 + `_rebuild_table` + `Connection.backup()`）；`schema.sql` 冻结为 v1 基线；`store.py` 29 列 `upsert_memory` + `_PROMOTABLE_FIELDS`；`retrieve.py`/`evolve.py`/`inject.py`/`authoring.py` 词汇切到 6 type / 7 status / lane；`contract/schema.py` 枚举同源；CLI `memory migrate/inspect` |
| （穿插）删除死 host 树 | `ffb2880` | `hosts/` 7 文件（2361 行）与所有指向它的记录：`contract/legacy.py`、`ENV_LEGACY_HOME`、README env 行、`roles.json` 误导注、`.freebuff/` |

## 二、测试结果（逐提交实测，在 /tmp 克隆上 checkout 后跑）

| 提交 | 阶段 | 全量 | 净增 |
|---|---|---|---|
| `fa3cab8` | 起点 | **151 passed** | — |
| `ce02163` | 3.0 | 153 | +2 |
| `8c8d7c7` | 3.1a | 170 | +17 |
| `c63f74c` | 3.1b | 186 | +16 |
| `f4ec9ed` | 3.1c | 199 | +13 |
| `26c7881` | 3.1d/e | 234 | +35 |
| `ffb2880` | 删 host | 233 | −1（随删的死测试） |
| `f108c84` | 3.1f | **279** | +46 |

151 → 279（+128 用例，`git diff` 口径 +117 个 `def test_`，差额来自参数化）。
**九个提交每个都单独全绿** ⇒ "每 Phase 一个提交、可单点 revert"这次是量出来的，不是承诺的。

新增测试的代表（完整名单在 `git diff fa3cab8 f108c84 -- tests/`）：
`test_no_one_can_author_a_memory_straight_into_verified`、
`test_every_seed_entry_states_its_rule_inside_the_budget`、
`test_injection_limits_come_from_the_policy_file`、
`test_fallback_postflight_reports_failure_not_completion`、
`test_mistyped_field_is_rejected_not_coerced`、
`test_missing_required_field_returns_fallback_and_nonzero_exit`、
迁移四条必测（`test_a_newer_database_than_the_engine_is_refused_not_downgraded` 等）。

## 三、行为变化（before → after）

- **屏幕上第一次出现注入块**（本阶段的验收项，已实测）：
  `./bin/aos memory seed` → `memory add` → `preflight --payload-stdin` →
  `python3 -c '...print(d["memory"]["injection"]["text"])'` 打出 `<agent_os>…</agent_os>`，
  含 `[id · type · evidence_level · confidence]` 标签行与 `适用：` 触发子句。
- 新记忆**出生即 hypothesis**：不带 `--verified` 一律被强制 `evidence_level=hypothesis / lane=hypothesis / status=candidate`；
  `--status verified` 这类越权在 authoring 层就报错。
- postflight 的未知字段不再被静默丢弃，而是回 `warnings`；请求体畸形 ⇒ fallback 文档 + 退出码 3（不再抛异常给 host）。
- `aos doctor` 报 schema 版本，并且**诊断不迁移**（`test_doctor_does_not_migrate_a_behind_database`）；
  `aos memory migrate --dry-run` 只报告不动手。
- 数据库被版本化：打开旧库自动走 v2；`user_version` 与 `schema_meta` 不一致 ⇒ 拒绝启动而不是猜。

**刻意没变**：注入仍只有一个出口（`inject.render`）；契约 1.0 的顶层键集与 `classification.domains` 语义原样；
`auto_modify_code=False`；零三方依赖；`memory/evolve.py` 未搬家；目录未改名。

## 四、风险与回滚

| 风险 | 实际发生 / 处置 |
|---|---|
| 碰持久层（v2 重建 `memories`） | **真发生了一次静默数据破坏**：`PRAGMA foreign_keys` 在事务内被 SQLite 忽略 ⇒ 重建时级联删掉了 tags/roles。修成"破坏性步骤在事务外关外键" + `PRAGMA foreign_key_check` + 回归测试 `test_tags_and_roles_are_cascaded_away_by_the_rebuild`，并写进种子记忆 `M-SEED-MIGRATE11` |
| 词汇切换改变已发布字段的取值域 | `MEMORY_TYPE` 从 7 旧值换成 6 新值 —— **这是 1.0 字段取值域变更**，`contract/schema.py:41` 注释已承认；今日无已部署消费者 ⇒ 风险接受，但它是 Stage 2 要复核的契约事实 |
| 迁移不可解释 | 由机制解决：`MIGRATIONS` append-only、每步一个事务、破坏性步骤先 `Connection.backup()` |
| 计划说 `validated→active`，实际映射成 `verified` | **偏离已记录**：`validated` 与 `evidence_level` 语义重叠，7 态里 `verified` 才是"强证据达成"。计划 §五 的这条写法不再回改，由 `docs/plan/final-plan.md` 追认 |

回滚：`git revert f108c84` 可单独撤 3.1f（含迁移代码，但**不会**降级已迁移的库 —— 库会停在 v2 并被引擎拒绝启动，需人工 `PRAGMA user_version` 或从 `.pre-v2.bak` 恢复）。这是本轮识别出的真实回滚限制，写进 final plan 的迁移风险一节。

## 五、是否破坏既有契约

**部分破坏，且已披露：**

1. **响应** `memory.injection{structured,text,…}`、`memory.status`、`aos_error`、`recovery.final_status` 语义 —— 全部 additive，1.0 顶层键集未删未变型（`tests/test_contract.py` 的 `FROZEN_1_0` 守卫）。
2. **取值域破坏**：`memory.memories[].type` 词汇换（旧 7 → 新 6），`status` 词汇换（3 → 7）。对 pin 1.0 的 host 是**破坏性变更**，虽然今日无消费者。
3. **请求**：新增 `validate_request` 的严格面 —— 字段类型错（如 `quality_score:"4.5"`）从"被吞掉"变成"拒绝 + 退出码 3"。**对不合规的 host 是行为破坏**，方向是收紧。
4. 计划预告会被打破的 `test_postflight_is_idempotent` **实际没被打破**（它断言两次调用相等而非字面 `completed`）—— 记为计划预测错误，不是实现错误。
