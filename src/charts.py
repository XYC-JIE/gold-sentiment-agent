"""图表生成。"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")           # 无显示环境（CI）必须有，否则会报错
import matplotlib.pyplot as plt
import pandas as pd

# Ubuntu CI 上装的是 fonts-noto-cjk，Windows 本地是 SimHei；按序尝试
FONT_CANDIDATES = ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "Microsoft YaHei", "SimHei"]

COLOR_BULL = "#c0392b"
COLOR_BEAR = "#27ae60"
COLOR_NEUTRAL = "#7f8c8d"


def configure_chinese_font() -> None:
    """设置中文字体。不设会得到一片方框（豆腐块），且不会有任何报错。"""
    plt.rcParams["font.sans-serif"] = FONT_CANDIDATES
    plt.rcParams["axes.unicode_minus"] = False


def _tail(df: pd.DataFrame, days: int) -> pd.DataFrame:
    return df.tail(days).copy()


def _save(fig, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


def plot_sentiment_trend(df: pd.DataFrame, days: int, out_path: Path) -> Path:
    """近 N 日情绪指数折线，带 0 轴基准。"""
    configure_chinese_font()
    fig, ax = plt.subplots(figsize=(9, 4))

    data = _tail(df, days)
    if not data.empty:
        ax.plot(data["date"], data["sentiment_score"], marker="o", color="#2c3e50")
        for label in ax.get_xticklabels():
            label.set_rotation(45)
            label.set_ha("right")

    ax.axhline(0, color="#bdc3c7", linewidth=1, linestyle="--")
    ax.set_ylim(-1.05, 1.05)
    ax.set_ylabel("情绪指数")
    ax.set_title(f"近 {days} 日金银情绪指数")
    ax.grid(alpha=0.3)
    return _save(fig, out_path)


def recent_event_rows(events_df: pd.DataFrame, days: int) -> pd.DataFrame:
    """取最近 days 个自然日的**全部**事件行。

    注意这是按日期切，不是按行数切。这里**不能**用 `_tail()`：events 表一天
    有多行，`df.tail(7)` 取的是"最后 7 条事件"而不是"最后 7 天"，实际可能只
    覆盖一两天，图上却标着"近 7 日"。

    单独抽成函数是为了能被直接断言——图表输出难以验证语义，这个选择可以。
    """
    if events_df.empty:
        return events_df
    recent_dates = sorted(events_df["date"].unique())[-days:]
    return events_df[events_df["date"].isin(recent_dates)]


def plot_event_distribution(
    events_df: pd.DataFrame, days: int, out_path: Path
) -> Path:
    """近 N 日事件类型分布（按方向堆叠）。"""
    configure_chinese_font()
    fig, ax = plt.subplots(figsize=(9, 4))

    data = recent_event_rows(events_df, days)
    if not data.empty:
        pivot = (
            data.pivot_table(
                index="event_type", columns="direction",
                values="summary", aggfunc="count", fill_value=0,
            )
        )
        order = [c for c in ["利多金银", "中性", "利空金银"] if c in pivot.columns]
        pivot = pivot[order]
        colors = [
            {"利多金银": COLOR_BULL, "中性": COLOR_NEUTRAL, "利空金银": COLOR_BEAR}[c]
            for c in order
        ]
        pivot.plot(kind="bar", stacked=True, ax=ax, color=colors)
        ax.set_ylabel("事件数")
        for label in ax.get_xticklabels():
            label.set_rotation(30)
            label.set_ha("right")

    ax.set_title(f"近 {days} 日事件类型分布")
    ax.grid(alpha=0.3, axis="y")
    return _save(fig, out_path)


def plot_sentiment_vs_gold(df: pd.DataFrame, days: int, out_path: Path) -> Path:
    """情绪指数与金价双轴对照图。"""
    configure_chinese_font()
    data = _tail(df, days).dropna(subset=["gold_close"])
    if data.empty:
        raise ValueError("无有效金价数据，无法绘制对照图")

    fig, ax1 = plt.subplots(figsize=(9, 4))
    ax1.plot(data["date"], data["sentiment_score"], marker="o", color="#2c3e50")
    ax1.axhline(0, color="#bdc3c7", linewidth=1, linestyle="--")
    ax1.set_ylabel("情绪指数", color="#2c3e50")
    ax1.set_ylim(-1.05, 1.05)

    ax2 = ax1.twinx()
    ax2.plot(data["date"], data["gold_close"], marker="s", color=COLOR_BULL)
    ax2.set_ylabel("金价（美元/盎司）", color=COLOR_BULL)

    for label in ax1.get_xticklabels():
        label.set_rotation(45)
        label.set_ha("right")

    ax1.set_title(f"近 {days} 日情绪指数与金价对照")
    ax1.grid(alpha=0.3)
    return _save(fig, out_path)
