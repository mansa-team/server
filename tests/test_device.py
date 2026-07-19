import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.app.authentication.device import parseUserAgent


class TestDeviceDetection:
    def test_parse_chrome_windows(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        result = parseUserAgent(ua)

        assert result.browser == "Chrome"
        assert "135" in result.browserVersion
        assert result.os == "Windows"
        assert result.deviceType == "desktop"

    def test_parse_firefox_windows(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0"
        result = parseUserAgent(ua)

        assert result.browser == "Firefox"
        assert "126" in result.browserVersion
        assert result.os == "Windows"

    def test_parse_safari_mac(self):
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
        result = parseUserAgent(ua)

        assert result.browser == "Safari"
        assert result.os == "macOS"

    def test_parse_chrome_android(self):
        ua = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36"
        result = parseUserAgent(ua)

        assert result.browser == "Chrome"
        assert result.os == "Android"
        assert result.deviceType == "mobile"

    def test_parse_safari_iphone(self):
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
        result = parseUserAgent(ua)

        assert result.os == "iOS"
        assert result.deviceType == "mobile"

    def test_parse_edge(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"
        result = parseUserAgent(ua)

        assert result.browser == "Edge"

    def test_parse_empty_user_agent(self):
        result = parseUserAgent("")

        assert result.browser == "Unknown"
        assert result.os == "Unknown"
        assert result.deviceType == "desktop"

    def test_parse_none_user_agent(self):
        result = parseUserAgent(None)

        assert result.browser == "Unknown"
        assert result.os == "Unknown"
