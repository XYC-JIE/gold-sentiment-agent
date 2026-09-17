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
