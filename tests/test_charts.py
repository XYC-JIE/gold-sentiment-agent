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


def test_configure_chinese_font_resolves_a_real_font():
    """不能只断言"候选列表第一项非空"——那对 ["完全没有这个字体"] 也成立。

    缺字体时没有异常、PNG 照常生成，图上却全是方框。所以这里真的解析一次。
    """
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties, findfont

    from src.charts import FONT_CANDIDATES

    configure_chinese_font()
    assert plt.rcParams["axes.unicode_minus"] is False

    resolved = findfont(
        FontProperties(family=FONT_CANDIDATES), fallback_to_default=False
    )
    assert resolved


def test_has_cjk_glyphs_rejects_font_without_han_glyphs():
    """能解析 ≠ 有汉字字形。

    本机 HYZhongHei（汉仪中黑，HYZhongHeiTi-197.ttf）能被 findfont 解析，
    但 `get_char_index('中')` 返回 0（.notdef）——收下它会让渲染刷屏
    "Glyph missing"，护栏却不报错。所以兜底搜索必须验字形覆盖。
    """
    from matplotlib.font_manager import FontProperties, findfont

    from src.charts import _has_cjk_glyphs

    hy_path = findfont(
        FontProperties(family=["HYZhongHei"]), fallback_to_default=False
    )
    assert _has_cjk_glyphs(hy_path) is False

    yahei_path = findfont(
        FontProperties(family=["Microsoft YaHei"]), fallback_to_default=False
    )
    assert _has_cjk_glyphs(yahei_path) is True


def test_plot_raises_clear_error_when_no_cjk_font(monkeypatch):
    """一个中文字体都没有时必须抛错，而不是安静地产出一张豆腐块图。

    兜底搜索也要一起屏蔽——否则本机的微软雅黑会被搜到，这个用例就不再是在
    测「一个都没有」的场景了。
    """
    import src.charts as charts_module
    from matplotlib import font_manager

    monkeypatch.setattr(
        charts_module, "FONT_CANDIDATES", ["完全不存在的字体XYZ"]
    )
    monkeypatch.setattr(font_manager.fontManager, "ttflist", [])
    with pytest.raises(ValueError, match="找不到任何可用中文字体"):
        charts_module.configure_chinese_font()


def test_font_fallback_search_recovers_when_candidates_miss(monkeypatch):
    """候选列表全不匹配时，兜底搜索应当找回一个能用的中文字体。

    CI 上实测踩过：Ubuntu 的 fonts-noto-cjk 暴露的族名不在候选列表里，
    精确匹配失败导致图表全变方框（护栏正确报错并拦下了）。这层搜索就是
    为那种情况准备的。本机（Windows）用微软雅黑验证这条路径。
    """
    import matplotlib.pyplot as plt

    import src.charts as charts_module

    monkeypatch.setattr(
        charts_module, "FONT_CANDIDATES", ["完全不存在的字体XYZ"]
    )
    charts_module.configure_chinese_font()      # 不抛异常即算通过
    assert plt.rcParams["font.sans-serif"][0] != "完全不存在的字体XYZ"


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
