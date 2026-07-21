"""WebSocket hub connecting the browser extension inside neko to the app.

The extension's service worker holds a socket open to /ws/nav; clicking Play
broadcasts a navigate message and the extension steers the active tab. This
replaces CDP-based navigation, which modern Chromium closes off in headful
mode. Pings every 20s keep the MV3 service worker alive.
"""

import asyncio
import json
import logging

from fastapi import WebSocket

log = logging.getLogger(__name__)

_clients: set[WebSocket] = set()


async def register(ws: WebSocket) -> None:
    await ws.accept()
    _clients.add(ws)
    log.info("nav client connected (%d total)", len(_clients))
    try:
        while True:
            await asyncio.sleep(20)
            await ws.send_text(json.dumps({"type": "ping"}))
    except Exception:
        pass
    finally:
        _clients.discard(ws)
        log.info("nav client disconnected (%d total)", len(_clients))


async def broadcast_navigate(url: str) -> bool:
    sent = False
    for ws in list(_clients):
        try:
            await ws.send_text(json.dumps({"type": "navigate", "url": url}))
            sent = True
        except Exception:
            _clients.discard(ws)
    return sent
