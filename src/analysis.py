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
