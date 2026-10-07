"""Shared state. No browser or protocol-specific server dependencies."""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import re
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .audio import AudioSniffer

if TYPE_CHECKING:
    from .platforms.base import AccessMode, PlatformDescriptor

# Stand-in for "one LAN" when a platform's access mode only admits nearby clients: the
# emulator knows the address it advertises, not the interface's real prefix length.
LOCAL_PREFIX = 24


# A field the emulated device is showing, not a setting: it never reaches the settings file.
# The bound is the emulator's own ceiling, independent of any firmware's per-field cap: every
# keystroke publishes the buffer to every dashboard subscriber.
MAX_TEXT_FIELD = 1024

# App launch payloads are useful diagnostic data, but every snapshot is broadcast to every
# dashboard subscriber. Keep the exact text up to a bounded, UI-friendly ceiling.
MAX_APPLICATION_PAYLOAD = 2048


def application_payload(value: Any) -> str:
    """Make a launch payload lossless and displayable without interpreting its contents."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return "base64:" + base64.b64encode(value).decode("ascii")
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass
class TextField:
    """The text field the emulated device currently has on screen."""

    focused: bool = False
    text: str = ""
    content_type: str = ""
    # Focus is an edge, and the payload readers must stay pure, so it is counted rather than
    # flagged: each subscriber compares the serial it last sent to decide "focus changed".
    focus_serial: int = 0
    # Who last wrote, so remote-typed and API-typed text are distinguishable in the dashboard.
    source: str = ""
    transport: str = ""


@dataclass
class VoiceState:
    """Protocol-neutral telemetry for one input session.

    The received audio is not kept here. The sniffer holds a short in-memory window of the most
    recent bytes to work out the format, and only its description reaches a snapshot.
    """

    state: str = "idle"
    active: bool = False
    session_id: str = ""
    chunks: int = 0
    bytes: int = 0
    started_at: str = ""
    ended_at: str = ""
    duration_ms: int = 0
    detail: str = ""
    transport: str = ""
    owner: str = ""
    # What the client said its audio is, when its protocol lets it say; it outranks the
    # platform's static description for this one session.
    declared_format: str = ""
    started_clock: float | None = None
    sniffer: AudioSniffer | None = None


@dataclass(frozen=True)
class Settings:
    device_profile: str = ""
    # Empty means "the active platform's first access mode"; the adapter resolves it.
    access_mode: str = ""
    # One entry per protocol the user has switched; anything absent keeps its declared
    # default. Which ids are valid depends on the active platform, so the runtime checks them.
    protocols: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def parse(cls, data: Any, base: Settings | None = None) -> Settings:
        if not isinstance(data, dict):
            raise ValueError("Settings must be a JSON object")
        data = dict(data)
        unknown = set(data) - {field.name for field in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")
        values = asdict(base or cls()) | data
        if base is not None and "protocols" in data and isinstance(data["protocols"], dict):
            # A partial patch switches the protocols it names and leaves the rest alone.
            values["protocols"] = base.protocols | data["protocols"]
        if (not isinstance(values["device_profile"], str) or
                len(values["device_profile"]) > 128):
            raise ValueError("device_profile must be a string up to 128 characters")
        # Which ids are valid depends on the active platform, so the runtime checks membership.
        if (not isinstance(values["access_mode"], str) or len(values["access_mode"]) > 32
                or not all(char.isalnum() or char in "-_" for char in values["access_mode"])):
            raise ValueError("access_mode must be an access mode id")
        protocols = values["protocols"]
        if (not isinstance(protocols, dict) or len(protocols) > 32
                or any(not isinstance(key, str)
                       or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", key)
                       or type(value) is not bool for key, value in protocols.items())):
            raise ValueError("protocols must map protocol ids to booleans")
        return cls(**values)


def parse_settings_document(document: Any) -> tuple[str | None, Settings]:
    """Split a settings file into its platform tag and its validated settings."""
    if not isinstance(document, dict) or document.get("schema_version") != 2:
        raise ValueError("A settings file with schema_version=2 is required; "
                         "delete it to start from defaults")
    configured_platform = document.get("platform")
    if configured_platform is not None and not isinstance(configured_platform, str):
        raise ValueError("platform must be a string")
    return configured_platform, Settings.parse(document.get("settings"), Settings())


def read_settings(path: Path) -> tuple[str | None, Settings]:
    """Return the platform the file was saved for, if any, and its settings."""
    if not path.exists():
        return None, Settings()
    return parse_settings_document(json.loads(path.read_text(encoding="utf-8")))


def write_settings(path: Path, settings: Settings, platform_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"schema_version": 2, "platform": platform_id,
                                     "settings": asdict(settings)},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _discovery_kinds() -> frozenset[str]:
    # Deferred: the platform contract imports Core, so it cannot be imported at module level.
    from .platforms.base import DISCOVERY_KINDS

    return DISCOVERY_KINDS


class Core:
    def __init__(self, platform: PlatformDescriptor, settings: Settings | None = None):
        self.platform = platform
        self.settings = settings or Settings()
        self.host = "127.0.0.1"
        self.service_port = platform.default_port
        self.service_port_pinned = False
        # Derived from `protocols`; kept as plain attributes so a test can drive one directly.
        self.service_listening = False
        self.discovery_active = False
        self.discovery_error: str | None = None
        self.protocols: list[dict[str, Any]] = []
        self.events: deque[dict] = deque(maxlen=500)
        self.sequence = 0
        self.revision = 0
        self.subscribers: set[asyncio.Queue] = set()
        self.connections: dict[str, dict] = {}
        self.held: dict[str, set[str]] = {}
        self.counts: Counter = Counter()
        self.accepted = 0
        self.rejected = 0
        self.last_key: dict | None = None
        self.power = True
        # Not every set counts to 100, and not every set boots at a quarter volume: both are
        # the platform's own scale, declared on its descriptor.
        self.volume = platform.volume.start
        self.muted = False
        self.device_profile: dict[str, Any] = {}
        self.device_profiles: list[dict[str, Any]] = []
        self.pairing: dict[str, Any] | None = None
        self.text_field = TextField()
        # Which field types exist is captured per device, so the adapter publishes them.
        self.content_types: tuple = ()
        self.default_content_type = ""
        self.voice_state = VoiceState()
        self.application_catalog: dict[str, dict[str, Any]] = {}
        self.dynamic_applications: dict[str, dict[str, Any]] = {}
        self.last_application_launch: dict[str, Any] | None = None
        self.application_epoch = 0

    @property
    def keys(self) -> tuple[str, ...]:
        # A property, not a copy: the active platform can be retargeted at runtime.
        return self.platform.keys

    @property
    def keyboard(self):
        """The active platform's KeyboardSpec, or None when it serves no text input."""
        return self.platform.keyboard

    @property
    def voice(self):
        """The active platform's VoiceSpec, or None when it exposes no voice input."""
        return self.platform.voice

    @property
    def applications(self):
        """The active platform's application-launch contract, or None."""
        return self.platform.applications

    @property
    def content_type(self):
        """The ContentType the focused field is showing, or None."""
        return self.content(self.text_field.content_type)

    def content(self, content_id: str):
        for content in self.content_types:
            if content.id == content_id:
                return content
        return None

    @property
    def default_content(self):
        """The content type a freshly reset field starts on."""
        return self.content(self.default_content_type) or (
            self.content_types[0] if self.content_types else None)

    def set_content_types(self, content_types, default: str = "") -> None:
        """Take the field types the active captured device reported."""
        self.content_types = tuple(content_types)
        self.default_content_type = default
        field = self.text_field
        default = self.default_content
        if self.content(field.content_type) is None:
            # Either the field type this device does not report, or none yet: a switch clears
            # the field before the arriving adapter publishes what its capture observed.
            self.text_field = TextField(content_type=default.id if default else "")

    @property
    def access(self) -> AccessMode:
        """The access mode in force, falling back to the platform's first mode."""
        for mode in self.platform.access_modes:
            if mode.id == self.settings.access_mode:
                return mode
        return self.platform.access_modes[0]

    def is_local_client(self, peer: str) -> bool:
        """Whether a client counts as being on the emulated device's own network."""
        try:
            client = ipaddress.IPv4Address(peer)
            host = ipaddress.IPv4Address(self.host)
        except (ipaddress.AddressValueError, ValueError):
            # An address the emulator cannot classify is never treated as remote.
            return True
        if client.is_loopback or host.is_loopback:
            return True
        return client in ipaddress.IPv4Network(f"{host}/{LOCAL_PREFIX}", strict=False)

    def access_denial(self, peer: str = "") -> tuple[int, str] | None:
        """The status and reason for refusing a whole request, or None to serve it."""
        mode = self.access
        if mode.query_status != 200:
            return mode.query_status, mode.detail or f"Rejected by {mode.label}"
        if mode.off_subnet_status and not self.is_local_client(peer):
            return (mode.off_subnet_status,
                    "Rejected: the client is outside the emulated device's network")
        return None

    def set_protocols(self, rows: list[dict[str, Any]]) -> None:
        """Take the adapter's protocol rows and refresh the aggregates shared code reads.

        The adapter owns the truth: it holds the typed profile, the platform's specs, and the
        listeners. Everything here is a summary the dashboard and `key()` can read without
        knowing which protocol carried a command.
        """
        # Deferred: base imports Core, so it cannot be imported at module level.
        from .platforms.base import DISCOVERY_KINDS

        self.protocols = rows
        self.service_listening = any(row["listening"] for row in rows if row["control"])
        self.discovery_active = any(row["listening"] for row in rows
                                    if row["kind"] in DISCOVERY_KINDS)
        self.discovery_error = "; ".join(
            f"{row['label']}: {row['error']}" for row in rows
            if row["error"] and row["kind"] in DISCOVERY_KINDS) or None

    def set_device_profile(self, active: dict[str, Any], available: list[dict[str, Any]]) -> None:
        self.device_profile = dict(active)
        self.device_profiles = [dict(item) for item in available]

    def retarget(self, platform: PlatformDescriptor) -> None:
        """Point shared state at another platform.

        Sessions, counters, and the captured-device selection belong to the platform that is
        being left, so none of them carry over. The port returns to the new platform's default;
        a `--port` override applies only to the platform started at launch.
        """
        self.platform = platform
        self.service_port = platform.default_port
        self.service_port_pinned = False
        self.connections.clear()
        self.held.clear()
        self.pairing = None
        self.device_profile = {}
        self.device_profiles = []
        self.content_types = ()
        self.default_content_type = ""
        self.discovery_error = None
        self.protocols = []
        self.service_listening = False
        self.discovery_active = False
        self.application_catalog.clear()
        self.dynamic_applications.clear()
        self.last_application_launch = None
        # No event here: the caller records the switch once the new adapter has published
        # its identity, so no subscriber ever sees a half-retargeted snapshot.
        self.clear_state()

    def snapshot(self) -> dict:
        # Deferred: the platform registry imports Core, so it cannot be imported at module level.
        from .platforms import platform_choices

        primary = next((row for row in self.protocols if row["primary"]), {})
        discovery = " · ".join(row["label"] for row in self.protocols
                               if row["kind"] in _discovery_kinds() and row["enabled"])
        return {
            "schema_version": 2, "revision": self.revision,
            "device": {
                **self.device_profile,
                "profile": self.device_profile.get("id", ""),
                "platform": self.platform.id,
                "platform_name": self.platform.display_name,
                "host": self.host,
                "port": self.service_port,
                "protocol": primary.get("protocol_label") or self.platform.protocol_label,
                "transports": self.platform.transports,
                "scheme": primary.get("scheme") or self.platform.service_scheme,
                "discovery": discovery or self.platform.discovery_label,
            },
            "device_profiles": self.device_profiles,
            "platforms": list(platform_choices()),
            "settings": asdict(self.settings), "keys": self.keys,
            "access_modes": [{"id": mode.id, "label": mode.label, "summary": mode.summary}
                             for mode in self.platform.access_modes],
            "protocols": [dict(row) for row in self.protocols],
            "access": {"id": self.access.id, "label": self.access.label,
                       "summary": self.access.summary, "status_label": self.access.status_label,
                       "badge": self.access.badge, "discoverable": self.access.discoverable},
            "service_listening": self.service_listening,
            "discovery_active": self.discovery_active, "discovery_error": self.discovery_error,
            "connections": list(self.connections.values()),
            "held_keys": sorted(name for name in set().union(*self.held.values())
                                if not self.is_literal_key(name)) if self.held else [],
            "counts": dict(self.counts), "accepted": self.accepted, "rejected": self.rejected,
            "last_key": self.last_key,
            "keyboard": self.keyboard_snapshot(),
            "voice": self.voice_snapshot(),
            "applications": self.application_snapshot(),
            "power": self.power, "volume": self.volume, "muted": self.muted,
            "events": list(self.events),
            "limitations": self.platform.limitations,
            "pairing": dict(self.pairing) if self.pairing is not None else None,
        }

    def application_surface(self, surface_id: str):
        spec = self.applications
        if spec is None:
            return None
        return next((surface for surface in spec.surfaces if surface.id == surface_id), None)

    @staticmethod
    def application_key(surface: str, app_id: str) -> str:
        return f"{surface}:{app_id}"

    def set_applications(self, items: list[dict[str, Any]]) -> None:
        """Publish a captured app catalogue for the active profile.

        A profile switch replaces both the captured catalogue and any IDs learned dynamically
        from protocols such as DIAL. Cross-surface aliases are deliberately not guessed: a
        native wire ID remains a distinct card until captured data explicitly says otherwise.
        """
        catalogue: dict[str, dict[str, Any]] = {}
        for item in items:
            surface_id = str(item.get("surface") or "")
            app_id = str(item.get("id") or "")
            surface = self.application_surface(surface_id)
            if surface is None or not app_id:
                raise ValueError("Application catalogue entries need a declared surface and id")
            key = self.application_key(surface_id, app_id)
            catalogue[key] = {
                "key": key, "id": app_id, "name": str(item.get("name") or app_id),
                "surface": surface_id, "surface_label": surface.label,
                "catalogued": True, "available": bool(item.get("available", True)),
            }
        self.application_catalog = catalogue
        self.dynamic_applications.clear()
        self.last_application_launch = None

    def observe_application(self, app_id: str, *, surface: str, name: str = "",
                            available: bool = True) -> dict[str, Any]:
        """Add a wire ID learned from a per-app query or launch request."""
        app_id = str(app_id)[:256]
        surface_spec = self.application_surface(surface)
        if surface_spec is None:
            raise ValueError(f"Unknown application surface: {surface}")
        if not app_id:
            app_id = "(missing app id)"
        key = self.application_key(surface, app_id)
        existing = self.application_catalog.get(key) or self.dynamic_applications.get(key)
        if existing is not None:
            if name and existing["name"] == existing["id"]:
                existing["name"] = str(name)[:160]
            existing["available"] = bool(available)
            return existing
        entry = {
            "key": key, "id": app_id, "name": str(name or app_id)[:160],
            "surface": surface, "surface_label": surface_spec.label,
            "catalogued": False, "available": bool(available),
        }
        self.dynamic_applications[key] = entry
        return entry

    def application_launch(self, app_id: str, *, surface: str, transport: str,
                           peer: str = "", name: str = "", payload: str = "",
                           status: int = 200, detail: str = "",
                           operation: str = "") -> dict[str, Any]:
        """Record one accepted or rejected native application-launch request."""
        normalized_id = str(app_id)[:256] or "(missing app id)"
        existing = (self.application_catalog.get(self.application_key(surface, normalized_id))
                    or self.dynamic_applications.get(
                        self.application_key(surface, normalized_id)))
        entry = self.observe_application(app_id, surface=surface, name=name,
                                         available=(existing["available"] if existing is not None
                                                    else status < 400))
        raw_payload = str(payload)
        clipped = raw_payload[:MAX_APPLICATION_PAYLOAD]
        summary = entry["id"]
        if raw_payload:
            summary += f"; payload={raw_payload[:350]}"
        event = self.record(
            "application", operation or f"app.launch/{surface}",
            transport=transport, peer=peer,
            status=status, detail=detail or summary,
            app_id=entry["id"], app_surface=surface,
        )
        self.last_application_launch = {
            "event_id": event["id"], "time": event["time"], "key": entry["key"],
            "id": entry["id"], "name": entry["name"], "surface": surface,
            "surface_label": entry["surface_label"], "transport": transport,
            "peer": peer[:160], "status": status, "detail": detail[:500],
            "payload": clipped, "payload_truncated": len(raw_payload) > len(clipped),
        }
        self.publish()
        return event

    def application_snapshot(self) -> dict | None:
        spec = self.applications
        if spec is None:
            return None
        items = list(self.application_catalog.values()) + list(self.dynamic_applications.values())
        return {
            "label": spec.label,
            "surfaces": [{"id": item.id, "label": item.label} for item in spec.surfaces],
            "items": [dict(item) for item in items],
            "last_launch": dict(self.last_application_launch)
            if self.last_application_launch is not None else None,
        }

    def keyboard_snapshot(self) -> dict | None:
        """What the dashboard needs to draw the keyboard tile, or None to hide it."""
        keyboard = self.keyboard
        if keyboard is None:
            return None
        field = self.text_field
        return {
            "label": keyboard.label,
            "content_types": [{"id": content.id, "label": content.label,
                               "hidden": content.hidden, "summary": content.summary}
                              for content in self.content_types],
            "text_api": keyboard.text_api,
            "literal_prefix": keyboard.literal_prefix,
            "delete_key": keyboard.delete_key,
            "enter_key": keyboard.enter_key,
            "max_length": keyboard.max_length or MAX_TEXT_FIELD,
            "field": {"focused": field.focused, "text": field.text,
                      "content_type": field.content_type, "hidden": self.masked(),
                      "length": len(field.text),
                      "source": field.source, "transport": field.transport},
        }

    def voice_snapshot(self) -> dict | None:
        """Status and counters for the dashboard, never the received audio itself."""
        voice = self.voice
        if voice is None:
            return None
        state = self.voice_state
        duration = state.duration_ms
        if state.active and state.started_clock is not None:
            duration = max(0, int((time.monotonic() - state.started_clock) * 1000))
        return {
            "label": voice.label,
            "mode": voice.mode,
            "format": state.declared_format or voice.audio_format,
            "state": state.state,
            "active": state.active,
            "session_id": state.session_id,
            "chunks": state.chunks,
            "bytes": state.bytes,
            "started_at": state.started_at,
            "ended_at": state.ended_at,
            "duration_ms": duration,
            "detail": state.detail,
            "transport": state.transport,
            "detected": state.sniffer.snapshot() if state.sniffer else None,
        }

    # ── voice input ─────────────────────────────────────────────────────────────────
    def voice_begin(self, session_id: int | str, *, owner: str, transport: str,
                    peer: str = "", listening: bool = False, detail: str = "") -> bool:
        """Open the single voice input owned by a protocol connection."""
        if self.voice is None or self.voice_state.active:
            return False
        now = datetime.now(timezone.utc).isoformat()
        self.voice_state = VoiceState(
            state="listening" if listening else "waiting",
            active=True,
            session_id=str(session_id),
            started_at=now,
            detail=detail,
            transport=transport,
            owner=owner,
            started_clock=time.monotonic(),
            sniffer=AudioSniffer(),
        )
        self.record("voice", "voice.begin", transport=transport, peer=peer, status=200,
                    detail=detail or f"session={session_id}")
        return True

    def _voice_matches(self, session_id: int | str, owner: str) -> bool:
        state = self.voice_state
        return state.active and state.session_id == str(session_id) and state.owner == owner

    def voice_ready(self, session_id: int | str, *, owner: str, transport: str,
                    peer: str = "", declared_format: str = "") -> bool:
        if not self._voice_matches(session_id, owner) or self.voice_state.state != "waiting":
            return False
        self.voice_state.declared_format = declared_format
        self.voice_state.state = "listening"
        self.voice_state.detail = "Ready for audio"
        self.record("voice", "voice.ready", transport=transport, peer=peer, status=200,
                    detail=f"session={session_id}")
        return True

    def voice_payload(self, session_id: int | str, byte_count: int, *, owner: str,
                      transport: str, peer: str = "", data: bytes | None = None) -> bool:
        """Count one chunk of audio; `data`, when the protocol hands it over, is sniffed."""
        if (not self._voice_matches(session_id, owner)
                or self.voice_state.state not in ("listening", "receiving")
                or byte_count <= 0):
            return False
        sniffer = self.voice_state.sniffer
        if data and sniffer is not None and sniffer.feed(data):
            found = sniffer.result
            self.record("voice", "voice.format", transport=transport, peer=peer, status=200,
                        detail=f"{found['label']} · {found['confidence']} · {found['basis']}")
        self.voice_state.state = "receiving"
        self.voice_state.chunks += 1
        self.voice_state.bytes += byte_count
        self.voice_state.detail = "Receiving audio"
        # Only the first chunk is an event: a client streaming a hundred frames a second would
        # push everything else out of the log. The counters and voice.end carry the rest.
        if self.voice_state.chunks == 1:
            self.record("voice", "voice.payload", transport=transport, peer=peer, status=200,
                        detail=f"session={session_id}; first chunk {byte_count} bytes")
        else:
            self.publish()
        return True

    def voice_end(self, session_id: int | str, *, owner: str, transport: str,
                  peer: str = "", detail: str = "") -> bool:
        if not self._voice_matches(session_id, owner):
            return False
        state = self.voice_state
        totals = f"{state.chunks} chunks, {state.bytes} bytes"
        self._finish_voice("completed", detail or "Voice input completed")
        self.record("voice", "voice.end", transport=transport, peer=peer, status=200,
                    detail=f"{detail or f'session={session_id}'}; {totals}")
        return True

    def voice_interrupt(self, *, owner: str, transport: str, peer: str = "",
                        detail: str = "Connection closed") -> bool:
        if not self.voice_state.active or self.voice_state.owner != owner:
            return False
        session_id = self.voice_state.session_id
        self._finish_voice("interrupted", detail)
        self.record("voice", "voice.interrupted", transport=transport, peer=peer,
                    status=499, detail=f"session={session_id}; {detail}")
        return True

    def _finish_voice(self, state: str, detail: str) -> None:
        voice = self.voice_state
        voice.state = state
        voice.active = False
        voice.ended_at = datetime.now(timezone.utc).isoformat()
        if voice.started_clock is not None:
            voice.duration_ms = max(0, int((time.monotonic() - voice.started_clock) * 1000))
        voice.started_clock = None
        voice.detail = detail
        voice.owner = ""

    def publish(self) -> None:
        self.revision += 1
        # Coalesce updates for slow UI clients; each message is a complete snapshot.
        for queue in self.subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(True)

    def record(self, kind: str, operation: str, *, transport: str = "lab",
               peer: str = "", status: int | None = None, detail: str = "", **extra) -> dict:
        self.sequence += 1
        event = {"id": self.sequence, "time": datetime.now(timezone.utc).isoformat(),
                 "kind": kind, "operation": operation[:160], "transport": transport,
                 "peer": peer[:160], "status": status, "detail": detail[:500], **extra}
        self.events.append(event)
        self.publish()
        return event

    # ── keys ───────────────────────────────────────────────────────────────────────────
    def key_name(self, key: str) -> str:
        """The declared spelling of a key that arrived, or "" when this set has no such key.

        A platform whose firmware ignores case declares `fold_key_case`, and every counter,
        held-key set and key effect is then keyed by the declared spelling rather than by
        whichever casing the client happened to send.
        """
        if key in self.keys:
            return key
        if self.platform.fold_key_case:
            folded = key.casefold()
            for name in self.keys:
                if name.casefold() == folded:
                    return name
        return ""

    # ── text input ─────────────────────────────────────────────────────────────────────
    def is_literal_key(self, key: str) -> bool:
        """Whether this key is one character of text on the active platform's remote."""
        keyboard = self.keyboard
        return bool(keyboard and keyboard.literal_char(key, self.platform.fold_key_case))

    def held_name(self, key: str) -> str:
        """A literal key in its declared spelling, so a down and its up match in any case."""
        keyboard = self.keyboard
        return keyboard.literal_prefix + keyboard.literal_char(key, self.platform.fold_key_case)

    def masked(self) -> bool:
        """Whether the focused field's characters must not be shown or logged."""
        content = self.content_type
        return bool(content and content.hidden)

    def text_detail(self, value: str) -> str:
        """How a piece of typed text may be described in an event.

        A hidden field is counted, never quoted: events are pushed to every subscriber and
        written to the log export, so the characters themselves must not reach them.
        """
        return f"{len(value)} chars" if self.masked() else value

    def log_key(self, key: str) -> str:
        """The key name as it may appear in an event, masking a character of hidden text."""
        keyboard = self.keyboard
        if keyboard and self.is_literal_key(key) and self.masked():
            # The prefix as it arrived, not the declared one: the log exists so a driver
            # author sees what was sent, and folding it would hide half of what was.
            return f"{key[:len(keyboard.literal_prefix)]}\u00b7"
        return key

    def type_key(self, key: str, transport: str, peer: str) -> None:
        """Apply one character sent as a remote keypress."""
        keyboard = self.keyboard
        if keyboard is None or not self.text_field.focused:
            return
        self.apply_text("insert", text=keyboard.literal_char(key, self.platform.fold_key_case))
        self.text_field.source, self.text_field.transport = transport, transport

    def edit_key(self, key: str, transport: str, peer: str) -> None:
        """Apply the remote's delete or submit button while a field has focus.

        `key` is the declared spelling, which is what `Core.key` resolved before calling.
        """
        keyboard = self.keyboard
        if keyboard is None or not self.text_field.focused:
            return
        if keyboard.delete_key and key == keyboard.delete_key:
            self.apply_text("delete", count=1)
        elif keyboard.enter_key and key == keyboard.enter_key:
            self.apply_text("enter")
        else:
            return
        self.text_field.source, self.text_field.transport = transport, transport

    def result_for_text(self, transport: str, peer: str = "") -> tuple[int, str]:
        """Whether a text command may proceed.

        The dashboard is the device's own screen, not a client on the network, so an access
        mode that refuses network control does not disable the on-screen keyboard.
        """
        if self.keyboard is None:
            return 404, "This platform serves no text input"
        if transport == "lab":
            return 200, "Accepted"
        denial = self.access_denial(peer)
        if denial:
            return denial
        mode = self.access
        status = dict(mode.control_statuses).get(transport, mode.control_status)
        if status != 200:
            return status, mode.detail or f"Rejected by {mode.label}"
        return 200, "Accepted"

    def focus_field(self, focused: bool, content_type: str | None = None,
                    *, transport: str = "lab", peer: str = "", source: str = "") -> None:
        """Move the emulated device's field focus, as an app on the TV would."""
        keyboard = self.keyboard
        if keyboard is None:
            raise ValueError("This platform serves no text input")
        field = self.text_field
        wanted = field.content_type
        if content_type is not None:
            if content_type and self.content(content_type) is None:
                raise ValueError(f"Unknown content type: {content_type}")
            wanted = content_type
        if not wanted:
            default = self.default_content
            wanted = default.id if default else ""
        changed = bool(focused) != field.focused
        field.focused = bool(focused)
        field.content_type = wanted
        if changed:
            # Only a real transition counts, so a subscriber is not told focus moved twice.
            field.focus_serial += 1
        if not field.focused:
            field.text = ""
        field.source, field.transport = source or transport, transport
        self.record("state", "field.focus" if field.focused else "field.blur",
                    transport=transport, peer=peer, status=200,
                    detail=f"{wanted or 'text'}" if field.focused else "")
        self.publish()

    def check_text(self, op: str, *, text: str = "", count: int = 1) -> None:
        """Validate a text command's arguments, whether or not anything has focus.

        Arguments are checked even when the command will be discarded, so a malformed
        request is still a 400 rather than a silent success.
        """
        if op not in ("insert", "delete", "enter", "clear"):
            raise ValueError(f"Unknown text operation: {op}")
        if op == "insert" and not isinstance(text, str):
            raise ValueError("text must be a string")
        if op == "delete" and (not isinstance(count, int) or isinstance(count, bool)
                               or count < 1):
            raise ValueError("count must be a positive integer")

    def apply_text(self, op: str, *, text: str = "", count: int = 1,
                   replace: bool = False) -> tuple[str, str]:
        """Mutate the buffer. Returns (operation name, event detail)."""
        self.check_text(op, text=text, count=count)
        field = self.text_field
        if op == "insert":
            value = text if replace else field.text + text
            if len(value) > MAX_TEXT_FIELD:
                value = value[:MAX_TEXT_FIELD]
            keyboard = self.keyboard
            if keyboard and keyboard.max_length:
                value = value[:keyboard.max_length]
            field.text = value
            detail = self.text_detail(text)
            return "text/insert", f"replace {detail}" if replace else detail
        if op == "delete":
            removed = min(count, len(field.text))
            field.text = field.text[:len(field.text) - removed]
            return "text/delete", f"{removed} of {count}"
        if op == "enter":
            detail = self.text_detail(field.text)
            # The captured set dismisses the keyboard on Enter: the widget it pushes next is
            # the blurred one, so submitting is a focus transition and not just an event.
            field.text = ""
            field.focused = False
            field.focus_serial += 1
            return "text/enter", detail
        field.text = ""
        return "text/clear", ""

    async def text(self, op: str, *, transport: str, peer: str = "", text: str = "",
                   count: int = 1, replace: bool = False,
                   source: str = "") -> tuple[int, str]:
        """Apply one text command from the dashboard or from the wire.

        A device may answer a text write successfully even when nothing on screen has focus,
        so an unfocused field is not an error here: the write is recorded and discarded, which
        is what the captured firmware does.
        """
        status, detail = self.result_for_text(transport, peer)
        self.record("request", f"text/{op}", transport=transport, peer=peer)
        if status == 200 and transport != "lab" and not self.service_listening:
            self.record("cancelled", f"text/{op}", transport=transport, peer=peer,
                        detail="Connection closed before command completion")
            return 503, "Service stopped"
        if status != 200:
            self.rejected += 1
            self.record("command", f"text/{op}", transport=transport, peer=peer,
                        status=status, detail=detail)
            self.publish()
            return status, detail
        field = self.text_field
        try:
            self.check_text(op, text=text, count=count)
        except ValueError as error:
            self.rejected += 1
            self.record("command", f"text/{op}", transport=transport, peer=peer, status=400,
                        detail=str(error))
            self.publish()
            return 400, str(error)
        if not field.focused:
            # The captured set accepts the write and drops it: there is no field to edit, and
            # it still answers returnValue true rather than failing the client's queue.
            self.record("command", f"text/{op}", transport=transport, peer=peer, status=200,
                        detail="discarded: no field focused")
            self.publish()
            return 200, "Accepted"
        operation, applied = self.apply_text(op, text=text, count=count, replace=replace)
        field.source, field.transport = source or transport, transport
        self.record("command", operation, transport=transport, peer=peer, status=200,
                    detail=applied)
        self.publish()
        return 200, "Accepted"

    def result_for_key(self, key: str, transport: str, peer: str = "") -> tuple[int, str]:
        if not self.key_name(key) and not self.is_literal_key(key):
            # A platform that declares no keyboard but whose own wire produces text keys
            # names their prefixes, so the refusal says out of scope rather than unknown.
            if self.keyboard is None and key.startswith(self.platform.text_key_prefixes):
                return 501, "Text input is out of scope"
            return 400, "Unknown key"
        denial = self.access_denial(peer)
        if denial:
            return denial
        mode = self.access
        status = dict(mode.control_statuses).get(transport, mode.control_status)
        if status != 200:
            return status, mode.detail or f"Rejected by {mode.label}"
        return 200, "Accepted"

    async def key(self, key: str, action: str, transport: str, peer: str,
                  owner: str, request_id: str = "", note: str = "") -> tuple[int, str]:
        # Decisions take effect at request arrival; settings do not rewrite in-flight commands.
        # `note` is what a protocol wants the log to show about the request beyond its key,
        # such as a body it did not otherwise act on.
        status, detail = self.result_for_key(key, transport, peer)
        epoch = self.connections.get(owner) if transport == "ws" else None
        self.record("request", f"{action}/{key}", transport=transport, peer=peer,
                    request_id=request_id, detail=note)
        if not self.service_listening or (transport == "ws" and self.connections.get(owner) is not epoch):
            self.record("cancelled", f"{action}/{key}", transport=transport, peer=peer,
                        detail="Connection closed before command completion", request_id=request_id)
            return 503, "Service stopped"
        if status == 200:
            literal = self.is_literal_key(key)
            name = self.held_name(key) if literal else self.key_name(key) or key
            if action == "keyup":
                held = self.held.get(owner, set())
                if name not in held and self.platform.unheld_release_status != 200:
                    status = self.platform.unheld_release_status
                    detail = "Accepted: the key was not held"
                held.discard(name)
            elif literal:
                # Text is not a button: a literal key stays out of the counters, and is held
                # only between its own down and up, so the set cannot grow as text is typed.
                self.accepted += 1
                if action == "keydown":
                    self.held.setdefault(owner, set()).add(name)
                self.type_key(key, transport, peer)
            else:
                self.accepted += 1
                self.counts[name] += 1
                if action == "keydown":
                    self.held.setdefault(owner, set()).add(name)
                if action != "keyup":
                    self.edit_key(name, transport, peer)
                effect = dict(self.platform.key_effects).get(name)
                if effect is not None:
                    self.apply(effect)
        else:
            self.rejected += 1
        logged = self.log_key(key)
        event = self.record("command", f"{action}/{logged}", transport=transport, peer=peer,
                            status=status, detail=detail, key=logged, action=action,
                            request_id=request_id)
        # A typed character is not a remote button, so it never becomes the "last key" tile.
        if not self.is_literal_key(key):
            self.last_key = event
        self.publish()
        return status, detail

    def apply(self, effect, reason: str = "") -> None:
        """Move one simulated device value, the only way any of them ever moves.

        A `reason` records the change in the event log. The key path leaves it empty because
        the command it belongs to is recorded already; a protocol that wakes the set outside
        a keypress passes one, so the log shows what a client would otherwise see happen for
        no visible cause.
        """
        current = getattr(self, effect.field)
        if effect.operation == "toggle":
            value = not current
        elif effect.operation == "set":
            # Volume is a number, so an absolute set carries it in `amount`; the others are flags.
            value = (self.platform.volume.clamp(effect.amount) if effect.field == "volume"
                     else effect.value)
        else:
            value = self.platform.volume.clamp(current + effect.amount)
        setattr(self, effect.field, value)
        if reason:
            self.record("state", f"{effect.field}.{effect.operation}", detail=reason)

    def clear_state(self) -> None:
        """Return simulated device state to its start-up values without recording an event."""
        self.counts.clear()
        self.held.clear()
        self.accepted = self.rejected = 0
        self.last_key = None
        self.power, self.volume, self.muted = True, self.platform.volume.start, False
        self.voice_state = VoiceState()
        self.dynamic_applications.clear()
        self.last_application_launch = None
        self.application_epoch += 1
        # Resolved from the arriving platform, so a snapshot never pairs one platform's
        # content type with another platform's descriptor.
        default = self.default_content
        self.text_field = TextField(content_type=default.id if default else "")

    def reset(self, detail: str = "State reset; settings and connections preserved") -> None:
        self.clear_state()
        self.record("state", "state.reset", detail=detail)
