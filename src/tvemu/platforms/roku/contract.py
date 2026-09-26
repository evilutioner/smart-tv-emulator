"""What a driver must know about the Roku sets that the captures alone do not say.

Captures decide which fields exist and at which wire type. What is written here is the part a
capture cannot prove: which value sets are closed, which fields one model omits, the
ecp-2 framing rules a live Streaming Stick 4K on 15.2.4 enforced when it was probed, and what
the TCL television on 15.3.4 refuses in Limited mode.
Where what clients expect and the hardware disagree, the hardware is recorded.
"""
from __future__ import annotations

from tvemu.platforms.common.claims import (
    BehaviorClaim, ClaimedValue, ConstraintClaim, OperationClaims, PresenceClaim,
    SerializationClaim, ValueSetClaim,
)
from tvemu.platforms.common.evidence import EvidenceRef

_STICK_12 = "roku-streaming-stick-4k-3820eu2"
_STICK_15 = "roku-streaming-stick-4k-15-3-4"
_TCL = "tcl-roku-tv-32s357-15-2-4"
_TCL_15 = "tcl-roku-tv-32s357-15-3-4"
_OFF = "tcl-roku-tv-32s357-disabled"
_ON = "tcl-roku-tv-32s357-enabled"
_PROBE = "roku-ecp2-probe-15-2-4"


def _at(exchange: str, *captures: str) -> tuple[EvidenceRef, ...]:
    return tuple(EvidenceRef("capture", capture, exchange) for capture in captures)


_DESCRIPTION = _at("http.device-description", _STICK_12, _TCL, _STICK_15, _TCL_15, _OFF, _ON)
_DEVICE_INFO = _at("http.device-info", _TCL, _STICK_15, _TCL_15, _ON)
_CLIENT = (EvidenceRef("client-contract", detail="ECP client expectations"),)
_ECP_DOCS = (EvidenceRef("client-contract", detail="Roku ECP documentation"),)
_LIVE = (EvidenceRef("probe", detail="Streaming Stick 4K on 15.2.4, probed live"),)


def _values(evidence, *literals: str) -> tuple[ClaimedValue, ...]:
    return tuple(ClaimedValue(literal, evidence) for literal in literals)


# The device-info elements an ECP client decodes as booleans. Nothing in a document
# says which elements are meant to be boolean, so the list is client knowledge; the closed
# set is what makes the merge gate fail if a capture answers one with anything else.
BOOLEAN_ELEMENTS = (
    "is-tv", "is-stick", "mobile-has-live-tv", "supports-ethernet", "has-wifi-5G-support",
    "secure-device", "time-zone-auto", "supports-suspend", "supports-find-remote",
    "supports-audio-guide", "supports-rva", "has-hands-free-voice-remote",
    "developer-enabled", "device-automation-bridge-enabled", "search-enabled",
    "search-channels-enabled", "voice-search-enabled", "supports-private-listening",
    "supports-private-listening-dtv", "supports-warm-standby", "headphones-connected",
    "supports-audio-settings", "supports-ecs-textedit", "supports-ecs-microphone",
    "supports-wake-on-wlan", "supports-airplay", "has-play-on-roku",
    "has-mobile-screensaver", "supports-trc",
)

# The split between a television and a stick is the model, not the firmware.
TELEVISION_ONLY = ("screen-size", "panel-id", "tuner-type", "trc-version",
                   "trc-channel-version", "supports-private-listening-dtv",
                   "supports-warm-standby")
STICK_ONLY = ("find-remote-is-possible", "is-powered-by-tv", "supports-cec-power-control",
              "supports-cec-audio-volume-control")

# Every request name an ecp-2 client can send. The set echoes the name as `response`
# and answers an unknown one with 404, so the emulator's 404 for the uncaptured ones reads
# the same as the set's.
ECP2_REQUESTS = ("authenticate", "key-press", "key-down", "key-up", "query-device-info")
ECP2_CLIENT_REQUESTS = (
    "query-apps", "query-active-app", "query-icon", "query-textedit-state",
    "set-textedit-text", "query-audio-device", "query-info-for-voice-service",
    "send-voice-events", "request-events", "set-audio-output", "launch",
)

_PROBE_RESPONSES = _at("ws.authenticate", _PROBE) + tuple(
    EvidenceRef("capture", _PROBE, exchange)
    for exchange in ("ws.key-press", "ws.key-down", "ws.key-up", "ws.query-device-info"))

