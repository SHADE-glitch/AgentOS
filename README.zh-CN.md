<p align="right"><a href="README.md">English</a> | <a href="README.zh-CN.md"><b>简体中文</b></a></p>

# 🧠 Agent OS

> **编码智能体的外置证据与治理层。**
> 真实运行 → 合成判决 → **人门** → 晋升为记忆 → 召回改变**下一次**喂给模型的内容。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![第三方依赖](https://img.shields.io/badge/%E7%AC%AC%E4%B8%89%E6%96%B9%E4%BE%9D%E8%B5%96-0-green)
![宿主契约](https://img.shields.io/badge/%E5%AE%BF%E4%B8%BB%E5%A5%91%E7%BA%A6-1.2-informational)
![SQLite schema](https://img.shields.io/badge/SQLite%20schema-v5-informational)
![测试](https://img.shields.io/badge/pytest-502%20passed-brightgreen)

> ⚠️ **Vibe coding 产物，就停在这里。** 本仓库几乎全部由 AI agent 的 vibe coding 写成，最初追的
> 是一个更大的想法：一套 **Agent OS** —— 多 Agent 的运行与治理平台，核心是 agent 的**自我进化**与
> **经验沉淀**。这个想法太大，后来被砍成你现在看到的这一小块（真实运行 → 合成判决 → 人门 →
> 记忆 → 召回）。作者**不再继续开发**，把它留作一次尝试的记录 —— 就现有内容而言，那个想法没能
> 被证明值得每天用。下面「判据 1 / 2026-10-29 收口」是**放弃之前**写下的判定框架，本段是**之后**
> 的结论；README 其余部分请当快照看，别当路线图。

宿主（目前是 [OpenCode](https://opencode.ai)）负责干活。本引擎决定它**动手前**该被告知什么、
**做完后**那段经历教会了什么。它从不改代码：所有路径上 `auto_modify_code` 都是 `False`。

> 📖 **分工说明**：深度参考（契约字段全集、四轴表、生命周期内部）的「单一副本」在
> [`README.md`](README.md)，本文件不复述 —— 同一份事实抄两遍，迟早只改一处。
> 这里镜像的是决定"要不要继续做"的那批事实；两份文件的共同数字由
> `tests/test_readme_bilingual.py` 钉住，漂移就是红的。

---

## 🧭 为什么中间要放一个人

[`docs/research/`](docs/research/) 调研的每一个项目，凡是让模型自述"我学到了什么"就自动晋升的，
最后都攒下了一批自信而错误的记忆。这个仓库把"变成耐久知识"的唯一入口留给人：

```text
  ┌──────────── 宿主在跑，引擎在旁边看着 ────────────┐
  │                                                   │
  ▼                                                   │
📥 preflight ──▶ 🧭 route ──▶ 🔍 recall ──▶ 📝 inject ──▶ 🤖 宿主执行
                    ▲                                     │
                    │                                     ▼
                    └──────── 📚 晋升后的记忆 ◀── 🚪 人门 ◀── 📊 判决
                                    │
                                    └──▶ ✋ 退休 / 衰减（降级是永久的，没有对称命令）
```

* **判决和归因是两件事。** 标一次 `failure` 只是记录你看到了什么；不点名 skill 就不归因任何记忆。
* **被召回过 ≠ 造成了结果。** 候选必须有归因，否则一次失败会把在场的所有记忆一起削弱。
* **假设绝不自动晋升。** 它变成一条 `pending` 评审行，等人来结。

---

## 📊 状态 —— 动手之前先读这张表

文档统一用四级标注：`✅ 已实测`（真宿主上量出来的）· `🟡 推断` · `⚠️ 未证`（设计了但没量）· `💭 判断`。

### ✅ 已经量到的

| 主张 | 证据 |
|---|---|
| 注入块真的到达模型 | 惰臂对照（同 cwd 同提示词）少 **583** 个输入 token |
| 人的一次决定改变了下次召回 | 真库上：注入从 **1122** 字符/3 条 变成 **1359** 字符/4 条，且 `+237` 是**跑之前**从真库副本预测出来的 |
| 方法级经验能穿过采集面 | "试 A → A 败 → 换 B → B 成"以有界有序、脱敏后的指纹进库，判重到"一次决定一行"，同时**判决权重 0.00**（测试钉住） |
| 失败即降级，不阻塞 | 库不在、邻居库不在、引擎慢 ⇒ 注入降级并在 `warnings` 里说原因；绝不挡住一次提问 |
| 停用零影响 | 不设 `AGENT_OS_ROOT` ⇒ `output.system` 与没装插件时**逐字节相同**（JS 断言） |
| 引擎不碰宿主 | 没有任何路径调用 `opencode`；宿主只经 `bin/aos` + JSON 契约进入 |

### ⚠️ 从来没量过的 —— 也就是这个项目仍可能被砍掉的理由

* ❓ **注入有没有让答案更好？** 从未测。已证的只是答案的**形状**变了，而且是在一个模型本来就会答的问题上。
* ❓ 有没有减少未来的尝试、有没有改变**第一个动作**？未答。
* ❓ 相对宿主自带的 `AGENTS.md` / 记忆能力，增量在哪？没有盲评。
* ❓ **被计数的那些运行是人驱动的吗？** 今天不可判（缺陷 `AR`）：宿主不暴露驱动者，
  所以 `hot` 是一个上界，而"可证由人敲"的下界是 0。
* ❓ 教训能不能跨轮粘住？证据偏弱：14 轮真机序列里有一轮召回为 0。

> **⏳ 去留判据（判据 1）。** 接线后 4 周内 `source='hot'` 的真实运行少于 **30** 条 ⇒ 停止加功能，
> 仓库收缩成三个可独立存活件 + 文档。窗口在 **2026-10-29** 收口。现值一律
> `./bin/aos doctor --json` 现取 —— **不要相信任何抄进文档的数字，包括这一份。**

---

## 🚀 上手

```bash
git clone https://github.com/SHADE-glitch/AgentOS && cd AgentOS
python3 -m pytest                       # 502 passed —— 测试套件就是规格说明
node --test tests/js/plugin.test.mjs    # 29 pass  —— 宿主接缝

./bin/aos doctor --json                 # 这份 checkout 到底做过什么
./bin/aos memory seed                   # 空库召不回任何东西，这步是第一步而不是可选项
./bin/aos run "加一个 /health 端点" --cwd /path/to/project --provider test_provider
./bin/aos review list                   # 人门：每条都写明批准会发生什么
```

<details>
<summary><strong>🔌 宿主怎么讲契约</strong></summary>

```bash
echo '{"schema_version": "1.2", "phase": "preflight", "task": "…", "session_id": "…", "cwd": "…"}' \
  | ./bin/aos preflight --payload-stdin
```

`memory.injection.text` 就是可以直接 append 的 `<agent_os>` 块；空字符串 ⇒ 什么都不推。

</details>

---

## 🏗️ 目录与文档地图

```text
AgentOS/
├── bin/aos                     # 薄壳 -> python3 -m aos.cli
├── aos/                        # 引擎（纯标准库）
│   ├── config.py               # 所有路径可注入；除这里以外不许写死位置
│   ├── contract/               # 冻结的 preflight/postflight 形状，schema_version = "1.2"
│   ├── core/memory/            # store · retrieve · record · evolve(人门) · policy · inject
│   │                           #   external(只读邻居召回) · external_write(批准时经 CLI 发布)
│   ├── core/loop/              # 状态机 · 生命周期 · 阶段 · pending-postflight
│   ├── core/routing/           # 路由器 · 角色目录 · 分类映射
│   └── cli/main.py             # doctor preflight postflight route run pending backfill memory review
├── integrations/opencode/      # 插件、fixture 测试、真机 rig
├── content/                    # 不改代码就能调的 JSON（策略 8 个、冷启动种子）
├── store/                      # 运行态 —— gitignore，测试永远不写它
├── docs/                       # architecture · decision · research · experiment · plan
└── tests/                      # pytest（hermetic tmp 库）+ tests/js/（node --test）
```

| 文档 | 里面是什么 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | 不可协商的检查 —— 你（或你的 agent）要改这个仓库，先读它 |
| [`docs/architecture/agent-os-v2.md`](docs/architecture/agent-os-v2.md) | §12 缺陷登记（A–AS）· §15 证据够到哪一层 · §16 能力边界 |
| [`docs/decision/positioning.md`](docs/decision/positioning.md) | §5 邻居笔记库算什么 · §6 停止/降级判据 |
| [`docs/plan/final-plan.md`](docs/plan/final-plan.md) | §11 执行日志： 大多是"怎么错的、怎么抓到、怎么修的" |
| [`docs/experiment/`](docs/experiment/) | 冻结实验、Stage 0 票面与出口判据、Stage 1 使用账本 |

---

## 🗳️ 记忆与人门（最小版）

`store/aos.db` 是唯一真相源（schema `v5`，迁移只追加）。一条记忆有四根**互不合并**的轴：
`type`（怎么说）· `evidence_level`（查到哪一步）· `status`（生命周期的哪一格）· `scope`（哪里能被召回）。
完整取值表和契约字段全集在 [`README.md`](README.md)。

阈值全部来自 `content/policies/*.json`，一共 **8 个**策略文件，合并方式是"内置默认被文件覆盖"：
`decay` `external` `external_write` `injection` `outcome` `promotion` `rejection` `retrieval`。
调门槛是改文件，不是在调用处补一个本地数字。

唯一一次外部调用（把批准的经验发布进笔记库）的实测代价是每次 spawn **8.1**–9.2 s，
所以它**永远不在热路径上**：preflight 的预算是 **1200** ms，超时的引擎会被杀掉、这轮就是不注入。

```bash
./bin/aos review list                                   # 每行都写着"批准会发生什么"
./bin/aos review label <id…> --outcome failure --skill bugfix
./bin/aos review approve <id> --title T --body B --when W --tags A,B
                                                        # 仅新建：由人写下信号给不出的「因为」，
                                                        # 并由人写下主题 tag —— 路由猜的 tag 不是主题
./bin/aos memory retire <id> --reason R                 # 退出召回；行与历史都留着
```

---

## 🧪 测试

```bash
python3 -m pytest                              # 502 passed
node --test tests/js/plugin.test.mjs           # 29 pass / 0 fail
```

两个已经咬过我们的坑：

* **别在 pytest 后面再补 `-q`。** `pyproject.toml` 已带一个 `-q`，第二个会把汇总行整个吃掉，
  于是 `pytest -q | grep passed` 什么都不打印，计数脚本静默读到 0。
* **别写 `node --test tests/js/`。** 那会把 `fake-aos.cjs` 当测试执行，输出 `# tests 1 / # fail 1`，是假红。

`python -m unittest discover -s tests` 收集到 **0** 条且退出 `0`：pytest 是唯一 runner。
每条测试都跑在 hermetic `tmp_path` 库里，并且 `AOS_BM_DB` / `AOS_BM_CONFIG_DIR` / `AOS_BM_BIN`
都指到不存在的路径 ⇒ 测试既读不到、也写不进真实笔记本。rig 另有 15 条（`integrations/opencode/live/tests`）。

---

## 🤝 接手开发

先读 [`AGENTS.md`](AGENTS.md)。交付规矩：**一个改动 = 一笔提交**，汇报固定五项 ——
改了哪些文件 · 测试前后计数 + 新增用例名 · 行为 before→after（**含刻意没变的**）· 风险与回滚
（能否单笔 revert）· 是否破坏契约。跳过某一步时，必须能证明那一步仍然可执行。

好的起点，以及每一条**为什么不是顺手就能修**（`AR`、`AK` 是新读者最先会注意到的两条未闭缺陷）：

| 事项 | 状态 | 为什么还开着 |
|---|---|---|
| `AR` 驱动者 | 未闭 | 宿主没有这个出口：`OPENCODE_CLIENT` 只被赋值过 `"acp"`，TUI 从不写它 ⇒ 人和 agent 都读成 `cli`。今天补一个"来源"字段就是造数据；要改契约，是 owner 的决定 |
| `AK` 中断 | 未闭 | `user_interrupted` 被契约和合成读，但没有任何一行赋值 ⇒ 中断否决权从不生效。需要宿主事件源 |
| `AI` 退出码归因 | 未闭 | 退出码看得见，但"这条命令算构建还是算测试"是判断，插件不许猜（那是自我打分，缺陷 `F3`） |
| `AS` 未闭合账 | 未闭 | 崩溃记录按 session 存、只有 postflight 会清 ⇒ `outstanding` 是**下界**：66 条未回报的 loop 只留下 1 个文件 |
| 残留列 | 未闭 | `use_count` / `success_count` / `last_used_at` 被 CLI 和排序原因读，但没有任何路径写它们 ⇒ `retrieve.py` 里有一个永远进不去的分支 |
| 到期与复验 | 未闭 | `revalidate_after` 只有一个写入者（作者的那个 flag），而 `expire_due` 会按它行动 ⇒ 复验过的记忆仍会按出生那天的日期过期 |
| 笔记归属接缝 | 未闭 | 召回会跳过带我们标记的笔记；没钉住的两条是"frontmatter 解析失败"（会被当人写笔记）和"人把标记删了" |
| Phase 2 | 只有设计约束，未开工 | 本轮量到的边界：spawn 8.1–9.2 s vs 预算 1200 ms；`retrieve()` 约 1 ms；**邻居的索引滞后于它的 md 文件** ⇒ 说"文本的家搬到 basic-memory"必须先说清读的是文件还是索引 |

这个项目**不会**接受的东西，无论看起来多好：第二套 skill 系统、自建遥测写入者、MCP、第三方依赖、
编排、会话检索、代码索引、会改代码的引擎、以及任何写 `~/.config/opencode/**` 的东西。

## 🔐 隐私与占位符

仓库已按公开标准脱敏：没有会话正文、提示词原文、工具输出、笔记标题、机器路径。
描述真实运行的文档改用占位符，于是数字和因果留着、地址簿不留：

| 占位符 | 含义 |
|---|---|
| `<repo>` | 本仓库的 checkout |
| `<subject-project>` | 真机运行当时的被试项目 |
| `<rig>` / `<rig>-void` | 实验脚手架目录 / 已作废并被封存的尝试 |
| `<bm-vault>` | 只读邻居召回指向的笔记目录 |
| `ses_redactedNN` | 匿名化后的宿主会话 id；不同 id 仍保持不同 |

写到规矩里而不是只写在这里：`tests/test_readme_bilingual.py` 会在任一 README 重新出现绝对家目录
路径或会话 id 时变红；`store/`（`*.db`、`loops/`、`evidence/`、`pending-postflight/`）在 gitignore 内，
`git ls-files store` 只应列出 `store/.gitignore`。

## ⚖️ 许可证

[MIT](LICENSE) © 2026 SHADE-glitch.
