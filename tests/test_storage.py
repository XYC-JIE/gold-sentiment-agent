import pandas as pd
import pytest

from src.models import Event
from src.storage import (
    INDEX_FIELDS,
    append_events,
    append_index_row,
    read_index,
)


def _event(summary="甲"):
    return Event(
        date="2026-09-15", event_type="货币政策", direction="利多金银",
        strength=4, relevant=True, summary=summary, source="金十数据快讯",
        url="https://x.com/1", published_at="2026-09-15T10:00:00+08:00",
    )


def _row(date="2026-09-15"):
    return {
        "date": date, "sentiment_score": 0.4, "bull_count": 2, "bear_count": 1,
        "total_events": 3, "gold_close": 2498.7,
    }


def test_append_events_creates_file_with_header(tmp_path):
    path = tmp_path / "events.csv"
    written = append_events([_event()], path)
    assert written == 1

    df = pd.read_csv(path)
    assert list(df.columns)[:3] == ["date", "event_type", "direction"]
    assert df.iloc[0]["summary"] == "甲"


def test_append_events_is_idempotent_for_same_date(tmp_path):
    """同一天重复跑时，先删掉该日旧行再写，避免重复累积。"""
    path = tmp_path / "events.csv"
    append_events([_event("第一次")], path)
    append_events([_event("第二次"), _event("第二次")], path)

    df = pd.read_csv(path)
    assert len(df) == 2
    assert set(df["summary"]) == {"第二次"}


def test_append_events_keeps_other_dates(tmp_path):
    path = tmp_path / "events.csv"
    append_events([_event("前一天")], path)

    later = Event(
        date="2026-09-16", event_type="通胀", direction="利空金银", strength=2,
        relevant=True, summary="后一天", source="金十数据快讯",
        url="https://x.com/2", published_at="2026-09-16T10:00:00+08:00",
    )
    append_events([later], path)

    df = pd.read_csv(path)
    assert set(df["summary"]) == {"前一天", "后一天"}


def test_append_events_with_empty_list_does_nothing(tmp_path):
    path = tmp_path / "events.csv"
    assert append_events([], path) == 0
    assert not path.exists()


def test_append_events_rejects_mixed_dates(tmp_path):
    """跨日期的列表会让未被覆盖的那一天静默重复，必须在入口大声失败。"""
    path = tmp_path / "events.csv"
    later = Event(
        date="2026-09-16", event_type="通胀", direction="利空金银", strength=2,
        relevant=True, summary="后一天", source="金十数据快讯",
        url="https://x.com/2", published_at="2026-09-16T10:00:00+08:00",
    )

    with pytest.raises(ValueError, match="同一日期"):
        append_events([_event("前一天"), later], path)


def test_append_index_row_appends(tmp_path):
    path = tmp_path / "daily_index.csv"
    append_index_row(_row("2026-09-15"), path)
    append_index_row(_row("2026-09-16"), path)

    df = read_index(path)
    assert list(df.columns) == INDEX_FIELDS
    assert len(df) == 2


def test_append_index_row_replaces_same_date(tmp_path):
    path = tmp_path / "daily_index.csv"
    append_index_row(_row("2026-09-15"), path)
    updated = _row("2026-09-15")
    updated["sentiment_score"] = -0.9
    append_index_row(updated, path)

    df = read_index(path)
    assert len(df) == 1
    assert df.iloc[0]["sentiment_score"] == pytest.approx(-0.9)


def test_read_index_returns_empty_frame_when_missing(tmp_path):
    df = read_index(tmp_path / "nope.csv")
    assert df.empty
    assert list(df.columns) == INDEX_FIELDS
