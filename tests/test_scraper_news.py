"""Regression: stockNews() parses Google News RSS into NOTICIAS records."""

import sys
from unittest.mock import MagicMock

# Stub research-repo `xango` module (main/app/scraper_b3/scraper.py:20
# `from xango import calculateInvestingScore` — absent here).
if "xango" not in sys.modules:
    _xango_stub = MagicMock()
    _xango_stub.calculateInvestingScore = MagicMock(return_value={})
    sys.modules["xango"] = _xango_stub

from main.app.scraper_b3.scraper import B3Scraper

RSS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<rss version="2.0"><channel><title>test - Google News</title>'
    "<item><title>N1</title><link>https://a</link><guid>x1</guid>"
    "<pubDate>Tue, 29 Sep 2026 12:00:00 GMT</pubDate><description>d1</description>"
    '<source url="https://s">suno.com.br</source></item>'
    "<item><title>N2</title><link>https://b</link><guid>x2</guid>"
    "<pubDate>Wed, 30 Sep 2026 13:00:00 GMT</pubDate><description>d2</description>"
    '<source url="https://s">info.com</source></item>'
    "</channel></rss>"
)


class _FakeResp:
    def __init__(self, text):
        self.text = text


def _scraper(text):
    # Bypass __init__ (hits network: cloudscraper + SELIC fetch).
    s = B3Scraper.__new__(B3Scraper)
    s.requests = MagicMock()
    s.requests.get.return_value = _FakeResp(text)
    return s


class TestStockNews:
    def test_parses_news_records(self):
        df = _scraper(RSS).stockNews("PETR4")
        recs = df["NOTICIAS"].iloc[0]
        assert [r["TITULO"] for r in recs] == ["N1", "N2"]
        assert recs[0]["SOURCE"] == "suno.com.br"
        assert "guid" not in recs[0] and "description" not in recs[0]
