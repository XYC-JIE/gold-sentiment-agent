from src.config import load_sources


def test_load_sources_returns_list():
    sources = load_sources()
    assert isinstance(sources, list)
    # 初版配了 11 个源，但 Task 3 的信源核验会剔除失效的。
    # 8 是底线：再少下去覆盖度就不够了。
    assert len(sources) >= 8


def test_every_source_has_required_keys():
    for s in load_sources():
        assert s["name"]
        assert s["type"] in {"rss", "jin10", "wallstreetcn", "gold_price"}
        assert s["category"] in {"ai", "finance", "market"}
        assert s["url"].startswith("http")
