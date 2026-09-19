# 金银舆情 AI 监控

**这是一个自用工具**，不是给别人用的产品。

每天早上 07:30（北京时间）用飞书机器人推一份日报：

1. **AI 前沿** 3–5 条（标题 + 一句"为什么重要"+ 链接）
2. **金银聚焦** 3–5 条（标注影响方向与强度）+ 当日情绪指数与多空倾向
3. **今日紧盯**：宏观日历
4. 同时把每日数据追加进 `data/` 下的 CSV，图表每次现算到 `charts/`。

设计判据只有两条：早上收到的东西我是否真的会看；长期积累的数据对判断金银是否真有帮助。
不做实时快讯、不做交易信号、不做交互式分析平台。

---

## 架构：三层各管一段

```
GitHub Actions（cron 每天 23:30 UTC = 次日 07:30 北京时间）
   │
   ① 采集   Python 抓取各源 → 去重 → 时间窗筛选 → interleave
   │
   ② 智能   调用 Dify Workflow API（LLM 结构化抽取 + 日报文案）
   │
   ③ 计算   追加 events → 算情绪指数 → Matplotlib 出图
   │
   ④ 分发   飞书机器人推送卡片
   │
   ⑤ 沉淀   git commit 回写 data/
```

| 层 | 承担 | 为什么是它 |
|---|---|---|
| **Dify** | LLM 编排：结构化抽取、日报生成、Prompt 迭代 | 画布 + 逐节点日志可观测；改 Prompt 不用改代码重新部署；LLM 节点的 JSON Schema 约束比手写解析稳 |
| **Python** | 采集、存储、指标计算、出图 | Dify 代码节点是受限沙箱，跑不了 pandas/matplotlib，也不能往仓库写文件 |
| **GitHub Actions** | 定时调度、结果回写 | 免费额度够用；跑在海外，访问墙外信源不用代理；不依赖本机开机 |

代码分工：

| 文件 | 职责 |
|---|---|
| `src/collectors/` | 采集器，一源一类（`rss` / `jin10` / `wallstreetcn` / `gold_price`） |
| `src/collectors/base.py` | 统一 HTTP 行为：15s 超时、最多 3 次尝试、指数退避 |
| `src/dedupe.py` | 去重、时间窗筛选、按 category 交替排列 |
| `src/dify_client.py` | 调 Dify API，解析 `events_json` / `digest_json` |
| `src/analysis.py` | 情绪指数计算（**纯函数**，无网络无文件） |
| `src/storage.py` | CSV 读写，同日重复运行覆盖该日数据 |
| `src/charts.py` | 三张图 |
| `src/notifier.py` | 飞书卡片与降级文本 |
| `src/main.py` | 串流程，带 `--dry-run` / `--offline` |
| `config/sources.yaml` | 信源配置（新增/替换源只改这里） |

---

## 本地运行

Windows + bash（Git Bash）。**用项目自带的解释器，不要用全局 `python`**：

```bash
cd "D:/金银舆情监控"
.venv/Scripts/python.exe -m src.main --dry-run --offline
```

两个开关互相独立，可以分别验证"智能层"和"分发层"：

| 开关 | 作用 |
|---|---|
| `--offline` | 不调 Dify，改用 `samples/dify_response.json` 的样本 |
| `--dry-run` | 跳过飞书推送（其余照常执行，CSV 和图表照写） |

常用组合：

```bash
# 全离线演练：不联网调 Dify、不推送，但走完整计算与出图
.venv/Scripts/python.exe -m src.main --offline --dry-run

# 只验证推送链路（用样本事件，真发飞书）
.venv/Scripts/python.exe -m src.main --offline

# 正式跑一次（真采集 + 真调 Dify + 真推送）
.venv/Scripts/python.exe -m src.main
```

跑测试：

```bash
.venv/Scripts/python.exe -m pytest
```

