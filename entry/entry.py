#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging
import os
import socket
from contextlib import suppress

import websockets
from websockets.client import connect as ws_connect

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ENTRY] %(levelname)s: %(message)s",
)

LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "25565"))
WS_URL = os.getenv("WS_URL", "wss://hyp.example.com/tunnel")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "zzyss666")
PING_INTERVAL = int(os.getenv("PING_INTERVAL", "60"))
PING_TIMEOUT = int(os.getenv("PING_TIMEOUT", "20"))
CONNECT_TIMEOUT = int(os.getenv("CONNECT_TIMEOUT", "10"))
CHUNK = int(os.getenv("CHUNK", "16384"))
FORCE_HOST = os.getenv("FORCE_HOST", "hyp.example.com")
FORCE_IP = os.getenv("FORCE_IP", "104.18.34.2")

_original_getaddrinfo = socket.getaddrinfo
def _forced_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == FORCE_HOST:
        return _original_getaddrinfo(FORCE_IP, port, family, type, proto, flags)
    return _original_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _forced_getaddrinfo
logging.info(f"DNS pin: {FORCE_HOST} -> {FORCE_IP} (process-only)")

async def tcp_to_ws(reader, ws):
    try:
        while True:
            data = await reader.read(CHUNK)
            if not data:
                with suppress(Exception):
                    await ws.close(code=1000, reason="tcp eof")
                break
            await ws.send(data)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logging.debug(f"tcp_to_ws err: {e!r}")
        with suppress(Exception):
            await ws.close()

async def ws_to_tcp(ws, writer):
    try:
        async for msg in ws:
            if isinstance(msg, (bytes, bytearray)):
                writer.write(msg)
                await writer.drain()
            else:
                logging.warning("received non-binary ws message; closing")
                break
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logging.debug(f"ws_to_tcp err: {e!r}")
    finally:
        with suppress(Exception):
            writer.close()
            await writer.wait_closed()

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    sock = writer.get_extra_info("socket")
    if sock is not None:
        with suppress(Exception):
            import socket as pysock
            sock.setsockopt(pysock.IPPROTO_TCP, pysock.TCP_NODELAY, 1)
    logging.info(f"client connected: {peer}")

    headers = {"User-Agent": "Mozilla/5.0 MEOW/1.3"}
    if AUTH_TOKEN:
        headers["X-Auth-Token"] = AUTH_TOKEN

    ws = None
    try:
        ws = await asyncio.wait_for(
            ws_connect(
                WS_URL,
                extra_headers=headers,
                max_size=None,
                ping_interval=PING_INTERVAL,
                ping_timeout=PING_TIMEOUT,
                compression=None,
            ),
            timeout=CONNECT_TIMEOUT,
        )
        logging.info(f"ws connected to {WS_URL}")

        t1 = asyncio.create_task(tcp_to_ws(reader, ws))
        t2 = asyncio.create_task(ws_to_tcp(ws, writer))
        done, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    except Exception as e:
        logging.warning(f"ws connect/transfer failed: {e!r}")
        with suppress(Exception):
            writer.close()
            await writer.wait_closed()
    finally:
        if ws is not None:
            with suppress(Exception):
                await ws.close()
        logging.info(f"client disconnected: {peer}")

async def main():
    logging.info(f"using websockets {getattr(websockets, '__version__', 'unknown')}")
    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    logging.info(f"entry proxy listening on {addrs}, tunneling to {WS_URL}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("shutting down...")
