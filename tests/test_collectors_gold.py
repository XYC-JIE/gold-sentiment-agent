from pathlib import Path

import pytest

from src.collectors.gold_price import GoldPriceCollector

FIXTURE = Path(__file__).parent / "fixtures" / "sina_gold.txt"
URL = "https://hq.sinajs.cn/list=hf_XAU"


def test_fetch_latest_parses_sina_payload(requests_mock):
    requests_mock.get(URL, content=FIXTURE.read_bytes())
    c = GoldPriceCollector(name="现货黄金", category="market", url=URL)
    date, price = c.fetch_latest()
    assert date == "2026-09-19"
    assert price == 4378.29


def test_fetch_latest_sends_referer(requests_mock):
    """新浪不带 Referer 会返回空——这个请求头是必需的，不是可选优化。"""
    requests_mock.get(URL, content=FIXTURE.read_bytes())
    c = GoldPriceCollector(name="现货黄金", category="market", url=URL)
    c.fetch_latest()
    assert "finance.sina.com.cn" in requests_mock.request_history[0].headers["Referer"]


def test_fetch_latest_raises_on_unexpected_body(requests_mock):
    requests_mock.get(URL, content="<html>反爬页面</html>".encode("gbk"))
    c = GoldPriceCollector(name="现货黄金", category="market", url=URL)
    with pytest.raises(ValueError, match="格式不符"):
        c.fetch_latest()


def test_fetch_latest_raises_on_non_numeric_price(requests_mock):
    body = 'var hq_str_hf_XAU="abc,1,2,3,4,5,6,7,8,0,0,0,2026-09-19,伦敦金";'
    requests_mock.get(URL, content=body.encode("gbk"))
    c = GoldPriceCollector(name="现货黄金", category="market", url=URL)
    with pytest.raises(ValueError, match="不是数字"):
        c.fetch_latest()
