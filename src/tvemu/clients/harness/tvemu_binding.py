"""What a client binding imports: steps, and the emulator's management API.

A binding runs inside the client's own virtual environment, which holds the upstream client
and nothing of the emulator. This module is put on its path alone, so it uses only the
standard library and talks to the emulator the way any test would: over `/api/v1`.

    from tvemu_binding import Harness

    async def main(harness: Harness):
        async with harness.step("press Home", "key"):
            await client.press("Home")
            await harness.wait(lambda state: state["counts"].get("Home") == 1, "Home counted")

    Harness.main(main)

Each step is appended to the results file as one JSON line with the event ids it covers, so
the runner can tell which emulator events a failure belongs to. A failed step does not stop
the binding unless it was `required`: later steps still say what they can.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.request
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable

DETAIL_LIMIT = 400


class Abort(Exception):
    """A required step failed; nothing after it can mean anything."""


class Harness:
    def __init__(self) -> None:
        self.device_host = os.environ["TVEMU_DEVICE_HOST"]
        self.device_port = int(os.environ["TVEMU_DEVICE_PORT"])
        self.profile = os.environ["TVEMU_PROFILE"]
        self.api_url = os.environ["TVEMU_API"].rstrip("/")
        self.workspace = os.environ["TVEMU_WORKSPACE"]
        self._results = os.environ["TVEMU_RESULTS"]

    # -- the management API -------------------------------------------------------------------

    def _call(self, method: str, path: str, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(f"{self.api_url}{path}", data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=10) as response:
            text = response.read().decode()
        if path.endswith("/export"):
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        return json.loads(text)

    async def state(self) -> dict:
        return await asyncio.to_thread(self._call, "GET", "/api/v1/state")

    async def events(self, since: int = 0) -> list[dict]:
        events = await asyncio.to_thread(self._call, "GET", "/api/v1/events/export")
        return [event for event in events if int(event.get("id") or 0) > since]

    async def action(self, name: str, data: dict | None = None) -> dict:
        return await asyncio.to_thread(self._call, "POST", f"/api/v1/actions/{name}", data or {})

    async def settings(self, patch: dict) -> dict:
        return await asyncio.to_thread(self._call, "PATCH", "/api/v1/settings", patch)

    async def last_event_id(self) -> int:
        events = (await self.state()).get("events") or []
        return int(events[-1]["id"]) if events else 0

    async def wait(self, predicate: Callable[[dict], bool], label: str,
                   timeout: float = 5.0) -> dict:
        """Poll the emulator's state until `predicate` holds for it."""
        deadline = time.monotonic() + timeout
        while True:
            state = await self.state()
            if predicate(state):
                return state
            if time.monotonic() >= deadline:
                raise AssertionError(f"timed out waiting for {label}")
            await asyncio.sleep(0.05)

    @staticmethod
    async def until(predicate: Callable[[], bool], label: str, timeout: float = 5.0) -> None:
        """Wait for a condition on the client's side, such as a callback having fired."""
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                raise AssertionError(f"timed out waiting for {label}")
            await asyncio.sleep(0.02)

    # -- steps --------------------------------------------------------------------------------

    def _write(self, record: dict) -> None:
        with open(self._results, "a", encoding="utf-8") as results:
            results.write(json.dumps(record, ensure_ascii=False) + "\n")

    @asynccontextmanager
    async def step(self, name: str, action: str, *, required: bool = False):
        first = await self.last_event_id()
        started = time.monotonic()
        record = {"name": name, "action": action, "status": "ok", "detail": ""}
        try:
            yield record
        except Exception as exc:      # the step's verdict, not the binding's crash
            record["status"] = "fail"
            record["detail"] = f"{type(exc).__name__}: {exc}"[:DETAIL_LIMIT]
        record["events"] = [first, await self.last_event_id()]
        record["duration_ms"] = round((time.monotonic() - started) * 1000)
        if required and record["status"] == "fail":
            record["required"] = True
        self._write(record)
        if record.get("required"):
            raise Abort(name)

    def not_offered(self, name: str, action: str, reason: str) -> None:
        """The client has no way to do this; a fact about the client, not a failure."""
        self._write({"name": name, "action": action, "status": "not-offered",
                     "detail": reason, "events": [0, 0], "duration_ms": 0})

    @classmethod
    def main(cls, body: Callable[["Harness"], Awaitable[None]]) -> None:
        harness = cls()
        try:
            asyncio.run(body(harness))
        except Abort as abort:
            raise SystemExit(f"stopped after required step {abort}")
