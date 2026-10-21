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
        "inputs": {"ecp-2.authenticate": ["param-response"],
                   "ecp-2.set-audio-output": ["param-sas-ip-address"]},
    },
}


def materialise(channel: str, step, received: list[bytes], screen) -> dict:
    if step.operation_id == "ecp-2.set-audio-output":
        return {"param-sas-ip-address": "127.0.0.1"}
    challenge = json.loads(received[0])["param-challenge"]
    return {"param-response": auth_response(challenge)}

# Partial captures are separate evidence scenarios, not selectable-profile replays.
EVIDENCE_COVERAGE = "complete"
from .audio import SCENARIOS as DATAGRAM_SCENARIOS, run as datagram_scenario
from .state import SCENARIOS as STATE_SCENARIOS, run as state_scenario

_audio_scenario = datagram_scenario
DATAGRAM_SCENARIOS = [*DATAGRAM_SCENARIOS, *STATE_SCENARIOS]


async def datagram_scenario(name, client):
    if name in {row['name'] for row in STATE_SCENARIOS}:
        await state_scenario(name, client)
    else:
        await _audio_scenario(name, client)
