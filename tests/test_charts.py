import pandas as pd
import pytest

from src.charts import (
    configure_chinese_font,
    plot_event_distribution,
    plot_sentiment_trend,
    plot_sentiment_vs_gold,
    recent_event_rows,
)


def _index_df():
    return pd.DataFrame({
        "date": ["2026-09-13", "2026-09-14", "2026-09-15"],
        "sentiment_score": [0.2, -0.4, 0.5],
        "bull_count": [2, 1, 3],
        "bear_count": [1, 2, 0],
        "total_events": [3, 3, 3],
        "gold_close": [2480.0, 2475.5, 2498.7],
    })


def _events_df():
    return pd.DataFrame({
        "date": ["2026-09-14", "2026-09-15", "2026-09-15"],
        "event_type": ["货币政策", "通胀", "货币政策"],
        "direction": ["利多金银", "利空金银", "中性"],
        "strength": [4, 3, 2],
        "relevant": [True, True, True],
        "summary": ["甲", "乙", "丙"],
        "source": ["s", "s", "s"],
        "url": ["u1", "u2", "u3"],
        "published_at": ["t1", "t2", "t3"],
    })


def test_configure_chinese_font_sets_family():
    configure_chinese_font()
    import matplotlib.pyplot as plt

    assert plt.rcParams["font.sans-serif"][0]
    assert plt.rcParams["axes.unicode_minus"] is False


def test_plot_sentiment_trend_writes_file(tmp_path):
    out = plot_sentiment_trend(_index_df(), days=30, out_path=tmp_path / "trend.png")
    assert out.exists() and out.stat().st_size > 1000


def test_plot_event_distribution_writes_file(tmp_path):
    out = plot_event_distribution(
        _events_df(), days=7, out_path=tmp_path / "dist.png"
    )
    assert out.exists() and out.stat().st_size > 1000


def test_recent_event_rows_slices_by_date_not_by_row_count():
    """一天多行时，"最近 N 天"必须拿满这几天的全部事件行。

    若实现退回成 df.tail(days)，本用例只会剩 2 行（且同属一天），断言失败。
    """
    df = pd.DataFrame({
        "date": ["2026-09-13"] * 5 + ["2026-09-14"] * 5 + ["2026-09-15"] * 5,
        "event_type": ["货币政策"] * 15,
        "direction": ["利多金银"] * 15,
        "strength": [3] * 15,
        "relevant": [True] * 15,
        "summary": [f"事件{i}" for i in range(15)],
        "source": ["s"] * 15,
        "url": ["u"] * 15,
        "published_at": ["t"] * 15,
    })
    result = recent_event_rows(df, days=2)
    assert len(result) == 10                  # 最近两天各 5 行，不是 2 行
    assert set(result["date"]) == {"2026-09-14", "2026-09-15"}


def test_recent_event_rows_handles_empty_frame():
    empty = pd.DataFrame(columns=["date", "event_type", "direction"])
    assert recent_event_rows(empty, days=7).empty


def test_plot_sentiment_vs_gold_writes_file(tmp_path):
    out = plot_sentiment_vs_gold(
        _index_df(), days=30, out_path=tmp_path / "vs_gold.png"
    )
    assert out.exists() and out.stat().st_size > 1000


def test_plot_sentiment_trend_tolerates_empty_frame(tmp_path):
    empty = pd.DataFrame(columns=[
        "date", "sentiment_score", "bull_count", "bear_count",
        "total_events", "gold_close",
    ])
    out = plot_sentiment_trend(empty, days=30, out_path=tmp_path / "empty.png")
    assert out.exists()


def test_plot_sentiment_vs_gold_skips_when_no_gold_price(tmp_path):
    df = _index_df()
    df["gold_close"] = None
    with pytest.raises(ValueError, match="无有效金价"):
        plot_sentiment_vs_gold(df, days=30, out_path=tmp_path / "x.png")
