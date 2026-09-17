"""飞书自定义机器人推送。

注意：自定义机器人无法内嵌图片（富文本的 image 需要 image_key，
而上传图片需自建应用凭证）。因此卡片只放文字，图表通过看板链接查看。
"""
from __future__ import annotations

import requests

TIMEOUT_SECONDS = 15
DASHBOARD_BUTTON_TEXT = "查看历史看板"


def _tendency(score: float) -> str:
    # ±0.15 是"值得标注方向"的最小强度：归一化区间里靠中间的微弱波动只算噪声，
    # 不该被渲染成方向性判断，故归为"中性"。
    if score >= 0.15:
        return "偏多"
    if score <= -0.15:
        return "偏空"
    return "中性"


def _format_ai_news(items: list[dict]) -> str:
    if not items:
        return "**暂无**"
    lines = []
    for idx, item in enumerate(items, start=1):
        title = item.get("title", "")
        why = item.get("why", "")
        url = item.get("url", "")
        line = f"{idx}. **{title}**\n{why}"
        if url:
            line += f" [原文]({url})"
        lines.append(line)
    return "\n".join(lines)


def _format_gold_news(items: list[dict]) -> str:
    if not items:
        return "**暂无**"
    lines = []
    for idx, item in enumerate(items, start=1):
        summary = item.get("summary", "")
        direction = item.get("direction", "")
        strength = item.get("strength", "")
        url = item.get("url", "")
        line = f"{idx}. **[{direction} · {strength}/5]** {summary}"
        if url:
            line += f" [原文]({url})"
        lines.append(line)
    return "\n".join(lines)


def _format_calendar(items: list[dict]) -> str:
    if not items:
        return "今日无明确宏观事件"
    return "\n".join(f"· {i.get('time', '')} {i.get('event', '')}".strip() for i in items)


def build_card(
    date: str,
    digest: dict,
    index_row: dict,
    failed_sources: list[str],
    dashboard_url: str = "",
) -> dict:
    score = float(index_row.get("sentiment_score") or 0.0)
    header = f"📊 每日情报 · {date}"

    blocks: list[str] = []

    if failed_sources:
        joined = "、".join(failed_sources)
        blocks.append(f"⚠️ {len(failed_sources)} 个源抓取失败：{joined}")

    blocks.append("🤖 **AI 前沿**\n" + _format_ai_news(digest.get("ai_news", [])))

    gold_header = (
        f"🥇 **金银聚焦** · 情绪指数 {score:+.2f}（{_tendency(score)}）\n"
        f"利多 {index_row.get('bull_count', 0)} 条 / "
        f"利空 {index_row.get('bear_count', 0)} 条"
    )
    gold_block = gold_header + "\n" + _format_gold_news(digest.get("gold_news", []))

    conclusion = digest.get("gold_conclusion")
    if conclusion:
        gold_block += f"\n**综合判断**：{conclusion}"
    blocks.append(gold_block)

    blocks.append("📅 **今日紧盯**\n" + _format_calendar(digest.get("calendar", [])))

    elements: list[dict] = []
    for idx, content in enumerate(blocks):
        if idx:
            elements.append({"tag": "hr"})
        elements.append({"tag": "markdown", "content": content})

    if dashboard_url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": DASHBOARD_BUTTON_TEXT},
                "type": "primary",
                "url": dashboard_url,
            }],
        })

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": header},
                "template": "blue",
            },
            "elements": elements,
        },
    }


def build_fallback_text(date: str, reason: str) -> dict:
    """降级通道：主流程失败时至少发出一条纯文本，绝不静默。"""
    return {
        "msg_type": "text",
        "content": {
            "text": (
                f"📊 每日情报 · {date}\n\n"
                f"⚠️ 今日日报生成失败：{reason}\n"
                f"请查看 GitHub Actions 运行日志。"
            )
        },
    }


def send_to_feishu(webhook_url: str, payload: dict) -> None:
    resp = requests.post(webhook_url, json=payload, timeout=TIMEOUT_SECONDS)
    resp.raise_for_status()

    body = resp.json()
    if body.get("code", 0) != 0:
        raise RuntimeError(f"飞书返回错误：code={body.get('code')} msg={body.get('msg')}")
