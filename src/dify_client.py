"""Dify Workflow API 客户端。"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from src.config import SAMPLES_DIR
from src.models import RawItem

API_URL = "https://api.dify.ai/v1/workflows/run"
TIMEOUT_SECONDS = 120       # LLM 链路较长，比采集的 15s 放宽
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (5, 15)


@dataclass(frozen=True)
class DifyResult:
    events: list[dict]
    digest: dict
    total_tokens: int


_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.DOTALL | re.IGNORECASE)


def _strip_reasoning(raw: str) -> str:
    """剥掉推理型模型夹带的 <think>...</think> 块。

    DeepSeek 的推理型模型（以及其他 thinking 模型）会把思考过程直接拼在
    回复前面，形成 `<think>...</think>[]` 这样的输出。不剥掉，json.loads 必挂。
    换模型能躲开，但代码不该赌下游换不换模型。
    """
    return _THINK_RE.sub("", raw).strip()


def _parse_json_field(raw: str | None, field_name: str) -> object:
    if raw is None:
        raise RuntimeError(f"Dify 返回中缺少 {field_name}")
    cleaned = _strip_reasoning(raw) if isinstance(raw, str) else raw
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(
            f"{field_name} 解析失败，原始内容前 200 字：{str(cleaned)[:200]}"
        ) from exc


class DifyClient:
    def __init__(self, api_key: str, url: str = API_URL) -> None:
        self.api_key = api_key
        self.url = url

    def run(self, items: list[RawItem], date: str) -> DifyResult:
        payload = {
            "inputs": {
                "raw_items": json.dumps(
                    [i.__dict__ for i in items], ensure_ascii=False
                ),
                "date": date,
            },
            "response_mode": "blocking",
            "user": "daily-intel",
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = requests.post(
                    self.url, json=payload, headers=headers, timeout=TIMEOUT_SECONDS
                )
                resp.raise_for_status()
                body = resp.json()
                data = body.get("data") or {}

                if data.get("status") != "succeeded":
                    raise RuntimeError(
                        f"Dify 工作流未成功：{data.get('error') or data.get('status')}"
                    )

                outputs = data.get("outputs") or {}
                return DifyResult(
                    events=_parse_json_field(outputs.get("events_json"), "events_json"),
                    digest=_parse_json_field(outputs.get("digest_json"), "digest_json"),
                    total_tokens=data.get("total_tokens", 0),
                )
            except RuntimeError:
                raise           # 业务错误不重试，重试也是同样结果
            except requests.HTTPError as exc:
                # 4xx 是确定性失败（密钥错、参数错、路径错），重试只是白等 20 秒；
                # 而且 `raise_for_status()` 抛出的异常**只带 URL 和状态码**，
                # Dify 把真正的原因放在响应体里（形如
                # {"code":"invalid_param","message":"..."}），会被丢掉。
                # 这里显式把它捞回来——错误信息里有没有原因，排查难度差一个数量级。
                response = exc.response
                status = response.status_code if response is not None else 0
                if 400 <= status < 500:
                    detail = (response.text or "")[:200] if response is not None else ""
                    raise RuntimeError(
                        f"Dify 返回 HTTP {status}：{detail}"
                    ) from exc
                last_error = exc            # 5xx 才重试
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(BACKOFF_SECONDS[attempt])
            except Exception as exc:  # noqa: BLE001 - 网络类错误才重试
                last_error = exc
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(BACKOFF_SECONDS[attempt])

        assert last_error is not None
        raise last_error


def load_sample_result() -> DifyResult:
    """读取 samples/dify_response.json，供 --offline 模式使用。

    **必须复用 `_parse_json_field`，不要直接 json.loads。** 样本文件是真实
    调用的产物，里面同样带 `<think>` 块；离线路径若不剥离，`--offline`
    一跑就挂，而线上路径（`run()`）却是好的——两条路径行为必须一致。
    """
    path = Path(SAMPLES_DIR) / "dify_response.json"
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)["data"]

    outputs = data["outputs"]
    return DifyResult(
        events=_parse_json_field(outputs.get("events_json"), "events_json"),
        digest=_parse_json_field(outputs.get("digest_json"), "digest_json"),
        total_tokens=data.get("total_tokens", 0),
    )
