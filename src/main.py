"""主流程：采集 → Dify → 计算 → 出图 → 推送。"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.analysis import build_index_row, to_events
from src.charts import (
    plot_event_distribution,
    plot_sentiment_trend,
    plot_sentiment_vs_gold,
)
from src.collectors import build_collectors, collect_all
from src.collectors.gold_price import GoldPriceCollector
from src.config import CHARTS_DIR, DATA_DIR, get_secret, load_sources
from src.dedupe import dedupe, within_hours
from src.dify_client import DifyClient, load_sample_result
from src.notifier import build_card, build_fallback_text, send_to_feishu
from src.storage import EVENT_FIELDS, append_events, append_index_row, read_index

BEIJING = timezone(timedelta(hours=8))
WINDOW_HOURS = 30          # 覆盖一天多一点，避免因调度延迟漏掉新闻


# 这两个写成函数而不是模块级常量：模块级常量在 import 时求值，
# 测试里 patch DATA_DIR 将不会生效，会写进真实目录。
def events_path() -> Path:
    return DATA_DIR / "events.csv"


def index_path() -> Path:
    return DATA_DIR / "daily_index.csv"


def today_beijing() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d")


def now_beijing_iso() -> str:
    return datetime.now(BEIJING).isoformat()


def fetch_gold_close() -> tuple[float | None, str]:
    """取金价。

    返回 (收盘价或 None, 信源名)。

    失败时返回 None 但不抛异常——金价缺失不该让整份日报失败。但**必须把
    信源名带出去**，好让调用方把它并进失败源列表、在飞书卡片上显式告警。
    否则金价断供只会留在 CI 日志的 stderr 里，而你不会去读那份日志：
    daily_index.csv 的 gold_close 列会一直空着，双轴对照图会一直不出，
    几天后才发现。这条通道的存在就是为了让这种情况当天就被看见。
    """
    cfg = next((s for s in load_sources() if s["type"] == "gold_price"), None)
    if cfg is None:
        return None, ""
    try:
        collector = GoldPriceCollector(
            name=cfg["name"], category=cfg["category"], url=cfg["url"]
        )
        _, close = collector.fetch_latest()
        return close, cfg["name"]
    except Exception as exc:  # noqa: BLE001
        print(f"[警告] 金价获取失败，本次不写入：{exc}", file=sys.stderr)
        return None, cfg["name"]


def run(dry_run: bool, offline: bool) -> int:
    date = today_beijing()
    print(f"=== 每日情报 {date} | dry_run={dry_run} offline={offline}")

    # 1. 采集
    items, failed_sources = collect_all(build_collectors())
    items = within_hours(dedupe(items), hours=WINDOW_HOURS, now=now_beijing_iso())
    print(f"采集到 {len(items)} 条（去重与时间窗筛选后），失败源 {len(failed_sources)} 个")

    # 2. Dify
    webhook_url = None
    try:
        if offline:
            result = load_sample_result()
        else:
            result = DifyClient(api_key=get_secret("DIFY_API_KEY")).run(items, date)
        events = to_events(result.events, date)
        digest = result.digest
        print(f"Dify 返回 {len(events)} 条有效事件，消耗 {result.total_tokens} token")

        # to_events 对缺失 relevant 字段默认取 False，于是事件会被静默排除、
        # 情绪指数恒为 0——卡片上只是"利多 0 条 / 利空 0 条"，看不出异常。
        # 这道护栏把"悄悄降级"变成"看得见"。
        if events and not any(e.relevant for e in events):
            print(
                "[警告] 全部事件 relevant=False，情绪指数将恒为 0 —— "
                "检查 Dify 提示词是否仍输出 relevant 字段",
                file=sys.stderr,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[错误] Dify 环节失败：{exc}", file=sys.stderr)
        if not dry_run:
            try:
                webhook_url = get_secret("FEISHU_WEBHOOK_URL")
                send_to_feishu(webhook_url, build_fallback_text(date, str(exc)))
                print("已发送降级告警")
            except Exception as notify_exc:  # noqa: BLE001
                print(f"[错误] 降级告警也失败了：{notify_exc}", file=sys.stderr)
        return 1

    # 3. 计算与存储
    gold_close, gold_source = fetch_gold_close()
    if gold_close is None and gold_source:
        # 让金价断供出现在飞书卡片上，而不是只躺在 CI 日志里
        failed_sources.append(gold_source)
    index_row = build_index_row(date, events, gold_close)
    print(f"情绪指数 {index_row['sentiment_score']:+.4f}，金价 {gold_close}")

    append_events(events, events_path())
    append_index_row(index_row, index_path())

    # 4. 出图
    # 缺中文字体或金价都不该让日报失败，但都要在日志里说清楚。
    # 外层捕获字体缺失（configure_chinese_font 会抛），内层捕获金价缺失。
    index_df = read_index(index_path())
    plots: dict = {}
    try:
        plots["sentiment_trend"] = plot_sentiment_trend(
            index_df, 30, CHARTS_DIR / "sentiment_trend.png"
        )
        plots["event_distribution"] = plot_event_distribution(
            read_index_events_df(), 7, CHARTS_DIR / "event_distribution.png"
        )
        try:
            plots["sentiment_vs_gold"] = plot_sentiment_vs_gold(
                index_df, 30, CHARTS_DIR / "sentiment_vs_gold.png"
            )
        except ValueError as exc:
            print(f"[提示] 跳过金价对照图：{exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"[警告] 图表生成失败：{exc}", file=sys.stderr)
    print(f"已生成 {len(plots)} 张图")

    # 5. 推送
    if dry_run:
        print("[dry-run] 跳过飞书推送")
        return 0

    try:
        webhook_url = get_secret("FEISHU_WEBHOOK_URL")
        try:
            card = build_card(date, digest, index_row, failed_sources)
        except Exception as exc:  # noqa: BLE001
            # 卡片构造失败时（例如 Dify 返回的 digest 结构畸形）必须改发纯文本。
            # 只把异常打进 stderr 就 return 的话，手机上今天**什么都收不到**——
            # 那正是设计文档 §8"任何情况下都必须有输出"要防的情况。
            print(f"[警告] 卡片构造失败，改发纯文本：{exc}", file=sys.stderr)
            card = build_fallback_text(date, f"卡片构造失败：{exc}")
        send_to_feishu(webhook_url, card)
        print("已推送飞书")
    except Exception as exc:  # noqa: BLE001
        print(f"[错误] 飞书推送失败：{exc}", file=sys.stderr)
        return 1

    return 0


def read_index_events_df():
    """读取 events.csv；不存在时返回空表。

    列名直接复用 storage 的 EVENT_FIELDS，不要在这里再抄一份字面量——
    两处真相源会随字段演进悄悄漂移。
    """
    import pandas as pd

    path = events_path()
    if not path.exists():
        return pd.DataFrame(columns=EVENT_FIELDS)
    return pd.read_csv(path, dtype={"date": str})


def main() -> int:
    parser = argparse.ArgumentParser(description="每日情报流水线")
    parser.add_argument(
        "--dry-run", action="store_true", help="不推送飞书（其余照常执行）"
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="不调用 Dify，改用 samples/dify_response.json",
    )
    args = parser.parse_args()
    return run(dry_run=args.dry_run, offline=args.offline)


if __name__ == "__main__":
    raise SystemExit(main())
