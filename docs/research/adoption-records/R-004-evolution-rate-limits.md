# R-004 · 进化必须带速率与冷却闸门（提案节流 + 单飞锁 + dry-run 覆盖面）

**来源项目与组件**
- `okdk7788/opencode-self-improving-skills`（MIT），`index.ts:337-376`（`pickEvolutionCandidate`）与
  `:348-350`（准入：`use≥2 AND fail≥1`，且 24h 冷却）、`:359`（`priority = use*(fail+1)/(total+2)`）、
  `:1140-1153`（`optimized_at` 写回 `skill_outcomes.json`）`[Verified·代理读源]`
- `ericmjl/agent-autolearn`（MIT），`plugin/autolearn-core.mjs:581-647`（三层节流：内容哈希去重 /
  `min_interval_ms=180000` / `max_reviews_per_day=60` 从 review 文件 mtime 计数）、
  `:301-335`（生成的 wrapper 内部**再跑一遍同样的门**，并用 `mkdir` 做原子单飞锁、15 分钟过期回收，
  且**在开始运行之前**就记录开始时间）、`:379-392`（每次加载把 wrapper 重写成只读 `0o544`，
  注释写明是为了防"旧实例回滚"）、`:658-714`（curator 独立 gate + 1 小时机器级冷却）、
  `install.sh:145-163`（reviewer agent 限 `steps: 20`、`edit: deny`）`[Verified·代理读源]`
- 同仓库的 `--dry-run` 覆盖面：`retention evict --dry-run`、`falsify run --dry-run`（`falsify.py:341-368`）、
  `improve escalate --dry-run` `[Verified·代理读源]`

**观察到的设计**
每一层都独立再判一次，且**闸门本身不可被更早的实例改回去**。输入是"是否还要再做一次进化"这个请求；
变换是哈希去重 + 时间下限 + 日配额 + 原子单飞；输出是"做 / 不做 / 只报告"；状态落在
`.review_gate/`、`.curator_gate`、`.curator_cooldown`、`skill_outcomes.json{_meta.evolution_nudge_at,
_optimized_at}`。`[Judgment]` 这是四份代码里唯一把"自我改进"当成**攻击者可能是自己**来设计的。

**解决的问题**
无限漂移的物理条件就是"没有速率与冷却"：一次坏经验触发一次改进，改进本身又成为下一次的输入。
okdk 的 24h 冷却与 autolearn 的三层节流是两套互不知情的独立解法，方向一致。
反例同样充分：`svtter` 用进程内 `setInterval(intervalDays)`（`src/index.ts:40`）当作调度 ——
不持久化、进程不活满 7 天就永不触发，等于**没有闸门**；`opencore` 无任何进化门（`findings.md Q4`）。

**为何适用于此处**
1. **≥2 独立血统采用**：成立（okdk、autolearn，两条不同路线；svtter 的 interval 是同一需求的失败实现）。
2. **共同问题**：任何"由观察自动生成变更建议"的系统都会遇到"同一条证据被反复消费"和"短时间刷屏"。
3. **Agent OS 也有这个问题，且已核实处于半开状态**：
   - 已有的：`promotion.max_promotions`（每轮自动晋升上限，`aos/core/memory/policy.py` promotion 段、
     `evolve.py:601-632` 消费，超限自动转 review）；候选消费 `consumed_at/consumed_by`（`evolve.py:699`）
     防止同一候选被重复处理 —— 这一条其实已经解决了"重放"类漂移，是 AOS 领先处；
   - **缺的**：没有时间维度。`_sweep_outcome_labels`（`evolve.py:580`）与 `_create_review` 只按
     "是否已有 pending"去重，没有冷却；`run_learning` 在每次 postflight 内联执行
     （`aos/core/loop/stages.py:417`），因此一个高频会话会产生高频循环，没有配额；
   - 实测症状（本会话前的一次 3.2 实演）：8 次同任务运行 ⇒ `learning_reviews` 里 `pending 16`，
     全部是同任务的不同 `create` 提案 —— **没有配额时，堆积就是症状**。R-003 的第 4 点解决身份合并，
     本条解决"即便身份合并了，也不该每小时问一次人"。
   - `--dry-run` 目前只覆盖 `memory migrate`（`aos/cli/main.py` 的 `_memory_migrate`），
     破坏性更强的 `review approve/reject/label` 无 dry-run。

**需要的改造**
- 在 `policy.py` 的 `promotion`/`rejection` 旁新增一个 `learning_rate` 段（内置默认，零依赖）：
  `{per_loop_max_candidates, per_day_max_promotions, review_cooldown_hours, proposal_min_evidence}`；
  **每个键必须有读者**（沿用 §4.2f 已立的"要么生效要么删"纪律，并加一条断言：策略键的读者非空）。
- 冷却状态落在库内而不是文件（与 AOS 的"SQLite 是唯一真源"一致）：
  复用 `telemetry_events` 或给 `learning_reviews` 加 `decided_at`（v3/v4 已有 `reviewed_at` ⇒ 直接用它做冷却判断即可，
  无需新迁移）。
- `run_learning` 在开 review 前查"同一 `dedupe_key`/同一 memory 上次被问是否 < 冷却窗"；
  `outcome_label` 扫描同理（按 loop 的时间戳）。
- 单飞：AOS 目前是"每次 postflight 内联跑一次完整学习循环"，多个会话并发时会互相重扫。
  需要的是一个**进程内/库内**的单飞（`BEGIN IMMEDIATE` 已具备该性质，`migrations.py:209` 用过这个模式），
  不需要 autolearn 的 `mkdir` 文件锁。
- `[Judgment]` **不抄** autolearn 的"自重写只读 wrapper 脚本"：那是绕过"插件无法持久化调度"的产物，
  而 AOS 把执行点放在 `postflight`/显式 CLI，不需要生成 shell 脚本 —— 生成并自改可执行文件对
  "零副作用"承诺是净负。

**为何不直接复制**
- 许可上两家都 MIT，可以；但 autolearn 的实现落在 POSIX shell + `mkdir` 原子性 + `0o544` 自重写 + 文件 mtime 计数上，
  移植到 Python 引擎等于引入一整套文件系统协调协议；AOS 已有 SQLite 事务可以做同样的事。
- okdk 的实现嵌在它的 `skill_outcomes.json` 平面文件模型里，与 AOS 的表结构不同构。

**建议去向**
**Learning / Evolution**（`evolve.py` + `policy.py`）。不落在 Plugin —— 插件不应有节流知识。

**风险**
- 失效模式一：冷却过长 ⇒ 真实的新证据被当作"最近问过"而丢失（沉默失败，正是本研究反复见到的类）。
  失效模式二：配额按天 ⇒ 跨时区/跨进程重启的日界不一致（`opencore/budget.ts:91` 用日期分文件即为此）。
- **如何证伪（一条会失败的断言）**：
  `tests/test_learning_gate.py` 新增：把同一 `dedupe_key` 的候选在冷却窗内提交两次 ⇒ 第二次
  `run_learning` 的 `summary["reviews_created"] == 0` 且 **`summary["suppressed_by_cooldown"] == 1`**
  （必须**显式报告被压制了多少**，不允许静默丢弃 —— 静默丢弃是本研究里出现频率最高的缺陷）；
  冷却窗外再提交 ⇒ 必须新建 review。
