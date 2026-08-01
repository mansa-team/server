import re
from dataclasses import dataclass


@dataclass
class DeviceInfo:
    browser: str
    os: str
    deviceType: str


def parseUserAgent(userAgent: str) -> DeviceInfo:
    if not userAgent:
        return DeviceInfo(
            browser="Unknown",
            os="Unknown",
            deviceType="desktop",
        )

    userAgent = userAgent.lower()

    browser = detectBrowser(userAgent)
    os = detectOS(userAgent)
    deviceType = detectDeviceType(userAgent)

    return DeviceInfo(
        browser=browser,
        os=os,
        deviceType=deviceType,
    )


def detectBrowser(ua: str) -> str:
    if "edg/" in ua or "edge/" in ua:
        return "Edge"

    if "chrome/" in ua and "chromium/" not in ua:
        return "Chrome"

    if "firefox/" in ua or "fx/" in ua:
        return "Firefox"

    if "safari/" in ua and "chrome/" not in ua:
        return "Safari"

    if "opera/" in ua or "opera mini" in ua:
        return "Opera"

    if "brave/" in ua:
        return "Brave"

    return "Unknown"


def detectOS(ua: str) -> str:
    osPatterns = [
        (r"windows nt 10\.0", "Windows"),
        (r"windows nt 6\.3", "Windows"),
        (r"windows nt 6\.2", "Windows"),
        (r"windows nt 6\.1", "Windows"),
        (r"windows phone (\d+[\.\d]*)", "Windows Phone"),
        (r"mac os x (\d+[\._\d]*)", "macOS"),
        (r"iphone os (\d+[\._\d]*)", "iOS"),
        (r"ipad.*os (\d+[\._\d]*)", "iPadOS"),
        (r"android (\d+[\.\d]*)", "Android"),
        (r"linux", "Linux"),
        (r"cros", "Chrome OS"),
        (r"freebsd", "FreeBSD"),
        (r"netbsd", "NetBSD"),
    ]

    for pattern, osName in osPatterns:
        if re.search(pattern, ua):
            return osName

    return "Unknown"


def detectDeviceType(ua: str) -> str:
    mobilePatterns = [
        r"mobile",
        r"android",
        r"iphone",
        r"ipod",
        r"windows phone",
        r"blackberry",
    ]

    tabletPatterns = [r"ipad", r"tab-\w", r"sm-t\d", r"kindle"]

    for pattern in tabletPatterns:
        if re.search(pattern, ua):
            return "tablet"

    for pattern in mobilePatterns:
        if re.search(pattern, ua):
            return "mobile"

    return "desktop"
