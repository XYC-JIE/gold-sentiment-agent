"""采集器基类：统一 HTTP 行为（超时 + 重试）。"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

import requests

from src.models import RawItem

TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3          # 首次 + 2 次重试
BACKOFF_SECONDS = (1, 2)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


class Collector(ABC):
    """所有采集器的父类。

    子类只需实现 fetch()，HTTP 细节由 get() 统一处理。
    """

    def __init__(self, name: str, category: str, url: str) -> None:
        self.name = name
        self.category = category
        self.url = url

    def get(self, params: dict | None = None, headers: dict | None = None) -> requests.Response:
        """发起 GET 请求，失败自动重试。耗尽重试后抛出最后一次异常。"""
        merged = {**DEFAULT_HEADERS, **(headers or {})}
        last_error: Exception | None = None

        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = requests.get(
                    self.url, params=params, headers=merged, timeout=TIMEOUT_SECONDS
                )
                resp.raise_for_status()
                return resp
            except Exception as exc:  # noqa: BLE001 - 需捕获 requests 各异常族
                last_error = exc
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(BACKOFF_SECONDS[attempt])

        assert last_error is not None
        raise last_error

    @abstractmethod
    def fetch(self) -> list[RawItem]:
        """抓取并解析该源，返回原始条目列表。"""
        raise NotImplementedError
