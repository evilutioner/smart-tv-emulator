#!/usr/bin/env python3
"""A minimal authenticated `ecp-2` client, as a worked example.

    python tools/ecp_client.py 192.168.1.20:8060

Opens the WebSocket, answers the challenge, presses a key, then holds the session open so
the dashboard shows one authenticated connection. This is the whole handshake: a real
remote application does the same thing before it sends anything.
"""
from __future__ import annotations

import asyncio
import sys

import aiohttp

from tvemu.platforms.roku.ecp import auth_response


async def main(address: str, key: str) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(f"http://{address}/ecp-session",
                                      protocols=("ecp-2",)) as ws:
            challenge = (await ws.receive_json())["param-challenge"]
            await ws.send_json({"request": "authenticate", "request-id": "1",
                                "param-response": auth_response(challenge)})
            print("authenticate ->", await ws.receive_json())

            await ws.send_json({"request": "key-press", "request-id": "2",
                                "param-key": key})
            print(f"{key} ->", await ws.receive_json())

            print("session open; press Ctrl+C to close it")
            async for message in ws:
                print("<-", message.data)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    try:
        asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "InstantReplay"))
    except KeyboardInterrupt:
        pass
