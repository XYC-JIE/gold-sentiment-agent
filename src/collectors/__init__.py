"""采集器注册表：按 sources.yaml 构建采集器，并容错地批量采集。"""
from __future__ import annotations

from src.collectors.base import Collector
from src.collectors.gold_price import GoldPriceCollector
from src.collectors.jin10 import Jin10Collector
from src.collectors.rss import RssCollector
from src.collectors.wallstreetcn import WallstreetcnCollector
from src.config import load_sources
from src.models import RawItem

_BUILDERS = {
    "rss": RssCollector,
    "jin10": Jin10Collector,
    "wallstreetcn": WallstreetcnCollector,
    "gold_price": GoldPriceCollector,
}

__all__ = ["build_collectors", "collect_all", "Collector"]


def _validate(cfg: dict) -> None:
    """校验 type 与 category 的配套关系，配置错误要大声失败，不要静默降级。"""
    if cfg["type"] == "gold_price" and cfg["category"] != "market":
        raise ValueError(
            f"信源「{cfg['name']}」配置错误：type 为 gold_price 时 "
            f"category 必须是 market，当前为 {cfg['category']}"
        )


def build_collectors() -> list[Collector]:
    collectors: list[Collector] = []
    for cfg in load_sources():
        builder = _BUILDERS.get(cfg["type"])
        if builder is None:
            raise ValueError(f"未知的信源类型：{cfg['type']}")
        _validate(cfg)
        collectors.append(
            builder(name=cfg["name"], category=cfg["category"], url=cfg["url"])
        )
    return collectors


def collect_all(collectors: list[Collector]) -> tuple[list[RawItem], list[str]]:
    """逐个采集。任一源失败只记录、不中断其余源。"""
    items: list[RawItem] = []
    failed: list[str] = []

    for collector in collectors:
        if collector.category == "market":
            continue  # 金价走 fetch_latest()，不产出 RawItem
        try:
            items.extend(collector.fetch())
        except Exception:  # noqa: BLE001 - 单个源的问题不应影响整体
            failed.append(collector.name)

    return items, failed
