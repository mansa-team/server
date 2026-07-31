"""Tests for main/app/authentication/device.py — covers all branches."""

import pytest
from main.app.authentication.device import (
    parseUserAgent,
    detectBrowser,
    detectOS,
    detectDeviceType,
    DeviceInfo,
)


class TestDetectBrowser:
    def test_edge_new(self):
        ua = "mozilla/5.0 (windows nt 10.0; win64; x64) edg/120.0.0.0"
        assert detectBrowser(ua) == "Edge"

    def test_edge_with_edge_suffix(self):
        ua = "mozilla/5.0 (windows nt 10.0; win64; x64) edge/18.17763"
        assert detectBrowser(ua) == "Edge"

    def test_chrome(self):
        ua = "mozilla/5.0 (windows nt 10.0; win64; x64) chrome/120.0.0.0 safari/537.36"
        assert detectBrowser(ua) == "Chrome"

    def test_firefox(self):
        ua = "mozilla/5.0 (windows nt 10.0; rv:109.0) firefox/121.0"
        assert detectBrowser(ua) == "Firefox"

    def test_firefox_fx_prefix(self):
        ua = "mozilla/5.0 (windows nt 10.0; rv:109.0) fx/121.0"
        assert detectBrowser(ua) == "Firefox"

    def test_safari(self):
        ua = "mozilla/5.0 (macintosh; intel mac os x 10_15_7) version/17.2 safari/605.1.15"
        assert detectBrowser(ua) == "Safari"

    def test_opera(self):
        ua = "mozilla/5.0 (windows nt 10.0; win64; x64) opera/106.0.0.0"
        assert detectBrowser(ua) == "Opera"

    def test_opera_mini(self):
        ua = "opera mini/10.0.0"
        assert detectBrowser(ua) == "Opera"

    def test_brave(self):
        ua = "mozilla/5.0 (windows nt 10.0; win64; x64) brave/120.0.0.0"
        assert detectBrowser(ua) == "Brave"

    def test_unknown_browser(self):
        ua = "some random agent"
        assert detectBrowser(ua) == "Unknown"


class TestDetectOS:
    def test_windows_10(self):
        ua = "windows nt 10.0"
        assert detectOS(ua) == "Windows"

    def test_windows_81(self):
        assert detectOS("windows nt 6.3") == "Windows"

    def test_windows_8(self):
        assert detectOS("windows nt 6.2") == "Windows"

    def test_windows_7(self):
        assert detectOS("windows nt 6.1") == "Windows"

    def test_windows_phone(self):
        ua = "windows phone 10.0"
        assert detectOS(ua) == "Windows Phone"

    def test_macos(self):
        ua = "mac os x 10_15_7"
        assert detectOS(ua) == "macOS"

    def test_ios(self):
        ua = "iphone os 16_0"
        assert detectOS(ua) == "iOS"

    def test_ipados(self):
        ua = "ipad os 16_0"
        assert detectOS(ua) == "iPadOS"

    def test_android(self):
        ua = "android 13"
        assert detectOS(ua) == "Android"

    def test_linux(self):
        ua = "linux x86_64"
        assert detectOS(ua) == "Linux"

    def test_chrome_os(self):
        ua = "cros x86_64"
        assert detectOS(ua) == "Chrome OS"

    def test_freebsd(self):
        ua = "freebsd amd64"
        assert detectOS(ua) == "FreeBSD"

    def test_netbsd(self):
        ua = "netbsd x86_64"
        assert detectOS(ua) == "NetBSD"

    def test_unknown_os(self):
        ua = "some random agent"
        assert detectOS(ua) == "Unknown"


class TestDetectDeviceType:
    def test_desktop(self):
        assert detectDeviceType("windows nt 10.0") == "desktop"

    def test_mobile_android(self):
        assert detectDeviceType("android 13 mobile") == "mobile"

    def test_mobile_iphone(self):
        assert detectDeviceType("iphone os 16_0") == "mobile"

    def test_mobile_ipod(self):
        assert detectDeviceType("ipod") == "mobile"

    def test_mobile_windows_phone(self):
        assert detectDeviceType("windows phone 10.0") == "mobile"

    def test_mobile_blackberry(self):
        assert detectDeviceType("blackberry") == "mobile"

    def test_tablet_ipad(self):
        assert detectDeviceType("ipad") == "tablet"

    def test_tablet_tab(self):
        assert detectDeviceType("tab-s8") == "tablet"

    def test_tablet_sm_t(self):
        assert detectDeviceType("sm-t870") == "tablet"

    def test_kindle(self):
        assert detectDeviceType("kindle fire") == "tablet"


class TestParseUserAgent:
    def test_empty_ua(self):
        result = parseUserAgent("")
        assert result.browser == "Unknown"
        assert result.os == "Unknown"
        assert result.deviceType == "desktop"

    def test_none_ua(self):
        result = parseUserAgent(None)
        assert result.browser == "Unknown"
        assert result.deviceType == "desktop"

    def test_full_chrome_windows(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        result = parseUserAgent(ua)
        assert result.browser == "Chrome"
        assert result.os == "Windows"
        assert result.deviceType == "desktop"

    def test_full_safari_macos(self):
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
        result = parseUserAgent(ua)
        assert result.browser == "Safari"
        assert result.os == "macOS"
