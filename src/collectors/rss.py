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
