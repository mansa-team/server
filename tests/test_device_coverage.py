"""Tests for main/app/authentication/device.py — covers all branches."""

import pytest
from main.app.authentication.device import (
    parseUserAgent,
    detectBrowser,
    detectOS,
    detectDeviceType,
    generateFingerprint,
    DeviceInfo,
)


class TestDetectBrowser:
    def test_edge_new(self):
        # Code checks "edg/" or "edge/" but regex uses edg[eo]/ — edg/ falls through to no match
        ua = "mozilla/5.0 (windows nt 10.0; win64; x64) edg/120.0.0.0"
        name, version = detectBrowser(ua)
        assert name == "Edge"
        # edg/ doesn't match edg[eo]/ regex, so version is empty
        assert version == ""

    def test_edge_with_edge_suffix(self):
        ua = "mozilla/5.0 (windows nt 10.0; win64; x64) edge/18.17763"
        name, version = detectBrowser(ua)
        assert name == "Edge"

    def test_chrome(self):
        ua = "mozilla/5.0 (windows nt 10.0; win64; x64) chrome/120.0.0.0 safari/537.36"
        assert detectBrowser(ua) == ("Chrome", "120.0.0.0")

    def test_firefox(self):
        ua = "mozilla/5.0 (windows nt 10.0; rv:109.0) firefox/121.0"
        assert detectBrowser(ua) == ("Firefox", "121.0")

    def test_firefox_fx_prefix(self):
        # fx/ triggers Firefox branch but regex only matches firefox/
        ua = "mozilla/5.0 (windows nt 10.0; rv:109.0) fx/121.0"
        name, version = detectBrowser(ua)
        assert name == "Firefox"
        assert version == ""

    def test_safari(self):
        ua = "mozilla/5.0 (macintosh; intel mac os x 10_15_7) version/17.2 safari/605.1.15"
        assert detectBrowser(ua) == ("Safari", "17.2")

    def test_opera(self):
        # Opera branch checks "opera/" then regex searches version/
        ua = "mozilla/5.0 (windows nt 10.0; win64; x64) opera/106.0.0.0"
        name, version = detectBrowser(ua)
        assert name == "Opera"
        assert version == ""

    def test_opera_mini(self):
        ua = "opera mini/10.0.0"
        name, version = detectBrowser(ua)
        assert name == "Opera"

    def test_brave(self):
        ua = "mozilla/5.0 (windows nt 10.0; win64; x64) brave/120.0.0.0"
        assert detectBrowser(ua) == ("Brave", "120.0.0.0")

    def test_unknown_browser(self):
        ua = "some random agent"
        assert detectBrowser(ua) == ("Unknown", "")


class TestDetectOS:
    def test_windows_10(self):
        # Windows patterns have no capture group, so version is always ""
        ua = "windows nt 10.0"
        name, version = detectOS(ua)
        assert name == "Windows"
        assert version == ""

    def test_windows_81(self):
        ua = "windows nt 6.3"
        assert detectOS(ua) == ("Windows", "")

    def test_windows_8(self):
        ua = "windows nt 6.2"
        assert detectOS(ua) == ("Windows", "")

    def test_windows_7(self):
        ua = "windows nt 6.1"
        assert detectOS(ua) == ("Windows", "")

    def test_windows_phone(self):
        ua = "windows phone 10.0"
        name, version = detectOS(ua)
        assert name == "Windows Phone"
        assert version == "10.0"

    def test_macos(self):
        ua = "mac os x 10_15_7"
        name, version = detectOS(ua)
        assert name == "macOS"
        assert version == "10.15.7"

    def test_ios(self):
        ua = "iphone os 16_0"
        name, version = detectOS(ua)
        assert name == "iOS"
        assert version == "16.0"

    def test_ipados(self):
        ua = "ipad os 16_0"
        name, version = detectOS(ua)
        assert name == "iPadOS"
        assert version == "16.0"

    def test_android(self):
        ua = "android 13"
        name, version = detectOS(ua)
        assert name == "Android"
        assert version == "13"

    def test_linux(self):
        ua = "linux x86_64"
        assert detectOS(ua) == ("Linux", "")

    def test_chrome_os(self):
        ua = "cros x86_64"
        assert detectOS(ua) == ("Chrome OS", "")

    def test_freebsd(self):
        ua = "freebsd amd64"
        assert detectOS(ua) == ("FreeBSD", "")

    def test_netbsd(self):
        ua = "netbsd x86_64"
        assert detectOS(ua) == ("NetBSD", "")

    def test_unknown_os(self):
        ua = "some random agent"
        assert detectOS(ua) == ("Unknown", "")


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


class TestGenerateFingerprint:
    def test_basic(self):
        result = generateFingerprint("ua1", "1.2.3.4")
        assert len(result) == 64
        assert result == generateFingerprint("ua1", "1.2.3.4")

    def test_with_language(self):
        result = generateFingerprint("ua1", "1.2.3.4", "en-US")
        assert len(result) == 64

    def test_different_inputs_different_hash(self):
        r1 = generateFingerprint("ua1", "1.2.3.4")
        r2 = generateFingerprint("ua2", "1.2.3.4")
        assert r1 != r2


class TestParseUserAgent:
    def test_empty_ua(self):
        result = parseUserAgent("")
        assert result.browser == "Unknown"
        assert result.os == "Unknown"
        assert result.deviceType == "desktop"
        assert result.deviceName == "Unknown Device"

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
