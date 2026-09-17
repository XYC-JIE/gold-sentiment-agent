# 每日情报流水线 实施计划（阶段 0–4）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建成一条端到端流水线：每天 07:30 自动抓取 12 个中英文信源，经 Dify LLM 结构化抽取与日报生成，计算金银情绪指数并出图，推送飞书卡片。

**Architecture:** 三层分工。Dify 承担 LLM 编排（结构化抽取 + 文案生成），Python 承担采集／存储／指标计算／出图（Dify 代码节点跑不了 pandas），GitHub Actions 承担定时调度与结果回写（海外运行免代理，且不依赖本机开机）。三层之间的接口是两个 JSON 字符串。

**Tech Stack:** Python 3.10 · requests · feedparser · PyYAML · pandas · matplotlib · pytest + requests-mock · Dify Cloud Workflow API · 飞书自定义机器人 Webhook · GitHub Actions

**Spec:** `docs/superpowers/specs/2026-09-15-daily-intel-design.md`

## Global Constraints

- Python **3.10**（本地与 CI 必须一致，避免本地过、CI 挂）
  - 本机只有 3.10.11 与 3.9，故取 3.10。所有模块均已加 `from __future__ import annotations`，`X | None` 与内建泛型在 3.10 下正常工作
  - **虚拟环境必须用 `D:/金银舆情监控/.venv`**，不要装到全局 Python
- 时间基准一律 **北京时间（Asia/Shanghai）**；所有 `date` 字段格式为 `YYYY-MM-DD`
- 所有 HTTP 请求 **超时 15 秒**，失败重试 **2 次**（指数退避：1s、2s）
- **不使用异步**（`async`/`await`）；单进程顺序执行，12 个源耗时在可接受范围内
- **信源地址只写在 `config/sources.yaml`**，代码中不得硬编码任何 URL
- 面向用户的所有文案为**中文**
- 密钥一律从环境变量读取，**不得写入仓库**；本地用 `.env`（已 gitignore）
- 依赖库清单固定在 `requirements.txt`，不额外引入爬虫框架（Scrapy／Selenium 等）

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `src/models.py` | `RawItem`、`Event` 两个数据类，全流程的公共语言 |
| `src/config.py` | 加载 `sources.yaml`、读取环境变量、定义路径常量 |
| `src/collectors/base.py` | `Collector` 抽象基类 + 带重试的 HTTP 会话 |
| `src/collectors/rss.py` | 通用 RSS/Atom 采集器，覆盖 6 个 AI 源 + 美联储 + CNBC |
| `src/collectors/jin10.py` | 金十数据快讯（JSON API） |
| `src/collectors/wallstreetcn.py` | 华尔街见闻快讯（JSON API） |
| `src/collectors/gold_price.py` | stooq XAUUSD 日线（CSV） |
| `src/collectors/__init__.py` | 按 `sources.yaml` 构建采集器列表 |
| `src/dedupe.py` | 去重、按时间窗筛选、按源配额截断 |
| `src/dify_client.py` | 调用 Dify Workflow API，解析两个 JSON 字符串输出 |
| `src/analysis.py` | 情绪指数计算、`daily_index` 行构建（纯函数） |
| `src/storage.py` | `events.csv` / `daily_index.csv` 的读写与追加 |
| `src/charts.py` | 三张图的生成 |
| `src/notifier.py` | 飞书卡片构造与发送，含降级路径 |
| `src/main.py` | 串联全流程，`--dry-run` / `--offline` 开关 |
| `config/sources.yaml` | 全部信源配置 |
| `tests/` | pytest 用例 + `fixtures/` 固定样本 |
| `samples/dify_response.json` | 离线模式用的 Dify 返回值样本 |
| `.github/workflows/daily.yml` | 定时任务 |

**边界原则：** `analysis.py` 只做纯计算、不碰网络和文件；`storage.py` 只管 CSV 读写、不含业务判断；`notifier.py` 只负责把已算好的数据变成卡片并发送。这样每个文件都能单独测。

---

