import hashlib
import re
from typing import Optional
from dataclasses import dataclass


@dataclass
class DeviceInfo:
    browser: str
    browserVersion: str
    os: str
    osVersion: str
    deviceType: str
    deviceName: str


def parseUserAgent(userAgent: str) -> DeviceInfo:
    if not userAgent:
        return DeviceInfo(
            browser="Unknown",
            browserVersion="",
            os="Unknown",
            osVersion="",
            deviceType="desktop",
            deviceName="Unknown Device",
        )

    userAgent = userAgent.lower()

    browser, browserVersion = detectBrowser(userAgent)
    os, osVersion = detectOS(userAgent)
    deviceType = detectDeviceType(userAgent)

    deviceName = f"{browser} on {os} {osVersion}".strip() if browser and os else "Unknown Device"

    return DeviceInfo(
        browser=browser,
        browserVersion=browserVersion,
        os=os,
        osVersion=osVersion,
        deviceType=deviceType,
        deviceName=deviceName,
    )


def detectBrowser(ua: str) -> tuple[str, str]:
    if "edg/" in ua or "edge/" in ua:
        match = re.search(r"edg[eo]/(\d+[\.\d]*)", ua)
        return ("Edge", match.group(1) if match else "")

    if "chrome/" in ua and "chromium/" not in ua:
        match = re.search(r"chrome/(\d+[\.\d]*)", ua)
        return ("Chrome", match.group(1) if match else "")

    if "firefox/" in ua or "fx/" in ua:
        match = re.search(r"firefox/(\d+[\.\d]*)", ua)
        return ("Firefox", match.group(1) if match else "")

    if "safari/" in ua and "chrome/" not in ua:
        match = re.search(r"version/(\d+[\.\d]*)", ua)
        return ("Safari", match.group(1) if match else "")

    if "opera/" in ua or "opera mini" in ua:
        match = re.search(r"version/(\d+[\.\d]*)", ua)
        return ("Opera", match.group(1) if match else "")

    if "brave/" in ua:
        match = re.search(r"brave/(\d+[\.\d]*)", ua)
        return ("Brave", match.group(1) if match else "")

    return ("Unknown", "")


def detectOS(ua: str) -> tuple[str, str]:
    osPatterns = [
        (r"windows nt 10\.0", "Windows", "10/11"),
        (r"windows nt 6\.3", "Windows", "8.1"),
        (r"windows nt 6\.2", "Windows", "8"),
        (r"windows nt 6\.1", "Windows", "7"),
        (r"windows phone (\d+[\.\d]*)", "Windows Phone", r"\1"),
        (r"mac os x (\d+[\._\d]*)", "macOS", r"\1"),
        (r"iphone os (\d+[\._\d]*)", "iOS", r"\1"),
        (r"ipad.*os (\d+[\._\d]*)", "iPadOS", r"\1"),
        (r"android (\d+[\.\d]*)", "Android", r"\1"),
        (r"linux", "Linux", ""),
        (r"cros", "Chrome OS", ""),
        (r"freebsd", "FreeBSD", ""),
        (r"netbsd", "NetBSD", ""),
    ]

    for pattern, osName, versionPattern in osPatterns:
        match = re.search(pattern, ua)
        if match:
            version = ""
            if versionPattern and match.groups():
                try:
                    version = match.group(1).replace("_", ".")
                except IndexError:
                    pass
            return (osName, version)

    return ("Unknown", "")


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


def generateFingerprint(userAgent: str, ipAddress: str, language: Optional[str] = None) -> str:
    raw = f"{userAgent}|{ipAddress}|{language or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]
