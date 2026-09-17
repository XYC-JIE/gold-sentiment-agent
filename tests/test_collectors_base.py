import pytest
import requests_mock as rm_module

from src.collectors.base import Collector
from src.models import RawItem


class _DummyCollector(Collector):
    def fetch(self):
        resp = self.get()
        return [RawItem(
            title=resp.text,
            url="https://example.com/a",
            source=self.name,
            category=self.category,
            published_at="2026-09-15T00:00:00+08:00",
            content="",
        )]


def test_collector_stores_name_and_category():
    c = _DummyCollector(name="测试源", category="ai", url="https://example.com/feed")
    assert c.name == "测试源"
    assert c.category == "ai"


def test_fetch_returns_raw_items(requests_mock):
    requests_mock.get("https://example.com/feed", text="hello")
    c = _DummyCollector(name="测试源", category="ai", url="https://example.com/feed")
    items = c.fetch()
    assert len(items) == 1
    assert items[0].title == "hello"
    assert items[0].source == "测试源"


def test_get_retries_then_succeeds(requests_mock):
    requests_mock.get(
        "https://example.com/feed",
        [
            {"exc": ConnectionError},
            {"text": "second try ok"},
        ],
    )
    c = _DummyCollector(name="测试源", category="ai", url="https://example.com/feed")
    assert c.get().text == "second try ok"


def test_get_raises_after_exhausting_retries(requests_mock):
    requests_mock.get("https://example.com/feed", exc=ConnectionError)
    c = _DummyCollector(name="测试源", category="ai", url="https://example.com/feed")
    with pytest.raises(ConnectionError):
        c.get()
