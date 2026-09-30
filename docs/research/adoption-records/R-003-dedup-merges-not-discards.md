# R-003 · 判重的结果必须是"合并并强化"，不是"丢弃新证据"

**来源项目与组件**
四个来源，四种实现，**没有一个把这件事做对**（本条是"共同问题存在但无解"的记录，借鉴的是约束而不是做法）：
- `svtter/src/skill-store.ts:106-113`（`findSimilarSkills` = SQL `LIKE '%triggers[0]%' OR LIKE '%name%' LIMIT 3`）
  → `:90-104`（`scoreAndSaveSkill` 命中即**用新内容覆盖首个匹配的全部字段** + `version+1`）`[Verified·一手]`
- `okdk/index.ts:583`（判重只存在于给模型的 prompt：「check for collisions」）；
  `:179` 声明 `absorbed_into` 字段，`:253` 实际只写成字面量 `"(deleted)"` `[Verified·代理读源]`
- `opencore/.opencode/plugins/memory.ts:144-187`（LLM 四值裁决 `ADD|UPDATE|DELETE|SKIP`），
  `:175,178,181`（**解析失败 fail-open 到 ADD**）`[Verified·代理读源]`
- `autolearn/skills/autolearn/scripts/registry.py:189`（`find_by_text` 名字/文本相等）+
  `autolearn.py:446`（promote 时已存在即跳过）`[Verified·代理读源]`

**观察到的设计**
共同形状是：新事实 → 找相似 → 三分支（新增 / 更新已有 / 忽略）。差别只在"找相似"的可判定性与"忽略"是否留痕。
**没有任何一家把"命中重复"转成"给已有条目增加一条证据"** ——
svtter 覆盖内容（丢掉了旧表述与旧证据）、okdk 让模型自己查（不保证）、opencore 让模型判并在新裁决失败时新增、
autolearn 直接跳过（新证据蒸发）。

**解决的问题**
"记忆越来越乱"的两个来源之一的另一面：重复堆积是乱，**把重复当噪声丢掉同样是乱** —— 后者会让
"同一事实被独立观察到 N 次"这一最强的置信信号永久丢失。Agent OS 的 6 档 `evidence_level` 与
`min_observations` 判据完全依赖这个计数。

**为何适用于此处**
1. **≥2 独立血统采用**：成立（4 家都在写入路径前设判重步骤，autolearn / svtter / okdk / opencore 血统互不相同）。
   ⇒ 判重是共同问题，**这一点证据充分**。
2. **共同问题**：重复条目污染检索与注入预算；覆盖丢失表述多样性；跳过丢失证据计数。
3. **Agent OS 也有，且已核实处于"半件"状态**：
   - schema 侧就位：`memories.dedupe_key` 列 + `uq_mem_dedupe ON memories(scope,dedupe_key) WHERE dedupe_key<>''`
     唯一索引（`aos/core/memory/migrations.py` v2 内建）；
   - **生成侧与命中侧都不存在**（实测：`grep -n "dedupe_key" aos/core/memory/authoring.py aos/core/memory/record.py`
     无任何匹配；`grep -n "dedupe_key" aos/core/memory/retrieve.py` 亦无匹配）⇒ 该列只有 `upsert_memory`
     写入默认值 `''`，而唯一索引带 `WHERE dedupe_key <> ''` ⇒ **索引永久不生效**，是一件装饰品；
   - 现在真的出现了堆积症状：本次会话前的一次 3.2 实演里，8 次相同任务的失败运行产生了
     多条 `create` 提案评审（`learning_reviews` 里 `pending 16`，全是同任务的不同 proposal id），
     正是"同一事实 N 次、每次一个新条目"的形态。

**需要的改造**（把别家的失败转成 AOS 的设计约束，而不是抄做法）
1. Phase 3.3 的 `aos/core/learning/dedupe.py` 必须实现三分支，其中**命中分支的语义是 reinforce 而不是 skip**：
   同 `dedupe_key` → `observation_count/evidence_count += 1`、更新 `last_verified_at`、
   把新证据的来源链 append 进原条目（`source_*` 列已有）；**绝不覆盖 `title/body`**（作者内容只由人改）。
2. 灰区（相似但不等价）才开 `learning_reviews(kind='conflict')`，与 §3.4 的冲突处理共用一条谓词；
   低于灰区 → 新增，但**必须留下 `supersedes=''` 的谱系起点**以便将来合并。
3. 唯一索引当前对 `dedupe_key=''` 无效（有意如此）⇒ 需要一条断言保证**每条正式记忆都有非空 key**，
   否则索引是装饰品（findings §18 的"死索引"风险）。
4. 提案侧同样要判重：`record.py:58` 的 `proposal_for_loop` 每次生成新 `M-XXXXXXXX` id ⇒ 相同任务的重复失败
   必然产生重复提案。改造：提案的 `target_memory` 用 `dedupe_key` 派生的**稳定 id**（而不是 uuid），
   让"同事实"在 `group_candidates`（`evolve.py:65-97`）里天然合并成一组、而不是 N 组。
   这条能直接消掉实演里看到的队列堆积。
5. 零依赖：`difflib.SequenceMatcher` + 集合 Jaccard，标准库内，符合约束。

**为何不直接复制**
- 无可复制物 —— 四家实现都是被否定的对象；`opencore` 还额外没有许可。
- `svtter` 的 `LIKE` 判重在语义上是"最后一位写入者赢"，与 AOS 的 provenance 原则直接冲突。

**建议去向**
**Learning**（`aos/core/learning/dedupe.py`，Phase 3.3）；提案稳定性那一小块落在 **Memory/record**（`record.py`）。

**风险**
- 失效模式：**误合并比漏合并更坏**（把"Java 17"与"Java 21"并成一条会永久失去区分）。灰区阈值一旦设低，
  就出现 svtter 那种"覆盖"故障的变体。
- **如何证伪（一条会失败的断言）**：
  `tests/test_dedupe.py` 必须同时有这两例并都通过 ——
  (a) 插入「Java17 / Java 17 / 项目 Java version=17 / 使用 JDK 17」四条 ⇒ 库中只剩 1 条且 `observation_count==4`
      （证明命中分支是强化）；
  (b) 插入 `Java 17` 与 `Java 21` ⇒ 两条**都在库中、`body` 与插入时逐字节相同**，且多出一条
      `kind='conflict'` 的 pending review；任何一条的 `title/body` 被改写就是本条要防的失败。
