"""HTTP ECP and ecp-2 server. Wire keys are kebab-case, as on the set."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
from http import HTTPStatus
from typing import Callable

from aiohttp import WSMsgType, web

from tvemu.core import Core
from tvemu.platforms.common import routing as route
from tvemu.platforms.common.reply import (
    TEXT, ErrorFormat, ReplyStyle, WireError, missing_capture,
)
from tvemu.platforms.common.routing import Surface

from .profile import RokuProfile

# ECP serves whatever the capture recorded; the profile names the type per route, because one
# television answers a route with an image where the rest of the family answers XML.
CAPTURED = ReplyStyle("captured", "text/xml")

# Both ECP wires refuse in their own way. HTTP answers the status with the reason as the body,
# and ecp-2 answers 200 with the status carried inside the envelope as a decimal string.
HTTP_ERROR = ErrorFormat(TEXT, lambda error: error.detail)

NO_CAPTURE = "No captured response is available in the selected device profile"

# Queries a plain HTTP client loses when the access mode restricts queries, measured on a
# TCL set on 15.3.4 in Limited mode. device-info and active-app stay open; a name not listed
# is not a route there at all and answers 404.
RESTRICTED_QUERIES = frozenset({
    "apps", "media-player", "icon", "tv-channels", "tv-active-channel", "audio-device",
    "sgnodes", "chanperf", "registry", "r2d2-bitmaps", "fwbeacons", "sgrendezvous",
    "graphics-frame-rate",
})


KNOWN_QUERIES = RESTRICTED_QUERIES | {"device-info", "active-app"}
# First path segments the set treats as ECP commands. Disabled mode refused all of them, a
# malformed key included, while a route outside them stayed 404.
COMMANDS = frozenset({"keypress", "keydown", "keyup", "launch", "search", "input"})


def _query_name(path: str) -> str | None:
    head, _, rest = path.partition("/query/")
    return None if head else rest.partition("/")[0]


def restricted_query(path: str) -> bool:
    return _query_name(path) in RESTRICTED_QUERIES


def is_command(path: str) -> bool:
    return (path.lstrip("/").partition("/")[0] in COMMANDS
            or _query_name(path) in KNOWN_QUERIES)


# The set writes its ecp-2 frames with keys in sorted order and without a space after the
# separators. A driver that hashes or compares a frame sees a different string otherwise, so
# both are reproduced rather than left to whatever the JSON library happens to do.
def frame(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)

def auth_response(challenge: str) -> str:
    # Protocol seed from Roku ECP challenge-response (not a user's credential).
    encoded = "95E610D0-7C29-44EF-FB0F-97F1FCE4C297"
    seed = "".join(format((24 - int(char, 16)) & 15, "X") if char in "0123456789ABCDEF"
                   else char for char in encoded)
    digest = hashlib.sha1((challenge + seed).encode(), usedforsecurity=False).digest()
    return base64.b64encode(digest).decode()


def response(operation: str, request_id: str, status: int = 200,
             content: bytes | None = None, content_type: str = "text/xml") -> dict:
    # `status-msg` is the status phrase and nothing else, the way the set answers: the
    # emulator's own explanation of a refusal belongs in the event log, not on the wire,
    # where a driver would come to depend on wording no television sends.
    result = {"response": operation, "response-id": request_id, "status": str(status),
              "status-msg": HTTPStatus(status).phrase}
    if content is not None:
        # The document and its type, charset spelling included, are the ones the capture
        # recorded rather than anything this wire decides.
        result.update({"content-type": content_type,
                       "content-data": base64.b64encode(content).decode()})
    return result


class ECP:
    def __init__(self, core: Core, current_profile: Callable[[], RokuProfile]):
        self.core = core
        self.current_profile = current_profile
        self.websockets: dict[str, web.WebSocketResponse] = {}
        self.pending: set[asyncio.Task] = set()
        self.http_transports: set = set()
        self.generation = 0
        # The device reports its own uptime in the challenge frame, so the clock starts with
        # the emulated set rather than with the process.
        self.started = time.monotonic()

    @web.middleware
    async def headers(self, request: web.Request, handler):
        if request.transport:
            self.http_transports.add(request.transport)
        self.http_transports = {t for t in self.http_transports if not t.is_closing()}
        if not self.core.service_listening:
            raise web.HTTPServiceUnavailable()
        # Network access can close the whole ECP surface, not just remote keys.
        denial = self.core.access_denial(request.remote or "")
        if denial:
            status, detail = denial
            self.core.record("access", f"{request.method} {request.path}", transport="http",
                             peer=request.remote or "", status=status, detail=detail)
            return HTTP_ERROR.response(WireError(status, detail))
        mode = self.core.access
        status = dict(mode.command_statuses).get("http", 200)
        if status != 200 and is_command(request.path):
            self.core.record("access", f"{request.method} {request.path}", transport="http",
                             peer=request.remote or "", status=status, detail=mode.detail)
            return web.Response(status=status,
                                headers={"Server": self.current_profile().server})
        try:
            result = await handler(request)
        except WireError as error:
            # A refusal is still this television answering, so it carries the Server header
            # the set puts on every reply.
            result = HTTP_ERROR.response(error)
        if not result.prepared:
            result.headers["Server"] = self.current_profile().server
        return result

    def surface(self) -> Surface:
        """Everything this platform answers, as declared -- HTTP and ecp-2 alike."""
        return Surface("roku", tuple(spec for spec, _ in route.declarations(self)),
                       tuple(spec for spec, _ in route.message_declarations(self)))

    def app(self) -> web.Application:
        return route.attach(
            web.Application(middlewares=[self.headers], client_max_size=16384), self)

    @route.get("/ecp-session", summary="The authenticated ecp-2 WebSocket.")
    async def websocket(self, request):
        return await self._websocket(request)

    @route.post("/{action:keypress|keydown|keyup}/{key}", operation_id="roku.http.key",
                summary="One remote key over plain HTTP ECP.")
    async def http_key(self, request):
        generation = self.generation
        task = asyncio.current_task()
        self.pending.add(task)
        try:
            status, detail = await self.core.key(request.match_info["key"], request.match_info["action"],
                                               "http", request.remote or "", f"http:{request.remote}")
            if generation != self.generation:
                raise asyncio.CancelledError
            # The set explains neither an unknown key nor a refused one: both are bodiless.
            return web.Response(status=status)
        finally:
            self.pending.discard(task)

    @route.post("/launch/{app_id}", operation_id="roku.http.launch",
                summary="Launch a channel by its ECP id.")
    async def launch_app(self, request):
        app_id = request.match_info["app_id"]
        mode = self.core.access
        status = dict(mode.control_statuses).get("http", mode.control_status)
        detail = "Accepted" if status == 200 else (
            mode.detail or f"Rejected by {mode.label}")
        payload = request.raw_path.partition("?")[2]
        self.core.application_launch(
            app_id, surface="ecp", transport="http", peer=request.remote or "",
            payload=payload, status=status, detail=detail,
        )
        # Like a key, a launch is answered by its status alone.
        return web.Response(status=status)

    @route.get("/", operation_id="roku.http.device-description",
               summary="The UPnP device description.", captured="/", missing=501,
               style=CAPTURED)
    @route.get("/query/device-info", summary="The ECP device inventory.",
               operation_id="roku.http.device-info",
               captured="/query/device-info", missing=501, style=CAPTURED)
    @route.get("/device-image.png", summary="A picture of the device.",
               operation_id="roku.http.device-image",
               captured="/device-image.png", missing=501, style=CAPTURED)
    @route.get("/ecp_SCPD.xml", operation_id="roku.http.ecp-scpd",
               summary="The ECP UPnP service description.",
               captured="/ecp_SCPD.xml", missing=501, style=CAPTURED)
    @route.get("/dial_SCPD.xml", operation_id="roku.http.dial-scpd",
               summary="The DIAL UPnP service description.",
               captured="/dial_SCPD.xml", missing=501, style=CAPTURED)
    @route.get("/query/apps", operation_id="roku.http.apps",
               summary="The captured installed-channel catalogue.",
               captured="/query/apps", missing=501, style=CAPTURED)
    @route.get("/query/active-app", operation_id="roku.http.active-app",
               summary="The captured foreground channel.",
               captured="/query/active-app", missing=501, style=CAPTURED)
    @route.get("/query/media-player", operation_id="roku.http.media-player",
               summary="The captured player state.",
               captured="/query/media-player", missing=501, style=CAPTURED)
    @route.get("/query/tv-channels", operation_id="roku.http.tv-channels",
               summary="The captured tuner channel list.",
               captured="/query/tv-channels", missing=501, style=CAPTURED)
    @route.get("/query/tv-active-channel", operation_id="roku.http.tv-active-channel",
               summary="The captured tuner channel on screen.",
               captured="/query/tv-active-channel", missing=501, style=CAPTURED)
    @route.get("/query/audio-device", operation_id="roku.http.audio-device",
               summary="The captured audio destinations and volume.",
               captured="/query/audio-device", missing=501, style=CAPTURED)
    @route.get("/query/icon/{channel_id}", operation_id="roku.http.icon",
               summary="A channel's icon.",
               captured="/query/icon/{channel_id}", missing=501, style=CAPTURED)
    @route.get("/{tail:.*}", summary="Any other route the selected capture recorded.",
               captured="*", missing=501, style=CAPTURED)
    async def document(self, request):
        mode = self.core.access
        status = dict(mode.query_statuses).get("http", 200)
        if status != 200 and restricted_query(request.path):
            # Refused before the capture is consulted: the set refuses a query it could
            # answer, so whether this profile recorded the document does not matter.
            self.core.record("access", f"GET {request.path}", transport="http",
                             peer=request.remote or "", status=status, detail=mode.detail)
            raise WireError(status, mode.refusal_body)
        profile = self.current_profile()
        content = profile.document(request.path)
        operation = "description" if request.path == "/" else request.path.removeprefix("/")
        if content is None:
            raise missing_capture(self.core, operation, profile.id, "http",
                                  request.remote or "", NO_CAPTURE)
        self.core.record("query", operation, transport="http", peer=request.remote or "", status=200,
                         detail=f"captured profile: {profile.id}")
        return CAPTURED.ok(content,
                           content_type=profile.document_content_type(request.path),
                           headers=profile.document_headers(request.path))

    @route.any_method("/{tail:.*}", summary="Anything this emulator does not serve.")
    async def unsupported(self, request):
        self.core.record("unsupported", f"{request.method} {request.path}", transport="http",
                         peer=request.remote or "", status=501, detail="Outside the Remote-only profile")
        return web.Response(status=501, text="Remote-only emulator: this endpoint is not implemented")

    @route.message("ecp-2", "param-challenge", "out",
                   summary="The authentication challenge, sent unprompted as the socket opens.")
    @route.message("ecp-2", "authenticate", "in",
                   summary="The only request that may carry request-id 1.")
    async def _websocket(self, request):
        protocols = [s.strip() for s in request.headers.get("Sec-WebSocket-Protocol", "").split(",")]
        if "ecp-2" not in protocols:
            raise web.HTTPBadRequest(text="Sec-WebSocket-Protocol: ecp-2 required")
        ws = web.WebSocketResponse(protocols=("ecp-2",), autoping=True, max_msg_size=16384)
        ws.headers["Server"] = self.current_profile().server
        await ws.prepare(request)
        owner = secrets.token_hex(6)
        peer = request.remote or ""
        self.websockets[owner] = ws
        self.core.connections[owner] = {"id": owner, "peer": peer, "authenticated": False, "transport": "ws"}
        self.core.record("connection", "ws.open", transport="ws", peer=peer)
        challenge = base64.b64encode(secrets.token_bytes(16)).decode()
        await self.send(ws, {
            "notify": "authenticate", "param-challenge": challenge,
            "param-methods": ["client-id", "jwt"],
            "timestamp": f"{time.monotonic() - self.started:.3f}",
        })
        worker = None
        queue: asyncio.Queue = asyncio.Queue(maxsize=128)
        try:
            message = await asyncio.wait_for(ws.receive(), timeout=5)
            try:
                auth = json.loads(message.data) if message.type == WSMsgType.TEXT else None
            except (ValueError, TypeError):
                auth = None
            answer = auth.get("param-response", auth.get("response")) if isinstance(auth, dict) else None
            valid = (isinstance(auth, dict) and auth.get("request") == "authenticate"
                     and auth.get("request-id") == "1" and isinstance(answer, str)
                     and hmac.compare_digest(answer, auth_response(challenge)))
            await self.send(ws, response("authenticate", "1", 200 if valid else 401))
            self.core.record("connection", "ws.authenticate", transport="ws", peer=peer,
                             status=200 if valid else 401)
            if not valid:
                await ws.close(code=1008, message=b"Authentication failed")
                return ws
            self.core.connections[owner]["authenticated"] = True
            self.core.publish()
            # Serialize commands on their own task so pings keep flowing while one is handled.
            worker = asyncio.create_task(self.process_queue(queue, ws, owner, peer))
            self.pending.add(worker)
            async for message in ws:
                if message.type == WSMsgType.TEXT:
                    try:
                        payload = json.loads(message.data)
                    except ValueError:
                        payload = None
                    if not isinstance(payload, dict):
                        # Not addressable, so there is nothing to answer: the set closes.
                        self.core.record("connection", "ws.malformed", transport="ws",
                                         peer=peer, status=400,
                                         detail="a frame must be a JSON object")
                        await ws.close(code=1002, message=b"Malformed frame")
                        break
                    try:
                        queue.put_nowait(payload)
                    except asyncio.QueueFull:
                        self.core.record("connection", "ws.overloaded", transport="ws", peer=peer, status=503)
                        await ws.close(code=1013, message=b"Command queue full")
                elif message.type == WSMsgType.ERROR:
                    break
        except (asyncio.TimeoutError, ConnectionError, RuntimeError):
            self.core.record("connection", "ws.closed", transport="ws", peer=peer,
                             detail="Authentication timeout or connection closed")
        finally:
            if worker:
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
                self.pending.discard(worker)
            self.websockets.pop(owner, None)
            self.core.connections.pop(owner, None)
            self.core.held.pop(owner, None)
            self.core.record("connection", "ws.disconnect", transport="ws", peer=peer)
            await ws.close()
        return ws

    async def process_queue(self, queue, ws, owner, peer):
        while True:
            data = await queue.get()
            try:
                await self.ws_command(ws, data, owner, peer)
            except (ConnectionError, RuntimeError):
                return
            finally:
                queue.task_done()

    @route.message("ecp-2", "response", "out",
                   summary="The envelope every reply arrives in.")
    async def send(self, ws, payload: dict) -> None:
        await ws.send_str(frame(payload))

    @route.message("ecp-2", "key-press", "in",
                   summary="A remote key, pressed and released.")
    @route.message("ecp-2", "key-down", "in",
                   summary="A remote key, held.")
    @route.message("ecp-2", "key-up", "in",
                   summary="A held remote key, released.")
    @route.message("ecp-2", "query-device-info", "in",
                   summary="The device inventory, answered as base64 inside the envelope.")
    @route.message("ecp-2", "query-active-app", "in",
                   summary="The foreground channel, answered inside the envelope.")
    @route.message("ecp-2", "query-apps", "in",
                   summary="The installed channels, answered inside the envelope.")
    @route.message("ecp-2", "query-media-player", "in",
                   summary="The player state, answered inside the envelope.")
    @route.message("ecp-2", "query-textedit-state", "in",
                   summary="The focused text field, answered as JSON inside the envelope.")
    @route.message("ecp-2", "query-audio-device", "in",
                   summary="Audio destinations and volume, answered inside the envelope.")
    @route.message("ecp-2", "query-tv-channels", "in",
                   summary="The tuner's channel list, answered inside the envelope.")
    async def ws_command(self, ws, data, owner, peer):
        operation, request_id = data.get("request"), data.get("request-id")
        if not isinstance(operation, str) or not isinstance(request_id, str):
            # Not an error reply: the set drops the whole session when either field is
            # missing or is not a string, so one malformed frame costs a driver its socket.
            self.core.record("connection", "ws.malformed", transport="ws", peer=peer,
                             status=400, detail="request and request-id must both be strings")
            await ws.close(code=1002, message=b"Malformed request")
            raise ConnectionError("Malformed ecp-2 request")
        if operation in ("key-press", "key-down", "key-up"):
            key = data.get("param-key")
            if not isinstance(key, str) or not key or len(key) > 128:
                await self.send(ws, response(operation, request_id, 400))
                return
            action = {"key-press": "keypress", "key-down": "keydown", "key-up": "keyup"}[operation]
            status, _ = await self.core.key(key, action, "ws", peer, owner, request_id)
            await self.send(ws, response(operation, request_id, status))
            return
        profile = self.current_profile()
        content, content_type = profile.ecp2_documents.get(operation, (None, ""))
        if content is None and operation == "query-device-info":
            # A capture without its own ecp-2 copy lends the HTTP document. The two are not
            # identical on hardware: the envelope's copy adds virtual-device-id.
            route = "/query/device-info"
            content, content_type = profile.document(route), profile.document_content_type(route)
        # An unhandled request is Not Found, the way the set answers one: the request name is
        # a route on this wire, so an unknown one is missing rather than unimplemented.
        status = 200 if content is not None else 404
        self.core.record("query" if status == 200 else "unsupported", operation,
                         transport="ws", peer=peer, status=status, request_id=request_id,
                         detail="" if status == 200 else NO_CAPTURE)
        await self.send(ws, response(operation, request_id, status, content=content,
                                     content_type=content_type))

    async def disconnect(self, detail: str | None = None):
        self.generation += 1
        for task in tuple(self.pending):
            task.cancel()
        if self.pending:
            await asyncio.gather(*tuple(self.pending), return_exceptions=True)
        # Abort transport as a reproducible network disconnect, including idle HTTP keep-alive.
        for transport in tuple(self.http_transports):
            transport.abort()
        self.http_transports.clear()
        for ws in tuple(self.websockets.values()):
            await ws.close(code=1001, message=b"Disconnected by tester")
        self.core.held.clear()
        self.core.record("connection", "disconnect-all",
                         detail=detail or "Roku connections terminated")
