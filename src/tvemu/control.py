"""Local, versioned management API, isolated from the emulated TV's LAN port."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from aiohttp import web

from .core import write_settings
from .view import openapi
from .platforms import PlatformUnavailable
from .platforms.catalogue import request_url
from .runtime import Runtime

STATIC = Path(__file__).parent / "web"
STATIC_ROOT = STATIC.resolve()
STATIC_SUFFIXES = frozenset({".html", ".css", ".js"})


def control_app(runtime: Runtime, settings_path: Path, port: int = 8888) -> web.Application:
    core = runtime.core

    @web.middleware
    async def local_only(request, handler):
        # Prevent arbitrary websites from writing to a localhost service or subscribing to logs.
        if request.host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            raise web.HTTPForbidden(text="Local Host required")
        origin = request.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            raise web.HTTPForbidden(text="Same-origin requests only")
        if request.method not in ("GET", "HEAD") and request.content_type != "application/json":
            raise web.HTTPUnsupportedMediaType(text="application/json required")
        try:
            result = await handler(request)
        except (ValueError, TypeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except OSError as exc:
            return web.json_response({"error": str(exc)}, status=503)
        if not result.prepared:
            result.headers.update({
                "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'self'; connect-src 'self'; style-src 'self'; "
                                           "script-src 'self'; frame-ancestors 'none'; base-uri 'none'",
            })
        return result

    async def state(request):
        return web.json_response(core.snapshot())

    async def describe(request):
        # The dashboard contract, said once, where a reader can find it.
        return web.json_response(openapi())

    async def settings(request):
        await runtime.configure(await request.json())
        return web.json_response(core.snapshot())

    async def platform(request):
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError("A JSON object is required")
        platform_id = data.get("platform")
        if not isinstance(platform_id, str) or not platform_id:
            raise ValueError("platform must be a platform id")
        try:
            await runtime.set_platform(platform_id)
        except PlatformUnavailable as exc:
            # 501, not 400: the id names a real television this product models, it is
            # simply not implemented in this build. `Runtime.set_platform` resolves the
            # platform before any teardown, so the one that was serving still is.
            entry = exc.entry
            return web.json_response(
                {"error": f"{entry.display_name} is not available in this build (N/A).",
                 "reason": "n/a", "platform": entry.id, "display_name": entry.display_name,
                 "summary": entry.summary, "devices": entry.devices, "docs": entry.docs,
                 "contact": request_url()},
                status=501)
        return web.json_response(core.snapshot())

    async def save(request):
        async with runtime.lock:
            write_settings(settings_path, core.settings, core.platform.id)
        core.record("settings", "settings.saved", detail=str(settings_path))
        return web.json_response({"saved": str(settings_path)})

    async def action(request):
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError("A JSON object is required")
        name = request.match_info["name"]
        if name == "disconnect":
            await runtime.platform.disconnect()
        elif name == "reset":
            core.reset()
        elif name == "clear-log":
            core.events.clear()
            core.publish()
        elif name == "text":
            # Typing is shared behaviour, so it lives here rather than behind the adapter hook.
            status, detail = await core.text(
                str(data.get("op") or "insert"), transport="lab", text=data.get("text") or "",
                count=data.get("count", 1), replace=bool(data.get("replace")),
                source="dashboard")
            if status != 200:
                return web.json_response({"error": detail}, status=status)
        elif name == "field":
            if core.keyboard is None:
                raise web.HTTPNotFound(reason="This platform serves no text input")
            content_type = data.get("content_type")
            if content_type is not None and not isinstance(content_type, str):
                raise ValueError("content_type must be a string")
            core.focus_field(bool(data.get("focused")), content_type, source="dashboard")
        else:
            await runtime.platform.action(name, data)
        return web.json_response(core.snapshot())

    async def events_export(request):
        text = "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in core.events)
        return web.Response(text=text, content_type="application/x-ndjson", headers={
            "Content-Disposition":
                f'attachment; filename="{core.platform.id}-events.jsonl"'})

    async def events(request):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        core.subscribers.add(queue)

        async def send_updates():
            await ws.send_json(core.snapshot())
            while True:
                await queue.get()
                await ws.send_json(core.snapshot())

        writer = asyncio.create_task(send_updates())
        try:
            async for _ in ws:
                pass
        finally:
            core.subscribers.discard(queue)
            writer.cancel()
            await asyncio.gather(writer, return_exceptions=True)
        return ws

    async def static(request):
        # Resolve under STATIC so a new platform module needs no server change, and so "..",
        # symlinks, and absolute paths cannot reach outside the dashboard assets.
        target = (STATIC / request.match_info.get("path", "index.html")).resolve()
        if (not target.is_relative_to(STATIC_ROOT) or target.suffix not in STATIC_SUFFIXES
                or not target.is_file()):
            raise web.HTTPNotFound()
        return web.FileResponse(target)

    app = web.Application(middlewares=[local_only], client_max_size=16384)
    app.add_routes([
        web.get("/", static), web.get("/api/v1/state", state),
        web.get("/api/v1/openapi.json", describe),
        web.patch("/api/v1/settings", settings), web.get("/api/v1/events", events),
        web.post("/api/v1/platform", platform),
        web.get("/api/v1/events/export", events_export),
        web.post("/api/v1/settings/save", save), web.post("/api/v1/actions/{name}", action),
        web.get("/{path:.+}", static),
    ])
    return app
