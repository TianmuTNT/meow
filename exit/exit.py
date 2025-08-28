#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging
import os
import signal
from contextlib import suppress

import websockets
from websockets.server import WebSocketServerProtocol

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EXIT] %(levelname)s: %(message)s",
)

WS_LISTEN_HOST = os.getenv("WS_LISTEN_HOST", "0.0.0.0")
WS_LISTEN_PORT = int(os.getenv("WS_LISTEN_PORT", "8765"))
MC_TARGET_HOST = os.getenv("MC_TARGET_HOST", "127.0.0.1")
MC_TARGET_PORT = int(os.getenv("MC_TARGET_PORT", "25565"))
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "zzyss666")
PING_INTERVAL = int(os.getenv("PING_INTERVAL", "60"))
PING_TIMEOUT = int(os.getenv("PING_TIMEOUT", "20"))
TCP_CONNECT_TIMEOUT = int(os.getenv("TCP_CONNECT_TIMEOUT", "10"))
CHUNK = int(os.getenv("CHUNK", "16384"))

async def ws_to_tcp(ws: WebSocketServerProtocol, writer: asyncio.StreamWriter):
    try:
        async for msg in ws:
            if isinstance(msg, (bytes, bytearray)):
                writer.write(msg)
                await writer.drain()
            else:
                logging.warning("received non-binary frame from entry; closing")
                break
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logging.debug(f"ws_to_tcp err: {e!r}")
    finally:
        with suppress(Exception):
            writer.close()
            await writer.wait_closed()

async def tcp_to_ws(reader: asyncio.StreamReader, ws: WebSocketServerProtocol):
    try:
        while True:
            data = await reader.read(CHUNK)
            if not data:
                await ws.close(code=1000, reason="tcp eof")
                break
            await ws.send(data)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logging.debug(f"tcp_to_ws err: {e!r}")
        with suppress(Exception):
            await ws.close()

async def handler(ws: WebSocketServerProtocol, path: str):
    
    if AUTH_TOKEN:
        token = ws.request_headers.get("X-Auth-Token", "")
        if token != AUTH_TOKEN:
            logging.warning("auth failed, closing")
            await ws.close(code=4001, reason="unauthorized")
            return

    peer = ws.remote_address
    logging.info(f"ws client connected: {peer} path={path}")

    try:
        conn_coro = asyncio.open_connection(MC_TARGET_HOST, MC_TARGET_PORT)
        reader, writer = await asyncio.wait_for(conn_coro, timeout=TCP_CONNECT_TIMEOUT)

        sock = writer.get_extra_info("socket")
        if sock is not None:
            with suppress(Exception):
                import socket as pysock
                sock.setsockopt(pysock.IPPROTO_TCP, pysock.TCP_NODELAY, 1)

        logging.info(f"connected to MC target {MC_TARGET_HOST}:{MC_TARGET_PORT}")

        t1 = asyncio.create_task(ws_to_tcp(ws, writer))
        t2 = asyncio.create_task(tcp_to_ws(reader, ws))
        done, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    except Exception as e:
        logging.warning(f"target connect/transfer failed: {e!r}")
        with suppress(Exception):
            await ws.close(code=1011, reason="target connect/transfer failed")
    finally:
        logging.info(f"ws client disconnected: {peer}")

async def main():
    server = await websockets.serve(
        handler,
        WS_LISTEN_HOST,
        WS_LISTEN_PORT,
        max_size=None,
        ping_interval=PING_INTERVAL,
        ping_timeout=PING_TIMEOUT,
        compression=None,
    )
    logging.info(f"exit proxy listening on ws://{WS_LISTEN_HOST}:{WS_LISTEN_PORT}")
    
    stop = asyncio.Event()
    for s in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(s, stop.set)

    await stop.wait()
    logging.info("shutting down...")
    server.close()
    await server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
