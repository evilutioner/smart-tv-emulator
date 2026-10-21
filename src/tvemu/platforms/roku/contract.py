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
import json
from importlib.resources import files

_STICK_12 = "roku-streaming-stick-4k-12-0-0"
_STICK_15 = "roku-streaming-stick-4k-15-3-4"
_STICK = "roku-streaming-stick-4k-3820eu2-15-3-4"
_TCL = "tcl-roku-tv-32s357-15-2-4"
_TCL_15 = "tcl-roku-tv-32s357-15-3-4"
_OFF = "tcl-roku-tv-32s357-disabled"
_ON = "tcl-roku-tv-32s357-enabled"
_STANDBY = "tcl-roku-tv-32s357-standby"
_PROBE = "roku-ecp2-probe-15-2-4"
_AUTH = "roku-ecp2-probe-3820eu2-15-3-4"


def _at(exchange: str, *captures: str) -> tuple[EvidenceRef, ...]:
    return tuple(EvidenceRef("capture", capture, exchange) for capture in captures)


_DESCRIPTION = _at("http.device-description", _STICK_12, _TCL, _STICK_15, _STICK, _TCL_15,
                   _OFF, _ON)
_DEVICE_INFO = _at("http.device-info", _TCL, _STICK_15, _STICK, _TCL_15, _ON)
_CLIENT = (EvidenceRef("client-contract", detail="Roku mobile app for Android 14.1.2, ECP "
                       "request list; client-contract.json records the parameters"),)
_ECP_DOCS = (EvidenceRef("client-contract", detail="Roku ECP documentation"),)
_LIVE = (EvidenceRef("probe", detail="Streaming Stick 4K on 15.2.4, probed live"),)
_LIVE_15 = (EvidenceRef("probe", detail="Streaming Stick 4K on 15.3.4, probed live 2026-10-17"),)


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
# Request names measured on the Streaming Stick 4K on 15.3.4 by the 2026-10-17 probe.
ECP2_STICK_REQUESTS = ("request-events", "launch", "input")
ECP2_CLIENT_REQUESTS = tuple(name for name, request in json.loads(
    files(__package__).joinpath("client-contract.json").read_text())["requests"].items()
    if request.get("wire", True))

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
_WRONG_ANSWER = _at("ws.authenticate-wrong-then-retry", _AUTH)
_UNAUTHENTICATED = _at("ws.query-before-authenticate", _AUTH)


