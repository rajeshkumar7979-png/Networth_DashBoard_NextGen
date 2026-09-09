# -------------------------------------------------
# Intelligence Data Gateway — shared HTTP seam.
#
# Every live provider call goes through _http_get so tests can freeze the
# network by monkeypatching this single function. Never logs request URLs or
# credentials. Timeouts map to ProviderTimeout; any HTTP non-200 to
# ProviderUnavailable; JSON decode failures to ProviderMalformed.
# -------------------------------------------------
from __future__ import annotations

import re

import requests

from .errors import ProviderMalformed, ProviderTimeout, ProviderUnavailable

DEFAULT_TIMEOUT = (10, 30)

# Strip every URL query segment ("...?k=v&k2=v2") from error text. requests'
# own exceptions embed the FULL request URL including query params, so a FRED
# api_key that lives in the query string must never surface in our messages.
_QUERY_SCRUB = re.compile(r"\?[^\s\"'<>]+")


def _sanitize_error(text) -> str:
    return _QUERY_SCRUB.sub("?[redacted]", str(text or ""))


def _http_get(url, *, params=None, headers=None, timeout=DEFAULT_TIMEOUT):
    """Perform one GET; return the requests.Response on success."""
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise ProviderTimeout(f"provider timed out for {url}") from exc
    except requests.exceptions.RequestException as exc:
        raise ProviderUnavailable(
            f"provider unreachable for {url}: {_sanitize_error(exc)}"
        ) from exc
    if response.status_code != 200:
        raise ProviderUnavailable(
            f"provider returned HTTP {response.status_code} for {url}"
        )
    return response


def _response_json(response) -> dict:
    """Parse a JSON body or map decode failures to ProviderMalformed."""
    try:
        data = response.json()
    except (ValueError, TypeError) as exc:
        raise ProviderMalformed(f"unparseable JSON body: {_sanitize_error(exc)}") from exc
    if not isinstance(data, dict):
        raise ProviderMalformed(f"expected JSON object, got {type(data).__name__}")
    return data