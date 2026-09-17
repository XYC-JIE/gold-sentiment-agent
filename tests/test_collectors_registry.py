import pytest

from src.collectors import build_collectors, collect_all


def test_build_collectors_covers_every_source():
    collectors = build_collectors()
    # 底线与 test_config.py 保持一致（见那里的注释）
    assert len(collectors) >= 8


def test_collect_all_survives_one_failing_source(requests_mock, monkeypatch):
    """单个源抛异常时，其余源的结果仍应返回，失败源名进入第二个返回值。"""
    from src.collectors import base as base_module
    from src.collectors.rss import RssCollector

    # 真实重试会 sleep 1+2 秒，测试里压掉
    monkeypatch.setattr(base_module, "MAX_ATTEMPTS", 1)
    monkeypatch.setattr(base_module, "BACKOFF_SECONDS", (0,))

    requests_mock.get("https://ok.com/feed", text=(
        '<?xml version="1.0"?><rss version="2.0"><channel><item>'
        "<title>好源</title><link>https://ok.com/1</link>"
        "</item></channel></rss>"
    ))
    requests_mock.get("https://bad.com/feed", exc=ConnectionError)

    collectors = [
        RssCollector(name="好源", category="ai", url="https://ok.com/feed"),
        RssCollector(name="坏源", category="ai", url="https://bad.com/feed"),
    ]
    items, failed = collect_all(collectors)

    assert failed == ["坏源"]
    assert any(i.title == "好源" for i in items)


def test_collect_all_skips_market_sources():
    """真实配置里的 market 源（金价）必须被跳过，不得调用 fetch()。

    若跳过逻辑被删，GoldPriceCollector.fetch() 会抛 NotImplementedError，
    被 collect_all 吞进 failed —— 于是这里的 failed == [] 断言失败。
    """
    from src.collectors.gold_price import GoldPriceCollector

    market_collectors = [c for c in build_collectors() if c.category == "market"]
    # 防真空：配置里必须真有 market 源，且都是不会发网络请求的金价采集器
    assert market_collectors, "配置中缺少 category == market 的信源，本用例将失去意义"
    assert all(isinstance(c, GoldPriceCollector) for c in market_collectors)

    items, failed = collect_all(market_collectors)
    assert (items, failed) == ([], [])


def test_build_collectors_rejects_gold_price_with_wrong_category(monkeypatch):
    """type: gold_price 必须配 category: market，否则大声失败而非静默降级。"""
    bad_sources = [
        {
            "name": "现货黄金日线",
            "category": "finance",  # 误配：应为 market
            "type": "gold_price",
            "url": "https://stooq.com/q/d/l/?s=xauusd&i=d",
        }
    ]
    monkeypatch.setattr("src.collectors.load_sources", lambda: bad_sources)

    with pytest.raises(ValueError) as excinfo:
        build_collectors()
    assert "现货黄金日线" in str(excinfo.value)