终端里中文可能乱码，加个前缀：

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m src.main --offline --dry-run
```

---

## 需要哪些环境变量

只两个，都在 `.env.example` 里给了模板：

| 变量 | 用途 | 从哪来 |
|---|---|---|
| `DIFY_API_KEY` | 调 Dify Workflow，形如 `app-xxxxxxxx` | Dify 应用 → 访问 API → 创建 API 密钥 |
| `FEISHU_WEBHOOK_URL` | 飞书自定义机器人 Webhook | 飞书群 → 设置 → 群机器人 → 自定义机器人 |

> **注意：代码不会自动读 `.env`。** `src/config.py` 的 `get_secret()` 只读 `os.environ`，
> 项目里没有 python-dotenv。本地跑之前得先把变量导进环境，例如：
>
> ```bash
> set -a; source .env; set +a
> ```
>
> 在 CI 上则由 Actions 的 `env:` 直接注入 Secrets，不经过 `.env`（`.env` 已被 gitignore，不会进仓库）。

**飞书机器人必须配「自定义关键词」安全设置，关键词填 `每日日报`**，且要和 `src/notifier.py` 里的
`FEISHU_KEYWORD` 一字不差。卡片标题固定是 `📊 每日日报 · 日期`，降级告警也用同样开头，所以一定命中。
改了一边忘了另一边，第二天推送会**静默全挂**（飞书拒收，返回错误码，日志里只有一行）。不要选 IP 白名单——Actions 出口 IP 是变的。

---

## 如何新增 / 替换信源

只改 `config/sources.yaml`，不用动代码：

```yaml
sources:
  - name: 雷锋网
    category: ai          # ai | finance | market
    type: rss             # rss | jin10 | wallstreetcn | gold_price
    url: https://www.leiphone.com/feed
```

- `type` 决定用哪个采集器（注册表在 `src/collectors/__init__.py` 的 `_BUILDERS`）。
- `category` 决定它在卡片里归到「AI 前沿」还是「金银聚焦」，也影响 `interleave_by_category` 的交替顺序（不交替的话，预筛节点按位置截断会把排在后面的源整类砍掉）。
- `type: gold_price` 时 `category` **必须**是 `market`，否则 `build_collectors` 直接抛错。
- 新增一个全新类型的源（不是 RSS 也不是已有三种）才需要写采集器：继承 `src/collectors/base.py` 的 `Collector`，实现 `fetch()`，然后在 `_BUILDERS` 里注册。

信源可达性的历史探测记录在 `docs/信源核验记录.md`，包括每个源的 curl 结果、判定依据和替换调研。
`docs/` 下的设计文档是这套东西的完整依据，README 只做索引，细节以设计文档为准。

---

## 数据与指标定义

两张表，都在 `data/` 下，**每日追加、只增不改**（同一天重复运行会覆盖当天那行，保证跑多次结果一致）。

### `data/events.csv`

```
date, event_type, direction, strength, relevant, summary, source, url, published_at
```

- `event_type`：货币政策 / 经济数据 / 地缘政治 / 央行购金 / 美元走势 / 通胀 / 就业 / 其他（**枚举**，不给自由文本，否则统计时分类会散得无法聚合）
- `direction`：利多金银 / 利空金银 / 中性
- `strength`：1–5 整数
- `relevant`：该条是否与金银走势有关。**AI 技术类新闻填 false**，保留在表里供回溯，但不参与指数计算。
- 格式不合规的条目（缺字段、strength 越界、direction 不在枚举内）在 `to_events` 里**丢弃而不是整体崩盘**。

### `data/daily_index.csv`

```
date, sentiment_score, bull_count, bear_count, total_events, gold_close
```

### 情绪指数怎么算

每条事件赋符号：利多 `+1`、利空 `-1`、中性 `0`。

```
sentiment_score = Σ(符号 × strength) / (5 × 事件数)
```

- 分母除以 `5 × n` 是为了让取值落进 `[-1, 1]`，从而**事件数不同的日期之间可比**。直接求和会让"新闻多的一天天然分高"，那测的是信息流量而不是市场情绪。
- **只统计 `relevant = true` 的事件**；`bull_count` / `bear_count` / `total_events` 同样只数 relevant 的。
- **中性事件符号为 0，但仍计入分母**——这是刻意的，不是 bug。
- 没有任何 relevant 事件时返回 `0.0`。

### 金价

`gold_close` 取新浪财经现货黄金报价 `https://hq.sinajs.cn/list=hf_XAU`（字段位置会校验，不是硬按下标取值）。
**这一列是整个项目的分析价值支点**：只有和真实金价并排，才能回答"这个指数到底有没有信息量"。
所以金价取失败时不会让日报失败，但**会把源名并进失败源列表、在飞书卡片上显式告警**——否则 `gold_close` 会一直空着、双轴图一直不出，几天后才发现。

