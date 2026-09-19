"""图表生成。"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")           # 无显示环境（CI）必须有，否则会报错
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties, findfont

# Ubuntu CI 上装的是 fonts-noto-cjk，Windows 本地是 SimHei；按序尝试
FONT_CANDIDATES = ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "Microsoft YaHei", "SimHei"]

COLOR_BULL = "#c0392b"
COLOR_BEAR = "#27ae60"
COLOR_NEUTRAL = "#7f8c8d"


def _has_cjk_glyphs(font_path: str) -> bool:
    """字体能解析 ≠ 字体有汉字字形。

    实测：本机的 `HYZhongHeiTi-197.ttf`（汉仪中黑）`get_char_index('中')` 返回
    **0**（.notdef，即没有这个字形），而微软雅黑返回 1048。前者能被 findfont
    解析，画出来却是一片空白——只看"能否解析"会把它当可用字体收下。
    """
    try:
        from matplotlib.ft2font import FT2Font

        return FT2Font(font_path).get_char_index(ord("中")) != 0
    except Exception:  # noqa: BLE001 - 读不了就认为不可用
        return False


def _pick_available_cjk_font() -> str | None:
    """按候选列表找中文字体；都不匹配就在系统字体里搜一个 CJK 字体。

    **为什么需要兜底搜索**：同一份字体在不同发行版下的族名不一样。Ubuntu 的
    `fonts-noto-cjk` 装的是 `.ttc` 字体集合，里面 SC/JP/KR 多张字面，而
    matplotlib 未必把 "Noto Sans CJK SC" 这个名字枚举出来——实测 CI 上就只
    暴露了别的名字。靠精确族名匹配会在换环境时突然失效，而失效形态是
    "安静地出一张方框图"。

    返回选中的族名；真找不到返回 None。
    """
    try:
        findfont(FontProperties(family=FONT_CANDIDATES), fallback_to_default=False)
        return FONT_CANDIDATES[0]
    except ValueError:
        pass

    keywords = ("CJK", "WenQuanYi", "Source Han", "Noto Sans SC", "Hei", "Ming", "Kai")
    names = {f.name for f in font_manager.fontManager.ttflist}
    for name in sorted(names):
        if not any(k.lower() in name.lower() for k in keywords):
            continue
        try:
            path = findfont(FontProperties(family=[name]), fallback_to_default=False)
        except ValueError:
            continue
        # **能解析 ≠ 有汉字**。实测本机的 HYZhongHei（汉仪中黑）能被 findfont
        # 解析出来，但一个汉字字形都没有，渲染时刷屏 "Glyph missing"——
        # 等于把"安静出方框图"以更隐蔽的形式重新引入：护栏不会报错，因为搜索
        # "成功"了。所以这里必须验字形覆盖，而不是只验能否解析。
        if not _has_cjk_glyphs(path):
            continue
        # 找到了就把它放到候选列表最前，后续绘图都用它
        plt.rcParams["font.sans-serif"] = [name] + FONT_CANDIDATES
        return name
    return None


def configure_chinese_font() -> None:
    """设置中文字体，并**确认真的解析得到**。

    缺字体时 matplotlib 只在 logging 里嘀咕一句 `findfont: Font family not found`，
    图照画、PNG 照生成、测试照全绿，只是所有中文变成一片方框（豆腐块）。
    这是本模块唯一无法靠断言捕获的失败模式——所以这里主动解析一次，
    全落空就抛错，让问题当场暴露，而不是几天后在手机上看到一堆 □。

    CI 上实测踩过：精确族名匹配失败，护栏正确报错。故加了一层按关键字
    搜索系统字体的兜底（见 `_pick_available_cjk_font`）。
    """
    plt.rcParams["font.sans-serif"] = FONT_CANDIDATES
    plt.rcParams["axes.unicode_minus"] = False

    if _pick_available_cjk_font() is not None:
        return

    available = sorted({f.name for f in font_manager.fontManager.ttflist})
    raise ValueError(
        f"找不到任何可用中文字体，图表会渲染成方框。候选列表：{FONT_CANDIDATES}。"
        f"系统现有字体（{len(available)} 个）：{available[:40]}。"
        "Linux 上请安装 fonts-noto-cjk 或 fonts-wqy-zenhei；"
        "Windows 上确认已安装微软雅黑或黑体。"
    )


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
        # 不设这两行，pandas 会把列名直接当图例标题和 xtick 标签，图上出现英文
        pivot.index.name = "事件类型"
        pivot.columns.name = "方向"
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
