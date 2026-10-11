"""How the replay conformance harness reaches this television's ecp-2 socket.

Plain data and one function, so this build carries nothing that imports the harness. The
format is described in `tvemu/conformance/websocket.py`.
"""
from __future__ import annotations

import json

from tvemu.platforms.roku.ecp import auth_response

# Every replay of every Roku profile runs; one left uncovered fails the merge gate.
COVERAGE = "complete"

CHANNELS = {
    "ecp-2": {
        "path": "/ecp-session",
        "protocols": ["ecp-2"],
        # The socket answers nothing until the client proves it knows the protocol seed.
        "opening": ["ws.authenticate"],
        # A fresh challenge per socket, and the set's own uptime: both are the emulator's.
        "masks": {"ecp-2.param-challenge": ["param-challenge", "timestamp"]},
        # The answer is a digest of that challenge, so it is recomputed for each session.
        "inputs": {"ecp-2.authenticate": ["param-response"]},
    },
}


def materialise(channel: str, step, received: list[bytes]) -> dict:
    challenge = json.loads(received[0])["param-challenge"]
    return {"param-response": auth_response(challenge)}