# Request names the TCL set answered over an authenticated session while in Limited mode.
ECP2_QUERIES = ("query-active-app", "query-apps", "query-media-player",
                "query-textedit-state", "query-audio-device", "query-tv-channels")
_TCL_QUERIES = tuple(EvidenceRef("capture", _TCL_15, f"ws.{name}") for name in ECP2_QUERIES)
_TCL_RESPONSES = _TCL_QUERIES + tuple(
    EvidenceRef("capture", _TCL_15, exchange)
    for exchange in ("ws.authenticate", "ws.query-device-info", "ws.key-down", "ws.key-up",
                     "ws.key-up-unheld"))
_UNHELD = _at("ws.key-up-unheld", _TCL_15, _ON)


def _disabled(exchange: str, what: str) -> BehaviorClaim:
    return BehaviorClaim(
        "", f"Refused before {what} is read, with neither words nor a Content-Type. The "
            "device documents, SSDP and an authenticated ecp-2 session keep working.",
        _at(exchange, _OFF),
        condition="ecp-setting-mode is disabled and the command arrives over plain HTTP",
        outcome="401 with an empty body")


def _limited(operation: str, summary: str, *extra: BehaviorClaim) -> OperationClaims:
    return OperationClaims(operation, summary, (*extra,
        BehaviorClaim(
            "", "Refused before the set looks for the document, so the channel it names "
                "does not matter. The authenticated ecp-2 session is not restricted.",
            _at(f"http.{operation.rpartition('.')[2]}", _TCL_15),
            condition="ecp-setting-mode is limited and the query arrives over plain HTTP",
            outcome="403 text/plain \"ECP command not allowed in Limited mode.\""),
    ))


def _key_press() -> OperationClaims:
    # key-down and key-up take the same param-key and obey the same framing.
    evidence = _at("ws.key-press", _PROBE)
    return OperationClaims("ecp-2.key-press", "A key press; key-down and key-up alike.", (
        ValueSetClaim(
            "param-key",
            "A button name, or Lit_ and exactly one raw UTF-8 character. Case is ignored, so "
            "a client that sends LIT_ works. Nothing is percent-decoded on this wire: Lit_%20 is "
            "400 while a literal space is 200, although over HTTP /keypress/%48ome presses "
            "Home. Anything else, or a field spelled key, is 400.",
            evidence, _values(evidence, "Home", "home", "Lit_a", "LIT_a"), closed=False),
        BehaviorClaim(
            "request-id",
            "Any string, echoed as response-id and never validated -- a reused \"1\" "
            "included.", evidence,
            condition="request-id or request is missing or not a string, or the frame is "
                      "not a JSON object",
            outcome="the set drops the session without a reply; the emulator sends close "
                    "code 1002 first"),
    ))


