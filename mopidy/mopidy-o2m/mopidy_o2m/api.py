"""Minimal read-only client for the O2M API.

Kept deliberately small: the extension is an adapter, so it fetches JSON and
maps it to Mopidy models. It never interprets O2M's own concepts — box data,
discover level, popularity — those stay in the service.

Failures are swallowed and returned as None rather than raised. Mopidy calls
`browse` and `search` on every backend, on the Tornado IO loop; an unreachable
o2m must degrade to "no results", never to a traceback or a stall.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 6


class O2mApi:
    def __init__(self, base_url: str, timeout: int = DEFAULT_TIMEOUT) -> None:
        # `api_url` is configured with its trailing /api/ — keep it verbatim so a
        # bare-metal install can point somewhere else entirely.
        self._base = base_url.rstrip("/") + "/"
        self._timeout = timeout

    def get(self, path: str, **params: Any) -> Any | None:
        url = self._base + path.lstrip("/")
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode() or "null")
        except urllib.error.HTTPError as e:
            # 400 on a too-short query is expected, not worth a warning.
            logger.debug("O2M API %s -> HTTP %s", path, e.code)
        except Exception as e:
            logger.warning("O2M API %s unreachable (%s)", path, e)
        return None
