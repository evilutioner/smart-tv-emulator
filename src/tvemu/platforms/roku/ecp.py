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
from tvemu.platforms.common import xmlbytes
from tvemu.platforms.common.reply import (
    TEXT, ErrorFormat, ReplyStyle, WireError, missing_capture,
)
from tvemu.platforms.common.routing import Surface

from .profile import RokuProfile
from .textedit import TextEdit

# ECP serves whatever the capture recorded; the profile names the type per route, because one
# television answers a route with an image where the rest of the family answers XML.
CAPTURED = ReplyStyle("captured", "text/xml")

# A captured answer other than a document -- a stick's 404 for the tuner -- carries only the
# headers the set sent, which for a bodiless refusal is no Content-Type at all.
CAPTURED_REFUSAL = ReplyStyle("captured-refusal", "")

# Both ECP wires refuse in their own way. HTTP answers the status with the reason as the body,
# and ecp-2 answers 200 with the status carried inside the envelope as a decimal string.
HTTP_ERROR = ErrorFormat(TEXT, lambda error: error.detail)
# The one refusal the set words, the Limited mode's 403 for a query, is spelled like its
# documents: a quoted charset and no-cache. Measured on the TCL on 15.3.4.
QUERY_REFUSAL = ErrorFormat(
    ReplyStyle("query-refusal", 'text/plain; charset="utf-8"',
               headers=(("Cache-Control", "no-cache"),)),
    lambda error: error.detail)

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


# What the emulator writes live into a replayed document, per field. device-info names the
# set's network-access value in the spelling the access modes use as their ids: enabled,
# limited and disabled were each captured off the TCL, permissive is the client contract.
LIVE_FIELDS: dict[str, Callable[[Core], str]] = {
    "ecp-setting-mode": lambda core: core.access.id,
}
# A field whose live value is per device rather than a platform trait: the profile's
# `runtime` names it for each state of the set, with the capture that measured it.
STATE_FIELDS: dict[str, Callable[[Core], str]] = {
    "power-mode": lambda core: "on" if core.power else "standby",
}


# The set writes its ecp-2 frames with keys in sorted order and without a space after the
# separators. A driver that hashes or compares a frame sees a different string otherwise, so
# both are reproduced rather than left to whatever the JSON library happens to do.
def frame(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)

def auth_response(challenge: str) -> str:
    # The ecp-2 answer is SHA-1 over the challenge and one fixed seed that every set and every
    # client shares; it identifies no unit and no user. The probe captures show a set
    # accepting an answer built this way. Published, with the digit transform that turns
    # 95E610D0-7C29-44EF-FB0F-97F1FCE4C297 into this, in "Building Roam (A Roku Remote)":
    # https://scottdriggers.com/blog/how-i-built-roam
    seed = "F3A278B8-1C6F-44A9-9D89-F1979CA4C6F1"
    digest = hashlib.sha1((challenge + seed).encode(), usedforsecurity=False).digest()
    return base64.b64encode(digest).decode()


# ecp-2 statuses that are not HTTP ones, with the phrase the set sends for each. A wrong
# challenge answer is 601, measured on the Streaming Stick 4K on 15.3.4.
STATUS_PHRASES = {601: "Invalid Credentials"}
# An ecp-2 session that has not authenticated is dropped this many seconds after it opened,
# without a close frame, whatever it sent meanwhile. Measured at 10.5 s on the same stick.
AUTH_DEADLINE = 10.5


# The notifications an ecp-2 session may subscribe to with request-events: every name the
# Streaming Stick 4K on 15.3.4 accepted, the television's tuner and input events included.
# Names are case sensitive and nothing is trimmed.
EVENTS = frozenset({
    "language-changed", "language-changing", "media-player-state-changed", "plugin-ui-run",
    "plugin-ui-run-script", "plugin-ui-exit", "screensaver-run", "screensaver-exit",
    "plugins-changed", "sync-completed", "power-mode-changed", "volume-changed",
    "textedit-opened", "textedit-closed", "textedit-changed", "device-name-changed",
    "device-location-changed", "audio-setting-changed", "audio-settings-invalidated",
    "user-profile-changed", "tv-power-volume-control-changed", "tv-channel-changed",
    "tvinput-ui-run", "tvinput-ui-exit",
})


