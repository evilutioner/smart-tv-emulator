"""Contract shared by Smart TV protocol adapters."""
from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol, TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from tvemu.core import Core

# A discovery protocol answers multicast probes instead of binding a service port of its own.
DISCOVERY_KINDS = frozenset({"ssdp", "mdns"})


@dataclass(frozen=True)
class AccessMode:
    """One value of a platform's own "who may control this TV" setting.

    A platform declares the modes its firmware actually offers; the shared code only reads
    this data, so a mode never becomes an `if platform == …` anywhere outside the platform
    package. `control_statuses` maps a transport id to the status returned for remote keys,
    and `control_status` covers the transports it does not list. A `query_status` other than
    200 closes the whole protocol surface, while `query_statuses` maps a transport id to the
    status for the queries the platform itself marks as restricted, leaving the rest served,
    and `command_statuses` refuses every command on a transport before it is even read.
    `refusal_body` is what the firmware writes on a refused query, where `detail` is the
    emulator's explanation for the event log. `off_subnet_status` rejects clients that do not
    share the device's subnet. Statuses belong to the platform contract and cannot be edited
    from the dashboard or a settings file.
    """

    id: str
    label: str
    summary: str
    status_label: str
    badge: str = "good"
    control_status: int = 200
    control_statuses: tuple[tuple[str, int], ...] = ()
    query_status: int = 200
    query_statuses: tuple[tuple[str, int], ...] = ()
    command_statuses: tuple[tuple[str, int], ...] = ()
    off_subnet_status: int = 0
    discoverable: bool = True
    detail: str = ""
    refusal_body: str = ""


# The single mode of a platform whose firmware has no equivalent restriction setting.
OPEN_ACCESS = AccessMode(
    id="enabled",
    label="Enabled — allow commands",
    summary="Paired clients may send remote commands.",
    status_label="Service available",
)


class DiscoveryResponder(Protocol):
    """A responder that answers searches on a fixed multicast group instead of a port."""

    name: str
    async def start(self) -> None: ...
    async def stop(self) -> None: ...


@dataclass(frozen=True)
class ProtocolSpec:
    """One network protocol a platform can serve, and how the dashboard names it.

    The catalogue is platform data: shared code renders, switches, and reports these entries
    without ever naming one. `kind` is the only wire fact shared code needs; a kind in
    `DISCOVERY_KINDS` advertises a port rather than binding one. Which of these a captured
    device actually exposes, and on which port, is profile data.
    """

    id: str
    # Short dashboard name: the protocols group lists these, so keep them terse.
    label: str
    kind: str
    summary: str
    # A captured profile may override this for the device it describes.
    default: bool = True
    # Remote key commands arrive over this protocol.
    control: bool = False
    # Address scheme when this protocol is the primary one; blank falls back to `kind`.
    scheme: str = ""
    protocol_label: str = ""
    transport: str = ""
    # The pairing mechanism this protocol brings with it, if any.
    pairing: str = ""


@dataclass(frozen=True)
class ContentType:
    """One kind of text field a captured device's firmware reported focus on.

    Which types exist is per-device capture data, not a platform trait, so these are published
    by the platform adapter from its captured profile rather than declared in the descriptor.

    `hidden` is the whole reason this is data rather than a name: shared code masks the
    buffer and keeps it out of the event log without knowing what a password field is called
    on any particular TV.
    """

    id: str
    label: str
    hidden: bool = False
    summary: str = ""


