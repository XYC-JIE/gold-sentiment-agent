from pathlib import Path

from src.collectors.rss import RssCollector

FIXTURE = Path(__file__).parent / "fixtures" / "rss_sample.xml"


def test_fetch_parses_rss_items(requests_mock):
    requests_mock.get(
        "https://openai.com/news/rss.xml",
        text=FIXTURE.read_text(encoding="utf-8"),
    )
    c = RssCollector(
        name="OpenAI News", category="ai", url="https://openai.com/news/rss.xml"
    )
    items = c.fetch()

    assert len(items) == 2
    assert items[0].title == "Introducing GPT-5.2"
    assert items[0].url == "https://openai.com/index/gpt-5-2"
    assert items[0].source == "OpenAI News"
    assert items[0].category == "ai"


def test_published_at_is_normalized_to_beijing(requests_mock):
    requests_mock.get(
        "https://openai.com/news/rss.xml",
        text=FIXTURE.read_text(encoding="utf-8"),
    )
    c = RssCollector(
        name="OpenAI News", category="ai", url="https://openai.com/news/rss.xml"
    )
    item = c.fetch()[0]
    # 09:00 GMT == 17:00 北京时间
    assert item.published_at.startswith("2026-09-15T17:00:00+08:00")


def test_html_in_description_is_stripped(requests_mock):
    xml = FIXTURE.read_text(encoding="utf-8").replace(
        "We are releasing GPT-5.2, our most capable model yet.",
        "&lt;p&gt;We are releasing &lt;b&gt;GPT-5.2&lt;/b&gt;.&lt;/p&gt;",
    )
    requests_mock.get("https://openai.com/news/rss.xml", text=xml)
    c = RssCollector(
        name="OpenAI News", category="ai", url="https://openai.com/news/rss.xml"
    )
    assert "<" not in c.fetch()[0].content
    assert "GPT-5.2" in c.fetch()[0].content