> 历史沿革：原用 stooq.com 的 XAUUSD 日线 CSV，后来该端点长期失效（本机返 JS 反爬页，CI 返 404），已换成新浪。详见 `docs/信源核验记录.md`。

### 三张图（`charts/`，每次现算，不进版本库）

1. `sentiment_trend.png` — 近 30 日情绪指数折线，带 0 轴基准
2. `event_distribution.png` — 近 7 日事件类型分布（按方向堆叠）
3. `sentiment_vs_gold.png` — 情绪指数 vs 金价双轴图，**这是判断指数有没有用的主要依据**

`charts/*.png` 被 gitignore，所以 Actions 回写那步只 `git add data/`。

---

## 错误处理原则

**任何情况下都必须有输出**，最差降级为纯文本告警。一个每天要送达的东西，静默失败远比推得难看严重。

| 故障 | 处理 |
|---|---|
| 单个源抓取失败 | 各采集器独立 try/except 互不影响，卡片上标注"N 个源失败" |
| 金价取失败 | 不写 `gold_close`，但把源名并进失败源列表显式告警 |
| Dify 调用失败 | 发飞书纯文本降级告警，不静默 |
| LLM 返回非法 JSON | 坏的条目丢弃，不让整体崩盘 |
| 卡片构造失败 | 改发纯文本（否则手机上今天什么都收不到） |
| 中文字体缺失 | `configure_chinese_font()` 主动解析一次，全落空就抛错 |
| 整个流水线的意外异常 | `run()` 外层兜底，转成降级告警 |

---

## 已知局限

清楚局限是使用指标的前提，否则会误信自己造出来的结论：

- **LLM 抽取存在误差。** `direction` 判错时指数会给出错误的多空倾向，而这个错误**看起来和正确结果一模一样**——没有报错，只有一张看起来合理的折线图。准确率验证（抽 50 条人工标注算分类准确率与方向准确率、出混淆矩阵）是设计文档里的独立阶段，尚未完成。
- **指数是相对指标，不是绝对刻度。** `strength` 的 1–5 由模型主观判断而非拟合得出，可用于比较趋势，不可当作绝对数值读。
- **情绪与金价是相关性而非因果。** 金价同时受实际利率、美元指数、避险需求等多重因素驱动。
- **单日事件量只有数条量级，统计功效有限**，不可用于高频推断。一个星期七天里能有几天情绪与金价方向对不上，是完全正常的。
- **信源会失效或改版**，需要持续维护（见 `docs/信源核验记录.md`）。
- 不做实时高频快讯，不做交易信号，不做投资建议。

---

## 定时任务

`.github/workflows/daily.yml`，cron 为 `30 23 * * *`（UTC），即次日 07:30 北京时间。
也支持 `workflow_dispatch` 手动触发。

流程：装 `fonts-noto-cjk` → 装依赖 → **校验中文字体真的解析得到**（否则整个任务失败）→ 跑测试 → 跑流水线（Secrets 注入两个变量）→ 把 `data/` 的变更 commit 回仓库。

需要 `permissions: contents: write` 才能回写。Secrets 在仓库 Settings → Secrets and variables → Actions 里配 `DIFY_API_KEY` 和 `FEISHU_WEBHOOK_URL`。