@dataclass(frozen=True)
class KeyboardSpec:
    """How text reaches one platform's emulated device.

    The key names live here, not in shared code: `delete_key` and `enter_key` are members of
    one platform's own key set, so a shared `if key == "Backspace"` would be a platform check
    wearing a key name. An empty string means this remote has no such key.
    """

    label: str
    # A per-character keypress prefix, for a remote that sends text as `<prefix><char>`.
    literal_prefix: str = ""
    delete_key: str = ""
    enter_key: str = ""
    # Whether the protocol carries whole strings rather than one keypress per character.
    text_api: bool = False
    # The emulated firmware's own per-field cap; 0 until a capture measures one.
    max_length: int = 0

    def __post_init__(self) -> None:
        if not (self.text_api or self.literal_prefix):
            raise ValueError("A keyboard needs either text_api or a literal_prefix")

    def literal_char(self, key: str, fold: bool = False) -> str:
        """The single character a literal keypress carries, or "" when it is not one.

        A remote of this kind sends one keypress per character, so anything longer than a
        single character after the prefix is a malformed key rather than text. `fold` is the
        platform's own `fold_key_case`: the prefix is then matched without regard to case
        while the character after it is carried through untouched, because the character is
        payload and its case is the text the user typed.
        """
        prefix = self.literal_prefix
        if not prefix:
            return ""
        head = key[:len(prefix)]
        if head != prefix and not (fold and head.casefold() == prefix.casefold()):
            return ""
        remainder = key[len(prefix):]
        return remainder if len(remainder) == 1 else ""


@dataclass(frozen=True)
class VoiceSpec:
    """How a platform exposes voice input to the shared status tile.

    ``stream`` means the emulator receives audio payloads. ``trigger`` represents a captured
    start/stop API whose audio transport is outside the emulated surface. The shared layer
    deliberately knows neither platform names nor wire messages.
    """

    label: str
    mode: str
    audio_format: str = ""

    def __post_init__(self) -> None:
        if self.mode not in ("stream", "trigger"):
            raise ValueError("Voice mode must be stream or trigger")
        if self.mode == "stream" and not self.audio_format:
            raise ValueError("A streaming voice input needs an audio format")


@dataclass(frozen=True)
class ApplicationSurface:
    """One native API through which a client can ask the device to launch an app."""

    id: str
    label: str


@dataclass(frozen=True)
class ApplicationSpec:
    """Platform-owned names for the application-launch block and its wire surfaces."""

    label: str
    surfaces: tuple[ApplicationSurface, ...]

    def __post_init__(self) -> None:
        ids = [surface.id for surface in self.surfaces]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("Application surfaces must be non-empty and unique")


@dataclass(frozen=True)
class ProtocolListener:
    """How the shared adapter brings one protocol up and drops that protocol's clients.

    Exactly one source is set. The platform supplies the callables, so `common/` starts an
    aiohttp app, a raw TCP server, or a discovery responder without knowing which platform
    or which protocol it is looking at. `disconnect` closes only this protocol's sessions,
    which is what lets one switch move without disturbing the others.
    """

    app: Callable[[], web.Application] | None = None
    ssl_context: Callable[[], ssl.SSLContext] | None = None
    connected: Callable[..., Any] | None = None
    responder: DiscoveryResponder | None = None
    disconnect: Callable[[], Awaitable[None]] | None = None

    def __post_init__(self) -> None:
        if sum(item is not None for item in (self.app, self.connected, self.responder)) != 1:
            raise ValueError("A protocol listener needs exactly one of app, connected, responder")
        # aiohttp and raw asyncio listeners may both terminate ordinary TLS. Protocols that
        # accept arbitrary self-signed client certificates still use their own memory-BIO.


@dataclass(frozen=True)
class KeyEffect:
    """What one remote key does to the simulated device, as data rather than a branch.

    The emulator models three values -- power, volume and mute -- because those are the three
    a client can observe through the protocols it speaks. Anything richer belongs to the
    television that has it, not to shared code.
    """

    field: str                 # "power" | "volume" | "muted"
    operation: str             # "toggle" | "set" | "step"
    amount: int = 0                # a step, or the target of an absolute volume `set`
    value: bool = False

    def __post_init__(self) -> None:
        if self.field not in ("power", "volume", "muted"):
            raise ValueError(f"{self.field} is not a simulated device field")
        if self.operation not in ("toggle", "set", "step"):
            raise ValueError(f"{self.operation} is not a key effect")
        if self.operation == "step" and not self.amount:
            raise ValueError("A step effect moves by a non-zero amount")


