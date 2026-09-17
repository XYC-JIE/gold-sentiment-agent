import pytest

from src.notifier import build_card, build_fallback_text, send_to_feishu

WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/test-hook"


def _digest():
    return {
        "ai_news": [
            {"title": "OpenAI 发布新模型", "why": "推理能力显著提升",
             "url": "https://openai.com/1"}
        ],
        "gold_news": [
            {"summary": "美联储官员放鸽", "direction": "利多金银",
             "strength": 4, "url": "https://x.com/1"}
        ],
        "gold_conclusion": "短期偏多",
        "calendar": [{"time": "20:30", "event": "美国 CPI 同比"}],
    }


def _index_row():
    return {"date": "2026-09-15", "sentiment_score": 0.42, "bull_count": 3,
            "bear_count": 1, "total_events": 4, "gold_close": 2498.7}


def _all_text(payload: dict) -> str:
    """把卡片里所有文本拼起来，方便断言。"""
    card = payload["card"]
    parts = [card["header"]["title"]["content"]]
    for el in card["elements"]:
        if el.get("content"):
            parts.append(el["content"])
        for action in el.get("actions", []):
            parts.append(action["text"]["content"])
    return "\n".join(parts)


def test_card_contains_all_sections():
    payload = build_card("2026-09-15", _digest(), _index_row(), failed_sources=[])
    text = _all_text(payload)

    assert "2026-09-15" in text
    assert "AI 前沿" in text
    assert "OpenAI 发布新模型" in text
    assert "推理能力显著提升" in text
    assert "金银聚焦" in text
    assert "美联储官员放鸽" in text
    assert "短期偏多" in text
    assert "美国 CPI 同比" in text


def test_card_shows_sentiment_score_and_tendency():
    payload = build_card("2026-09-15", _digest(), _index_row(), failed_sources=[])
    text = _all_text(payload)
    assert "+0.42" in text
    assert "偏多" in text


def test_card_warns_about_failed_sources():
    payload = build_card(
        "2026-09-15", _digest(), _index_row(), failed_sources=["量子位", "CNBC Markets"]
    )
    assert "2 个源抓取失败" in _all_text(payload)
    assert "量子位" in _all_text(payload)


def test_card_omits_warning_when_no_failures():
    payload = build_card("2026-09-15", _digest(), _index_row(), failed_sources=[])
    assert "抓取失败" not in _all_text(payload)


def test_card_includes_dashboard_button_when_url_given():
    payload = build_card(
        "2026-09-15", _digest(), _index_row(), failed_sources=[],
        dashboard_url="https://example.github.io/dashboard/",
    )
    text = _all_text(payload)
    assert "查看历史看板" in text


def test_card_handles_empty_ai_and_gold_sections():
    digest = {"ai_news": [], "gold_news": [], "gold_conclusion": "",
              "calendar": []}
    payload = build_card("2026-09-15", digest, _index_row(), failed_sources=[])
    text = _all_text(payload)
    assert "AI 前沿" in text
    assert "暂无" in text


def test_send_to_feishu_posts_payload(requests_mock):
    requests_mock.post(WEBHOOK, json={"code": 0, "msg": "success"})
    payload = build_card("2026-09-15", _digest(), _index_row(), failed_sources=[])
    send_to_feishu(WEBHOOK, payload)
    assert requests_mock.request_history[0].json() == payload


def test_send_to_feishu_raises_on_nonzero_code(requests_mock):
    requests_mock.post(WEBHOOK, json={"code": 9499, "msg": "Bad Request"})
    payload = build_card("2026-09-15", _digest(), _index_row(), failed_sources=[])
    with pytest.raises(RuntimeError, match="飞书返回错误"):
        send_to_feishu(WEBHOOK, payload)


def test_fallback_text_mentions_reason():
    payload = build_fallback_text("2026-09-15", "Dify 调用失败")
    assert payload["msg_type"] == "text"
    assert "Dify 调用失败" in payload["content"]["text"]
    assert "2026-09-15" in payload["content"]["text"]
