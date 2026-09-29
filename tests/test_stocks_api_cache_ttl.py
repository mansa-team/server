import re

from main.app.stocks_api.cache import STALE_AFTER_SECONDS
from main.controller import stocksapi_controller as mod


def _seconds(ttl: str) -> int:
    match = re.fullmatch(r"(\d+)([smhd])", ttl)
    assert match, f"unparseable ttl: {ttl}"
    value, unit = match.groups()
    return int(value) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def test_long_endpoints_share_one_six_hour_constant():
    assert mod.STOCKS_TTL == "6h"
    assert _seconds(mod.STOCKS_TTL) == 6 * 3600


def test_cache_control_max_age_matches_the_decorator_ttl():
    assert mod.STOCKS_MAX_AGE == _seconds(mod.STOCKS_TTL)
    assert mod.LIVE_MAX_AGE == _seconds(mod.LIVE_TTL)


def test_endpoint_ttl_never_exceeds_the_staleness_policy():
    assert _seconds(mod.STOCKS_TTL) <= STALE_AFTER_SECONDS


def test_live_ttl_is_not_widened():
    assert mod.LIVE_TTL == "15s"
