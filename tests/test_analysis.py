import pytest

from src.analysis import build_index_row, compute_sentiment_score, to_events
from src.models import Event


def _event(direction="利多金银", strength=5, relevant=True, event_type="货币政策"):
    return Event(
        date="2026-09-15", event_type=event_type, direction=direction,
        strength=strength, relevant=relevant, summary="测试",
        source="源", url="https://x.com/1", published_at="2026-09-15T10:00:00+08:00",
    )


def test_all_bullish_max_strength_scores_one():
    events = [_event(strength=5) for _ in range(3)]
    assert compute_sentiment_score(events) == 1.0


def test_all_bearish_max_strength_scores_minus_one():
    events = [_event(direction="利空金银", strength=5) for _ in range(2)]
    assert compute_sentiment_score(events) == -1.0


def test_balanced_bull_bear_scores_zero():
    events = [_event(strength=5), _event(direction="利空金银", strength=5)]
    assert compute_sentiment_score(events) == 0.0


def test_neutral_counts_in_denominator():
    """中性事件符号为 0 但仍进分母——这是归一化的关键，别改成剔除。"""
    events = [_event(strength=5), _event(direction="中性", strength=5)]
    assert compute_sentiment_score(events) == 0.5


def test_empty_returns_zero():
    assert compute_sentiment_score([]) == 0.0


def test_irrelevant_events_are_excluded():
    """relevant=False 的事件完全不参与计算，也不进分母。"""
    events = [_event(strength=5), _event(strength=5, relevant=False)]
    assert compute_sentiment_score(events) == 1.0


def test_unknown_direction_raises():
    events = [_event(direction="可能利多")]
    with pytest.raises(ValueError, match="未知的影响方向"):
        compute_sentiment_score(events)


def test_build_index_row_counts_bull_and_bear():
    events = [
        _event(direction="利多金银"),
        _event(direction="利多金银"),
        _event(direction="利空金银"),
        _event(direction="中性"),
        _event(direction="利空金银", relevant=False),
    ]
    row = build_index_row("2026-09-15", events, gold_close=2498.7)

    assert row["date"] == "2026-09-15"
    assert row["bull_count"] == 2
    assert row["bear_count"] == 1
    assert row["total_events"] == 4          # 只数 relevant 的
    assert row["gold_close"] == 2498.7


def test_build_index_row_handles_missing_gold_price():
    row = build_index_row("2026-09-15", [_event()], gold_close=None)
    assert row["gold_close"] is None


def test_to_events_converts_raw_dicts():
    raw = [{
        "event_type": "通胀", "direction": "利空金银", "strength": 3,
        "relevant": True, "summary": "CPI 超预期", "source": "金十数据快讯",
        "url": "https://x.com/1", "published_at": "2026-09-15T20:30:00+08:00",
    }]
    events = to_events(raw, date="2026-09-15")
    assert len(events) == 1
    assert events[0].event_type == "通胀"
    assert events[0].date == "2026-09-15"


def test_to_events_skips_malformed_entries():
    raw = [
        {"event_type": "通胀", "direction": "利空金银", "strength": 3,
         "relevant": True, "summary": "好的", "source": "s", "url": "u",
         "published_at": "2026-09-15T20:30:00+08:00"},
        {"direction": "利空金银"},                      # 缺字段
        {"event_type": "通胀", "direction": "利空金银", "strength": "高",
         "relevant": True, "summary": "强度不是数字", "source": "s", "url": "u",
         "published_at": "2026-09-15T20:30:00+08:00"},
    ]
    events = to_events(raw, date="2026-09-15")
    assert len(events) == 1
    assert events[0].summary == "好的"


def test_to_events_survives_overflow_published_at():
    """超长数字串会让 dateutil 内部溢出，不能连累整天的事件。"""
    raw = [{
        "event_type": "通胀", "direction": "利空金银", "strength": 3,
        "relevant": True, "summary": "畸形时间戳", "source": "s", "url": "u",
        "published_at": "999999999999999999999",
    }]
    events = to_events(raw, date="2026-09-15")
    assert len(events) == 1
    assert events[0].published_at == "999999999999999999999"


def test_to_events_coerces_non_string_published_at_to_str():
    """非字符串的 published_at 兜底后必须是 str，不能违反类型注解。"""
    raw = [{
        "event_type": "通胀", "direction": "利空金银", "strength": 3,
        "relevant": True, "summary": "整数时间戳", "source": "s", "url": "u",
        "published_at": 12345,
    }]
    events = to_events(raw, date="2026-09-15")
    assert len(events) == 1
    assert isinstance(events[0].published_at, str)