OPERATION_CLAIMS = {
    "roku.http.device-description": OperationClaims(
        "roku.http.device-description", "The UPnP device description.", (
            PresenceClaim("device.UDN", "The UDN is the stable identity of a UPnP device.",
                          _DESCRIPTION, presence="required"),
            BehaviorClaim("", "Served in every access mode, Disabled included.",
                          _at("http.device-description", _OFF),
                          condition="ecp-setting-mode is disabled", outcome="200 as usual"),
        ),
    ),
    "roku.http.device-info": OperationClaims(
        "roku.http.device-info", "The ECP device inventory.", (
            BehaviorClaim(
                "", "The 12.0.0 stick capture has no device-info exchange; 15.x answers it.",
                (EvidenceRef("probe", detail=f"{_STICK_12} records no device-info exchange"),),
                condition="the firmware predates the route",
                outcome="501: the model does not report, which is not a transport failure"),
            _disabled("http.device-info", "the query"),
            SerializationClaim(
                "", "Every element is optional and names are case sensitive "
                    "(has-wifi-5G-support). Every value is XML text: numeric-looking "
                    "elements are strings, and av-sync-calibration-enabled answers \"3.0\".",
                _DEVICE_INFO, feature="xml-text", value=True),
            *(ValueSetClaim(name, "XML boolean text. A strict boolean decoder fails the "
                                  "whole document on an empty one.",
                            _DEVICE_INFO, _values(_DEVICE_INFO, "true", "false"))
              for name in BOOLEAN_ELEMENTS),
            *(PresenceClaim(name, "Television only: absent from the stick.", _DEVICE_INFO)
              for name in TELEVISION_ONLY),
            *(PresenceClaim(name, "Stick only: absent from the television.", _DEVICE_INFO)
              for name in STICK_ONLY),
            ValueSetClaim(
                "ecp-setting-mode",
                "Which clients the set answers; mirrors the platform's four access modes.",
                _DEVICE_INFO,
                (ClaimedValue("limited", _at("http.device-info", _TCL)),
                 ClaimedValue("enabled", _at("http.device-info", _STICK_15, _ON)),
                 ClaimedValue("disabled", _at("ws.query-device-info", _OFF)),
                 *_values(_CLIENT, "permissive"))),
            ValueSetClaim(
                "user-profile-type",
                "Who is signed in on the set; the same TCL answered none and later adult.",
                _DEVICE_INFO,
                (ClaimedValue("none", _at("http.device-info", _TCL, _STICK_15)),
                 ClaimedValue("adult", _at("http.device-info", _TCL_15, _ON))), closed=False),
            ValueSetClaim(
                "power-mode",
                "A sleeping set does not answer, so only PowerOn is captured.",
                _DEVICE_INFO,
                (ClaimedValue("PowerOn", _DEVICE_INFO),
                 *_values(_ECP_DOCS, "DisplayOff", "Headless", "Ready")), closed=False),
        ),
    ),
    "roku.http.device-image": OperationClaims(
        "roku.http.device-image", "A picture of the device.", (
            SerializationClaim(
                "", "The one captured route that is not XML. The 15.2.4 stick answers 404 "
                    "and offers /query/icon/<channel-id> as image/jpeg instead.",
                _at("http.device-image", _TCL, _TCL_15), feature="media_type",
                value="image/png"),
        ),
    ),
    "roku.http.active-app": OperationClaims(
        "roku.http.active-app", "The foreground channel.", (
            PresenceClaim(
                "screensaver",
                "Present only while a screensaver runs, beside app rather than instead of it: "
                "the set answered app Roku both times.",
                _at("http.active-app-screensaver", _TCL_15)),
            _disabled("http.active-app", "the query"),
        ),
    ),
    "roku.http.apps": _limited(
        "roku.http.apps", "The installed channels.",
        _disabled("http.apps", "the query"),
        BehaviorClaim(
            "", "Not a copy of the ecp-2 document: the envelope's gives every appl a subtype "
                "(ndka, rsga, sdka, and it moves -- Netflix answered ndka, then rsga) that "
                "the HTTP list of the same set leaves out.",
            _at("http.apps", _ON),
            condition="the channel list is asked for over plain HTTP",
            outcome="app elements carry id, type and version only")),
    "roku.http.media-player": _limited("roku.http.media-player", "The player state."),
    "roku.http.icon": _limited("roku.http.icon", "A channel's icon."),
    "roku.http.key": OperationClaims("roku.http.key", "One remote key over plain HTTP.", (
        BehaviorClaim(
            "", "The key name is judged before the access mode, so an unknown key is 400 "
                "even where every key would be refused.",
            _at("http.key-unknown", _TCL_15),
            condition="the key is neither a button name nor Lit_ and one character",
            outcome="400 with an empty body"),
        BehaviorClaim(
            "", "Unlike a refused query, a refused key carries no words and no Content-Type.",
            _at("http.key-refused", _TCL_15),
            condition="ecp-setting-mode is limited",
            outcome="403 with an empty body; the same key over ecp-2 is accepted"),
        _disabled("http.key-unknown", "the key name, so even an unknown key is 401 and not 400"),
        BehaviorClaim(
            "", "The same rule as ecp-2: releasing a key nobody pressed is accepted as 202.",
            _at("http.key-up-unheld", _ON),
            condition="keyup names a key this client is not holding",
            outcome="202 with an empty body"),
    )),
    "roku.http.launch": OperationClaims("roku.http.launch", "Launch a channel.", (
        _disabled("http.launch", "the channel id, so an unknown channel is 401 and not 404"),
        BehaviorClaim(
            "", "The set checks the id against its installed channels. The emulator accepts "
                "any id, so a driver's launch can be observed without a catalogue.",
            _at("http.launch-unknown", _ON),
            condition="the channel id is not installed", outcome="404 with an empty body"),
    )),
    "ecp-2.query-device-info": OperationClaims(
        "ecp-2.query-device-info", "The device inventory inside the envelope.", (
            BehaviorClaim(
                "", "Not a copy of the HTTP document: the envelope's adds virtual-device-id "
                    "after udn, which HTTP /query/device-info of the same set leaves out.",
                _at("ws.query-device-info", _TCL_15),
                condition="device-info is asked for over ecp-2",
                outcome="the document carries virtual-device-id"),
        ),
    ),
    "ecp-2.key-up": OperationClaims("ecp-2.key-up", "A held remote key, released.", (
        BehaviorClaim(
            "", "The set tracks what is held, character keys included: releasing a key that "
                "went down answers 200.", _UNHELD,
            condition="the key is not held by this session",
            outcome="status 202, status-msg Accepted"),
    )),
    "ecp-2.param-challenge": OperationClaims(
        "ecp-2.param-challenge", "The unprompted frame as the ecp-2 socket opens.", (
            ValueSetClaim("notify", "A notification, not a reply: no response or status.",
                          _at("ws.authenticate", _PROBE),
                          _values(_at("ws.authenticate", _PROBE), "authenticate")),
            ValueSetClaim("param-methods[]",
                          "The only param that is not a string. Older firmware sent none, "
                          "so a client must not depend on it.",
                          _at("ws.authenticate", _PROBE),
                          _values(_at("ws.authenticate", _PROBE), "client-id", "jwt"),
                          closed=False),
            ConstraintClaim("timestamp",
                            "Device uptime in seconds as a decimal string; it resets on reboot.",
                            _at("ws.authenticate", _PROBE),
                            constraint="pattern", value=r"[0-9]+\.[0-9]{3}"),
        ),
    ),
    "ecp-2.authenticate": OperationClaims(
        "ecp-2.authenticate", "The answer to the challenge.", (
            ValueSetClaim("request-id", "The one request id the set prescribes.",
                          _at("ws.authenticate", _PROBE),
                          _values(_at("ws.authenticate", _PROBE), "1")),
        ),
    ),
    "ecp-2.key-press": _key_press(),
    "ecp-2.response": OperationClaims(
        "ecp-2.response", "The envelope every ecp-2 reply arrives in.", (
            ValueSetClaim("response", "Echoes the request name.", _PROBE_RESPONSES,
                          (*_values(_PROBE_RESPONSES, *ECP2_REQUESTS),
                           *_values(_TCL_QUERIES, *ECP2_QUERIES),
                           *_values(_CLIENT, *(name for name in ECP2_CLIENT_REQUESTS
                                               if name not in ECP2_QUERIES)))),
            ValueSetClaim("status",
                          "A decimal string about the request, not the transport: a refusal "
                          "arrives in a successful frame. 400 is an unusable parameter, 404 "
                          "an unknown request name, 202 the release of a key not held.",
                          _PROBE_RESPONSES + _TCL_RESPONSES,
                          (ClaimedValue("200", _PROBE_RESPONSES + _TCL_RESPONSES),
                           ClaimedValue("202", _UNHELD),
                           *_values(_LIVE, "400", "404"))),
            ValueSetClaim("status-msg", "The status phrase only; the set never explains.",
                          _PROBE_RESPONSES + _TCL_RESPONSES,
                          (ClaimedValue("OK", _PROBE_RESPONSES + _TCL_RESPONSES),
                           ClaimedValue("Accepted", _UNHELD),
                           *_values(_LIVE, "Bad Request", "Not Found"))),
            SerializationClaim(
                "content-type",
                "Present only with content-data. Hardware spells it with a quoted charset "
                "(text/xml; charset=\"utf-8\", application/json for textedit-state) and the "
                "emulator replays what the capture recorded; the 15.2.4 probe kept none.",
                _TCL_QUERIES, feature="charset", value=True),
            SerializationClaim(
                "", "No space after either JSON separator, reproduced for drivers that "
                    "compare or hash frames.", _PROBE_RESPONSES,
                feature="json_separators", value=",:"),
            SerializationClaim(
                "", "Keys in sorted order, so content-data comes first in a frame that has "
                    "one.", _TCL_RESPONSES, feature="json_key_order", value="sorted"),
        ),
    ),
}
