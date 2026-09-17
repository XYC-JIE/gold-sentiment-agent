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
    """写入某一日的事件。返回写入条数。同日已有数据会被替换。

    events 必须同属一个日期；跨日期的列表会被拒绝，因为覆盖语义只认一个
    日期键，其余日期的旧行不会被剔除，会静默重复。
    """
    if not events:
        return 0

    dates = {e.date for e in events}
    if len(dates) > 1:
        raise ValueError(
            f"append_events 一次只能写入同一日期的事件，收到 {len(dates)} 个"
            f"不同日期：{sorted(dates)}。请按日期分批调用。"
        )

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
