"""Best-effort navigation of the neko-streamed Chromium via Chrome DevTools Protocol.

Used ONLY to point the streamed browser at a title's URL when Play is clicked —
a remote control, nothing more. Requires the Chromium inside the neko container
to be started with --remote-debugging-port (see neko/README.md); when NEKO_CDP_URL
is unset or unreachable, callers fall back to showing the link for manual paste.
"""

import asyncio
import json
import logging
import socket
from urllib.parse import urlparse, urlunparse

import httpx
import websockets

from config import settings

log = logging.getLogger(__name__)


def _resolve_to_ip(url: str) -> str:
    """Chromium's DevTools HTTP server rejects non-localhost/IP Host headers,
    so 'http://neko:9222' must become 'http://<container-ip>:9222'."""
    parts = urlparse(url)
    ip = socket.gethostbyname(parts.hostname)
    netloc = f"{ip}:{parts.port or 9222}"
    return urlunparse(parts._replace(netloc=netloc))


async def navigate(url: str) -> bool:
    if not settings.neko_cdp_url:
        return False
    try:
        cdp = _resolve_to_ip(settings.neko_cdp_url)
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{cdp}/json/list")
            r.raise_for_status()
        page = next((t for t in r.json() if t.get("type") == "page"), None)
        if not page:
            return False
        async with websockets.connect(page["webSocketDebuggerUrl"], open_timeout=5) as ws:
            await ws.send(json.dumps(
                {"id": 1, "method": "Page.navigate", "params": {"url": url}}
            ))
            await asyncio.wait_for(ws.recv(), timeout=5)
        return True
    except Exception as exc:
        log.warning("CDP navigation failed, falling back to manual: %s", exc)
        return False
