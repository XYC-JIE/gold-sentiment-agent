from src.dedupe import dedupe, interleave_by_category, within_hours
from src.models import RawItem


def _item(title, url, source="源A", published_at="2026-09-15T08:00:00+08:00",
          category="ai"):
    return RawItem(
        title=title, url=url, source=source, category=category,
        published_at=published_at, content="",
    )


def test_interleave_alternates_ai_and_finance():
    """AI 与金融交替排列，同类内部保持原顺序。"""
    items = [
        _item("AI1", "https://a.com/1"),
        _item("AI2", "https://a.com/2"),
        _item("AI3", "https://a.com/3"),
        _item("FIN1", "https://b.com/1", category="finance"),
        _item("FIN2", "https://b.com/2", category="finance"),
    ]
    assert [i.title for i in interleave_by_category(items)] == [
        "AI1", "FIN1", "AI2", "FIN2", "AI3",
    ]


def test_interleave_keeps_positional_truncation_balanced():
    """这是它存在的理由：截掉后一半时两侧都还留有代表。

    实测背景：115 条里 Hacker News 的 20 条全被截掉，而排在 sources.yaml
    末尾的华尔街见闻留下 16 条——纯位置截断会让某一类整类消失。
    """
    items = [_item(f"AI{i}", f"https://a.com/{i}") for i in range(10)]
    items += [
        _item(f"FIN{i}", f"https://b.com/{i}", category="finance")
        for i in range(10)
    ]
    kept = interleave_by_category(items)[:10]
    assert sum(1 for i in kept if i.category == "ai") == 5
    assert sum(1 for i in kept if i.category != "ai") == 5


def test_interleave_handles_empty_and_single_sided():
    assert interleave_by_category([]) == []
    only_ai = [_item("AI", "https://a.com/1")]
    assert [i.title for i in interleave_by_category(only_ai)] == ["AI"]


def test_dedupe_removes_same_url():
    items = [_item("标题甲", "https://a.com/1"), _item("标题甲", "https://a.com/1")]
    assert len(dedupe(items)) == 1


def test_dedupe_is_case_and_whitespace_insensitive_on_title():
    items = [
        _item("Gold Rises", "https://a.com/1"),
        _item("  gold rises  ", "https://a.com/2"),
    ]
    assert len(dedupe(items)) == 1


def test_dedupe_removes_same_url_even_with_different_titles():
    """单靠标题键不应通过：URL 相同、标题不同也必须去掉重复。"""
    items = [
        _item("标题甲", "https://a.com/1"),
        _item("标题完全不同的乙", "https://a.com/1"),
    ]
    assert len(dedupe(items)) == 1


def test_dedupe_is_case_and_whitespace_insensitive_on_url():
    """URL 大小写与首尾空白归一化后相同，也应视为重复（标题故意不同）。"""
    items = [
        _item("标题甲", "https://A.com/1"),
        _item("标题乙", " https://a.com/1 "),
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


def test_within_hours_accepts_naive_now():
    """now 不带时区时按北京时间补齐，不应抛 naive/aware 比较错误。"""
    now = "2026-09-15T08:00:00"  # 无时区，按北京时间理解
    items = [
        _item("新", "https://a.com/1", published_at="2026-09-15T07:30:00+08:00"),
        _item("旧", "https://a.com/2", published_at="2026-09-10T07:30:00+08:00"),
    ]
    kept = within_hours(items, hours=24, now=now)
    assert [i.title for i in kept] == ["新"]
