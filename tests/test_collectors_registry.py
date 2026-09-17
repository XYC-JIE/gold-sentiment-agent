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