## Task 1: 项目脚手架与测试基线

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `.gitignore`, `src/__init__.py`, `src/config.py`
- Create: `config/sources.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces: `src.config.load_sources() -> list[dict]`、`src.config.ROOT_DIR: Path`、`src.config.DATA_DIR`、`src.config.CHARTS_DIR`、`src.config.SAMPLES_DIR`

- [ ] **Step 1: 创建 `requirements.txt`**

```
requests>=2.31
feedparser>=6.0.10
PyYAML>=6.0
pandas>=2.1
matplotlib>=3.8
python-dateutil>=2.8
pytest>=8.0
requests-mock>=1.11
```

- [ ] **Step 2: 创建 `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q
pythonpath = .
```

> `pythonpath = .` 是必需的：`python -m pytest` 会把当前目录放进 `sys.path`，但 `pytest` 控制台脚本不会，`from src.xxx import` 会直接 ModuleNotFoundError。加上这行让两个入口等价。

- [ ] **Step 3: 创建 `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.env
.pytest_cache/
charts/*.png
```

> 注意：`data/` **不能**忽略——数据积累是本项目的产物，必须进版本库。`charts/*.png` 反之要忽略，由 CI 每次重新生成。

- [ ] **Step 4: 创建 `config/sources.yaml`（第一版，RSS 源）**

```yaml
# 信源配置。新增/替换源只需改这里，不必动代码。
# category: ai | finance | market

sources:
  - name: OpenAI News
    category: ai
    type: rss
    url: https://openai.com/news/rss.xml

  - name: Google DeepMind Blog
    category: ai
    type: rss
    url: https://deepmind.google/blog/rss.xml

  - name: Hacker News
    category: ai
    type: rss
    url: https://hnrss.org/frontpage

  - name: arXiv cs.AI
    category: ai
    type: rss
    url: http://export.arxiv.org/rss/cs.AI

  - name: 机器之心
    category: ai
    type: rss
    url: https://www.jiqizhixin.com/rss

  - name: 量子位
    category: ai
    type: rss
    url: https://www.qbitai.com/feed

  - name: 美联储新闻稿
    category: finance
    type: rss
    url: https://www.federalreserve.gov/feeds/press_all.xml

  - name: CNBC Markets
    category: finance
    type: rss
    url: https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258

  - name: 金十数据快讯
    category: finance
    type: jin10
    url: https://flash-api.jin10.com/get_flash_list

  - name: 华尔街见闻
    category: finance
    type: wallstreetcn
    url: https://api-one.wallstcn.com/apiv1/content/lives

  - name: 现货黄金日线
    category: market
    type: gold_price
    url: https://stooq.com/q/d/l/?s=xauusd&i=d
```

> **Anthropic News 与 Hugging Face Daily Papers 暂缺**：两者无稳定公开 RSS。先按上表 11 个源跑通，Task 3 结束时用 curl 验证这两家是否可补；补不上就用 `其他` 类源替代，不影响流水线。

- [ ] **Step 5: 创建 `src/__init__.py`（空文件）**

```python
```

- [ ] **Step 6: 创建 `src/config.py`**

```python
"""配置加载：路径常量、信源配置、环境变量。"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
CHARTS_DIR = ROOT_DIR / "charts"
SAMPLES_DIR = ROOT_DIR / "samples"
CONFIG_PATH = ROOT_DIR / "config" / "sources.yaml"


def load_sources() -> list[dict]:
    """读取 sources.yaml，返回信源配置列表。"""
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    sources = data.get("sources") or []
    if not sources:
        raise ValueError(f"未在 {CONFIG_PATH} 中找到任何信源配置")
    return sources


def get_secret(name: str) -> str:
    """读取密钥；缺失时抛出明确错误，避免带着 None 继续跑。"""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"缺少环境变量 {name}，请检查 .env 或 GitHub Secrets")
    return value
```

- [ ] **Step 7: 写失败测试 `tests/test_config.py`**

```python
from src.config import load_sources


def test_load_sources_returns_list():
    sources = load_sources()
    assert isinstance(sources, list)
    # 初版配了 11 个源，但 Task 3 的信源核验会剔除失效的。
    # 8 是底线：再少下去覆盖度就不够了。
    assert len(sources) >= 8


def test_every_source_has_required_keys():
    for s in load_sources():
        assert s["name"]
        assert s["type"] in {"rss", "jin10", "wallstreetcn", "gold_price"}
        assert s["category"] in {"ai", "finance", "market"}
        assert s["url"].startswith("http")
```

- [ ] **Step 8: 运行测试**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS（2 个用例）

- [ ] **Step 9: 提交**

```bash
git add requirements.txt pytest.ini .gitignore src/ config/ tests/
git commit -m "chore: 项目脚手架与信源配置"
```

---

## Task 2: 数据模型与采集器基类

**Files:**
- Create: `src/models.py`, `src/collectors/__init__.py`, `src/collectors/base.py`
- Test: `tests/test_collectors_base.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `RawItem(title: str, url: str, source: str, category: str, published_at: str, content: str)`
  - `Collector(name: str, category: str, url: str)` 抽象基类，抽象方法 `fetch(self) -> list[RawItem]`
  - `Collector.get(self, params=None, headers=None) -> requests.Response`（带 15s 超时与 2 次重试）

- [ ] **Step 1: 写失败测试 `tests/test_collectors_base.py`**

```python
import pytest
import requests_mock as rm_module

from src.collectors.base import Collector
from src.models import RawItem


class _DummyCollector(Collector):
    def fetch(self):
        resp = self.get()
        return [RawItem(
            title=resp.text,
            url="https://example.com/a",
            source=self.name,
            category=self.category,
            published_at="2026-09-15T00:00:00+08:00",
            content="",
        )]


def test_collector_stores_name_and_category():
    c = _DummyCollector(name="测试源", category="ai", url="https://example.com/feed")
    assert c.name == "测试源"
    assert c.category == "ai"


def test_fetch_returns_raw_items(requests_mock):
    requests_mock.get("https://example.com/feed", text="hello")
    c = _DummyCollector(name="测试源", category="ai", url="https://example.com/feed")
    items = c.fetch()
    assert len(items) == 1
    assert items[0].title == "hello"
    assert items[0].source == "测试源"


def test_get_retries_then_succeeds(requests_mock):
    requests_mock.get(
        "https://example.com/feed",
        [
            {"exc": ConnectionError},
            {"text": "second try ok"},
        ],
    )
    c = _DummyCollector(name="测试源", category="ai", url="https://example.com/feed")
    assert c.get().text == "second try ok"


def test_get_raises_after_exhausting_retries(requests_mock):
    requests_mock.get("https://example.com/feed", exc=ConnectionError)
    c = _DummyCollector(name="测试源", category="ai", url="https://example.com/feed")
    with pytest.raises(ConnectionError):
        c.get()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_collectors_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.collectors'`

- [ ] **Step 3: 实现 `src/models.py`**

```python
"""全流程公共数据模型。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawItem:
    """采集层的原始条目，尚未经过 LLM 处理。"""

    title: str
    url: str
    source: str
    category: str          # ai | finance | market
    published_at: str      # ISO8601，带时区
    content: str = ""


@dataclass(frozen=True)
class Event:
    """LLM 结构化抽取后的事件。"""

    date: str              # YYYY-MM-DD
    event_type: str
    direction: str         # 利多金银 | 利空金银 | 中性
    strength: int          # 1-5
    relevant: bool         # 是否与金银走势有关
    summary: str
    source: str
    url: str
    published_at: str
```

- [ ] **Step 4: 实现 `src/collectors/__init__.py`**

```python
```

- [ ] **Step 5: 实现 `src/collectors/base.py`**

```python
"""采集器基类：统一 HTTP 行为（超时 + 重试）。"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

import requests

from src.models import RawItem

TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3          # 首次 + 2 次重试
BACKOFF_SECONDS = (1, 2)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


class Collector(ABC):
    """所有采集器的父类。

    子类只需实现 fetch()，HTTP 细节由 get() 统一处理。
    """

    def __init__(self, name: str, category: str, url: str) -> None:
        self.name = name
        self.category = category
        self.url = url

    def get(self, params: dict | None = None, headers: dict | None = None) -> requests.Response:
        """发起 GET 请求，失败自动重试。耗尽重试后抛出最后一次异常。"""
        merged = {**DEFAULT_HEADERS, **(headers or {})}
        last_error: Exception | None = None

        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = requests.get(
                    self.url, params=params, headers=merged, timeout=TIMEOUT_SECONDS
                )
                resp.raise_for_status()
                return resp
            except Exception as exc:  # noqa: BLE001 - 需捕获 requests 各异常族
                last_error = exc
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(BACKOFF_SECONDS[attempt])

        assert last_error is not None
        raise last_error

    @abstractmethod
    def fetch(self) -> list[RawItem]:
        """抓取并解析该源，返回原始条目列表。"""
        raise NotImplementedError
```

- [ ] **Step 6: 运行测试确认通过**

Run: `python -m pytest tests/test_collectors_base.py -v`
Expected: PASS（4 个用例）

- [ ] **Step 7: 提交**

```bash
git add src/models.py src/collectors/ tests/test_collectors_base.py
git commit -m "feat: 数据模型与采集器基类（含重试）"
```

---

## Task 3: RSS 采集器（覆盖 8 个源）与信源可用性核验

**Files:**
- Create: `src/collectors/rss.py`, `tests/fixtures/rss_sample.xml`
- Test: `tests/test_collectors_rss.py`
- Modify: `config/sources.yaml`（按核验结果增删源）

**Interfaces:**
- Consumes: `Collector`、`RawItem`
- Produces: `RssCollector(name, category, url)`，其 `fetch()` 返回 `list[RawItem]`

- [ ] **Step 1: 探测信源可达性（人工步骤，不可跳过，但务必按下面的判读规则）**

> ⚠️ **本机在国内网络。被墙的源和真正失效的源，在 curl 看来一模一样——都是连不上。**
> OpenAI、DeepMind、Hacker News 恰好是价值最高的几个 AI 源，误删它们等于砍掉项目最有用的部分。
> 而流水线实际跑在 GitHub Actions（海外）上，那里的可达性才算数。所以本步**只记录、不删源**。

**判读规则（照此分类，不要自行发挥）：**

| curl 表现 | 含义 | 动作 |
|---|---|---|
| HTTP 403 / 404 / 410 等**具体错误码** | 源确实失效或被拒绝 | 替换为同类替代源 |
| HTTP 200 但体积 < 1KB | 返回了空 feed | 替换为同类替代源 |
| `http=000` / 超时 / `Connection reset` | **疑似被墙，不代表源失效** | **保留，结论记"待 CI 验证"** |

```bash
for u in \
  "https://openai.com/news/rss.xml" \
  "https://deepmind.google/blog/rss.xml" \
  "https://hnrss.org/frontpage" \
  "http://export.arxiv.org/rss/cs.AI" \
  "https://www.jiqizhixin.com/rss" \
  "https://www.qbitai.com/feed" \
  "https://www.federalreserve.gov/feeds/press_all.xml" \
  "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258" ; do
  printf '=== %s\n' "$u"
  curl -s -o /dev/null -m 15 \
    -w 'http=%{http_code} size=%{size_download}\n' "$u" \
    || echo "  curl 退出码 $? —— 连接失败（疑似被墙，保留）"
done
```

顺带探测这两家能不能补进 `sources.yaml`（结果同样只记录）：

```bash
curl -s -m 15 "https://www.anthropic.com/news" | grep -c "<title" || echo "Anthropic 连接失败（疑似被墙）"
curl -s -m 15 "https://huggingface.co/api/daily_papers" | head -c 300 || echo "Hugging Face 连接失败（疑似被墙）"
```

**默认动作是「什么都不删」。** 只有收到具体 4xx/5xx 错误码时才替换该源；替换后总数**不得跌破 8 个**（`tests/test_config.py` 与 `tests/test_collectors_registry.py` 的下限）。若会跌破，停下来告知用户一起商量，不要硬删。

把结果记进新建的 `docs/信源核验记录.md`（记日期是为了日后能判断某源从哪天起失效）：

```markdown
# 信源核验记录

## 2026-09-15（本机探测，国内网络）

| 信源 | 本机结果 | 结论 |
|---|---|---|
| OpenAI News | 连接失败 | 待 CI 验证 |
| 量子位 | 403 | 已替换为 XXX |

## 待 CI 验证的源

以下源在本机不可达，需在 GitHub Actions 首次运行后确认（见 Task 14 Step 7）：
- OpenAI News
- ...

## 替代源调研

- Anthropic News：结果
- Hugging Face Daily Papers：结果
```

- [ ] **Step 2: 写失败测试 `tests/fixtures/rss_sample.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>OpenAI News</title>
    <item>
      <title>Introducing GPT-5.2</title>
      <link>https://openai.com/index/gpt-5-2</link>
      <description>We are releasing GPT-5.2, our most capable model yet.</description>
      <pubDate>Mon, 15 Sep 2026 09:00:00 GMT</pubDate>
    </item>
    <item>
      <title>New safety research</title>
      <link>https://openai.com/index/safety-research</link>
      <description>An update on our safety work.</description>
      <pubDate>Sun, 14 Sep 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
```

- [ ] **Step 3: 写失败测试 `tests/test_collectors_rss.py`**

```python
from pathlib import Path

from src.collectors.rss import RssCollector

FIXTURE = Path(__file__).parent / "fixtures" / "rss_sample.xml"


def test_fetch_parses_rss_items(requests_mock):
    requests_mock.get(
        "https://openai.com/news/rss.xml",
        text=FIXTURE.read_text(encoding="utf-8"),
    )
    c = RssCollector(
        name="OpenAI News", category="ai", url="https://openai.com/news/rss.xml"
    )
    items = c.fetch()

    assert len(items) == 2
    assert items[0].title == "Introducing GPT-5.2"
    assert items[0].url == "https://openai.com/index/gpt-5-2"
    assert items[0].source == "OpenAI News"
    assert items[0].category == "ai"


def test_published_at_is_normalized_to_beijing(requests_mock):
    requests_mock.get(
        "https://openai.com/news/rss.xml",
        text=FIXTURE.read_text(encoding="utf-8"),
    )
    c = RssCollector(
        name="OpenAI News", category="ai", url="https://openai.com/news/rss.xml"
    )
    item = c.fetch()[0]
    # 09:00 GMT == 17:00 北京时间
    assert item.published_at.startswith("2026-09-15T17:00:00+08:00")


def test_html_in_description_is_stripped(requests_mock):
    xml = FIXTURE.read_text(encoding="utf-8").replace(
        "We are releasing GPT-5.2, our most capable model yet.",
        "&lt;p&gt;We are releasing &lt;b&gt;GPT-5.2&lt;/b&gt;.&lt;/p&gt;",
    )
    requests_mock.get("https://openai.com/news/rss.xml", text=xml)
    c = RssCollector(
        name="OpenAI News", category="ai", url="https://openai.com/news/rss.xml"
    )
    assert "<" not in c.fetch()[0].content
    assert "GPT-5.2" in c.fetch()[0].content
```

- [ ] **Step 4: 运行测试确认失败**

Run: `python -m pytest tests/test_collectors_rss.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.collectors.rss'`

- [ ] **Step 5: 实现 `src/collectors/rss.py`**

```python
"""通用 RSS/Atom 采集器。"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

import feedparser
from dateutil import parser as date_parser

from src.collectors.base import Collector
from src.models import RawItem

BEIJING = timezone(timedelta(hours=8))
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


def _to_beijing_iso(entry) -> str:
    """把 feed 里的时间规范成北京时间 ISO8601；缺失时用当前时间兜底。"""
    raw = entry.get("published") or entry.get("updated")
    if raw:
        dt = date_parser.parse(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BEIJING).isoformat()
    return datetime.now(BEIJING).isoformat()


class RssCollector(Collector):
    def fetch(self) -> list[RawItem]:
        resp = self.get()
        feed = feedparser.parse(resp.content)

        items: list[RawItem] = []
        for entry in feed.entries:
            link = entry.get("link", "")
            if not link:
                continue
            items.append(
                RawItem(
                    title=_strip_html(entry.get("title", "")),
                    url=link,
                    source=self.name,
                    category=self.category,
                    published_at=_to_beijing_iso(entry),
                    content=_strip_html(
                        entry.get("summary") or entry.get("description") or ""
                    )[:2000],
                )
            )
        return items
```

> 用 `resp.content`（bytes）而非 `resp.text`：`feedparser` 会自行嗅探 XML 声明的编码，中文源用 `resp.text` 可能被 requests 猜错编码而乱码。

- [ ] **Step 6: 运行测试确认通过**

Run: `python -m pytest tests/test_collectors_rss.py -v`
Expected: PASS（3 个用例）

- [ ] **Step 7: 提交**

```bash
git add src/collectors/rss.py tests/fixtures/rss_sample.xml tests/test_collectors_rss.py docs/信源核验记录.md config/sources.yaml
git commit -m "feat: RSS 采集器，并完成信源可用性核验"
```

---

## Task 4: JSON API 采集器（金十、华尔街见闻）

**Files:**
- Create: `src/collectors/jin10.py`, `src/collectors/wallstreetcn.py`
- Create: `tests/fixtures/jin10_flash.json`, `tests/fixtures/wallstreetcn_lives.json`
- Test: `tests/test_collectors_json_api.py`

**Interfaces:**
- Consumes: `Collector`、`RawItem`
- Produces: `Jin10Collector(name, category, url)`、`WallstreetcnCollector(name, category, url)`，均实现 `fetch() -> list[RawItem]`

- [ ] **Step 1: 核验两个 API 的真实返回结构（人工步骤，不可跳过）**

```bash
curl -s -m 15 -H "User-Agent: Mozilla/5.0" -H "x-app-id: bVBF4FyRTn5NJF5n" -H "x-version: 1.0.0" \
  "https://flash-api.jin10.com/get_flash_list?channel=-8200&vip=1" | head -c 1500

curl -s -m 15 -H "User-Agent: Mozilla/5.0" \
  "https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=20" | head -c 1500
```

**把真实返回的一份样本存成 fixture**，并核对下面这些字段路径是否与代码一致：

| 源 | 字段路径 | 代码中的假设 |
|---|---|---|
| 金十 | `data[].id` | 唯一 ID |
| 金十 | `data[].time` | `YYYY-MM-DD HH:MM:SS`（北京时间） |
| 金十 | `data[].data.content` | 正文文本 |
| 金十 | `data[].important` | 1 表示重要 |
| 华尔街见闻 | `data.items[].id` | 唯一 ID |
| 华尔街见闻 | `data.items[].content_text` | 正文文本 |
| 华尔街见闻 | `data.items[].display_time` | Unix 时间戳（秒） |

**若实际结构与上表不符**：以真实样本为准修改下方解析代码中的取字段部分，其余逻辑不动。字段名差异不影响架构。

- [ ] **Step 2: 写 fixture `tests/fixtures/jin10_flash.json`**

```json
{
  "status": 200,
  "data": [
    {
      "id": "20260915100001",
      "time": "2026-09-15 10:00:01",
      "important": 1,
      "data": {
        "content": "美联储官员沃勒表示，若通胀数据继续改善，年内可能进一步降息。"
      }
    },
    {
      "id": "20260915100002",
      "time": "2026-09-15 10:05:00",
      "important": 0,
      "data": {
        "content": "现货黄金短线走高 5 美元，现报 2480 美元/盎司。"
      }
    }
  ]
}
```

- [ ] **Step 3: 写 fixture `tests/fixtures/wallstreetcn_lives.json`**

```json
{
  "code": 20000,
  "data": {
    "items": [
      {
        "id": 3188001,
        "content_text": "美国 8 月 CPI 同比升 2.4%，低于预期的 2.6%。",
        "display_time": 1789437200
      },
      {
        "id": 3188002,
        "content_text": "世界黄金协会：8 月全球黄金 ETF 净流入 21 亿美元。",
        "display_time": 1789438400
      }
    ]
  }
}
```

- [ ] **Step 4: 写失败测试 `tests/test_collectors_json_api.py`**

```python
from pathlib import Path

from src.collectors.jin10 import Jin10Collector
from src.collectors.wallstreetcn import WallstreetcnCollector

FIXTURES = Path(__file__).parent / "fixtures"


def test_jin10_parses_flash_items(requests_mock):
    requests_mock.get(
        "https://flash-api.jin10.com/get_flash_list",
        text=(FIXTURES / "jin10_flash.json").read_text(encoding="utf-8"),
    )
    c = Jin10Collector(
        name="金十数据快讯", category="finance",
        url="https://flash-api.jin10.com/get_flash_list",
    )
    items = c.fetch()

    assert len(items) == 2
    assert "沃勒" in items[0].content
    assert items[0].source == "金十数据快讯"
    assert items[0].url == "https://www.jin10.com/flash/20260915100001"
    assert items[0].published_at.startswith("2026-09-15T10:00:01+08:00")


def test_jin10_skips_entries_without_content(requests_mock):
    payload = '{"status": 200, "data": [{"id": "1", "time": "2026-09-15 10:00:00", "data": {}}]}'
    requests_mock.get("https://flash-api.jin10.com/get_flash_list", text=payload)
    c = Jin10Collector(
        name="金十数据快讯", category="finance",
        url="https://flash-api.jin10.com/get_flash_list",
    )
    assert c.fetch() == []


def test_wallstreetcn_parses_lives(requests_mock):
    requests_mock.get(
        "https://api-one.wallstcn.com/apiv1/content/lives",
        text=(FIXTURES / "wallstreetcn_lives.json").read_text(encoding="utf-8"),
    )
    c = WallstreetcnCollector(
        name="华尔街见闻", category="finance",
        url="https://api-one.wallstcn.com/apiv1/content/lives",
    )
    items = c.fetch()

    assert len(items) == 2
    assert "CPI" in items[0].content
    assert items[0].url == "https://wallstreetcn.com/livenews/3188001"
    # 1789437200 == 2026-09-15 01:53:20 UTC == 09:53:20 北京时间
    assert items[0].published_at.startswith("2026-09-15T09:53:20+08:00")
```

- [ ] **Step 5: 运行测试确认失败**

Run: `python -m pytest tests/test_collectors_json_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.collectors.jin10'`

- [ ] **Step 6: 实现 `src/collectors/jin10.py`**

```python
"""金十数据快讯采集器。"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from dateutil import parser as date_parser

from src.collectors.base import Collector
from src.models import RawItem

BEIJING = timezone(timedelta(hours=8))

# 金十快讯接口要求这两个头，缺失会被拒绝
API_HEADERS = {"x-app-id": "bVBF4FyRTn5NJF5n", "x-version": "1.0.0"}
API_PARAMS = {"channel": "-8200", "vip": "1"}


class Jin10Collector(Collector):
    def fetch(self) -> list[RawItem]:
        resp = self.get(params=API_PARAMS, headers=API_HEADERS)
        payload = resp.json()

        items: list[RawItem] = []
        for row in payload.get("data") or []:
            content = (row.get("data") or {}).get("content") or ""
            if not content.strip():
                continue

            flash_id = str(row.get("id") or "")
            raw_time = row.get("time")
            if raw_time:
                dt = date_parser.parse(raw_time).replace(tzinfo=BEIJING)
            else:
                dt = datetime.now(BEIJING)

            items.append(
                RawItem(
                    title=content.strip()[:60],
                    url=f"https://www.jin10.com/flash/{flash_id}",
                    source=self.name,
                    category=self.category,
                    published_at=dt.isoformat(),
                    content=content.strip(),
                )
            )
        return items
```

- [ ] **Step 7: 实现 `src/collectors/wallstreetcn.py`**

```python
"""华尔街见闻快讯采集器。"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from src.collectors.base import Collector
from src.models import RawItem

BEIJING = timezone(timedelta(hours=8))
API_PARAMS = {"channel": "global-channel", "limit": "50"}


class WallstreetcnCollector(Collector):
    def fetch(self) -> list[RawItem]:
        resp = self.get(params=API_PARAMS)
        payload = resp.json()

        items: list[RawItem] = []
        for row in ((payload.get("data") or {}).get("items") or []):
            content = (row.get("content_text") or "").strip()
            if not content:
                continue

            live_id = row.get("id")
            ts = row.get("display_time")
            dt = (
                datetime.fromtimestamp(int(ts), tz=BEIJING)
                if ts
                else datetime.now(BEIJING)
            )

            items.append(
                RawItem(
                    title=content[:60],
                    url=f"https://wallstreetcn.com/livenews/{live_id}",
                    source=self.name,
                    category=self.category,
                    published_at=dt.isoformat(),
                    content=content,
                )
            )
        return items
```

- [ ] **Step 8: 运行测试确认通过**

Run: `python -m pytest tests/test_collectors_json_api.py -v`
Expected: PASS（3 个用例）

- [ ] **Step 9: 提交**

```bash
git add src/collectors/jin10.py src/collectors/wallstreetcn.py tests/fixtures/ tests/test_collectors_json_api.py
git commit -m "feat: 金十与华尔街见闻快讯采集器"
```

---

## Task 5: 金价采集器

**Files:**
- Create: `src/collectors/gold_price.py`
- Create: `tests/fixtures/stooq_xauusd.csv`
- Test: `tests/test_collectors_gold.py`

**Interfaces:**
- Consumes: `Collector`
- Produces: `GoldPriceCollector(name, category, url)`，实现 `fetch_latest() -> tuple[str, float]`，返回 `(YYYY-MM-DD, 收盘价)`

> 该类**不实现** `fetch()`（不产出 `RawItem`），因为它不是文本信源。为避免被基类的抽象方法卡住，让它继承 `Collector` 并覆盖 `fetch()` 抛 `NotImplementedError`，由调用方改用 `fetch_latest()`。

- [ ] **Step 1: 写 fixture `tests/fixtures/stooq_xauusd.csv`**

```csv
Date,Open,High,Low,Close,Volume
2026-09-11,2470.5,2490.2,2465.1,2485.3,0
2026-09-12,2485.3,2495.0,2478.0,2490.1,0
2026-09-15,2490.1,2502.4,2488.0,2498.7,0
```

- [ ] **Step 2: 写失败测试 `tests/test_collectors_gold.py`**

```python
from pathlib import Path

import pytest

from src.collectors.gold_price import GoldPriceCollector

FIXTURE = Path(__file__).parent / "fixtures" / "stooq_xauusd.csv"
URL = "https://stooq.com/q/d/l/?s=xauusd&i=d"


def test_fetch_latest_returns_last_row(requests_mock):
    requests_mock.get(URL, text=FIXTURE.read_text(encoding="utf-8"))
    c = GoldPriceCollector(name="现货黄金日线", category="market", url=URL)
    date, close = c.fetch_latest()
    assert date == "2026-09-15"
    assert close == 2498.7


def test_fetch_latest_skips_rows_without_close(requests_mock):
    csv = "Date,Open,High,Low,Close,Volume\n2026-09-15,2490.1,2502.4,2488.0,,0\n"
    requests_mock.get(URL, text=csv)
    c = GoldPriceCollector(name="现货黄金日线", category="market", url=URL)
    with pytest.raises(ValueError, match="未找到有效收盘价"):
        c.fetch_latest()
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_collectors_gold.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.collectors.gold_price'`

- [ ] **Step 4: 实现 `src/collectors/gold_price.py`**

```python
"""现货黄金日线采集器（stooq 免费 CSV）。"""
from __future__ import annotations

import csv
import io

from src.collectors.base import Collector
from src.models import RawItem


class GoldPriceCollector(Collector):
    def fetch(self) -> list[RawItem]:
        raise NotImplementedError("金价是数值数据，请调用 fetch_latest()")

    def fetch_latest(self) -> tuple[str, float]:
        """返回最新一个交易日的 (日期, 收盘价)。"""
        resp = self.get()
        reader = csv.DictReader(io.StringIO(resp.text))

        latest: tuple[str, float] | None = None
        for row in reader:
            raw_close = (row.get("Close") or "").strip()
            raw_date = (row.get("Date") or "").strip()
            if not raw_close or not raw_date:
                continue
            try:
                latest = (raw_date, float(raw_close))
            except ValueError:
                continue

        if latest is None:
            raise ValueError("stooq 返回中未找到有效收盘价")
        return latest
```

> 取"最后一行有效数据"而非"今天"，是因为周末与节假日没有行情；这样即使周一早上跑，也能拿到上周五的收盘价。

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_collectors_gold.py -v`
Expected: PASS（2 个用例）

- [ ] **Step 6: 提交**

```bash
git add src/collectors/gold_price.py tests/fixtures/stooq_xauusd.csv tests/test_collectors_gold.py
git commit -m "feat: 现货黄金日线采集器"
```

---

## Task 6: 采集编排与去重

**Files:**
- Modify: `src/collectors/__init__.py`
- Create: `src/dedupe.py`
- Test: `tests/test_dedupe.py`, `tests/test_collectors_registry.py`

**Interfaces:**
- Consumes: 四个采集器类、`load_sources()`
- Produces:
  - `build_collectors() -> list[Collector]`
  - `collect_all(collectors) -> tuple[list[RawItem], list[str]]` — 返回条目与失败源名列表
  - `dedupe(items: list[RawItem]) -> list[RawItem]`
  - `within_hours(items: list[RawItem], hours: int, now: str) -> list[RawItem]`
    （`now` 是必填的 ISO8601 字符串，由调用方传入而不是在函数内取当前时间——这样测试可以冻结时间）

- [ ] **Step 1: 写失败测试 `tests/test_dedupe.py`**

```python
from src.dedupe import dedupe, within_hours
from src.models import RawItem


def _item(title, url, source="源A", published_at="2026-09-15T08:00:00+08:00"):
    return RawItem(
        title=title, url=url, source=source, category="ai",
        published_at=published_at, content="",
    )


def test_dedupe_removes_same_url():
    items = [_item("标题甲", "https://a.com/1"), _item("标题甲", "https://a.com/1")]
    assert len(dedupe(items)) == 1


def test_dedupe_is_case_and_whitespace_insensitive_on_title():
    items = [
        _item("Gold Rises", "https://a.com/1"),
        _item("  gold rises  ", "https://a.com/2"),
    ]
    assert len(dedupe(items)) == 1


def test_dedupe_keeps_distinct_items():
    items = [_item("甲", "https://a.com/1"), _item("乙", "https://a.com/2")]
    assert len(dedupe(items)) == 2


def test_dedupe_preserves_first_occurrence_order():
    items = [_item("甲", "https://a.com/1"), _item("乙", "https://a.com/2"),
             _item("甲", "https://a.com/1")]
    assert [i.title for i in dedupe(items)] == ["甲", "乙"]


def test_within_hours_filters_old_items():
    now = "2026-09-15T08:00:00+08:00"
    items = [
        _item("新", "https://a.com/1", published_at="2026-09-15T07:30:00+08:00"),
        _item("旧", "https://a.com/2", published_at="2026-09-10T07:30:00+08:00"),
    ]
    kept = within_hours(items, hours=24, now=now)
    assert [i.title for i in kept] == ["新"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_dedupe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.dedupe'`

- [ ] **Step 3: 实现 `src/dedupe.py`**

```python
"""去重与时间窗筛选。"""
from __future__ import annotations

from datetime import datetime, timedelta

from dateutil import parser as date_parser

from src.models import RawItem


def dedupe(items: list[RawItem]) -> list[RawItem]:
    """按 URL 去重；标题归一化后相同也视为重复。保留首次出现的顺序。"""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    result: list[RawItem] = []

    for item in items:
        url_key = item.url.strip().lower()
        title_key = " ".join(item.title.split()).lower()

        if url_key in seen_urls or (title_key and title_key in seen_titles):
            continue

        seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        result.append(item)

    return result


def within_hours(items: list[RawItem], hours: int, now: str) -> list[RawItem]:
    """只保留 now 之前 hours 小时内发布的条目。

    解析失败的时间戳一律保留——宁可多看一条，也不要因为格式问题丢新闻。
    """
    now_dt = date_parser.parse(now)
    cutoff = now_dt - timedelta(hours=hours)

    kept: list[RawItem] = []
    for item in items:
        try:
            published = date_parser.parse(item.published_at)
        except (ValueError, TypeError):
            kept.append(item)
            continue
        if published.tzinfo is None:
            kept.append(item)
            continue
        if published >= cutoff:
            kept.append(item)
    return kept
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_dedupe.py -v`
Expected: PASS（5 个用例）

- [ ] **Step 5: 写失败测试 `tests/test_collectors_registry.py`**

```python
from src.collectors import build_collectors, collect_all


def test_build_collectors_covers_every_source():
    collectors = build_collectors()
    # 底线与 test_config.py 保持一致（见那里的注释）
    assert len(collectors) >= 8


def test_collect_all_survives_one_failing_source(requests_mock, monkeypatch):
    """单个源抛异常时，其余源的结果仍应返回，失败源名进入第二个返回值。"""
    from src.collectors import base as base_module
    from src.collectors.rss import RssCollector

    # 真实重试会 sleep 1+2 秒，测试里压掉
    monkeypatch.setattr(base_module, "MAX_ATTEMPTS", 1)
    monkeypatch.setattr(base_module, "BACKOFF_SECONDS", (0,))

    requests_mock.get("https://ok.com/feed", text=(
        '<?xml version="1.0"?><rss version="2.0"><channel><item>'
        "<title>好源</title><link>https://ok.com/1</link>"
        "</item></channel></rss>"
    ))
    requests_mock.get("https://bad.com/feed", exc=ConnectionError)

    collectors = [
        RssCollector(name="好源", category="ai", url="https://ok.com/feed"),
        RssCollector(name="坏源", category="ai", url="https://bad.com/feed"),
    ]
    items, failed = collect_all(collectors)

    assert failed == ["坏源"]
    assert any(i.title == "好源" for i in items)
```

- [ ] **Step 6: 运行测试确认失败**

Run: `python -m pytest tests/test_collectors_registry.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_collectors'`

- [ ] **Step 7: 实现 `src/collectors/__init__.py`**

```python
"""采集器注册表：按 sources.yaml 构建采集器，并容错地批量采集。"""
from __future__ import annotations

from src.collectors.base import Collector
from src.collectors.gold_price import GoldPriceCollector
from src.collectors.jin10 import Jin10Collector
from src.collectors.rss import RssCollector
from src.collectors.wallstreetcn import WallstreetcnCollector
from src.config import load_sources
from src.models import RawItem

_BUILDERS = {
    "rss": RssCollector,
    "jin10": Jin10Collector,
    "wallstreetcn": WallstreetcnCollector,
    "gold_price": GoldPriceCollector,
}

__all__ = ["build_collectors", "collect_all", "Collector"]


def build_collectors() -> list[Collector]:
    collectors: list[Collector] = []
    for cfg in load_sources():
        builder = _BUILDERS.get(cfg["type"])
        if builder is None:
            raise ValueError(f"未知的信源类型：{cfg['type']}")
        collectors.append(
            builder(name=cfg["name"], category=cfg["category"], url=cfg["url"])
        )
    return collectors


def collect_all(collectors: list[Collector]) -> tuple[list[RawItem], list[str]]:
    """逐个采集。任一源失败只记录、不中断其余源。"""
    items: list[RawItem] = []
    failed: list[str] = []

    for collector in collectors:
        if collector.category == "market":
            continue  # 金价走 fetch_latest()，不产出 RawItem
        try:
            items.extend(collector.fetch())
        except Exception:  # noqa: BLE001 - 单个源的问题不应影响整体
            failed.append(collector.name)

    return items, failed
```

- [ ] **Step 8: 运行全部测试**

Run: `python -m pytest -v`
Expected: 全绿

- [ ] **Step 9: 提交**

```bash
git add src/collectors/__init__.py src/dedupe.py tests/test_dedupe.py tests/test_collectors_registry.py
git commit -m "feat: 采集编排与去重"
```

---

## Task 7: 在 Dify 上搭建工作流

**Files:**
- Create: `dify/daily-intel-workflow.yml`（从 Dify 导出）
- Create: `docs/dify工作流说明.md`

**Interfaces:**
- Consumes: `raw_items` 的 JSON 字符串
- Produces: 两个 **string** 类型输出变量 `events_json`、`digest_json`；以及 Workflow API Key（存为 `DIFY_API_KEY`）

> 本任务无自动化测试——它是在 Dify 网页上的人工操作。可验证的产出是：用 curl 调通并拿到符合结构的 JSON。

- [ ] **Step 1: 注册 Dify 并创建 Chatflow/Workflow**

访问 `https://cloud.dify.ai`，注册账号。创建应用时选 **Workflow**（不是 Chatflow）。命名为 `daily-intel`。

- [ ] **Step 2: 配置模型供应商**

在「设置 → 模型供应商」中选 DeepSeek，填入 API Key（从 `platform.deepseek.com` 获取）。选 `deepseek-chat` 作为对话模型。

- [ ] **Step 3: 编排开始节点**

添加两个输入变量：

| 变量名 | 类型 | 必填 |
|---|---|---|
| `raw_items` | String | 是 |
| `date` | String | 是 |

- [ ] **Step 4: 添加代码节点「预筛」**

输入变量：`raw_items`（String）。输出变量：`items`（String）。

```python
import json

def main(raw_items: str) -> dict:
    try:
        items = json.loads(raw_items)
    except Exception:
        return {"items": "[]"}

    cut = []
    for it in items:
        content = (it.get("content") or "").strip()
        title = (it.get("title") or "").strip()
        if not content and not title:
            continue
        cut.append({
            "title": title[:200],
            "content": content[:800],
            "url": it.get("url", ""),
            "source": it.get("source", ""),
            "category": it.get("category", ""),
            "published_at": it.get("published_at", ""),
        })
        if len(cut) >= 60:
            break

    return {"items": json.dumps(cut, ensure_ascii=False)}
```

> 60 条上限与每条 800 字上限共同把输入控制在约 20k token 内，避免超长与高成本。

- [ ] **Step 5: 添加 LLM 节点 A「结构化抽取」**

模型：`deepseek-chat`，温度 **0.1**，开启「结构化输出 / JSON」。输入变量插入上一步的 `items`。System Prompt：

````
你是金融与 AI 新闻分析助手。输入是一批新闻条目（JSON 数组）。请对每一条输出结构化分析。

对每条新闻输出一个对象，字段如下：

- event_type：从以下枚举中选且只能选一个，禁止自创：
  货币政策 | 经济数据 | 地缘政治 | 央行购金 | 美元走势 | 通胀 | 就业 | 其他
  判定规则：
  * 利率决议、官员表态、缩表扩表 → 货币政策
  * GDP、PMI、零售销售等非通胀非就业数据 → 经济数据
  * 战争、制裁、选举、贸易摩擦 → 地缘政治
  * 央行买卖黄金、黄金储备变动 → 央行购金
  * 美元指数、美债收益率 → 美元走势
  * CPI、PCE、物价 → 通胀
  * 非农、失业率、初请失业金 → 就业
  * 无法归入上述任何一类 → 其他

- direction：利多金银 | 利空金银 | 中性
  判定：提升实际利率预期 → 利空金银；压低实际利率预期 → 利多金银；
  避险需求上升 → 利多金银；与金银无关 → 中性

- strength：1 到 5 的整数。1=影响微弱，3=中等，5=重大冲击

- relevant：布尔值。该条是否与金银走势相关。AI 技术类新闻填 false

- summary：一句话中文摘要，不超过 40 字

- source / url / published_at：原样保留输入中的对应字段

只输出 JSON 数组，不要输出任何解释文字或 Markdown 代码块标记。
输出数组的长度必须与输入一致，且顺序一一对应。
````

User Prompt：用变量选择器插入代码节点的输出 `items`（会写成 `{{#代码节点id.items#}}` 的形式，不要手打）。

> **关于输出变量名**：Dify 的 LLM 节点输出变量名固定为 `text`，在节点内改不了。所以这里不要纠结命名——后续节点用变量选择器引用它，最后在结束节点统一映射成 `events_json`（见 Step 7）。

- [ ] **Step 6: 添加 LLM 节点 B「日报生成」**

模型：`deepseek-chat`，温度 **0.3**，开启 JSON 输出。输入变量插入节点 A 的输出 `events_json`。System Prompt：

````
你是金银与 AI 情报编辑。根据输入的结构化事件列表，生成一份中文日报。

输出严格 JSON，结构如下：

{
  "ai_news": [{"title": "标题", "why": "为什么重要", "url": "链接"}],
  "gold_news": [{"summary": "事件摘要", "direction": "利多金银", "strength": 4, "url": "链接"}],
  "gold_conclusion": "一句综合判断",
  "calendar": [{"time": "20:30", "event": "美国 8 月 CPI 同比"}]
}

要求：
- ai_news：挑 3 到 5 条与 AI 技术、模型、行业相关的（relevant 为 false 的那些）。
  why 字段用一句话说明为什么值得关注，不超过 40 字
- gold_news：挑 3 到 5 条与金银最相关的（relevant 为 true），按 strength 从高到低排列
- gold_conclusion：结合当日事件给出一句多空倾向判断，不超过 60 字
- calendar：只填输入中明确提到的今日宏观事件；没有就填空数组 []
- **严禁编造输入中不存在的信息**，url 必须来自输入
- 只输出 JSON，不要输出 Markdown 代码块标记
````

User Prompt：

```
{{#节点A.text#}}
```

> 用变量选择器插入节点 A 的输出即可，不要手打节点 ID。

- [ ] **Step 7: 结束节点**

添加两个输出变量，都设为 String 类型，分别引用前面两个 LLM 节点的 `text`：

| 结束节点输出变量名 | 取值 |
|---|---|
| `events_json` | `{{#节点A.text#}}` |
| `digest_json` | `{{#节点B.text#}}` |

**这两个变量名必须与 Python 侧 `src/dify_client.py` 中读取的键名完全一致**，否则会报"缺少 events_json"。

- [ ] **Step 8: 用 curl 调通并验证结构**

在「访问 API」页创建 API Key（形如 `app-xxxx`）。然后：

用 Python 生成请求体（嵌套引号交给 JSON 序列化处理，避免 shell 转义踩坑）：

```bash
export DIFY_API_KEY="app-你的key"

python - <<'PY'
import json, pathlib
items = [{
    "title": "美联储官员放鸽",
    "content": "沃勒表示年内可能进一步降息",
    "url": "https://x.com/1",
    "source": "金十数据快讯",
    "category": "finance",
    "published_at": "2026-09-15T10:00:00+08:00",
}]
payload = {
    "inputs": {"raw_items": json.dumps(items, ensure_ascii=False), "date": "2026-09-15"},
    "response_mode": "blocking",
    "user": "daily-intel",
}
pathlib.Path("samples/_tmp_payload.json").write_text(
    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
)
PY

curl -s -X POST "https://api.dify.ai/v1/workflows/run" \
  -H "Authorization: Bearer $DIFY_API_KEY" \
  -H "Content-Type: application/json" \
  --data @"samples/_tmp_payload.json" \
  -o samples/_tmp_response.json

python -m json.tool samples/_tmp_response.json
```

**验收标准（三条全过才算完成）：**

1. `data.status` 为 `"succeeded"`
2. `data.outputs.events_json` 能 `json.loads` 成数组，且数组中每条都有 `event_type`／`direction`／`strength`／`relevant`／`summary`
3. `event_type` 的取值全部落在枚举内；`direction` 为「利多金银」或「利空金银」或「中性」

验证通过后，把真实返回留作离线样本，并清理临时文件：

```bash
mv samples/_tmp_response.json samples/dify_response.json
rm -f samples/_tmp_payload.json
```

这个文件后续有两处会用到：Task 8 的 `load_sample_result()` 测试，以及 Task 13 的 `--offline` 模式。

**注意：** 它在仓库里会公开。返回体里只有新闻文本与 token 计数，不含密钥，可以公开。

- [ ] **Step 9: 导出 DSL 并提交**

在应用右上角「导出 DSL」→ 保存为 `dify/daily-intel-workflow.yml`。在 `docs/dify工作流说明.md` 中记录：节点职责、两个 Prompt 的完整内容、模型与温度选择、本次 curl 验证的结果、以及后续调整 Prompt 时的注意事项。

```bash
git add dify/ docs/dify工作流说明.md samples/dify_response.json
git commit -m "feat: Dify 工作流（结构化抽取 + 日报生成）"
```

---

## Task 8: Dify 客户端

**Files:**
- Create: `src/dify_client.py`
- Test: `tests/test_dify_client.py`

**Interfaces:**
- Consumes: `RawItem`、`SAMPLES_DIR`
- Produces: `run_workflow(items: list[RawItem], date: str, api_key: str) -> DifyResult`；`DifyResult(events: list[dict], digest: dict, total_tokens: int)`；`load_sample_result() -> DifyResult`

- [ ] **Step 1: 写失败测试 `tests/test_dify_client.py`**

```python
import json

import pytest

from src.dify_client import DifyClient
from src.models import RawItem

URL = "https://api.dify.ai/v1/workflows/run"


def _raw_items():
    return [
        RawItem(
            title="美联储官员放鸽",
            url="https://x.com/1",
            source="金十数据快讯",
            category="finance",
            published_at="2026-09-15T10:00:00+08:00",
            content="沃勒表示年内可能进一步降息",
        )
    ]


def _dify_response():
    return {
        "workflow_run_id": "wf-1",
        "data": {
            "status": "succeeded",
            "outputs": {
                "events_json": json.dumps([
                    {
                        "event_type": "货币政策",
                        "direction": "利多金银",
                        "strength": 4,
                        "relevant": True,
                        "summary": "美联储官员释放降息信号",
                        "source": "金十数据快讯",
                        "url": "https://x.com/1",
                        "published_at": "2026-09-15T10:00:00+08:00",
                    }
                ], ensure_ascii=False),
                "digest_json": json.dumps({
                    "ai_news": [],
                    "gold_news": [{"summary": "放鸽", "direction": "利多金银",
                                   "strength": 4, "url": "https://x.com/1"}],
                    "gold_conclusion": "偏多",
                    "calendar": [],
                }, ensure_ascii=False),
            },
            "total_tokens": 12345,
        },
    }


def test_run_workflow_parses_outputs(requests_mock):
    requests_mock.post(URL, json=_dify_response())
    client = DifyClient(api_key="app-test", url=URL)
    result = client.run(_raw_items(), date="2026-09-15")

    assert result.events[0]["event_type"] == "货币政策"
    assert result.digest["gold_conclusion"] == "偏多"
    assert result.total_tokens == 12345


def test_run_workflow_posts_expected_payload(requests_mock):
    requests_mock.post(URL, json=_dify_response())
    client = DifyClient(api_key="app-test", url=URL)
    client.run(_raw_items(), date="2026-09-15")

    body = requests_mock.request_history[0].json()
    assert body["response_mode"] == "blocking"
    assert body["inputs"]["date"] == "2026-09-15"
    assert "沃勒" in body["inputs"]["raw_items"]
    assert requests_mock.request_history[0].headers["Authorization"] == "Bearer app-test"


def test_run_workflow_raises_on_failed_status(requests_mock):
    payload = _dify_response()
    payload["data"]["status"] = "failed"
    payload["data"]["error"] = "model timeout"
    requests_mock.post(URL, json=payload)

    client = DifyClient(api_key="app-test", url=URL)
    with pytest.raises(RuntimeError, match="model timeout"):
        client.run(_raw_items(), date="2026-09-15")


def test_run_workflow_raises_on_malformed_json_output(requests_mock):
    payload = _dify_response()
    payload["data"]["outputs"]["events_json"] = "这不是 JSON"
    requests_mock.post(URL, json=payload)

    client = DifyClient(api_key="app-test", url=URL)
    with pytest.raises(RuntimeError, match="events_json 解析失败"):
        client.run(_raw_items(), date="2026-09-15")


def test_load_sample_result_reads_repo_sample():
    from src.dify_client import load_sample_result

    result = load_sample_result()
    assert isinstance(result.events, list)
    assert isinstance(result.digest, dict)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_dify_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.dify_client'`

- [ ] **Step 3: 实现 `src/dify_client.py`**

```python
"""Dify Workflow API 客户端。"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from src.config import SAMPLES_DIR
from src.models import RawItem

API_URL = "https://api.dify.ai/v1/workflows/run"
TIMEOUT_SECONDS = 120       # LLM 链路较长，比采集的 15s 放宽
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (5, 15)


@dataclass(frozen=True)
class DifyResult:
    events: list[dict]
    digest: dict
    total_tokens: int


def _parse_json_field(raw: str | None, field_name: str) -> object:
    if raw is None:
        raise RuntimeError(f"Dify 返回中缺少 {field_name}")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(
            f"{field_name} 解析失败，原始内容前 200 字：{str(raw)[:200]}"
        ) from exc


class DifyClient:
    def __init__(self, api_key: str, url: str = API_URL) -> None:
        self.api_key = api_key
        self.url = url

    def run(self, items: list[RawItem], date: str) -> DifyResult:
        payload = {
            "inputs": {
                "raw_items": json.dumps(
                    [i.__dict__ for i in items], ensure_ascii=False
                ),
                "date": date,
            },
            "response_mode": "blocking",
            "user": "daily-intel",
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = requests.post(
                    self.url, json=payload, headers=headers, timeout=TIMEOUT_SECONDS
                )
                resp.raise_for_status()
                body = resp.json()
                data = body.get("data") or {}

                if data.get("status") != "succeeded":
                    raise RuntimeError(
                        f"Dify 工作流未成功：{data.get('error') or data.get('status')}"
                    )

                outputs = data.get("outputs") or {}
                return DifyResult(
                    events=_parse_json_field(outputs.get("events_json"), "events_json"),
                    digest=_parse_json_field(outputs.get("digest_json"), "digest_json"),
                    total_tokens=data.get("total_tokens", 0),
                )
            except RuntimeError:
                raise           # 业务错误不重试，重试也是同样结果
            except Exception as exc:  # noqa: BLE001 - 网络类错误才重试
                last_error = exc
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(BACKOFF_SECONDS[attempt])

        assert last_error is not None
        raise last_error


def load_sample_result() -> DifyResult:
    """读取 samples/dify_response.json，供 --offline 模式使用。"""
    path = Path(SAMPLES_DIR) / "dify_response.json"
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)["data"]

    outputs = data["outputs"]
    return DifyResult(
        events=json.loads(outputs["events_json"]),
        digest=json.loads(outputs["digest_json"]),
        total_tokens=data.get("total_tokens", 0),
    )
```

> `run()` 里区分了两类异常：`RuntimeError` 表示 Dify 明确返回了业务失败（模型超时、JSON 格式错），重试无用，立即抛出；其余（超时、连接中断、5xx）才重试。这样既不会白等，也不会因为网络抖动丢掉一天的数据。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_dify_client.py -v`
Expected: PASS（5 个用例）

- [ ] **Step 5: 提交**

```bash
git add src/dify_client.py tests/test_dify_client.py
git commit -m "feat: Dify Workflow API 客户端（含离线样本模式）"
```

---

## Task 9: 情绪指数计算

**Files:**
- Create: `src/analysis.py`
- Test: `tests/test_analysis.py`

**Interfaces:**
- Consumes: `Event`、`daily_index` 的既有行
- Produces:
  - `SIGN: dict[str, int]`
  - `to_events(raw_events: list[dict], date: str) -> list[Event]`
  - `compute_sentiment_score(events: list[Event]) -> float`
  - `build_index_row(date: str, events: list[Event], gold_close: float | None) -> dict`

- [ ] **Step 1: 写失败测试 `tests/test_analysis.py`**

```python
import pytest

from src.analysis import build_index_row, compute_sentiment_score, to_events
from src.models import Event


def _event(direction="利多金银", strength=5, relevant=True, event_type="货币政策"):
    return Event(
        date="2026-09-15", event_type=event_type, direction=direction,
        strength=strength, relevant=relevant, summary="测试",
        source="源", url="https://x.com/1", published_at="2026-09-15T10:00:00+08:00",
    )


def test_all_bullish_max_strength_scores_one():
    events = [_event(strength=5) for _ in range(3)]
    assert compute_sentiment_score(events) == 1.0


def test_all_bearish_max_strength_scores_minus_one():
    events = [_event(direction="利空金银", strength=5) for _ in range(2)]
    assert compute_sentiment_score(events) == -1.0


def test_balanced_bull_bear_scores_zero():
    events = [_event(strength=5), _event(direction="利空金银", strength=5)]
    assert compute_sentiment_score(events) == 0.0


def test_neutral_counts_in_denominator():
    """中性事件符号为 0 但仍进分母——这是归一化的关键，别改成剔除。"""
    events = [_event(strength=5), _event(direction="中性", strength=5)]
    assert compute_sentiment_score(events) == 0.5


def test_empty_returns_zero():
    assert compute_sentiment_score([]) == 0.0


def test_irrelevant_events_are_excluded():
    """relevant=False 的事件完全不参与计算，也不进分母。"""
    events = [_event(strength=5), _event(strength=5, relevant=False)]
    assert compute_sentiment_score(events) == 1.0


def test_unknown_direction_raises():
    events = [_event(direction="可能利多")]
    with pytest.raises(ValueError, match="未知的影响方向"):
        compute_sentiment_score(events)


def test_build_index_row_counts_bull_and_bear():
    events = [
        _event(direction="利多金银"),
        _event(direction="利多金银"),
        _event(direction="利空金银"),
        _event(direction="中性"),
        _event(direction="利空金银", relevant=False),
    ]
    row = build_index_row("2026-09-15", events, gold_close=2498.7)

    assert row["date"] == "2026-09-15"
    assert row["bull_count"] == 2
    assert row["bear_count"] == 1
    assert row["total_events"] == 4          # 只数 relevant 的
    assert row["gold_close"] == 2498.7


def test_build_index_row_handles_missing_gold_price():
    row = build_index_row("2026-09-15", [_event()], gold_close=None)
    assert row["gold_close"] is None


def test_to_events_converts_raw_dicts():
    raw = [{
        "event_type": "通胀", "direction": "利空金银", "strength": 3,
        "relevant": True, "summary": "CPI 超预期", "source": "金十数据快讯",
        "url": "https://x.com/1", "published_at": "2026-09-15T20:30:00+08:00",
    }]
    events = to_events(raw, date="2026-09-15")
    assert len(events) == 1
    assert events[0].event_type == "通胀"
    assert events[0].date == "2026-09-15"


def test_to_events_skips_malformed_entries():
    raw = [
        {"event_type": "通胀", "direction": "利空金银", "strength": 3,
         "relevant": True, "summary": "好的", "source": "s", "url": "u",
         "published_at": "2026-09-15T20:30:00+08:00"},
        {"direction": "利空金银"},                      # 缺字段
        {"event_type": "通胀", "direction": "利空金银", "strength": "高",
         "relevant": True, "summary": "强度不是数字", "source": "s", "url": "u",
         "published_at": "2026-09-15T20:30:00+08:00"},
    ]
    events = to_events(raw, date="2026-09-15")
    assert len(events) == 1
    assert events[0].summary == "好的"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_analysis.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.analysis'`

- [ ] **Step 3: 实现 `src/analysis.py`**

```python
"""情绪指数计算。本模块为纯函数，不涉及网络与文件。"""
from __future__ import annotations

from dateutil import parser as date_parser

from src.models import Event

# 事件方向 -> 符号
SIGN = {"利多金银": 1, "利空金银": -1, "中性": 0}

# 强度满分，用于归一化
MAX_STRENGTH = 5

_REQUIRED_FIELDS = ("event_type", "direction", "strength", "summary", "url")


def to_events(raw_events: list[dict], date: str) -> list[Event]:
    """把 Dify 返回的 dict 列表转成 Event。格式不合规的条目丢弃，不中断整体。"""
    events: list[Event] = []

    for raw in raw_events:
        if not isinstance(raw, dict):
            continue
        if any(raw.get(f) is None for f in _REQUIRED_FIELDS):
            continue
        try:
            strength = int(raw["strength"])
        except (TypeError, ValueError):
            continue
        if not 1 <= strength <= MAX_STRENGTH:
            continue
        if raw["direction"] not in SIGN:
            continue

        events.append(
            Event(
                date=date,
                event_type=str(raw["event_type"]),
                direction=str(raw["direction"]),
                strength=strength,
                relevant=bool(raw.get("relevant", False)),
                summary=str(raw["summary"]),
                source=str(raw.get("source", "")),
                url=str(raw["url"]),
                published_at=_normalize_published_at(raw.get("published_at", "")),
            )
        )
    return events


def _normalize_published_at(raw: str) -> str:
    """尽力解析成 ISO8601；解析不了就原样返回，不阻塞。"""
    if not raw:
        return ""
    try:
        return date_parser.parse(raw).isoformat()
    except (ValueError, TypeError):
        return raw


def compute_sentiment_score(events: list[Event]) -> float:
    """计算情绪指数，取值 [-1, 1]。

    公式：Σ(符号 × 强度) / (5 × 事件数)
    分母除以 5×n 是为了让事件数不同的日期之间可比；否则新闻多的一天
    天然分高，测的就成了信息流量而非情绪。中性事件符号为 0，
    但仍计入分母——这是刻意的，不要"优化"成剔除。
    只统计 relevant=True 的事件。
    """
    relevant = [e for e in events if e.relevant]
    if not relevant:
        return 0.0

    total = 0
    for event in relevant:
        if event.direction not in SIGN:
            raise ValueError(f"未知的影响方向：{event.direction!r}")
        total += SIGN[event.direction] * event.strength

    return round(total / (MAX_STRENGTH * len(relevant)), 4)


def build_index_row(
    date: str, events: list[Event], gold_close: float | None
) -> dict:
    """构建 daily_index.csv 的一行。"""
    relevant = [e for e in events if e.relevant]
    return {
        "date": date,
        "sentiment_score": compute_sentiment_score(events),
        "bull_count": sum(1 for e in relevant if e.direction == "利多金银"),
        "bear_count": sum(1 for e in relevant if e.direction == "利空金银"),
        "total_events": len(relevant),
        "gold_close": gold_close,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_analysis.py -v`
Expected: PASS（11 个用例）

- [ ] **Step 5: 提交**

```bash
git add src/analysis.py tests/test_analysis.py
git commit -m "feat: 情绪指数计算（纯函数，TDD）"
```

---

## Task 10: CSV 存储

**Files:**
- Create: `src/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: `Event`、`daily_index` 行字典
- Produces:
  - `EVENT_FIELDS: list[str]`、`INDEX_FIELDS: list[str]`
  - `append_events(events: list[Event], path: Path) -> int`
  - `append_index_row(row: dict, path: Path) -> None`
  - `read_index(path: Path) -> pandas.DataFrame`

- [ ] **Step 1: 写失败测试 `tests/test_storage.py`**

```python
import pandas as pd
import pytest

from src.models import Event
from src.storage import (
    INDEX_FIELDS,
    append_events,
    append_index_row,
    read_index,
)


def _event(summary="甲"):
    return Event(
        date="2026-09-15", event_type="货币政策", direction="利多金银",
        strength=4, relevant=True, summary=summary, source="金十数据快讯",
        url="https://x.com/1", published_at="2026-09-15T10:00:00+08:00",
    )


def _row(date="2026-09-15"):
    return {
        "date": date, "sentiment_score": 0.4, "bull_count": 2, "bear_count": 1,
        "total_events": 3, "gold_close": 2498.7,
    }


def test_append_events_creates_file_with_header(tmp_path):
    path = tmp_path / "events.csv"
    written = append_events([_event()], path)
    assert written == 1

    df = pd.read_csv(path)
    assert list(df.columns)[:3] == ["date", "event_type", "direction"]
    assert df.iloc[0]["summary"] == "甲"


def test_append_events_is_idempotent_for_same_date(tmp_path):
    """同一天重复跑时，先删掉该日旧行再写，避免重复累积。"""
    path = tmp_path / "events.csv"
    append_events([_event("第一次")], path)
    append_events([_event("第二次"), _event("第二次")], path)

    df = pd.read_csv(path)
    assert len(df) == 2
    assert set(df["summary"]) == {"第二次"}


def test_append_events_keeps_other_dates(tmp_path):
    path = tmp_path / "events.csv"
    append_events([_event("前一天")], path)

    later = Event(
        date="2026-09-16", event_type="通胀", direction="利空金银", strength=2,
        relevant=True, summary="后一天", source="金十数据快讯",
        url="https://x.com/2", published_at="2026-09-16T10:00:00+08:00",
    )
    append_events([later], path)

    df = pd.read_csv(path)
    assert set(df["summary"]) == {"前一天", "后一天"}


def test_append_events_with_empty_list_does_nothing(tmp_path):
    path = tmp_path / "events.csv"
    assert append_events([], path) == 0
    assert not path.exists()


def test_append_index_row_appends(tmp_path):
    path = tmp_path / "daily_index.csv"
    append_index_row(_row("2026-09-15"), path)
    append_index_row(_row("2026-09-16"), path)

    df = read_index(path)
    assert list(df.columns) == INDEX_FIELDS
    assert len(df) == 2


def test_append_index_row_replaces_same_date(tmp_path):
    path = tmp_path / "daily_index.csv"
    append_index_row(_row("2026-09-15"), path)
    updated = _row("2026-09-15")
    updated["sentiment_score"] = -0.9
    append_index_row(updated, path)

    df = read_index(path)
    assert len(df) == 1
    assert df.iloc[0]["sentiment_score"] == pytest.approx(-0.9)


def test_read_index_returns_empty_frame_when_missing(tmp_path):
    df = read_index(tmp_path / "nope.csv")
    assert df.empty
    assert list(df.columns) == INDEX_FIELDS
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_storage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.storage'`

- [ ] **Step 3: 实现 `src/storage.py`**

```python
"""CSV 读写。同一日重复运行会覆盖该日数据，保证跑多次结果一致。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.models import Event

EVENT_FIELDS = [
    "date", "event_type", "direction", "strength", "relevant",
    "summary", "source", "url", "published_at",
]

INDEX_FIELDS = [
    "date", "sentiment_score", "bull_count", "bear_count",
    "total_events", "gold_close",
]


def _write_with_replace(new_df: pd.DataFrame, path: Path, date: str, fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        old = pd.read_csv(path, dtype={"date": str})
        old = old[old["date"] != date]
        combined = pd.concat([old, new_df], ignore_index=True)
    else:
        combined = new_df

    combined = combined.sort_values("date").reset_index(drop=True)
    combined.to_csv(path, index=False, columns=fields, encoding="utf-8-sig")


def append_events(events: list[Event], path: Path) -> int:
    """写入某一日的事件。返回写入条数。同日已有数据会被替换。"""
    if not events:
        return 0

    date = events[0].date
    df = pd.DataFrame([e.__dict__ for e in events], columns=EVENT_FIELDS)
    _write_with_replace(df, path, date, EVENT_FIELDS)
    return len(events)


def append_index_row(row: dict, path: Path) -> None:
    """写入某一日的指数行。同日已有数据会被替换。"""
    df = pd.DataFrame([row], columns=INDEX_FIELDS)
    _write_with_replace(df, path, row["date"], INDEX_FIELDS)


def read_index(path: Path) -> pd.DataFrame:
    """读取 daily_index.csv；文件不存在时返回带列名的空表。"""
    if not Path(path).exists():
        return pd.DataFrame(columns=INDEX_FIELDS)
    return pd.read_csv(path, dtype={"date": str})
```

> 用 `utf-8-sig` 编码：这样用 Excel 直接双击打开 CSV 不会中文乱码，方便你自己翻看。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_storage.py -v`
Expected: PASS（7 个用例）

- [ ] **Step 5: 提交**

```bash
git add src/storage.py tests/test_storage.py
git commit -m "feat: CSV 存储（同日覆盖式写入）"
```

---

## Task 11: 图表生成

**Files:**
- Create: `src/charts.py`
- Test: `tests/test_charts.py`

**Interfaces:**
- Consumes: `read_index()` 返回的 DataFrame、`CHARTS_DIR`
- Produces:
  - `configure_chinese_font() -> None`
  - `recent_event_rows(events_df, days: int) -> pd.DataFrame`（按**日期**切最近 N 天，不是按行数）
  - `plot_sentiment_trend(df, days: int, out_path: Path) -> Path`
  - `plot_event_distribution(events_df, days: int, out_path: Path) -> Path`
  - `plot_sentiment_vs_gold(df, days: int, out_path: Path) -> Path`

- [ ] **Step 1: 写失败测试 `tests/test_charts.py`**

```python
import pandas as pd
import pytest

from src.charts import (
    configure_chinese_font,
    plot_event_distribution,
    plot_sentiment_trend,
    plot_sentiment_vs_gold,
    recent_event_rows,
)


def _index_df():
    return pd.DataFrame({
        "date": ["2026-09-13", "2026-09-14", "2026-09-15"],
        "sentiment_score": [0.2, -0.4, 0.5],
        "bull_count": [2, 1, 3],
        "bear_count": [1, 2, 0],
        "total_events": [3, 3, 3],
        "gold_close": [2480.0, 2475.5, 2498.7],
    })


def _events_df():
    return pd.DataFrame({
        "date": ["2026-09-14", "2026-09-15", "2026-09-15"],
        "event_type": ["货币政策", "通胀", "货币政策"],
        "direction": ["利多金银", "利空金银", "中性"],
        "strength": [4, 3, 2],
        "relevant": [True, True, True],
        "summary": ["甲", "乙", "丙"],
        "source": ["s", "s", "s"],
        "url": ["u1", "u2", "u3"],
        "published_at": ["t1", "t2", "t3"],
    })


def test_configure_chinese_font_resolves_a_real_font():
    """不能只断言"候选列表第一项非空"——那对 ["完全没有这个字体"] 也成立。

    缺字体时没有异常、PNG 照常生成，图上却全是方框。所以这里真的解析一次。
    """
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties, findfont

    from src.charts import FONT_CANDIDATES

    configure_chinese_font()
    assert plt.rcParams["axes.unicode_minus"] is False

    resolved = findfont(
        FontProperties(family=FONT_CANDIDATES), fallback_to_default=False
    )
    assert resolved


def test_plot_raises_clear_error_when_no_cjk_font(monkeypatch):
    """字体全落空时必须抛错，而不是安静地产出一张豆腐块图。"""
    import src.charts as charts_module

    monkeypatch.setattr(
        charts_module, "FONT_CANDIDATES", ["完全不存在的字体XYZ"]
    )
    with pytest.raises(ValueError, match="找不到任何可用中文字体"):
        charts_module.configure_chinese_font()


def test_plot_sentiment_trend_writes_file(tmp_path):
    out = plot_sentiment_trend(_index_df(), days=30, out_path=tmp_path / "trend.png")
    assert out.exists() and out.stat().st_size > 1000


def test_plot_event_distribution_writes_file(tmp_path):
    out = plot_event_distribution(
        _events_df(), days=7, out_path=tmp_path / "dist.png"
    )
    assert out.exists() and out.stat().st_size > 1000


def test_recent_event_rows_slices_by_date_not_by_row_count():
    """一天多行时，"最近 N 天"必须拿满这几天的全部事件行。

    若实现退回成 df.tail(days)，本用例只会剩 2 行（且同属一天），断言失败。
    """
    df = pd.DataFrame({
        "date": ["2026-09-13"] * 5 + ["2026-09-14"] * 5 + ["2026-09-15"] * 5,
        "event_type": ["货币政策"] * 15,
        "direction": ["利多金银"] * 15,
        "strength": [3] * 15,
        "relevant": [True] * 15,
        "summary": [f"事件{i}" for i in range(15)],
        "source": ["s"] * 15,
        "url": ["u"] * 15,
        "published_at": ["t"] * 15,
    })
    result = recent_event_rows(df, days=2)
    assert len(result) == 10                  # 最近两天各 5 行，不是 2 行
    assert set(result["date"]) == {"2026-09-14", "2026-09-15"}


def test_recent_event_rows_handles_empty_frame():
    empty = pd.DataFrame(columns=["date", "event_type", "direction"])
    assert recent_event_rows(empty, days=7).empty


def test_plot_sentiment_vs_gold_writes_file(tmp_path):
    out = plot_sentiment_vs_gold(
        _index_df(), days=30, out_path=tmp_path / "vs_gold.png"
    )
    assert out.exists() and out.stat().st_size > 1000


def test_plot_sentiment_trend_tolerates_empty_frame(tmp_path):
    empty = pd.DataFrame(columns=[
        "date", "sentiment_score", "bull_count", "bear_count",
        "total_events", "gold_close",
    ])
    out = plot_sentiment_trend(empty, days=30, out_path=tmp_path / "empty.png")
    assert out.exists()


def test_plot_sentiment_vs_gold_skips_when_no_gold_price(tmp_path):
    df = _index_df()
    df["gold_close"] = None
    with pytest.raises(ValueError, match="无有效金价"):
        plot_sentiment_vs_gold(df, days=30, out_path=tmp_path / "x.png")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_charts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.charts'`

- [ ] **Step 3: 实现 `src/charts.py`**

```python
"""图表生成。"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")           # 无显示环境（CI）必须有，否则会报错
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.font_manager import FontProperties, findfont

# Ubuntu CI 上装的是 fonts-noto-cjk，Windows 本地是 SimHei；按序尝试
FONT_CANDIDATES = ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "Microsoft YaHei", "SimHei"]

COLOR_BULL = "#c0392b"
COLOR_BEAR = "#27ae60"
COLOR_NEUTRAL = "#7f8c8d"


def configure_chinese_font() -> None:
    """设置中文字体，并**确认候选字体真的解析得到**。

    缺字体时 matplotlib 只在 logging 里嘀咕一句 `findfont: Font family not found`，
    图照画、PNG 照生成、测试照全绿，只是所有中文变成一片方框（豆腐块）。
    这是本模块唯一无法靠断言捕获的失败模式——所以这里主动解析一次，
    全落空就抛错，让问题当场暴露，而不是几天后在手机上看到一堆 □。
    """
    plt.rcParams["font.sans-serif"] = FONT_CANDIDATES
    plt.rcParams["axes.unicode_minus"] = False

    try:
        findfont(FontProperties(family=FONT_CANDIDATES), fallback_to_default=False)
    except ValueError as exc:
        raise ValueError(
            f"找不到任何可用中文字体，图表会渲染成方框。候选列表：{FONT_CANDIDATES}。"
            "Linux 上请安装 fonts-noto-cjk；Windows 上确认已安装微软雅黑或黑体。"
        ) from exc


def _tail(df: pd.DataFrame, days: int) -> pd.DataFrame:
    return df.tail(days).copy()


def _save(fig, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


def plot_sentiment_trend(df: pd.DataFrame, days: int, out_path: Path) -> Path:
    """近 N 日情绪指数折线，带 0 轴基准。"""
    configure_chinese_font()
    fig, ax = plt.subplots(figsize=(9, 4))

    data = _tail(df, days)
    if not data.empty:
        ax.plot(data["date"], data["sentiment_score"], marker="o", color="#2c3e50")
        for label in ax.get_xticklabels():
            label.set_rotation(45)
            label.set_ha("right")

    ax.axhline(0, color="#bdc3c7", linewidth=1, linestyle="--")
    ax.set_ylim(-1.05, 1.05)
    ax.set_ylabel("情绪指数")
    ax.set_title(f"近 {days} 日金银情绪指数")
    ax.grid(alpha=0.3)
    return _save(fig, out_path)


def recent_event_rows(events_df: pd.DataFrame, days: int) -> pd.DataFrame:
    """取最近 days 个自然日的**全部**事件行。

    注意这是按日期切，不是按行数切。这里**不能**用 `_tail()`：events 表一天
    有多行，`df.tail(7)` 取的是"最后 7 条事件"而不是"最后 7 天"，实际可能只
    覆盖一两天，图上却标着"近 7 日"。

    单独抽成函数是为了能被直接断言——图表输出难以验证语义，这个选择可以。
    """
    if events_df.empty:
        return events_df
    recent_dates = sorted(events_df["date"].unique())[-days:]
    return events_df[events_df["date"].isin(recent_dates)]


def plot_event_distribution(
    events_df: pd.DataFrame, days: int, out_path: Path
) -> Path:
    """近 N 日事件类型分布（按方向堆叠）。"""
    configure_chinese_font()
    fig, ax = plt.subplots(figsize=(9, 4))

    data = recent_event_rows(events_df, days)
    if not data.empty:
        pivot = (
            data.pivot_table(
                index="event_type", columns="direction",
                values="summary", aggfunc="count", fill_value=0,
            )
        )
        order = [c for c in ["利多金银", "中性", "利空金银"] if c in pivot.columns]
        pivot = pivot[order]
        # 不设这两行，pandas 会把列名直接当图例标题和 xtick 标签，图上出现英文
        pivot.index.name = "事件类型"
        pivot.columns.name = "方向"
        colors = [
            {"利多金银": COLOR_BULL, "中性": COLOR_NEUTRAL, "利空金银": COLOR_BEAR}[c]
            for c in order
        ]
        pivot.plot(kind="bar", stacked=True, ax=ax, color=colors)
        ax.set_ylabel("事件数")
        for label in ax.get_xticklabels():
            label.set_rotation(30)
            label.set_ha("right")

    ax.set_title(f"近 {days} 日事件类型分布")
    ax.grid(alpha=0.3, axis="y")
    return _save(fig, out_path)


def plot_sentiment_vs_gold(df: pd.DataFrame, days: int, out_path: Path) -> Path:
    """情绪指数与金价双轴对照图。"""
    configure_chinese_font()
    data = _tail(df, days).dropna(subset=["gold_close"])
    if data.empty:
        raise ValueError("无有效金价数据，无法绘制对照图")

    fig, ax1 = plt.subplots(figsize=(9, 4))
    ax1.plot(data["date"], data["sentiment_score"], marker="o", color="#2c3e50")
    ax1.axhline(0, color="#bdc3c7", linewidth=1, linestyle="--")
    ax1.set_ylabel("情绪指数", color="#2c3e50")
    ax1.set_ylim(-1.05, 1.05)

    ax2 = ax1.twinx()
    ax2.plot(data["date"], data["gold_close"], marker="s", color=COLOR_BULL)
    ax2.set_ylabel("金价（美元/盎司）", color=COLOR_BULL)

    for label in ax1.get_xticklabels():
        label.set_rotation(45)
        label.set_ha("right")

    ax1.set_title(f"近 {days} 日情绪指数与金价对照")
    ax1.grid(alpha=0.3)
    return _save(fig, out_path)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_charts.py -v`
Expected: PASS（9 个用例）

- [ ] **Step 5: 人工检查中文是否正常显示**

```bash
python -c "
import pandas as pd
from src.charts import plot_sentiment_trend
df = pd.DataFrame({
    'date': ['2026-09-13', '2026-09-14', '2026-09-15'],
    'sentiment_score': [0.2, -0.4, 0.5],
    'bull_count': [2, 1, 3], 'bear_count': [1, 2, 0],
    'total_events': [3, 3, 3], 'gold_close': [2480.0, 2475.5, 2498.7],
})
plot_sentiment_trend(df, 30, __import__('pathlib').Path('charts/manual_check.png'))
"
```

打开 `charts/manual_check.png` 确认标题「近 30 日金银情绪指数」显示为正常汉字而非方框。若为方框，说明本机缺中文字体，安装后重试；**这一步不做，CI 上出的图会是豆腐块而你看不出来**。

- [ ] **Step 6: 提交**

```bash
git add src/charts.py tests/test_charts.py
git commit -m "feat: 三张图表生成（含中文字体处理）"
```

---

## Task 12: 飞书推送

**Files:**
- Create: `src/notifier.py`
- Test: `tests/test_notifier.py`

**Interfaces:**
- Consumes: `digest` dict、`index_row` dict、`failed_sources` 列表
- Produces:
  - `build_card(date: str, digest: dict, index_row: dict, failed_sources: list[str], dashboard_url: str = "") -> dict`
  - `send_to_feishu(webhook_url: str, payload: dict) -> None`
  - `build_fallback_text(date: str, reason: str) -> dict`

- [ ] **Step 1: 写失败测试 `tests/test_notifier.py`**

```python
import pytest

from src.notifier import build_card, build_fallback_text, send_to_feishu

WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/test-hook"


def _digest():
    return {
        "ai_news": [
            {"title": "OpenAI 发布新模型", "why": "推理能力显著提升",
             "url": "https://openai.com/1"}
        ],
        "gold_news": [
            {"summary": "美联储官员放鸽", "direction": "利多金银",
             "strength": 4, "url": "https://x.com/1"}
        ],
        "gold_conclusion": "短期偏多",
        "calendar": [{"time": "20:30", "event": "美国 CPI 同比"}],
    }


def _index_row():
    return {"date": "2026-09-15", "sentiment_score": 0.42, "bull_count": 3,
            "bear_count": 1, "total_events": 4, "gold_close": 2498.7}


def _all_text(payload: dict) -> str:
    """把卡片里所有文本拼起来，方便断言。"""
    card = payload["card"]
    parts = [card["header"]["title"]["content"]]
    for el in card["elements"]:
        if el.get("content"):
            parts.append(el["content"])
        for action in el.get("actions", []):
            parts.append(action["text"]["content"])
    return "\n".join(parts)


def test_card_contains_all_sections():
    payload = build_card("2026-09-15", _digest(), _index_row(), failed_sources=[])
    text = _all_text(payload)

    assert "2026-09-15" in text
    assert "AI 前沿" in text
    assert "OpenAI 发布新模型" in text
    assert "推理能力显著提升" in text
    assert "金银聚焦" in text
    assert "美联储官员放鸽" in text
    assert "短期偏多" in text
    assert "美国 CPI 同比" in text


def test_card_shows_sentiment_score_and_tendency():
    payload = build_card("2026-09-15", _digest(), _index_row(), failed_sources=[])
    text = _all_text(payload)
    assert "+0.42" in text
    assert "偏多" in text


def test_card_warns_about_failed_sources():
    payload = build_card(
        "2026-09-15", _digest(), _index_row(), failed_sources=["量子位", "CNBC Markets"]
    )
    assert "2 个源抓取失败" in _all_text(payload)
    assert "量子位" in _all_text(payload)


def test_card_omits_warning_when_no_failures():
    payload = build_card("2026-09-15", _digest(), _index_row(), failed_sources=[])
    assert "抓取失败" not in _all_text(payload)


def test_card_includes_dashboard_button_when_url_given():
    payload = build_card(
        "2026-09-15", _digest(), _index_row(), failed_sources=[],
        dashboard_url="https://example.github.io/dashboard/",
    )
    text = _all_text(payload)
    assert "查看历史看板" in text


def test_card_handles_empty_ai_and_gold_sections():
    digest = {"ai_news": [], "gold_news": [], "gold_conclusion": "",
              "calendar": []}
    payload = build_card("2026-09-15", digest, _index_row(), failed_sources=[])
    text = _all_text(payload)
    assert "AI 前沿" in text
    assert "暂无" in text


def test_send_to_feishu_posts_payload(requests_mock):
    requests_mock.post(WEBHOOK, json={"code": 0, "msg": "success"})
    payload = build_card("2026-09-15", _digest(), _index_row(), failed_sources=[])
    send_to_feishu(WEBHOOK, payload)
    assert requests_mock.request_history[0].json() == payload


def test_send_to_feishu_raises_on_nonzero_code(requests_mock):
    requests_mock.post(WEBHOOK, json={"code": 9499, "msg": "Bad Request"})
    payload = build_card("2026-09-15", _digest(), _index_row(), failed_sources=[])
    with pytest.raises(RuntimeError, match="飞书返回错误"):
        send_to_feishu(WEBHOOK, payload)


def test_fallback_text_mentions_reason():
    payload = build_fallback_text("2026-09-15", "Dify 调用失败")
    assert payload["msg_type"] == "text"
    assert "Dify 调用失败" in payload["content"]["text"]
    assert "2026-09-15" in payload["content"]["text"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_notifier.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.notifier'`

- [ ] **Step 3: 实现 `src/notifier.py`**

```python
"""飞书自定义机器人推送。

注意：自定义机器人无法内嵌图片（富文本的 image 需要 image_key，
而上传图片需自建应用凭证）。因此卡片只放文字，图表通过看板链接查看。
"""
from __future__ import annotations

import requests

TIMEOUT_SECONDS = 15
DASHBOARD_BUTTON_TEXT = "查看历史看板"


def _tendency(score: float) -> str:
    if score >= 0.15:
        return "偏多"
    if score <= -0.15:
        return "偏空"
    return "中性"


def _format_ai_news(items: list[dict]) -> str:
    if not items:
        return "**暂无**"
    lines = []
    for idx, item in enumerate(items, start=1):
        title = item.get("title", "")
        why = item.get("why", "")
        url = item.get("url", "")
        line = f"{idx}. **{title}**\n{why}"
        if url:
            line += f" [原文]({url})"
        lines.append(line)
    return "\n".join(lines)


def _format_gold_news(items: list[dict]) -> str:
    if not items:
        return "**暂无**"
    lines = []
    for idx, item in enumerate(items, start=1):
        summary = item.get("summary", "")
        direction = item.get("direction", "")
        strength = item.get("strength", "")
        url = item.get("url", "")
        line = f"{idx}. **[{direction} · {strength}/5]** {summary}"
        if url:
            line += f" [原文]({url})"
        lines.append(line)
    return "\n".join(lines)


def _format_calendar(items: list[dict]) -> str:
    if not items:
        return "今日无明确宏观事件"
    return "\n".join(f"· {i.get('time', '')} {i.get('event', '')}".strip() for i in items)


def build_card(
    date: str,
    digest: dict,
    index_row: dict,
    failed_sources: list[str],
    dashboard_url: str = "",
) -> dict:
    score = float(index_row.get("sentiment_score") or 0.0)
    header = f"📊 每日情报 · {date}"

    blocks: list[str] = []

    if failed_sources:
        joined = "、".join(failed_sources)
        blocks.append(f"⚠️ {len(failed_sources)} 个源抓取失败：{joined}")

    blocks.append("🤖 **AI 前沿**\n" + _format_ai_news(digest.get("ai_news", [])))

    gold_header = (
        f"🥇 **金银聚焦** · 情绪指数 {score:+.2f}（{_tendency(score)}）\n"
        f"利多 {index_row.get('bull_count', 0)} 条 / "
        f"利空 {index_row.get('bear_count', 0)} 条"
    )
    gold_block = gold_header + "\n" + _format_gold_news(digest.get("gold_news", []))

    conclusion = digest.get("gold_conclusion")
    if conclusion:
        gold_block += f"\n**综合判断**：{conclusion}"
    blocks.append(gold_block)

    blocks.append("📅 **今日紧盯**\n" + _format_calendar(digest.get("calendar", [])))

    elements: list[dict] = []
    for idx, content in enumerate(blocks):
        if idx:
            elements.append({"tag": "hr"})
        elements.append({"tag": "markdown", "content": content})

    if dashboard_url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": DASHBOARD_BUTTON_TEXT},
                "type": "primary",
                "url": dashboard_url,
            }],
        })

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": header},
                "template": "blue",
            },
            "elements": elements,
        },
    }


def build_fallback_text(date: str, reason: str) -> dict:
    """降级通道：主流程失败时至少发出一条纯文本，绝不静默。"""
    return {
        "msg_type": "text",
        "content": {
            "text": (
                f"📊 每日情报 · {date}\n\n"
                f"⚠️ 今日日报生成失败：{reason}\n"
                f"请查看 GitHub Actions 运行日志。"
            )
        },
    }


def send_to_feishu(webhook_url: str, payload: dict) -> None:
    resp = requests.post(webhook_url, json=payload, timeout=TIMEOUT_SECONDS)
    resp.raise_for_status()

    body = resp.json()
    if body.get("code", 0) != 0:
        raise RuntimeError(f"飞书返回错误：code={body.get('code')} msg={body.get('msg')}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_notifier.py -v`
Expected: PASS（9 个用例）

- [ ] **Step 5: 真实发送一条验证卡片样式**

```bash
export FEISHU_WEBHOOK_URL="你的 webhook 地址"
python -c "
import os
from src.notifier import build_card, send_to_feishu
digest = {
  'ai_news': [{'title': '示例：某模型发布', 'why': '用于检查卡片排版是否正常', 'url': 'https://example.com'}],
  'gold_news': [{'summary': '示例：某官员放鸽', 'direction': '利多金银', 'strength': 4, 'url': 'https://example.com'}],
  'gold_conclusion': '示例结论', 'calendar': [{'time': '20:30', 'event': '示例事件'}],
}
row = {'date': '2026-09-15', 'sentiment_score': 0.42, 'bull_count': 3, 'bear_count': 1, 'total_events': 4, 'gold_close': 2498.7}
send_to_feishu(os.environ['FEISHU_WEBHOOK_URL'], build_card('2026-09-15', digest, row, [], ''))
print('已发送，请到飞书查看')
"
```

在手机上确认：标题显示正常、分段清晰、链接可点、超长文本没有溢出。

- [ ] **Step 6: 提交**

```bash
git add src/notifier.py tests/test_notifier.py
git commit -m "feat: 飞书卡片推送与降级文本"
```

---

## Task 13: 主流程

**Files:**
- Create: `src/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: 前面所有模块
- Produces: `run(dry_run: bool, offline: bool) -> int`；命令行入口 `python -m src.main [--dry-run] [--offline]`

- [ ] **Step 1: 写失败测试 `tests/test_main.py`**

```python
from pathlib import Path

import pytest

from src import main as main_module
from src.dify_client import DifyResult


@pytest.fixture
def patched_pipeline(monkeypatch, tmp_path):
    """把外部依赖全部替换掉，只验证编排逻辑。"""
    from src.models import RawItem

    monkeypatch.setattr(
        main_module, "build_collectors",
        lambda: [object()],
    )
    monkeypatch.setattr(
        main_module, "collect_all",
        lambda collectors: ([RawItem(
            title="测试条目", url="https://x.com/1", source="金十数据快讯",
            category="finance", published_at="2026-09-15T10:00:00+08:00",
            content="沃勒表示可能降息",
        )], []),
    )
    monkeypatch.setattr(main_module, "fetch_gold_close", lambda: (2498.7, "现货黄金日线"))
    monkeypatch.setattr(
        main_module, "load_sample_result",
        lambda: DifyResult(
            events=[{
                "event_type": "货币政策", "direction": "利多金银", "strength": 4,
                "relevant": True, "summary": "放鸽", "source": "金十数据快讯",
                "url": "https://x.com/1", "published_at": "2026-09-15T10:00:00+08:00",
            }],
            digest={"ai_news": [], "gold_news": [], "gold_conclusion": "偏多",
                    "calendar": []},
            total_tokens=1000,
        ),
    )
    monkeypatch.setattr(main_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main_module, "CHARTS_DIR", tmp_path / "charts")
    monkeypatch.setattr(main_module, "send_to_feishu", lambda url, payload: None)

    return tmp_path


def test_run_offline_writes_data_and_charts(patched_pipeline):
    code = main_module.run(dry_run=False, offline=True)
    assert code == 0

    events_file = patched_pipeline / "events.csv"
    index_file = patched_pipeline / "daily_index.csv"
    assert events_file.exists()
    assert index_file.exists()

    import pandas as pd
    idx = pd.read_csv(index_file)
    assert idx.iloc[0]["total_events"] == 1
    assert idx.iloc[0]["gold_close"] == 2498.7
    assert (patched_pipeline / "charts" / "sentiment_trend.png").exists()


def test_run_sends_feishu_card(patched_pipeline, monkeypatch, capsys):
    sent = {}

    def _capture(url, payload):
        sent["payload"] = payload

    monkeypatch.setattr(main_module, "send_to_feishu", _capture)
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/x")

    main_module.run(dry_run=False, offline=True)
    assert sent["payload"]["msg_type"] == "interactive"


def test_run_dry_run_skips_sending(patched_pipeline, monkeypatch):
    sent = {}
    monkeypatch.setattr(
        main_module, "send_to_feishu",
        lambda url, payload: sent.setdefault("called", True),
    )
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/x")

    main_module.run(dry_run=True, offline=True)
    assert "called" not in sent


def test_run_sends_fallback_when_dify_fails(patched_pipeline, monkeypatch):
    sent = {}

    def _boom(items, date):
        raise RuntimeError("Dify 工作流未成功：model timeout")

    monkeypatch.setattr(main_module, "load_sample_result", _boom)
    monkeypatch.setattr(
        main_module, "send_to_feishu",
        lambda url, payload: sent.update(payload),
    )
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/x")

    code = main_module.run(dry_run=False, offline=True)
    assert code == 1
    assert sent["msg_type"] == "text"
    assert "model timeout" in sent["content"]["text"]


def test_run_falls_back_to_text_when_card_build_fails(
    patched_pipeline, monkeypatch
):
    """卡片构造失败也必须让人收到东西——静默无输出是最坏情况。"""
    sent = {}

    def _boom(*args, **kwargs):
        raise TypeError("digest 结构畸形")

    monkeypatch.setattr(main_module, "build_card", _boom)
    monkeypatch.setattr(
        main_module, "send_to_feishu", lambda url, payload: sent.update(payload)
    )
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/x")

    code = main_module.run(dry_run=False, offline=True)
    assert code == 0
    assert sent["msg_type"] == "text"
    assert "卡片构造失败" in sent["content"]["text"]


def test_run_reports_gold_failure_in_card(patched_pipeline, monkeypatch):
    """金价断供必须出现在卡片上——它只躺在 stderr 里等于没有告警。"""
    sent = {}
    monkeypatch.setattr(
        main_module, "fetch_gold_close", lambda: (None, "现货黄金日线")
    )
    monkeypatch.setattr(
        main_module, "send_to_feishu", lambda url, payload: sent.update(payload)
    )
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/x")

    code = main_module.run(dry_run=False, offline=True)
    assert code == 0

    text = "\n".join(
        el["content"] for el in sent["card"]["elements"] if el.get("content")
    )
    assert "现货黄金日线" in text
    assert "抓取失败" in text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.main'`

- [ ] **Step 3: 实现 `src/main.py`**

```python
"""主流程：采集 → Dify → 计算 → 出图 → 推送。"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.analysis import build_index_row, to_events
from src.charts import (
    plot_event_distribution,
    plot_sentiment_trend,
    plot_sentiment_vs_gold,
)
from src.collectors import build_collectors, collect_all
from src.collectors.gold_price import GoldPriceCollector
from src.config import CHARTS_DIR, DATA_DIR, get_secret, load_sources
from src.dedupe import dedupe, within_hours
from src.dify_client import DifyClient, load_sample_result
from src.notifier import build_card, build_fallback_text, send_to_feishu
from src.storage import EVENT_FIELDS, append_events, append_index_row, read_index

BEIJING = timezone(timedelta(hours=8))
WINDOW_HOURS = 30          # 覆盖一天多一点，避免因调度延迟漏掉新闻


# 这两个写成函数而不是模块级常量：模块级常量在 import 时求值，
# 测试里 patch DATA_DIR 将不会生效，会写进真实目录。
def events_path() -> Path:
    return DATA_DIR / "events.csv"


def index_path() -> Path:
    return DATA_DIR / "daily_index.csv"


def today_beijing() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d")


def now_beijing_iso() -> str:
    return datetime.now(BEIJING).isoformat()


def fetch_gold_close() -> tuple[float | None, str]:
    """取金价。

    返回 (收盘价或 None, 信源名)。

    失败时返回 None 但不抛异常——金价缺失不该让整份日报失败。但**必须把
    信源名带出去**，好让调用方把它并进失败源列表、在飞书卡片上显式告警。
    否则金价断供只会留在 CI 日志的 stderr 里，而你不会去读那份日志：
    daily_index.csv 的 gold_close 列会一直空着，双轴对照图会一直不出，
    几天后才发现。这条通道的存在就是为了让这种情况当天就被看见。
    """
    cfg = next((s for s in load_sources() if s["type"] == "gold_price"), None)
    if cfg is None:
        return None, ""
    try:
        collector = GoldPriceCollector(
            name=cfg["name"], category=cfg["category"], url=cfg["url"]
        )
        _, close = collector.fetch_latest()
        return close, cfg["name"]
    except Exception as exc:  # noqa: BLE001
        print(f"[警告] 金价获取失败，本次不写入：{exc}", file=sys.stderr)
        return None, cfg["name"]


def run(dry_run: bool, offline: bool) -> int:
    date = today_beijing()
    print(f"=== 每日情报 {date} | dry_run={dry_run} offline={offline}")

    # 1. 采集
    items, failed_sources = collect_all(build_collectors())
    items = within_hours(dedupe(items), hours=WINDOW_HOURS, now=now_beijing_iso())
    print(f"采集到 {len(items)} 条（去重与时间窗筛选后），失败源 {len(failed_sources)} 个")

    # 2. Dify
    webhook_url = None
    try:
        if offline:
            result = load_sample_result()
        else:
            result = DifyClient(api_key=get_secret("DIFY_API_KEY")).run(items, date)
        events = to_events(result.events, date)
        digest = result.digest
        print(f"Dify 返回 {len(events)} 条有效事件，消耗 {result.total_tokens} token")

        # to_events 对缺失 relevant 字段默认取 False，于是事件会被静默排除、
        # 情绪指数恒为 0——卡片上只是"利多 0 条 / 利空 0 条"，看不出异常。
        # 这道护栏把"悄悄降级"变成"看得见"。
        if events and not any(e.relevant for e in events):
            print(
                "[警告] 全部事件 relevant=False，情绪指数将恒为 0 —— "
                "检查 Dify 提示词是否仍输出 relevant 字段",
                file=sys.stderr,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[错误] Dify 环节失败：{exc}", file=sys.stderr)
        if not dry_run:
            try:
                webhook_url = get_secret("FEISHU_WEBHOOK_URL")
                send_to_feishu(webhook_url, build_fallback_text(date, str(exc)))
                print("已发送降级告警")
            except Exception as notify_exc:  # noqa: BLE001
                print(f"[错误] 降级告警也失败了：{notify_exc}", file=sys.stderr)
        return 1

    # 3. 计算与存储
    gold_close, gold_source = fetch_gold_close()
    if gold_close is None and gold_source:
        # 让金价断供出现在飞书卡片上，而不是只躺在 CI 日志里
        failed_sources.append(gold_source)
    index_row = build_index_row(date, events, gold_close)
    print(f"情绪指数 {index_row['sentiment_score']:+.4f}，金价 {gold_close}")

    append_events(events, events_path())
    append_index_row(index_row, index_path())

    # 4. 出图
    # 缺中文字体或金价都不该让日报失败，但都要在日志里说清楚。
    # 外层捕获字体缺失（configure_chinese_font 会抛），内层捕获金价缺失。
    index_df = read_index(index_path())
    plots: dict = {}
    try:
        plots["sentiment_trend"] = plot_sentiment_trend(
            index_df, 30, CHARTS_DIR / "sentiment_trend.png"
        )
        plots["event_distribution"] = plot_event_distribution(
            read_index_events_df(), 7, CHARTS_DIR / "event_distribution.png"
        )
        try:
            plots["sentiment_vs_gold"] = plot_sentiment_vs_gold(
                index_df, 30, CHARTS_DIR / "sentiment_vs_gold.png"
            )
        except ValueError as exc:
            print(f"[提示] 跳过金价对照图：{exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"[警告] 图表生成失败：{exc}", file=sys.stderr)
    print(f"已生成 {len(plots)} 张图")

    # 5. 推送
    if dry_run:
        print("[dry-run] 跳过飞书推送")
        return 0

    try:
        webhook_url = get_secret("FEISHU_WEBHOOK_URL")
        try:
            card = build_card(date, digest, index_row, failed_sources)
        except Exception as exc:  # noqa: BLE001
            # 卡片构造失败时（例如 Dify 返回的 digest 结构畸形）必须改发纯文本。
            # 只把异常打进 stderr 就 return 的话，手机上今天**什么都收不到**——
            # 那正是设计文档 §8"任何情况下都必须有输出"要防的情况。
            print(f"[警告] 卡片构造失败，改发纯文本：{exc}", file=sys.stderr)
            card = build_fallback_text(date, f"卡片构造失败：{exc}")
        send_to_feishu(webhook_url, card)
        print("已推送飞书")
    except Exception as exc:  # noqa: BLE001
        print(f"[错误] 飞书推送失败：{exc}", file=sys.stderr)
        return 1

    return 0


def read_index_events_df():
    """读取 events.csv；不存在时返回空表。

    列名直接复用 storage 的 EVENT_FIELDS，不要在这里再抄一份字面量——
    两处真相源会随字段演进悄悄漂移。
    """
    import pandas as pd

    path = events_path()
    if not path.exists():
        return pd.DataFrame(columns=EVENT_FIELDS)
    return pd.read_csv(path, dtype={"date": str})


def main() -> int:
    parser = argparse.ArgumentParser(description="每日情报流水线")
    parser.add_argument(
        "--dry-run", action="store_true", help="不推送飞书（其余照常执行）"
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="不调用 Dify，改用 samples/dify_response.json",
    )
    args = parser.parse_args()
    return run(dry_run=args.dry_run, offline=args.offline)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_main.py -v`
Expected: PASS（6 个用例）

- [ ] **Step 5: 本地端到端试跑（离线模式）**

```bash
python -m src.main --offline --dry-run
```

Expected: 打印采集条数、Dify 事件数、情绪指数与金价，生成三张图，最后输出 `[dry-run] 跳过飞书推送`。

- [ ] **Step 6: 本地端到端试跑（真实 Dify）**

```bash
export DIFY_API_KEY="app-你的key"
python -m src.main --dry-run
```

Expected: 与上一步类似，但事件来自真实 Dify 调用。**观察 token 消耗**，若明显高于 2 万，回到 Task 7 Step 4 收紧每条字数上限。

- [ ] **Step 7: 运行全部测试**

Run: `python -m pytest -v`
Expected: 全绿

- [ ] **Step 8: 提交**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: 主流程串联与 dry-run/offline 开关"
```

---

## Task 14: GitHub Actions 定时任务与上线

**Files:**
- Create: `.github/workflows/daily.yml`
- Create: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: `python -m src.main`、Secrets `DIFY_API_KEY`、`FEISHU_WEBHOOK_URL`
- Produces: 定时运行的流水线，并把 `data/`、`charts/` 回写进仓库

- [ ] **Step 1: 创建 `.env.example`**

```
# 复制为 .env 并填入真实值（.env 已被 gitignore）
DIFY_API_KEY=app-xxxxxxxxxxxxxxxx
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx
```

- [ ] **Step 2: 创建 `.github/workflows/daily.yml`**

```yaml
name: daily-digest

on:
  schedule:
    # GitHub 的 cron 用 UTC。23:30 UTC = 次日 07:30 北京时间。
    - cron: "30 23 * * *"
  workflow_dispatch:        # 支持手动触发，便于调试

permissions:
  contents: write           # 需要写权限才能把数据回写进仓库

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
          cache: pip

      - name: 安装中文字体
        run: |
          sudo apt-get update
          sudo apt-get install -y fonts-noto-cjk

      - name: 安装依赖
        run: pip install -r requirements.txt

      - name: 校验中文字体可用
        run: |
          python -c "
          from src.charts import configure_chinese_font
          configure_chinese_font()
          print('中文字体可用')
          "

      - name: 运行测试
        run: python -m pytest

      - name: 运行流水线
        env:
          DIFY_API_KEY: ${{ secrets.DIFY_API_KEY }}
          FEISHU_WEBHOOK_URL: ${{ secrets.FEISHU_WEBHOOK_URL }}
        run: python -m src.main

      - name: 回写数据与图表
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          if git diff --staged --quiet; then
            echo "无数据变更"
          else
            git commit -m "chore: 每日数据 $(date -u +%F)"
            git push
          fi
```

> `charts/` 被 gitignore 了，所以这里只回写 `data/`。图表每次现算，不进版本库。

- [ ] **Step 3: 在 GitHub 上创建仓库并配置 Secrets**

> **这一步会产生对外可见的仓库，属于不可逆的公开动作，执行前与用户确认。**

1. 在 GitHub 新建仓库 `gold-sentiment-agent`（**Public**；私有仓库的 Actions 免费额度只有 2000 分钟/月，且看板与图片链接在私有库下不可访问）
2. 仓库 Settings → Secrets and variables → Actions → New repository secret，添加两条：
   - `DIFY_API_KEY`
   - `FEISHU_WEBHOOK_URL`

```bash
git remote add origin https://github.com/XYC-JIE/gold-sentiment-agent.git
git branch -M main
git push -u origin main
```

- [ ] **Step 4: 确认 Actions 用默认分支的配置**

`schedule` 触发只认默认分支上的 workflow 文件。推送后在仓库 Actions 页确认 `daily-digest` 已出现。若默认分支不是 `main`，到 Settings → Branches 改过来。

- [ ] **Step 5: 手动触发一次验证完整链路**

在 Actions 页面点 `daily-digest` → `Run workflow`。等待完成后检查：

1. 任务为绿色，日志中能看到采集条数、情绪指数、`已推送飞书`
2. 飞书收到卡片
3. 仓库 `data/` 下出现 `events.csv` 与 `daily_index.csv`，且有 bot 的提交
4. 下载该次运行的 artifacts（或本地复跑）确认三张图的中文正常
5. 日志里若有 `失败源 N 个`，记下是哪些

**另外必须单独确认「金价」这一项**——它是设计文档 §5.4 点名的分析价值支点，且已在开发期被证实有风险：本机（国内 IP）访问 stooq 时拿到的是 JS 反爬验证页而非 CSV。本机的探测结果**不能代表 CI**（stooq 的拦截像是按 IP 地域/信誉做的），但反过来也必须亲自验证，不能想当然。

具体查三件事：

1. 卡片上**没有**出现"现货黄金日线"这条失败告警
2. `data/daily_index.csv` 最新一行的 `gold_close` **非空**
3. `charts/` 下有 `sentiment_vs_gold.png`，且打开看两条线都画出来了

只要有任一条不满足，就说明 stooq 在 CI 上也被拦了。应对：换一个金价源（新浪财经 `hq.sinajs.cn` 或 Yahoo `GC=F` 之类，需要改 `GoldPriceCollector` 的解析部分），改完把 `docs/信源核验记录.md` 记上。**好消息是历史行情随处可得，中间断的那几天可以事后回填**，所以这不紧急，但不能不查。

> ⚠️ **换源时务必注意一处排序假设**：`fetch_latest()` 取的是**响应里顺序上的最后一条**，不是 `max(date)`。stooq 的日线是升序，所以现在是对的；但若换成降序返回的源（或将来 stooq 改了顺序），它会**静默返回最旧的一条价格**——不报错、格式也合法，只是数字全错。这是"看起来合理但是错的"最坏失效模式，而它恰好落在 §5.4 点名的分析价值支点上。换源时要么确认新源是升序，要么顺手把它改成按日期取最大值。

- [ ] **Step 6: 依据 CI 日志最终修剪信源**

这一步是 Task 3 Step 1 的收尾——**只有在这里，源的可达性判断才是可信的**，因为这里就是流水线的真实运行环境。

若 Step 5 的日志显示有失败源：

- 打开该次运行的「运行流水线」这一步，确认失败的源名
- 对每个失败源，**在 CI 环境里**单独验一次（临时加一步调试或本地挂代理跑同一个 URL），区分"被墙"与"真失效"
- 真失效的从 `sources.yaml` 移除或换替代源；被墙的留着（CI 里本来就能通）
- 更新 `docs/信源核验记录.md`，把"待 CI 验证"一行行结掉

若日志显示全部源可用，把记录表里的"待 CI 验证"直接改成"已在 CI 验证可用"。

- [ ] **Step 7: 更新 README.md**

写清楚：项目做什么、三层架构与各自职责、如何本地运行（含 `--dry-run` / `--offline`）、`.env` 需要哪些变量、如何新增信源（改 `sources.yaml`）、数据与指标的定义和已知局限（引用设计文档）。

- [ ] **Step 8: 连续观察三天**

每天收到卡片后核对一件事：**当天的情绪指数和当天金价涨跌方向是否大致一致**。目标是先积累感觉，不必急着下结论——一个星期七天里能有几天对不上是完全正常的（见设计文档「已知局限」）。

三天的数据也是阶段 5「准确率验证」的第一批素材。

- [ ] **Step 9: 提交**

```bash
git add .github/ .env.example README.md config/sources.yaml docs/信源核验记录.md
git commit -m "ci: GitHub Actions 每日定时任务，并按 CI 实测结果修剪信源"
git push
```

---

## 完成标准

阶段 0–4 全部完成的判据：

- [ ] `python -m pytest` 全绿
- [ ] 连续三天在 07:30 前后于飞书收到卡片
- [ ] 仓库 `data/` 下的 CSV 逐日增长，且当天只有一行
- [ ] 三张图的中文显示正常（在 CI 产物上确认，不只是本地）
- [ ] 人为把 `DIFY_API_KEY` 改错跑一次，确认收到的是降级告警文本而非静默失败
- [ ] 人为把 `sources.yaml` 里某个源的域名改错跑一次，确认日报里出现"N 个源抓取失败"且其余内容正常

最后两条是刻意制造的故障演练——**降级路径没被验证过，就等于不存在**。

---

## 后续（另行计划）

- **阶段 5：准确率验证** — 抽 50 条事件人工标注，算 `event_type` 分类准确率与 `direction` 判断准确率，出混淆矩阵。依据结果迭代 Task 7 的 Prompt。
- **阶段 6：静态看板页** — 生成 HTML 部署到 GitHub Pages，飞书卡片加上看板按钮。
