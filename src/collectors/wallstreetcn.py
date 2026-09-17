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
