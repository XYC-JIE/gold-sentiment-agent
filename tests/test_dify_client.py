import json

import pytest

from src.dify_client import DifyClient
from src.models import RawItem

URL = "https://api.dify.ai/v1/workflows/run"


def _raw_items():
    return [
        RawItem(
            title="美联储官员放鸽",
            url="https://x.com/1",
            source="金十数据快讯",
            category="finance",
            published_at="2026-09-15T10:00:00+08:00",
            content="沃勒表示年内可能进一步降息",
        )
    ]


def _dify_response():
    return {
        "workflow_run_id": "wf-1",
        "data": {
            "status": "succeeded",
            "outputs": {
                "events_json": json.dumps([
                    {
                        "event_type": "货币政策",
                        "direction": "利多金银",
                        "strength": 4,
                        "relevant": True,
                        "summary": "美联储官员释放降息信号",
                        "source": "金十数据快讯",
                        "url": "https://x.com/1",
                        "published_at": "2026-09-15T10:00:00+08:00",
                    }
                ], ensure_ascii=False),
                "digest_json": json.dumps({
                    "ai_news": [],
                    "gold_news": [{"summary": "放鸽", "direction": "利多金银",
                                   "strength": 4, "url": "https://x.com/1"}],
                    "gold_conclusion": "偏多",
                    "calendar": [],
                }, ensure_ascii=False),
            },
            "total_tokens": 12345,
        },
    }


def test_run_workflow_parses_outputs(requests_mock):
    requests_mock.post(URL, json=_dify_response())
    client = DifyClient(api_key="app-test", url=URL)
    result = client.run(_raw_items(), date="2026-09-15")

    assert result.events[0]["event_type"] == "货币政策"
    assert result.digest["gold_conclusion"] == "偏多"
    assert result.total_tokens == 12345


def test_run_workflow_posts_expected_payload(requests_mock):
    requests_mock.post(URL, json=_dify_response())
    client = DifyClient(api_key="app-test", url=URL)
    client.run(_raw_items(), date="2026-09-15")

    body = requests_mock.request_history[0].json()
    assert body["response_mode"] == "blocking"
    assert body["inputs"]["date"] == "2026-09-15"
    assert "沃勒" in body["inputs"]["raw_items"]
    assert requests_mock.request_history[0].headers["Authorization"] == "Bearer app-test"


def test_run_workflow_raises_on_failed_status(requests_mock):
    payload = _dify_response()
    payload["data"]["status"] = "failed"
    payload["data"]["error"] = "model timeout"
    requests_mock.post(URL, json=payload)

    client = DifyClient(api_key="app-test", url=URL)
    with pytest.raises(RuntimeError, match="model timeout"):
        client.run(_raw_items(), date="2026-09-15")


def test_run_workflow_raises_on_malformed_json_output(requests_mock):
    payload = _dify_response()
    payload["data"]["outputs"]["events_json"] = "这不是 JSON"
    requests_mock.post(URL, json=payload)

    client = DifyClient(api_key="app-test", url=URL)
    with pytest.raises(RuntimeError, match="events_json 解析失败"):
        client.run(_raw_items(), date="2026-09-15")


def test_run_workflow_does_not_retry_4xx(requests_mock):
    """4xx 是确定性失败（密钥错、参数错），重试只是白等 20 秒。

    更要紧的是：`raise_for_status()` 抛出的异常只带状态码，而 Dify 把真正
    的原因放在响应体里。这里验证原因被捞回来、且只发了一次请求。
    """
    requests_mock.post(
        URL,
        status_code=401,
        text='{"code":"unauthorized","message":"invalid api key"}',
    )
    client = DifyClient(api_key="app-bad", url=URL)

    with pytest.raises(RuntimeError, match="invalid api key"):
        client.run(_raw_items(), date="2026-09-15")

    assert len(requests_mock.request_history) == 1


def test_run_workflow_strips_reasoning_blocks(requests_mock):
    """推理型模型会把 <think>...</think> 拼在 JSON 前面，必须先剥掉再解析。

    实测 DeepSeek 的推理型模型输出形如：
        <think>\n<!--dify-deepseek-reasoning-->...\n</think>[]
    不剥掉 json.loads 必挂。
    """
    payload = _dify_response()
    payload["data"]["outputs"]["events_json"] = (
        "<think>\n<!--dify-deepseek-reasoning-->Let me think.\n</think>"
        + payload["data"]["outputs"]["events_json"]
    )
    payload["data"]["outputs"]["digest_json"] = (
        "<think>\nthinking...\n</think>"
        + payload["data"]["outputs"]["digest_json"]
    )
    requests_mock.post(URL, json=payload)

    client = DifyClient(api_key="app-test", url=URL)
    result = client.run(_raw_items(), date="2026-09-15")

    assert result.events[0]["event_type"] == "货币政策"
    assert result.digest["gold_conclusion"] == "偏多"


def test_load_sample_result_reads_repo_sample():
    from src.dify_client import load_sample_result

    result = load_sample_result()
    assert isinstance(result.events, list)
    assert isinstance(result.digest, dict)
