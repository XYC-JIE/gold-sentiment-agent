from pathlib import Path

from src.collectors.jin10 import Jin10Collector
from src.collectors.wallstreetcn import WallstreetcnCollector

FIXTURES = Path(__file__).parent / "fixtures"


def test_jin10_parses_flash_items(requests_mock):
    requests_mock.get(
        "https://flash-api.jin10.com/get_flash_list",
        text=(FIXTURES / "jin10_flash.json").read_text(encoding="utf-8"),
    )
    c = Jin10Collector(
        name="金十数据快讯", category="finance",
        url="https://flash-api.jin10.com/get_flash_list",
    )
    items = c.fetch()

    assert len(items) == 2
    assert "沃勒" in items[0].content
    assert items[0].source == "金十数据快讯"
    assert items[0].url == "https://www.jin10.com/flash/20260915100001"
    assert items[0].published_at.startswith("2026-09-15T10:00:01+08:00")


def test_jin10_skips_entries_without_content(requests_mock):
    payload = '{"status": 200, "data": [{"id": "1", "time": "2026-09-15 10:00:00", "data": {}}]}'
    requests_mock.get("https://flash-api.jin10.com/get_flash_list", text=payload)
    c = Jin10Collector(
        name="金十数据快讯", category="finance",
        url="https://flash-api.jin10.com/get_flash_list",
    )
    assert c.fetch() == []


def test_wallstreetcn_parses_lives(requests_mock):
    requests_mock.get(
        "https://api-one.wallstcn.com/apiv1/content/lives",
        text=(FIXTURES / "wallstreetcn_lives.json").read_text(encoding="utf-8"),
    )
    c = WallstreetcnCollector(
        name="华尔街见闻", category="finance",
        url="https://api-one.wallstcn.com/apiv1/content/lives",
    )
    items = c.fetch()

    assert len(items) == 2
    assert "CPI" in items[0].content
    assert items[0].url == "https://wallstreetcn.com/livenews/3188001"
    # 1789437200 == 2026-09-15 01:53:20 UTC == 09:53:20 北京时间
    assert items[0].published_at.startswith("2026-09-15T09:53:20+08:00")
