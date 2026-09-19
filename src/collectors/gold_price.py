"""现货黄金价格采集器（新浪财经）。

**为什么不用 stooq**：原用的 `stooq.com/q/d/l/?s=xauusd&i=d` 已长期失效——
本机直连返回 JS 反爬验证页，CI 侧返回 HTTP 404，两个环境都复现。改用新浪
财经的现货黄金报价，国内外均可达。

**取到的是什么**：`fetch_latest()` 返回的是**取数时刻的最新价**，不是当日
收盘价。流水线每天早上跑，拿到的就是那时市场的最新成交价——用它做
「情绪 vs 金价」的对照比用前一日收盘更贴合，因为前者已包含到取数时刻为止的
信息。列名仍沿用 `gold_close`（改它要动 T9/T10/T11 三处，不值当）。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

from src.collectors.base import Collector
from src.models import RawItem

BEIJING = timezone(timedelta(hours=8))

# 新浪要求带 Referer，否则返回空内容
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}

# var hq_str_hf_XAU="4378.29,4341.620,...,2026-09-19,伦敦金（现货黄金）";
_PAYLOAD_RE = re.compile(r'"([^"]*)"')
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


class GoldPriceCollector(Collector):
    def fetch(self) -> list[RawItem]:
        raise NotImplementedError("金价是数值数据，请调用 fetch_latest()")

    def fetch_latest(self) -> tuple[str, float]:
        """返回 (日期, 最新价)。"""
        resp = self.get(headers=SINA_HEADERS)
        # 响应是 GBK；用 resp.content 自己解码，不要指望 requests 猜对
        text = resp.content.decode("gbk", errors="replace")

        matched = _PAYLOAD_RE.search(text)
        if not matched:
            raise ValueError(f"新浪返回格式不符，无法解析：{text[:200]}")
        payload = matched.group(1)

        fields = payload.split(",")
        if len(fields) < 13:
            raise ValueError(
                f"新浪返回字段数不足（{len(fields)}）：{payload[:200]}"
            )

        try:
            price = float(fields[0])
        except ValueError as exc:
            raise ValueError(f"新浪返回的最新价不是数字：{fields[0]!r}") from exc

        # 日期用正则找而不是按下标取：字段顺序若变，下标会静默取错值，
        # 而"取到一个像日期的字符串"这个判据不会。
        date_hits = _DATE_RE.findall(payload)
        if not date_hits:
            raise ValueError(f"新浪返回里找不到日期：{payload[:200]}")

        return date_hits[-1], price
