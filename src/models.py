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
