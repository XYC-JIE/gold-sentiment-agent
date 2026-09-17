from src.dedupe import dedupe, within_hours
from src.models import RawItem


def _item(title, url, source="源A", published_at="2026-09-15T08:00:00+08:00"):
    return RawItem(
        title=title, url=url, source=source, category="ai",
        published_at=published_at, content="",
    )


def test_dedupe_removes_same_url():
    items = [_item("标题甲", "https://a.com/1"), _item("标题甲", "https://a.com/1")]
    assert len(dedupe(items)) == 1


def test_dedupe_is_case_and_whitespace_insensitive_on_title():
    items = [
        _item("Gold Rises", "https://a.com/1"),
        _item("  gold rises  ", "https://a.com/2"),
    ]
    assert len(dedupe(items)) == 1


def test_dedupe_keeps_distinct_items():
    items = [_item("甲", "https://a.com/1"), _item("乙", "https://a.com/2")]
    assert len(dedupe(items)) == 2


def test_dedupe_preserves_first_occurrence_order():
    items = [_item("甲", "https://a.com/1"), _item("乙", "https://a.com/2"),
             _item("甲", "https://a.com/1")]
    assert [i.title for i in dedupe(items)] == ["甲", "乙"]


def test_within_hours_filters_old_items():
    now = "2026-09-15T08:00:00+08:00"
    items = [
        _item("新", "https://a.com/1", published_at="2026-09-15T07:30:00+08:00"),
        _item("旧", "https://a.com/2", published_at="2026-09-10T07:30:00+08:00"),
    ]
    kept = within_hours(items, hours=24, now=now)
    assert [i.title for i in kept] == ["新"]