POWER_TOGGLE = KeyEffect("power", "toggle")
POWER_ON = KeyEffect("power", "set", value=True)
POWER_OFF = KeyEffect("power", "set", value=False)
VOLUME_UP = KeyEffect("volume", "step", amount=1)
VOLUME_DOWN = KeyEffect("volume", "step", amount=-1)
MUTE_TOGGLE = KeyEffect("muted", "toggle")

# The canonical key names shared code may act on. A platform whose remote spells one of these
# differently maps it in its own wire module, so this table never grows a platform's spelling.
DEFAULT_KEY_EFFECTS = (
    ("Power", POWER_TOGGLE), ("PowerOn", POWER_ON), ("PowerOff", POWER_OFF),
    ("VolumeUp", VOLUME_UP), ("VolumeDown", VOLUME_DOWN), ("VolumeMute", MUTE_TOGGLE),
)


@dataclass(frozen=True)
class VolumeRange:
    """The scale this television's own firmware reports volume on.

    Not every set counts to 100: a scale is a platform fact a client reads and writes, so it
    is declared here rather than assumed by shared code.
    """

    minimum: int = 0
    maximum: int = 100
    start: int = 25

    def __post_init__(self) -> None:
        if not self.minimum <= self.start <= self.maximum:
            raise ValueError("A volume range starts inside itself")

    def clamp(self, value: int) -> int:
        return max(self.minimum, min(self.maximum, value))


@dataclass(frozen=True)
class PlatformDescriptor:
    id: str
    display_name: str
    default_device_profile: str
    protocol_label: str
    default_port: int
    keys: tuple[str, ...]
    transports: tuple[str, ...]
    limitations: str
    service_scheme: str = "http"
    discovery_label: str = "Network discovery"
    access_modes: tuple[AccessMode, ...] = (OPEN_ACCESS,)
    protocols: tuple[ProtocolSpec, ...] = ()
    # None means the platform serves no text input, so shared code keeps refusing it.
    keyboard: KeyboardSpec | None = None
    # None means the platform exposes no voice input, so shared UI hides the status tile.
    voice: VoiceSpec | None = None
    # None means this platform has no app-launch surface, so shared UI hides the tile.
    applications: ApplicationSpec | None = None
    # Whether this firmware matches key names without regard to case. Data, because it is a
    # firmware trait rather than a rule: one platform's hardware answers `home`, `HOME` and
    # `lit_a` exactly as it answers `Home` and `Lit_a`, and another's has never been measured.
    fold_key_case: bool = False
    # Key prefixes a platform's own wire produces for text even though it declares no
    # keyboard. Such a key is refused as out of scope rather than as unknown, and naming the
    # prefix here keeps that refusal from being a constant in shared code.
    text_key_prefixes: tuple[str, ...] = ()
    # The status for releasing a key the client is not holding, character keys included.
    # 200 means the firmware does not tell a stray release apart, or has not been measured.
    unheld_release_status: int = 200
    # What a remote key does to the simulated device. Data, so no shared `if key == …` exists.
    key_effects: tuple[tuple[str, KeyEffect], ...] = DEFAULT_KEY_EFFECTS
    volume: VolumeRange = VolumeRange()
    # Where this platform sits in the dashboard selector. The lowest is the build's default.
    # A sort key rather than a list in shared code, so a build that ships a subset of the
    # platforms keeps a stable order without anything having to enumerate them.
    order: int = 500


class PlatformAdapter(Protocol):
    """Lifecycle boundary implemented by every emulated TV platform."""

    descriptor: PlatformDescriptor

    def __init__(self, core: Core): ...

    def profile_ids(self) -> tuple[str, ...]: ...

    def publish_profile(self) -> None: ...

    async def select_profile(self, profile_id: str) -> None: ...

    def register_protocol(self, protocol_id: str, **listener) -> None: ...

    async def start_protocol(self, protocol_id: str) -> None: ...

    async def stop_protocol(self, protocol_id: str) -> None: ...

    async def reconcile_protocols(self) -> dict[str, str]: ...

    async def warm_up(self, protocol_id: str) -> None: ...

    async def stop_all(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def action(self, name: str, data: dict) -> None: ...
