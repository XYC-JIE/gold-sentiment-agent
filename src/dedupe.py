"""去重与时间窗筛选。"""
from __future__ import annotations

from datetime import timedelta, timezone

from dateutil import parser as date_parser

from src.models import RawItem

# 本项目全局时间基准为北京时间。
BEIJING = timezone(timedelta(hours=8))


def interleave_by_category(items: list[RawItem]) -> list[RawItem]:
    """把 AI 类与金融类交替排列，同类内部保持原顺序。

    **为什么需要它**：Dify 预筛节点是按**位置**截断的（上限 60 条），而采集
    结果是按 sources.yaml 顺序拼接的——同一类的条目扎堆，排在后面的源会被
    整类截掉。实测就发生过：115 条里 Hacker News 的 20 条全没进预筛，而排在
    文件末尾的华尔街见闻留下 16 条。交替排列让位置截断天然保持两侧都有代表。

    注意这只是"让截断公平"，不改变截断本身——控制 token 是它的本职。
    """
    ai = [i for i in items if i.category == "ai"]
    other = [i for i in items if i.category != "ai"]

    result: list[RawItem] = []
    for idx in range(max(len(ai), len(other))):
        if idx < len(ai):
            result.append(ai[idx])
        if idx < len(other):
            result.append(other[idx])
    return result


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
    if now_dt.tzinfo is None:
        # 给无时区的 now 赋予北京时间（不是换算，语义即"这就是北京时间"）
        now_dt = now_dt.replace(tzinfo=BEIJING)
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
