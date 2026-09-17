"""去重与时间窗筛选。"""
from __future__ import annotations

from datetime import timedelta, timezone

from dateutil import parser as date_parser

from src.models import RawItem

# 本项目全局时间基准为北京时间。
BEIJING = timezone(timedelta(hours=8))


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