def subscription(events) -> tuple[int, tuple[str, ...]]:
    """The status request-events answers, and the +name/-name entries the set takes from it."""
    if not isinstance(events, str):
        return 400, ()
    entries = [entry for entry in events.split(",") if entry]
    known = tuple(entry for entry in entries if entry[:1] in "+-" and entry[1:] in EVENTS)
    if not known:
        return 404, ()
    # A list the set only partly knows is taken in part, and says so.
    return (200 if len(known) == len(entries) else 202), known


def response(operation: str, request_id: str, status: int = 200,
             content: bytes | None = None, content_type: str = "text/xml") -> dict:
    # `status-msg` is the status phrase and nothing else, the way the set answers: the
    # emulator's own explanation of a refusal belongs in the event log, not on the wire,
    # where a driver would come to depend on wording no television sends.
    result = {"response": operation, "response-id": request_id, "status": str(status),
              "status-msg": STATUS_PHRASES.get(status) or HTTPStatus(status).phrase}
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
        self.ws_transports: dict[str, asyncio.BaseTransport] = {}
        # The channel an ecp-2 launch or input brought to the foreground, None on the home
        # screen. It decides only the 204 a repeated launch gets; the queries stay captured.
        self.foreground: str | None = None
        # What each authenticated session asked to be told about. Nothing is sent yet: the
        # notification frames other than screensaver-exit have not been captured.
        self.subscriptions: dict[str, set[str]] = {}
        self.pending: set[asyncio.Task] = set()
        self.http_transports: set = set()
        self.generation = 0
        # The device reports its own uptime in the challenge frame, so the clock starts with
        # the emulated set rather than with the process.
        self.started = time.monotonic()
        self.audio = None
        self.notification_queues: dict[str, asyncio.Queue] = {}
        self.notification_ready: dict[str, asyncio.Event] = {}
        self.command_locks: dict[str, asyncio.Lock] = {}
        self.last_launch_event = 0
        self.last_home_event = 0
        self.textedit = TextEdit(core, current_profile, self.notify_textedit)

    def observe(self):
        """Observe every state transition, before dashboard updates can coalesce it."""
        self.textedit.observe()
        launch = self.core.last_application_launch or {}
        event_id = launch.get("event_id", 0)
        if event_id != self.last_launch_event:
            self.last_launch_event = event_id
            if launch.get("surface") == "ecp" and launch.get("status") == 200:
                previous = self.foreground
                if previous:
                    self.notify("plugin-ui-exit", previous)
                self.foreground = launch["id"]
                self.notify("plugin-ui-run", self.foreground)
        key = self.core.last_key or {}
        if key.get("id", 0) != self.last_home_event:
            self.last_home_event = key.get("id", 0)
            if (self.core.key_name(key.get("key", "")) == "Home"
                    and key.get("status") == 200 and key.get("action") != "keyup"):
                if self.foreground:
                    self.notify("plugin-ui-exit", self.foreground)
                self.foreground = None

    def notify(self, name, channel):
        profile = self.current_profile()
        template = profile.notifications.get(name)
        if not template:
            return
        payload = dict(template)
        # These substitutions are explicitly declared on each profile's notify replay.
        title = str(channel)
        for body, _ in profile.ecp2_documents.values():
            if body and b"<apps>" in body:
                import xml.etree.ElementTree as ET
                title = next((item.text or str(channel) for item in ET.fromstring(body)
                              if item.get("id") == str(channel)), title)
                break
        payload.update({"param-channel-id": str(channel), "param-channel-title": title,
                        "timestamp": f"{time.monotonic() - self.started:.3f}"})
        self.queue_notification(name, payload)

    def notify_textedit(self, name, details):
        template = self.current_profile().native_text_notifications.get(name)
        if not template:
            return
        payload = dict(template)
        for key, value in details.items():
            path = "param-" + key
            if path not in template:
                raise ValueError(f"Native notification template has no {path}")
            payload[path] = value
        payload["timestamp"] = f"{time.monotonic() - self.started:.3f}"
        self.queue_notification(name, payload)

    def queue_notification(self, name, payload):
        for owner, queue in tuple(self.notification_queues.items()):
            if name in self.subscriptions.get(owner, ()):
                try:
                    queue.put_nowait(payload)
                    self.notification_ready[owner].set()
                except asyncio.QueueFull:
                    # Never silently coalesce transitions. Overload invalidates the session.
                    transport = self.ws_transports.get(owner)
                    if transport:
                        transport.abort()

    @route.message("ecp-2", "plugin-ui-run", "out", summary="A subscribed channel-start notification.")
    @route.message("ecp-2", "plugin-ui-run-script", "out", summary="A captured channel-script notification; requires a profile template.")
    @route.message("ecp-2", "plugin-ui-exit", "out", summary="A subscribed channel-exit notification.")
    @route.message("ecp-2", "textedit-opened", "out", summary="A measured native text field opened.")
    @route.message("ecp-2", "textedit-changed", "out", summary="Native text and collapsed cursor changed.")
    @route.message("ecp-2", "textedit-closed", "out", summary="The native text field closed.")
    async def send_notifications(self, owner, ws):
        while True:
            await self.notification_ready[owner].wait()
            async with self.command_locks[owner]:
                await self.flush_notifications(owner, ws)

    async def flush_notifications(self, owner, ws):
        queue = self.notification_queues[owner]
        while not queue.empty():
            await self.send(ws, queue.get_nowait())
            queue.task_done()
        self.notification_ready[owner].clear()

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

    def live(self, profile: RokuProfile, name: str, content: bytes) -> bytes:
        """A replayed document with the fields its profile lets the emulator write filled in.

        An ecp-2 substitution names the field inside the envelope's document
        (`content-data::ecp-setting-mode`); the document here is already decoded.
        """
        for path in profile.substitutions_for(name):
            field = path.rpartition("::")[2]
            audio_state = profile.runtime.get("audio", {}).get("query_state", {})
            if name in ("/query/audio-device", "query-audio-device") and field in audio_state.get("fields", ()):
                sessions = tuple(self.audio.sessions.values()) if self.audio else ()
                # The last-started session is an explicit emulator view when several own
                # independent senders. Physical conflict arbitration remains unmeasured.
                session = sessions[-1] if sessions else None
                if field == "rtp-info.rtp-address":
                    value = (f"{session.address[0]}:{session.address[1]}" if session
                             and session.mode == "datagram" else "")
                else:
                    value = audio_state["destinations"][session.mode if session else "idle"]
                content = xmlbytes.replace_value(content, field, value)
                continue
            if field in STATE_FIELDS:
                value = profile.live_states[field][STATE_FIELDS[field](self.core)]
            else:
                value = LIVE_FIELDS[field](self.core)
            content = xmlbytes.replace_text(content, field, value)
        return content

    def surface(self) -> Surface:
        """Everything this platform answers, as declared -- HTTP and ecp-2 alike."""
        return Surface("roku", tuple(spec for spec, _ in route.declarations(self)),
                       tuple(spec for spec, _ in route.message_declarations(self)))

    def app(self) -> web.Application:
        app = route.attach(web.Application(middlewares=[self.headers], client_max_size=16384), self)
        async def start(app):
            self.core.state_observers.add(self.observe)
        async def stop(app):
            self.core.state_observers.discard(self.observe)
            await self.disconnect()
        app.on_startup.append(start)
        app.on_shutdown.append(stop)
        return app

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
            self.track_key(request.match_info["key"], status)
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

    def _control_status(self) -> tuple[int, str]:
        mode = self.core.access
        status = dict(mode.control_statuses).get("http", mode.control_status)
        return status, "Accepted" if status == 200 else (mode.detail or f"Rejected by {mode.label}")

    # The TCL on 15.3.4 answered search and input 200 with no body, and moved nothing the
    # queries show: search opens a screen inside the home channel, and input goes to whatever
    # runs. Neither is rendered here; the request is recorded with its parameters.
    @route.post("/search/browse", operation_id="roku.http.search",
                summary="Open the search screen, with the keyword it names.")
    @route.post("/input", operation_id="roku.http.input",
                summary="Hand parameters to the channel in the foreground.")
    async def command(self, request):
        status, detail = self._control_status()
        query = request.raw_path.partition("?")[2]
        self.core.record("command", request.path.lstrip("/"), transport="http",
                         peer=request.remote or "", status=status,
                         detail=f"{detail}; {query}" if query else detail)
        return web.Response(status=status)

    @route.post("/input/{app_id}", operation_id="roku.http.input-channel",
                summary="Hand parameters to one channel by its ECP id (Play on Roku is 15985).")
    async def input_channel(self, request):
        # The set answers 404 for a channel that is not installed, as launch does; the
        # emulator accepts any id for the same reason it accepts any launch.
        status, detail = self._control_status()
        self.core.application_launch(
            request.match_info["app_id"], surface="ecp", transport="http",
            peer=request.remote or "", payload=request.raw_path.partition("?")[2],
            status=status, detail=detail, operation="app.input/ecp")
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
               operation_id="roku.http.other", captured="*", missing=501, style=CAPTURED)
    async def document(self, request):
        mode = self.core.access
        status = dict(mode.query_statuses).get("http", 200)
        if status != 200 and restricted_query(request.path):
            # Refused before the capture is consulted: the set refuses a query it could
            # answer, so whether this profile recorded the document does not matter.
            self.core.record("access", f"GET {request.path}", transport="http",
                             peer=request.remote or "", status=status, detail=mode.detail)
            return QUERY_REFUSAL.response(WireError(status, mode.refusal_body))
        profile = self.current_profile()
        content = profile.document(request.path)
        operation = "description" if request.path == "/" else request.path.removeprefix("/")
        if content is None:
            raise missing_capture(self.core, operation, profile.id, "http",
                                  request.remote or "", NO_CAPTURE)
        status = profile.document_status(request.path)
        self.core.record("query", operation, transport="http", peer=request.remote or "",
                         status=status, detail=f"captured profile: {profile.id}")
        if status != 200:
            # What the set answered instead of a document, a route it does not have.
            return CAPTURED_REFUSAL.ok(
                content, status=status,
                content_type=profile.document_content_type(request.path, default=""),
                headers=profile.document_headers(request.path))
        return CAPTURED.ok(self.live(profile, request.path, content),
                           content_type=profile.document_content_type(request.path),
                           headers=profile.document_headers(request.path))

    @route.any_method("/{tail:.*}", summary="Anything this emulator does not serve.")
    async def unsupported(self, request):
        self.core.record("unsupported", f"{request.method} {request.path}", transport="http",
                         peer=request.remote or "", status=501, detail="Outside the Remote-only profile")
        return web.Response(status=501, text="Remote-only emulator: this endpoint is not implemented")

    @route.message("ecp-2", "param-challenge", "out",
                   summary="The authentication challenge, sent unprompted as the socket opens.")
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
        if request.transport is not None:
            self.ws_transports[owner] = request.transport
        self.core.connections[owner] = {"id": owner, "peer": peer, "authenticated": False, "transport": "ws"}
        self.core.record("connection", "ws.open", transport="ws", peer=peer)
        challenge = base64.b64encode(secrets.token_bytes(16)).decode()
        await self.send(ws, {
            "notify": "authenticate", "param-challenge": challenge,
            "param-methods": ["client-id", "jwt"],
            "timestamp": f"{time.monotonic() - self.started:.3f}",
        })
        worker = None
        notifier = None
        queue: asyncio.Queue = asyncio.Queue(maxsize=128)
        # The set keeps a session that has not authenticated open, answering it, until a
        # deadline counted from the open; then it drops the connection with no close frame.
        deadline = asyncio.get_running_loop().call_later(
            AUTH_DEADLINE, self.drop_unauthenticated, request.transport, peer)
        try:
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
                    if worker is None:
                        if not await self.authenticate(ws, payload, challenge, peer):
                            continue
                        deadline.cancel()
                        self.core.connections[owner]["authenticated"] = True
                        self.notification_queues[owner] = asyncio.Queue(maxsize=128)
                        self.notification_ready[owner] = asyncio.Event()
                        self.command_locks[owner] = asyncio.Lock()
                        notifier = asyncio.create_task(self.send_notifications(owner, ws))
                        self.core.publish()
                        # Serialize commands on their own task so pings keep flowing while
                        # one is handled.
                        worker = asyncio.create_task(self.process_queue(queue, ws, owner, peer))
                        self.pending.add(worker)
                        continue
                    try:
                        queue.put_nowait(payload)
                    except asyncio.QueueFull:
                        self.core.record("connection", "ws.overloaded", transport="ws", peer=peer, status=503)
                        await ws.close(code=1013, message=b"Command queue full")
                elif message.type == WSMsgType.ERROR:
                    break
        except (ConnectionError, RuntimeError):
            self.core.record("connection", "ws.closed", transport="ws", peer=peer,
                             detail="Connection closed")
        finally:
            deadline.cancel()
            # Clear connection-owned resources before the first await: aiohttp may
            # cancel this request as its peer closes the transport.
            tasks = [task for task in (notifier, worker) if task is not None]
            for task in tasks:
                task.cancel()
            if self.audio:
                audio_task = self.audio.cancel(owner)
                if audio_task:
                    tasks.append(audio_task)
            self.notification_queues.pop(owner, None)
            self.notification_ready.pop(owner, None)
            self.command_locks.pop(owner, None)
            if worker:
                self.pending.discard(worker)
            self.websockets.pop(owner, None)
            self.ws_transports.pop(owner, None)
            self.subscriptions.pop(owner, None)
            self.core.connections.pop(owner, None)
            self.core.held.pop(owner, None)
            self.core.record("connection", "ws.disconnect", transport="ws", peer=peer)
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await ws.close()
        return ws

    @route.message("ecp-2", "authenticate", "in",
                   summary="The answer to the challenge, the only request before it succeeds.")
    async def authenticate(self, ws, data: dict, challenge: str, peer: str) -> bool:
        """Answer one frame of a session that has not authenticated yet."""
        operation, request_id = data.get("request"), data.get("request-id")
        if not isinstance(operation, str) or not isinstance(request_id, str):
            # The set drops the connection without a reply, the same as after authenticating.
            self.core.record("connection", "ws.malformed", transport="ws", peer=peer,
                             status=400, detail="request and request-id must both be strings")
            await ws.close(code=1002, message=b"Malformed request")
            raise ConnectionError("Malformed ecp-2 request")
        if operation != "authenticate":
            # Any other request is refused in the envelope; the session stays open.
            self.core.record("connection", "ws.unauthenticated", transport="ws", peer=peer,
                             status=401, request_id=request_id, detail=operation)
            await self.send(ws, response(operation, request_id, 401))
            return False
        # The request id is the client's own, echoed like any other: the official Android
        # app numbers its requests from 0 and others from 1, and the set accepts either.
        answer = data.get("param-response", data.get("response"))
        valid = isinstance(answer, str) and answer.isascii() and hmac.compare_digest(answer, auth_response(challenge))
        status = 200 if valid else 601
        self.core.record("connection", "ws.authenticate", transport="ws", peer=peer,
                         status=status, request_id=request_id)
        # A wrong answer leaves the session open, so the client may answer again.
        await self.send(ws, response("authenticate", request_id, status))
        return valid

    def drop_unauthenticated(self, transport, peer: str) -> None:
        self.core.record("connection", "ws.auth-deadline", transport="ws", peer=peer,
                         detail=f"not authenticated {AUTH_DEADLINE} s after the open")
        if transport is not None:
            transport.abort()

    async def process_queue(self, queue, ws, owner, peer):
        while True:
            data = await queue.get()
            try:
                async with self.command_locks[owner]:
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
    @route.message("ecp-2", "launch", "in",
                   summary="Launch a channel, with its params as one JSON string.")
    @route.message("ecp-2", "input", "in",
                   summary="Hand params to a channel, launching it if it is not running.")
    @route.message("ecp-2", "request-events", "in",
                   summary="Subscribe to notifications, +name or -name, comma separated.")
    @route.message("ecp-2", "set-audio-output", "in", summary="Start prepared private-listening test audio.")
    @route.message("ecp-2", "mobile-sas-disconnect", "in", summary="Stop this client's SAS stream.")
    @route.message("ecp-2", "set-textedit-text", "in", summary="A whole-field write; no native field captured yet.")
    @route.message("ecp-2", "query-themes", "in", summary="Captured theme catalogue.")
    @route.message("ecp-2", "query-screensavers", "in", summary="Captured screensaver catalogue.")
    @route.message("ecp-2", "query-av-sync-offset", "in", summary="Captured AV synchronization offsets.")
    @route.message("ecp-2", "query-curr-audio-format", "in", summary="Captured audio format.")
    @route.message("ecp-2", "query-tv-active-channel", "in", summary="The active tuner channel, or a captured refusal.")
    @route.message("ecp-2", "query-tv-channels-ex", "in", summary="Extended tuner channels, or a captured refusal.")
    @route.message("ecp-2", "query-tv-active-input", "in", summary="The active TV input, or a captured refusal.")
    @route.message("ecp-2", "query-warm-standby", "in", summary="Warm standby, or a captured refusal.")
    @route.message("ecp-2", "query-pq-options", "in", summary="Picture options, or a captured refusal.")
    @route.message("ecp-2", "query-pq-picture-modes", "in", summary="Picture modes, or a captured refusal.")
    @route.message("ecp-2", "query-pq-picture-settings", "in", summary="Picture settings, or a captured refusal.")
    @route.message("ecp-2", "query-audio-settings", "in", summary="Audio settings, or a captured refusal.")
    @route.message("ecp-2", "check-link", "in", summary="Captured device-link status.")
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
            self.track_key(key, status)
            # Hardware captures show notify both before and after the Home reply.
            # Keep replies FIFO; send queued notifications after this reply.
            await self.send(ws, response(operation, request_id, status))
            return
        if operation in ("launch", "input"):
            await self.send(ws, response(operation, request_id,
                                         self.ecp2_launch(operation, data, peer, request_id)))
            return
        if operation == "request-events":
            events = data.get("param-events")
            status, entries = subscription(events)
            chosen = self.subscriptions.setdefault(owner, set())
            for entry in entries:
                (chosen.add if entry[0] == "+" else chosen.discard)(entry[1:])
            self.core.record("request", operation, transport="ws", peer=peer, status=status,
                             request_id=request_id,
                             detail=events if isinstance(events, str) else "no param-events")
            await self.send(ws, response(operation, request_id, status))
            return
        profile = self.current_profile()
        if operation == "set-audio-output" and profile.runtime.get("audio") and self.audio:
            try:
                await self.audio.start(data, owner, peer)
            except (ValueError, KeyError, TypeError, OSError) as error:
                self.core.record("unsupported", operation, transport="ws", peer=peer,
                                 status=400, detail=str(error))
                await self.send(ws, response(operation, request_id, 400))
            else:
                content, content_type = profile.ecp2_documents["action.set-audio-output"]
                await self.send(ws, response(operation, request_id, 200, content, content_type))
            return
        if operation == "mobile-sas-disconnect" and profile.runtime.get("audio") and self.audio:
            session = self.audio.sessions.get(owner)
            if session and session.mode == "mobile-sas" and session.guid == data.get("param-devname"):
                await self.audio.stop(owner)
            await self.send(ws, response(operation, request_id, 200))
            return
        if operation == "set-textedit-text" and profile.runtime.get("textedit", {}).get("no_field_write"):
            status = await self.textedit.write(data, peer)
            self.core.record("command", operation, transport="ws", peer=peer,
                             status=status, detail="native textedit; text omitted")
            await self.send(ws, response(operation, request_id, status))
            return
        if operation == "query-textedit-state" and self.textedit.config():
            content_type = profile.ecp2_documents[operation][1]
            await self.send(ws, response(operation, request_id, 200,
                                         self.textedit.document(), content_type))
            return
        content, content_type = profile.ecp2_documents.get(operation, (None, ""))
        if content is None and operation == "query-device-info":
            # A capture without its own ecp-2 copy lends the HTTP document. The two are not
            # identical on hardware: the envelope's copy adds virtual-device-id.
            route = "/query/device-info"
            content, content_type = profile.document(route), profile.document_content_type(route)
        if content is not None:
            content = self.live(profile, operation, content)
        # An unhandled request is Not Found, the way the set answers one: the request name is
        # a route on this wire, so an unknown one is missing rather than unimplemented.
        status = profile.ecp2_statuses.get(operation, 200 if content is not None else 404)
        # An unanswered request names its parameters, never their values: a guid or the
        # phone's own address is the session's, not the contract's.
        params = ", ".join(sorted(name for name in data if name not in ("request", "request-id")))
        self.core.record("query" if status == 200 else "unsupported", operation,
                         transport="ws", peer=peer, status=status, request_id=request_id,
                         detail="" if status == 200 else
                         f"{NO_CAPTURE}; params: {params or 'none'}")
        await self.send(ws, response(operation, request_id, status, content=content,
                                     content_type=content_type))

    def track_key(self, key: str, status: int) -> None:
        # Home leaves whatever channel ran for the home screen, on the set's own remote too.
        if status == 200 and self.core.key_name(key) == "Home":
            self.foreground = None

    def ecp2_launch(self, operation: str, data: dict, peer: str, request_id: str) -> int:
        """The status of an ecp-2 launch or input, measured on the Streaming Stick 4K."""
        channel, params = data.get("param-channel-id"), data.get("param-params")
        if not isinstance(channel, str) or not channel:
            status = 400
        elif params is not None and not isinstance(params, str):
            status = 400
        else:
            try:
                parsed = json.loads(params) if params else {}
            except ValueError:
                parsed = None
            if parsed is None:
                # Not JSON: the set refuses the whole request rather than dropping the params.
                status = 400
            elif operation == "launch" and channel == self.foreground and not parsed:
                # The channel already runs and nothing asks it to do anything else: the set
                # leaves it alone, where a launch with params restarts it.
                status = 204
            else:
                # The set answers 404 for a channel that is not installed; like the HTTP
                # launch, the emulator accepts any id so a client's own id is not refused.
                status = 200
            # The application event observer records the transition and notifications.
        self.core.application_launch(
            channel if isinstance(channel, str) else "", surface="ecp", transport="ws",
            peer=peer, payload=params if isinstance(params, str) else "", status=status,
            detail=f"request-id {request_id}; status {status}",
            operation=f"app.{operation}/ecp-2")
        return status

    async def disconnect(self, detail: str | None = None):
        self.generation += 1
        if self.audio:
            await self.audio.disconnect()
        for task in tuple(self.pending):
            task.cancel()
        if self.pending:
            await asyncio.gather(*tuple(self.pending), return_exceptions=True)
        # Abort transport as a reproducible network disconnect, including idle HTTP keep-alive.
        for transport in tuple(self.http_transports):
            transport.abort()
        self.http_transports.clear()
        # The ecp-2 sockets drop the same way, with no close frame: a client reads a lost
        # connection as one, where a close code would be a statement from the set. The
        # official Roku app for Android reconnects after a drop and not after a 1001.
        for transport in tuple(self.ws_transports.values()):
            transport.abort()
        self.core.held.clear()
        self.core.record("connection", "disconnect-all",
                         detail=detail or "Roku connections terminated")
