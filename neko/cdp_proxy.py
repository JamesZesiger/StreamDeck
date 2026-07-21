"""TCP forwarder 0.0.0.0:9223 -> 127.0.0.1:9222.

Chromium ignores --remote-debugging-address outside headless mode and binds
DevTools to localhost only; this makes it reachable from the app container.
Runs under supervisord inside the neko container (see chromium.conf).
"""

import asyncio

LISTEN_PORT = 9223
TARGET = ("127.0.0.1", 9222)


async def _pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def _handle(client_reader, client_writer):
    try:
        upstream_reader, upstream_writer = await asyncio.open_connection(*TARGET)
    except OSError:
        client_writer.close()
        return
    await asyncio.gather(
        _pipe(client_reader, upstream_writer),
        _pipe(upstream_reader, client_writer),
    )


async def main():
    server = await asyncio.start_server(_handle, "0.0.0.0", LISTEN_PORT)
    async with server:
        await server.serve_forever()


asyncio.run(main())