def _disabled(exchange: str, what: str, consequence: str = "") -> BehaviorClaim:
    return BehaviorClaim(
        "", f"Refused before {what} is read, with neither words nor a Content-Type.{consequence} "
            "The device documents, SSDP and an authenticated ecp-2 session keep working.",
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
            evidence + _LIVE_15,
            (*_values(evidence, "Home", "home", "Lit_a", "LIT_a"),
             *_values(_LIVE_15, "Stop", "Guide", "LiveTV", "Exit", "ClosedCaption", "Red",
                      "Green", "Yellow", "Blue")), closed=False),
        BehaviorClaim(
            "param-key", "Names the official Roku app for Android has that the set does not "
                         "take.", _LIVE_15,
            condition="param-key is a digit, \".\", Keyboard, TextSearch or VoiceSearch",
            outcome="status 400, status-msg Bad Request"),
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
            BehaviorClaim("serial-number", "The Roku mobile app requires this field in a "
                          "successful document. A refused HTTP query has no document to "
                          "decode.", _CLIENT,
                          condition="a client decodes a successful device-info document",
                          outcome="serial-number must be present for the Roku mobile app"),
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
                "Which clients the set answers; mirrors the platform's four access modes. The "
                "emulator writes the selected mode here, over HTTP and inside the envelope.",
                _DEVICE_INFO,
                (ClaimedValue("limited", _at("http.device-info", _TCL)),
                 ClaimedValue("enabled", _at("http.device-info", _STICK_15, _STICK, _ON)),
                 ClaimedValue("disabled", _at("ws.query-device-info", _OFF)),
                 *_values(_CLIENT, "permissive"))),
            ValueSetClaim(
                "user-profile-type",
                "Who is signed in on the set; the same TCL answered none and later adult.",
                _DEVICE_INFO,
                (ClaimedValue("none", _at("http.device-info", _TCL, _STICK_15, _STICK)),
                 ClaimedValue("adult", _at("http.device-info", _TCL_15, _ON))), closed=False),
            ValueSetClaim(
                "power-mode",
                "A television in standby keeps answering: the TCL said Ready after PowerOff, "
                "over both wires, and PowerOn again after PowerOn. The emulator writes it from "
                "the power state where the profile gives both values; the stick's standby is "
                "not measured, so it stays as captured.",
                _DEVICE_INFO + _at("http.device-info-standby", _STANDBY),
                (ClaimedValue("PowerOn", _DEVICE_INFO),
                 ClaimedValue("Ready", _at("http.device-info-standby", _STANDBY)),
                 *_values(_ECP_DOCS, "DisplayOff", "Headless")), closed=False),
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
            BehaviorClaim(
                "", "The type is appl and ui-location is the channel id, where the home screen "
                    "answers type home and ui-location home. The emulator replays the captured "
                    "document whatever was launched.",
                _at("http.active-app-launched", _STANDBY),
                condition="a launched channel is running",
                outcome="app names that channel, with its id, type, version and name"),
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
    **{operation: OperationClaims(operation, summary, (
        BehaviorClaim(
            "", "A stick has no tuner, and the route is not there at all: the same answer over "
                "ecp-2 is a 404 frame.",
            _at(f"http.{operation.rpartition('.')[2]}", _STICK),
            condition="the set is not a television (is-tv false)",
            outcome="404 with an empty body"),
    )) for operation, summary in (("roku.http.tv-channels", "The tuner's channel list."),
                                  ("roku.http.tv-active-channel", "The tuned channel."))},
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
        _disabled("http.key-unknown", "the key name", " An unknown key is 401 too, not 400."),
        BehaviorClaim(
            "", "The same rule as ecp-2: releasing a key nobody pressed is accepted as 202.",
            _at("http.key-up-unheld", _ON),
            condition="keyup names a key this client is not holding",
            outcome="202 with an empty body"),
    )),
    "roku.http.launch": OperationClaims("roku.http.launch", "Launch a channel.", (
        _disabled("http.launch", "the channel id", " An unknown channel is 401 too, not 404."),
        BehaviorClaim(
            "", "The set checks the id against its installed channels. The emulator accepts "
                "any id, so a driver's launch can be observed without a catalogue.",
            _at("http.launch-unknown", _ON),
            condition="the channel id is not installed", outcome="404 with an empty body"),
        BehaviorClaim(
            "", "The channel comes to the foreground; see active-app.",
            _at("http.launch", _STANDBY),
            condition="the channel id is installed", outcome="200 with an empty body"),
    )),
    "roku.http.search": OperationClaims("roku.http.search", "Open the search screen.", (
        BehaviorClaim(
            "", "The search screen belongs to the home channel, so active-app still answers "
                "the home screen afterwards.",
            _at("http.search-browse", _STANDBY),
            condition="a keyword search is asked for", outcome="200 with an empty body"),
    )),
    "roku.http.input": OperationClaims("roku.http.input", "Parameters for the foreground channel.", (
        BehaviorClaim(
            "", "Accepted on the home screen too, where nothing consumes it.",
            _at("http.input", _STANDBY),
            condition="any parameters are posted", outcome="200 with an empty body"),
    )),
    "roku.http.input-channel": OperationClaims(
        "roku.http.input-channel", "Parameters for one channel by id.", (
            BehaviorClaim(
                "", "Play on Roku (15985) is a channel like any other: this TCL does not have "
                    "it installed. The emulator accepts any id, as it does for launch.",
                _at("http.input-uninstalled", _STANDBY),
                condition="the channel id is not installed", outcome="404 with an empty body"),
        ),
    ),
    "roku.http.other": OperationClaims("roku.http.other", "Any other route.", (
        BehaviorClaim(
            "", "A query name the set does not know is no different from any other unknown "
                "path. The emulator answers 501 for every route it holds no capture of, "
                "which keeps a gap in the emulator distinguishable from the set's answer.",
            _at("http.route-unknown", _STANDBY) + _at("http.query-unknown", _STANDBY),
            condition="the set has no such route", outcome="404 with an empty body"),
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
            "", "The set tracks what is held, character keys included: releasing a key this "
                "session did not press answers 202, where releasing a held one answers 200.",
            _UNHELD,
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
            ValueSetClaim(
                "request-id",
                "Any string, echoed as response-id like every other request's: the set "
                "prescribes no value. The official Roku app for Android numbers its requests "
                "from 0, so its authenticate carries \"0\"; other clients start at 1.",
                _at("ws.authenticate", _PROBE) + _at("ws.authenticate-request-id-0", _AUTH),
                (ClaimedValue("1", _at("ws.authenticate", _PROBE)),
                 ClaimedValue("0", _at("ws.authenticate-request-id-0", _AUTH)),
                 ClaimedValue("abc", _at("ws.authenticate-request-id-text", _AUTH))),
                closed=False),
            BehaviorClaim(
                "request-id", "The same framing rule as after authenticating.", _LIVE_15,
                condition="request-id is a number or is missing",
                outcome="the set drops the connection without a reply; the emulator sends "
                        "close code 1002 first"),
            BehaviorClaim(
                "param-response", "A wrong answer does not end the session: the client may "
                                  "answer the same challenge again, and a right answer then "
                                  "authenticates it.", _WRONG_ANSWER,
                condition="the answer is not the one the challenge asks for",
                outcome="status 601, status-msg Invalid Credentials; the socket stays open"),
            BehaviorClaim(
                "", "The deadline runs from the open, whatever the client sent meanwhile; an "
                    "authenticated session idle for 80 s stayed open.", _LIVE_15,
                condition="the session has not authenticated 10.5 s after it opened",
                outcome="the set drops the connection with no close frame"),
            BehaviorClaim(
                "", "Once authenticated, authenticate is no longer a request the session has.",
                _at("ws.authenticate-twice", _AUTH),
                condition="authenticate arrives on a session that has already authenticated",
                outcome="status 404, status-msg Not Found"),
        ),
    ),
    "ecp-2.request-events": OperationClaims(
        "ecp-2.request-events", "Subscribe to notifications.", (
            ValueSetClaim(
                "param-events",
                "Comma-separated entries, each + or - and an event name; empty entries are "
                "skipped. Names are case sensitive and nothing is trimmed. A stick takes the "
                "television's tuner and input events too. The list the official Roku app for "
                "Android sends is the one captured.",
                _at("ws.request-events", _AUTH),
                (ClaimedValue(
                    "+language-changed,+language-changing,+media-player-state-changed,"
                    "+plugin-ui-run,+plugin-ui-run-script,+plugin-ui-exit,+screensaver-run,"
                    "+screensaver-exit,+plugins-changed,+sync-completed,+power-mode-changed,"
                    "+volume-changed,+textedit-opened,+textedit-closed,+textedit-changed,"
                    "+device-name-changed,+device-location-changed,+audio-setting-changed,"
                    "+audio-settings-invalidated,+user-profile-changed,"
                    "+tv-power-volume-control-changed", _at("ws.request-events", _AUTH)),
                 ClaimedValue("+volume-changed,+no-such-event",
                              _at("ws.request-events-partial", _AUTH)),
                 ClaimedValue("+VOLUME-CHANGED", _at("ws.request-events-unknown", _AUTH))),
                closed=False),
            BehaviorClaim(
                "param-events", "Part of the list is taken.",
                _at("ws.request-events-partial", _AUTH),
                condition="some entries name a known event and some do not",
                outcome="status 202, status-msg Accepted"),
            BehaviorClaim(
                "param-events", "Nothing is taken.", _at("ws.request-events-unknown", _AUTH),
                condition="no entry names a known event with its sign, or the list is empty",
                outcome="status 404, status-msg Not Found"),
            BehaviorClaim(
                "", "The parameter is required.", _at("ws.request-events-missing", _AUTH),
                condition="param-events is missing",
                outcome="status 400, status-msg Bad Request"),
        ),
    ),
    "ecp-2.launch": OperationClaims(
        "ecp-2.launch", "Launch a channel.", (
            ValueSetClaim(
                "param-params",
                "One string holding a JSON object; the official Roku app for Android always "
                "sends its gc_run_source keys. Missing, empty and {} are all no params.",
                _at("ws.launch", _AUTH),
                (ClaimedValue("{}", _at("ws.launch-foreground-empty-params", _AUTH)),
                 ClaimedValue("not json", _at("ws.launch-params-not-json", _AUTH))),
                closed=False),
            BehaviorClaim(
                "", "The set leaves a running channel alone; the official Roku app for Android "
                    "reads 204 as already launched.", _at("ws.launch-foreground", _AUTH)
                + _at("ws.launch-foreground-empty-params", _AUTH),
                condition="the channel is in the foreground and there are no params",
                outcome="status 204, status-msg No Content"),
            BehaviorClaim(
                "", "With params, a running channel is restarted.", _at("ws.launch", _AUTH),
                condition="the channel is in the foreground and params are given",
                outcome="status 200; the channel exits and runs again"),
            BehaviorClaim(
                "param-channel-id", "The emulator does not follow: like the HTTP launch, it "
                                    "accepts any id.", _at("ws.launch-not-installed", _AUTH),
                condition="the channel is not installed",
                outcome="status 404 on the set; 200 from the emulator"),
            BehaviorClaim(
                "", "Both parameters are checked before anything runs.",
                _at("ws.launch-no-channel", _AUTH) + _at("ws.launch-params-not-json", _AUTH),
                condition="param-channel-id is missing or param-params is not JSON",
                outcome="status 400, status-msg Bad Request"),
        ),
    ),
    "ecp-2.input": OperationClaims(
        "ecp-2.input", "Hand params to a channel.", (
            BehaviorClaim(
                "", "A channel that is not running is launched to take them.",
                _at("ws.input", _AUTH),
                condition="the channel is installed but not in the foreground",
                outcome="status 200; the channel runs"),
            BehaviorClaim(
                "param-channel-id", "The emulator does not follow, as for launch.",
                _at("ws.input-not-installed", _AUTH),
                condition="the channel is not installed",
                outcome="status 404 on the set; 200 from the emulator"),
        ),
    ),
    "ecp-2.key-press": _key_press(),
    "ecp-2.response": OperationClaims(
        "ecp-2.response", "The envelope every ecp-2 reply arrives in.", (
            ValueSetClaim("response", "Echoes the request name.", _PROBE_RESPONSES,
                          (*_values(_PROBE_RESPONSES, *ECP2_REQUESTS),
                           *(ClaimedValue(name, _at(f"ws.{name}", _AUTH))
                             for name in ECP2_STICK_REQUESTS),
                           *_values(_TCL_QUERIES, *ECP2_QUERIES),
                           *_values(_CLIENT, *(name for name in ECP2_CLIENT_REQUESTS
                                               if name not in ECP2_QUERIES)))),
            ValueSetClaim("status",
                          "A decimal string about the request, not the transport: a refusal "
                          "arrives in a successful frame. 400 is an unusable parameter, 404 "
                          "an unknown request name, 202 the release of a key not held, 401 a request "
                          "before authenticating and 601 a wrong challenge answer.",
                          _PROBE_RESPONSES + _TCL_RESPONSES,
                          (ClaimedValue("200", _PROBE_RESPONSES + _TCL_RESPONSES),
                           ClaimedValue("202", _UNHELD),
                           ClaimedValue("204", _at("ws.launch-foreground", _AUTH)),
                           ClaimedValue("401", _UNAUTHENTICATED),
                           ClaimedValue("601", _WRONG_ANSWER),
                           *_values(_LIVE, "400", "404"))),
            BehaviorClaim(
                "status", "Nothing but authenticate is served before it succeeds.",
                _UNAUTHENTICATED,
                condition="any other request arrives before a successful authenticate",
                outcome="status 401, status-msg Unauthorized; the socket stays open"),
            ValueSetClaim("status-msg", "The status phrase only; the set never explains.",
                          _PROBE_RESPONSES + _TCL_RESPONSES,
                          (ClaimedValue("OK", _PROBE_RESPONSES + _TCL_RESPONSES),
                           ClaimedValue("Accepted", _UNHELD),
                           ClaimedValue("No Content", _at("ws.launch-foreground", _AUTH)),
                           ClaimedValue("Unauthorized", _UNAUTHENTICATED),
                           ClaimedValue("Invalid Credentials", _WRONG_ANSWER),
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

_AUDIO_STATE = _at('audio-states', 'roku-audio-state-3820eu2-2026-10-18')
_TEXT_WRITE = _at('text-writes', 'roku-text-write-3820eu2-2026-10-18')
_TEXT_LIMITS = _at('text-limits', 'roku-text-limits-3820eu2-2026-10-18')
_TEXT_FOCUS = _at('text-focus', 'roku-text-focus-3820eu2-2026-10-18')
for _operation, _prefix, _evidence in (
    ('roku.http.audio-device', '', _at('http.rtp-running', 'roku-audio-state-3820eu2-2026-10-18')),
    ('ecp-2.query-audio-device', 'content-data::', _AUDIO_STATE),
):
    OPERATION_CLAIMS[_operation] = OperationClaims(_operation, 'Current audio destinations.', (
        *(PresenceClaim(_prefix + path,
                        'Profile-declared live destination state. A single active transport follows the measured transitions; with multiple independent senders the last-started view is emulator-owned.',
                        _evidence, scope='served') for path in
          ('global.destination-list', 'destinations.destination.@name', 'rtp-info.rtp-address')),
        BehaviorClaim('', 'Ordered Stick audio-state capture, separately measured over HTTP and ecp-2.',
                      _evidence, condition='private listening starts or stops',
                      outcome='hdmi changes to mobile-sas or datagram and returns to hdmi; RTP address names the datagram destination only'),
    ))
OPERATION_CLAIMS['ecp-2.query-textedit-state'] = OperationClaims(
    'ecp-2.query-textedit-state', 'The native field backed by the shared text buffer.', (
        *(PresenceClaim('content-data::textedit-state.' + name,
                        'Live only on a profile with measured native full fields while the dashboard field is focused; textedit-id is none otherwise.',
                        _TEXT_WRITE, scope='served') for name in
          ('textedit-id', 'textedit-type', 'text', 'masked', 'max-length', 'selection-start', 'selection-end')),
    ))
OPERATION_CLAIMS['ecp-2.set-textedit-text'] = OperationClaims(
    'ecp-2.set-textedit-text', 'Replace the focused native full field.', (
        BehaviorClaim('', 'Measured unmasked full field only. Android String.length uses UTF-16, but this field counts Unicode codepoints.',
                      _TEXT_LIMITS, condition='selection-end is supplied',
                      outcome='cursor collapses to that position clamped to 0..text length; selection-start is ignored; missing end uses text length, invalid numeric text uses zero'),
        BehaviorClaim('', 'The advertised full-field maximum was 75 characters.', _TEXT_WRITE + _TEXT_LIMITS,
                      condition='id is unknown or replacement exceeds the character limit',
                      outcome='200 with unchanged field and no textedit-changed notification'),
    ))
for _event in ('textedit-opened', 'textedit-changed', 'textedit-closed'):
    _source = _TEXT_WRITE if _event == 'textedit-changed' else _TEXT_FOCUS
    OPERATION_CLAIMS['ecp-2.' + _event] = OperationClaims('ecp-2.' + _event, 'Subscribed native textedit transition.', (
        PresenceClaim('param-textedit-id', 'Live field identity increments on opening; closing names the former id.', _source, scope='served'),
        BehaviorClaim('', 'Subscribed connections have independent notification queues.', _source,
                      condition='a measured native field changes focus or text', outcome='send the corresponding captured textedit event to subscribed clients'),
    ))
