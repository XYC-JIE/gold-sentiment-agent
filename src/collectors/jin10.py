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
