"""A Model Context Protocol server over stdio, so a coding agent can drive the emulator.

The loop it exists for: an agent writes or changes a driver, runs the app against the
emulator, then asks the emulator what actually arrived — `events` and `expect` — instead of
trusting its own reading of the code. It also reads the declared surface and contract of any
platform, so the agent writes the driver against the same contract the emulator enforces.

    tvemu-mcp                                  # talks to http://127.0.0.1:8888
    tvemu-mcp --url http://127.0.0.1:9999      # or TVEMU_URL

Registering it with a client, for example Claude Code:

    claude mcp add tvemu -- tvemu-mcp

Newline-delimited JSON-RPC 2.0 on stdin and stdout, with no SDK: the protocol surface is
initialize, ping, tools/list and tools/call. Everything the tools change goes through the
same local `/api/v1` the dashboard uses, so an agent can do nothing a tester could not.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any, Awaitable, Callable

from aiohttp import ClientSession

from . import __version__
from . import expect as expectations

PROTOCOL_VERSION = "2025-06-18"
DEFAULT_URL = os.environ.get("TVEMU_URL", expectations.DEFAULT_URL)


def _object(properties: dict | None = None, required: tuple[str, ...] = ()) -> dict:
    schema: dict[str, Any] = {"type": "object", "properties": properties or {},
                              "additionalProperties": False}
    if required:
        schema["required"] = list(required)
    return schema


PLATFORM = {"type": "string", "description": "A platform id, as `state` lists them."}
SINCE = {"type": "integer", "minimum": 0,
         "description": "Only events whose id is greater than this."}

TOOLS: dict[str, tuple[str, dict]] = {
    "state": ("The emulated television right now: platform, captured device, address, "
              "protocols and their ports, pairing, keys, power, volume, keyboard and "
              "launches. The event log is left out; read it with `events`.", _object()),
    "events": ("The event log, oldest first: every request, response status and refusal "
               "reason, each with a monotonic id. Pass since_id to read only what happened "
               "after an earlier call.",
               _object({"since_id": SINCE,
                        "limit": {"type": "integer", "minimum": 1, "maximum": 500,
                                  "description": "At most this many, newest kept."}})),
    "expect": ("Check the event log against a scenario and say what is missing. Patterns "
               "match an event when every named field is equal; a string ending in * is a "
               "prefix. `expect` is a subsequence when ordered (the default); any event "
               "matching `forbid` fails.",
               _object({"expect": {"type": "array", "items": {"type": "object"}},
                        "forbid": {"type": "array", "items": {"type": "object"}},
                        "ordered": {"type": "boolean"}, "since_id": SINCE},
                       required=("expect",))),
    "reset": ("Reset simulated device state: counters, held keys, power, volume. Settings "
              "and the event log stay.", _object()),
    "clear_log": ("Empty the event log, so the next check starts clean.", _object()),
    "disconnect": ("Drop every client session on the emulated device, as a network drop "
                   "would. Pairing that lives in memory is forgotten.", _object()),
    "type_text": ("Type into the focused field on the emulated device, as its viewer would.",
                  _object({"text": {"type": "string"},
                           "replace": {"type": "boolean",
                                       "description": "Replace the field instead of "
                                                      "inserting at the cursor."}},
                          required=("text",))),
    "focus_field": ("Focus or blur the text field on the emulated device, which is what "
                    "makes a keyboard appear on a real set.",
                    _object({"focused": {"type": "boolean"},
                             "content_type": {"type": "string",
                                              "description": "A field type the captured "
                                                             "device offers."}},
                            required=("focused",))),
    "configure": ("Apply a partial settings update: device_profile, access_mode, or "
                  "protocols as {id: true|false}.",
                  _object({"settings": {"type": "object"}}, required=("settings",))),
    "switch_platform": ("Switch the emulated television without restarting.",
                        _object({"platform": PLATFORM}, required=("platform",))),
    "api_map": ("Everything a platform answers, from the route and message declarations "
                "beside its handlers. format: text (default), openapi or asyncapi.",
                _object({"platform": PLATFORM,
                         "format": {"type": "string", "enum": ["text", "openapi", "asyncapi"]}},
                        required=("platform",))),
    "contract": ("A platform's curated claims — what is required, which value sets are "
                 "closed, the quirks a driver must handle — with any disagreement with its "
                 "captures.", _object({"platform": PLATFORM}, required=("platform",))),
}


class ToolError(Exception):
    """A failure the agent should read, reported as a tool result rather than a crash."""


class Server:
    def __init__(self, url: str = DEFAULT_URL):
        self.url = url.rstrip("/")

    async def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        async with ClientSession() as session:
            async with session.request(method, self.url + path,
                                       json=body if method != "GET" else None) as response:
                text = await response.text()
                if response.status >= 400:
                    raise ToolError(f"{method} {path} answered {response.status}: {text}")
                if response.content_type == "application/json":
                    return json.loads(text)
                return text

    async def _events(self) -> list[dict]:
        return expectations.read_jsonl(await self._request("GET", "/api/v1/events/export"))

    async def _action(self, name: str, body: dict | None = None) -> dict:
        snapshot = await self._request("POST", f"/api/v1/actions/{name}", body or {})
        return _without_events(snapshot)

    # ── tools ──────────────────────────────────────────────────────────────────────
    async def state(self) -> dict:
        return _without_events(await self._request("GET", "/api/v1/state"))

    async def events(self, since_id: int = 0, limit: int = 100) -> list[dict]:
        rows = [event for event in await self._events() if int(event.get("id") or 0) > since_id]
        return rows[-limit:]

    async def expect(self, expect: list, forbid: list | None = None, ordered: bool = True,
                     since_id: int = 0) -> dict:
        scenario = {"expect": expect, "forbid": forbid or [], "ordered": ordered}
        try:
            problems = expectations.check(await self._events(), scenario, since=since_id)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        return {"ok": not problems, "problems": problems}

    async def reset(self) -> dict:
        return await self._action("reset")

    async def clear_log(self) -> dict:
        return await self._action("clear-log")

    async def disconnect(self) -> dict:
        return await self._action("disconnect")

    async def type_text(self, text: str, replace: bool = False) -> dict:
        return await self._action("text", {"op": "insert", "text": text, "replace": replace})

    async def focus_field(self, focused: bool, content_type: str | None = None) -> dict:
        body: dict[str, Any] = {"focused": focused}
        if content_type is not None:
            body["content_type"] = content_type
        return await self._action("field", body)

    async def configure(self, settings: dict) -> dict:
        return _without_events(await self._request("PATCH", "/api/v1/settings", settings))

    async def switch_platform(self, platform: str) -> dict:
        return _without_events(await self._request("POST", "/api/v1/platform",
                                                   {"platform": platform}))

    async def api_map(self, platform: str, format: str = "text") -> Any:
        from .platforms.common import report
        surface = _surface(platform)
        if format == "openapi":
            documents = report.openapi_documents(platform, surface)
            return documents[""] if list(documents) == [""] else documents
        if format == "asyncapi":
            return report.asyncapi(platform, surface)
        return report.render_surface(surface)

    async def contract(self, platform: str) -> str:
        from .platforms.common import report
        surface = _surface(platform)
        text = report.render_contract(platform, surface)
        problems = report.contract_problems(platform, surface)
        if problems:
            text += "\n\nDisagreements with the captures:\n" + "\n".join(
                f"  - {problem}" for problem in problems)
        return text

    # ── protocol ───────────────────────────────────────────────────────────────────
    async def handle(self, message: dict) -> dict | None:
        """One JSON-RPC message in, its response out; None for a notification."""
        method = message.get("method")
        ident = message.get("id")
        if ident is None:
            return None
        try:
            if method == "initialize":
                requested = (message.get("params") or {}).get("protocolVersion")
                result: Any = {
                    "protocolVersion": requested or PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "tvemu", "version": __version__},
                    "instructions": "Drive and inspect a Smart TV emulator. Read `state`, "
                                    "`api_map` and `contract` before writing a driver; after "
                                    "running the app, confirm with `events` or `expect`.",
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [{"name": name, "description": description,
                                     "inputSchema": schema}
                                    for name, (description, schema) in TOOLS.items()]}
            elif method == "tools/call":
                result = await self._call(message.get("params") or {})
            else:
                return _error(ident, -32601, f"Unknown method {method!r}")
        except (TypeError, ValueError) as exc:
            return _error(ident, -32602, str(exc))
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    async def _call(self, params: dict) -> dict:
        name = params.get("name")
        if name not in TOOLS:
            raise ValueError(f"Unknown tool {name!r}")
        tool: Callable[..., Awaitable[Any]] = getattr(self, name)
        arguments = params.get("arguments") or {}
        try:
            value = await tool(**arguments)
        except TypeError as exc:
            return _text(f"Bad arguments for {name}: {exc}", error=True)
        except ToolError as exc:
            return _text(str(exc), error=True)
        except OSError as exc:
            return _text(f"The emulator is not reachable at {self.url}: {exc}. "
                         f"Start it with `tvemu --no-browser`.", error=True)
        failed = isinstance(value, dict) and value.get("ok") is False
        return _text(value if isinstance(value, str) else json.dumps(value, indent=2),
                     error=failed)


def _surface(platform: str):
    from .platforms import platform_ids
    from .platforms.common import report
    if platform not in platform_ids():
        raise ToolError(f"{platform!r} is not a platform this build runs; "
                        f"available: {', '.join(platform_ids())}")
    surface = report.surface_of(platform)
    if surface is None:
        raise ToolError(f"{platform} does not declare its surface")
    return surface


def _without_events(snapshot: Any) -> Any:
    if isinstance(snapshot, dict):
        return {name: value for name, value in snapshot.items() if name != "events"}
    return snapshot


def _text(text: str, error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": error}


def _error(ident, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}


async def serve(server: Server, reader=sys.stdin, writer=sys.stdout) -> None:
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, reader.readline)
        if not line:
            return
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response: dict | None = _error(None, -32700, f"Parse error: {exc}")
        else:
            response = await server.handle(message) if isinstance(message, dict) \
                else _error(None, -32600, "A request is a JSON object")
        if response is not None:
            writer.write(json.dumps(response) + "\n")
            writer.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tvemu-mcp", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=DEFAULT_URL,
                        help="the emulator's dashboard address (default: %(default)s)")
    args = parser.parse_args(argv)
    try:
        asyncio.run(serve(Server(args.url)))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
