from pathlib import Path

import pytest

from src import main as main_module
from src.dify_client import DifyResult


@pytest.fixture
def patched_pipeline(monkeypatch, tmp_path):
    """把外部依赖全部替换掉，只验证编排逻辑。"""
    from src.models import RawItem

    monkeypatch.setattr(
        main_module, "build_collectors",
        lambda: [object()],
    )
    monkeypatch.setattr(
        main_module, "collect_all",
        lambda collectors: ([RawItem(
            title="测试条目", url="https://x.com/1", source="金十数据快讯",
            category="finance", published_at="2026-09-15T10:00:00+08:00",
            content="沃勒表示可能降息",
        )], []),
    )
    monkeypatch.setattr(main_module, "fetch_gold_close", lambda: (2498.7, "现货黄金日线"))
    monkeypatch.setattr(
        main_module, "load_sample_result",
        lambda: DifyResult(
            events=[{
                "event_type": "货币政策", "direction": "利多金银", "strength": 4,
                "relevant": True, "summary": "放鸽", "source": "金十数据快讯",
                "url": "https://x.com/1", "published_at": "2026-09-15T10:00:00+08:00",
            }],
            digest={"ai_news": [], "gold_news": [], "gold_conclusion": "偏多",
                    "calendar": []},
            total_tokens=1000,
        ),
    )
    monkeypatch.setattr(main_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main_module, "CHARTS_DIR", tmp_path / "charts")
    monkeypatch.setattr(main_module, "send_to_feishu", lambda url, payload: None)

    return tmp_path


def test_run_offline_writes_data_and_charts(patched_pipeline, monkeypatch):
    # 必须给 webhook：run() 走完流程会调 get_secret("FEISHU_WEBHOOK_URL")，
    # 缺了会抛异常使 run 返回 1，而本用例的真正断言（数据与图表）其实都过了
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/x")

    code = main_module.run(dry_run=False, offline=True)
    assert code == 0

    events_file = patched_pipeline / "events.csv"
    index_file = patched_pipeline / "daily_index.csv"
    assert events_file.exists()
    assert index_file.exists()

    import pandas as pd
    idx = pd.read_csv(index_file)
    assert idx.iloc[0]["total_events"] == 1
    assert idx.iloc[0]["gold_close"] == 2498.7
    assert (patched_pipeline / "charts" / "sentiment_trend.png").exists()


def test_run_sends_feishu_card(patched_pipeline, monkeypatch, capsys):
    sent = {}

    def _capture(url, payload):
        sent["payload"] = payload

    monkeypatch.setattr(main_module, "send_to_feishu", _capture)
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/x")

    main_module.run(dry_run=False, offline=True)
    assert sent["payload"]["msg_type"] == "interactive"


def test_run_dry_run_skips_sending(patched_pipeline, monkeypatch):
    sent = {}
    monkeypatch.setattr(
        main_module, "send_to_feishu",
        lambda url, payload: sent.setdefault("called", True),
    )
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/x")

    main_module.run(dry_run=True, offline=True)
    assert "called" not in sent


def test_run_sends_fallback_when_dify_fails(patched_pipeline, monkeypatch):
    sent = {}

    def _boom(*args, **kwargs):
        # 用 *args 而不是 (items, date)：run() 调的是零参 load_sample_result()，
        # 写死两参会 TypeError 而不是我们想测的那个 RuntimeError
        raise RuntimeError("Dify 工作流未成功：model timeout")

    monkeypatch.setattr(main_module, "load_sample_result", _boom)
    monkeypatch.setattr(
        main_module, "send_to_feishu",
        lambda url, payload: sent.update(payload),
    )
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/x")

    code = main_module.run(dry_run=False, offline=True)
    assert code == 1
    assert sent["msg_type"] == "text"
    assert "model timeout" in sent["content"]["text"]


def test_run_falls_back_to_text_when_card_build_fails(
    patched_pipeline, monkeypatch
):
    """卡片构造失败也必须让人收到东西——静默无输出是最坏情况。"""
    sent = {}

    def _boom(*args, **kwargs):
        raise TypeError("digest 结构畸形")

    monkeypatch.setattr(main_module, "build_card", _boom)
    monkeypatch.setattr(
        main_module, "send_to_feishu", lambda url, payload: sent.update(payload)
    )
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/x")

    code = main_module.run(dry_run=False, offline=True)
    assert code == 0
    assert sent["msg_type"] == "text"
    assert "卡片构造失败" in sent["content"]["text"]


def test_run_reports_gold_failure_in_card(patched_pipeline, monkeypatch):
    """金价断供必须出现在卡片上——它只躺在 stderr 里等于没有告警。"""
    sent = {}
    monkeypatch.setattr(
        main_module, "fetch_gold_close", lambda: (None, "现货黄金日线")
    )
    monkeypatch.setattr(
        main_module, "send_to_feishu", lambda url, payload: sent.update(payload)
    )
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/x")

    code = main_module.run(dry_run=False, offline=True)
    assert code == 0

    text = "\n".join(
        el["content"] for el in sent["card"]["elements"] if el.get("content")
    )
    assert "现货黄金日线" in text
    assert "抓取失败" in text


def test_run_actually_interleaves_before_sending(patched_pipeline, monkeypatch):
    """编排必须**真的调用** interleave_by_category。

    背景：这个函数写好、单测全绿，但 main.py 漏掉了调用点，于是修复完全失效
    而 6 个用例照样全过——因为桩数据只有单条 finance 条目，交替与否结果相同。
    所以这里断言调用**发生过**，而不是断言它的效果。
    """
    called = {}

    def _spy(items):
        called["arg"] = list(items)
        return items

    monkeypatch.setattr(main_module, "interleave_by_category", _spy)
    monkeypatch.setattr(main_module, "send_to_feishu", lambda url, p: None)
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/x")

    main_module.run(dry_run=False, offline=True)
    assert "arg" in called, "run() 没有调用 interleave_by_category"


def test_run_sends_fallback_on_unexpected_failure(patched_pipeline, monkeypatch):
    """上游炸了（配置读不到、磁盘写不进）也必须发出告警，不能静默崩掉。"""
    sent = {}

    def _boom(*args, **kwargs):
        raise FileNotFoundError("config/sources.yaml 不见了")

    monkeypatch.setattr(main_module, "build_collectors", _boom)
    monkeypatch.setattr(
        main_module, "send_to_feishu", lambda url, payload: sent.update(payload)
    )
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/x")

    code = main_module.run(dry_run=False, offline=True)
    assert code == 1
    assert sent["msg_type"] == "text"
    assert "未预期的失败" in sent["content"]["text"]
