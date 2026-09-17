from pathlib import Path

import pytest

from src.collectors.gold_price import GoldPriceCollector

FIXTURE = Path(__file__).parent / "fixtures" / "stooq_xauusd.csv"
URL = "https://stooq.com/q/d/l/?s=xauusd&i=d"


def test_fetch_latest_returns_last_row(requests_mock):
    requests_mock.get(URL, text=FIXTURE.read_text(encoding="utf-8"))
    c = GoldPriceCollector(name="现货黄金日线", category="market", url=URL)
    date, close = c.fetch_latest()
    assert date == "2026-09-15"
    assert close == 2498.7


def test_fetch_latest_skips_rows_without_close(requests_mock):
    csv = "Date,Open,High,Low,Close,Volume\n2026-09-15,2490.1,2502.4,2488.0,,0\n"
    requests_mock.get(URL, text=csv)
    c = GoldPriceCollector(name="现货黄金日线", category="market", url=URL)
    with pytest.raises(ValueError, match="未找到有效收盘价"):
        c.fetch_latest()
