# Roku

Emulates the network contract a Roku remote application speaks: SSDP discovery, the captured
device documents, HTTP ECP commands, and the authenticated `ecp-2` WebSocket. Two physical
devices are modelled — a TCL Roku TV 32S357 on 15.3.4, captured in each of its network-access
modes, and a Roku Streaming Stick 4K on Roku OS 12.0.0 — and they differ in ways a driver has
to handle. The TCL is the default: every open-source Roku client reads `/query/device-info`
first, and the 12.0.0 stick capture has none.

For project-wide setup, architecture and the management API, see the
[main README](../../README.md).

## Running it

```sh
python -m tvemu --platform roku
python -m tvemu --device-profile tcl-roku-tv-32s357
python -m tvemu --bind 192.168.1.10 --port 8060
```

ECP listens on TCP **8060** and SSDP answers on UDP **1900 / 239.255.255.250**. The phone and
the computer must share a LAN that allows client-to-client traffic; loopback works only for
checks on the same machine. Use `--bind` when a VPN or several adapters make the choice of
address ambiguous.

## The surface

Generated from the route declarations beside the handlers — `tvemu --api-map roku` prints the
same thing, and `--format openapi` writes the HTTP half for Swagger UI or Postman, with a
response schema wherever a capture showed one.

<!-- generated:surface -->
| Method | Path | Answers with | Auth |
| --- | --- | --- | --- |
| `GET` | `/ecp-session` | computed | — |
| `POST` | `/{action:keypress\|keydown\|keyup}/{key}` | computed | — |
| `POST` | `/launch/{app_id}` | computed | — |
| `GET` | `/` | captured `/`, else **501** | — |
| `GET` | `/query/device-info` | captured `/query/device-info`, else **501** | — |
| `GET` | `/device-image.png` | captured `/device-image.png`, else **501** | — |
| `GET` | `/ecp_SCPD.xml` | captured `/ecp_SCPD.xml`, else **501** | — |
| `GET` | `/dial_SCPD.xml` | captured `/dial_SCPD.xml`, else **501** | — |
| `GET` | `/query/apps` | captured `/query/apps`, else **501** | — |
| `GET` | `/query/active-app` | captured `/query/active-app`, else **501** | — |
| `GET` | `/query/media-player` | captured `/query/media-player`, else **501** | — |
| `GET` | `/query/tv-channels` | captured `/query/tv-channels`, else **501** | — |
| `GET` | `/query/tv-active-channel` | captured `/query/tv-active-channel`, else **501** | — |
| `GET` | `/query/audio-device` | captured `/query/audio-device`, else **501** | — |
| `GET` | `/query/icon/{channel_id}` | captured `/query/icon/{channel_id}`, else **501** | — |
| `GET` | `/{tail:.*}` | any other captured route, else **501** | — |
| `*` | `/{tail:.*}` | computed | — |

`ecp-2` messages:

- `param-challenge` (from the set) — The authentication challenge, sent unprompted as the socket opens.
- `authenticate` (to the set) — The only request that may carry request-id 1.
- `response` (from the set) — The envelope every reply arrives in.
- `key-press` (to the set) — A remote key, pressed and released.
- `key-down` (to the set) — A remote key, held.
- `key-up` (to the set) — A held remote key, released.
- `query-device-info` (to the set) — The device inventory, answered as base64 inside the envelope.
- `query-active-app` (to the set) — The foreground channel, answered inside the envelope.
- `query-apps` (to the set) — The installed channels, answered inside the envelope.
- `query-media-player` (to the set) — The player state, answered inside the envelope.
- `query-textedit-state` (to the set) — The focused text field, answered as JSON inside the envelope.
- `query-audio-device` (to the set) — Audio destinations and volume, answered inside the envelope.
- `query-tv-channels` (to the set) — The tuner's channel list, answered inside the envelope.
<!-- /generated -->

## What a driver must know

Generated from `src/tvemu/platforms/roku/contract.py` and checked against every capture —
`tvemu --contract roku` prints the same thing.

<!-- generated:contract -->
Checked against 7 captures: `roku-ecp2-probe-15-2-4`, `roku-streaming-stick-4k-15-3-4`, `roku-streaming-stick-4k-3820eu2`, `tcl-roku-tv-32s357-15-2-4`, `tcl-roku-tv-32s357-15-3-4`, `tcl-roku-tv-32s357-disabled`, `tcl-roku-tv-32s357-enabled`.

### The UPnP device description.

- **`device.UDN`** (presence: required) — The UDN is the stable identity of a UPnP device.
- **The whole document** (behavior: ecp-setting-mode is disabled -> 200 as usual) — Served in every access mode, Disabled included.

### The ECP device inventory.

- **The whole document** (behavior: the firmware predates the route -> 501: the model does not report, which is not a transport failure) — The 12.0.0 stick capture has no device-info exchange; 15.x answers it.
- **The whole document** (behavior: ecp-setting-mode is disabled and the command arrives over plain HTTP -> 401 with an empty body) — Refused before the query is read, with neither words nor a Content-Type. The device documents, SSDP and an authenticated ecp-2 session keep working.
- **The whole document** (serialization: xml-text=True) — Every element is optional and names are case sensitive (has-wifi-5G-support). Every value is XML text: numeric-looking elements are strings, and av-sync-calibration-enabled answers "3.0".
- **`is-tv`, `is-stick`, `mobile-has-live-tv`, `supports-ethernet`, `has-wifi-5G-support`, `secure-device`, `time-zone-auto`, `supports-suspend`, `supports-find-remote`, `supports-audio-guide`, `supports-rva`, `has-hands-free-voice-remote`, `developer-enabled`, `device-automation-bridge-enabled`, `search-enabled`, `search-channels-enabled`, `voice-search-enabled`, `supports-private-listening`, `supports-private-listening-dtv`, `supports-warm-standby`, `headphones-connected`, `supports-audio-settings`, `supports-ecs-textedit`, `supports-ecs-microphone`, `supports-wake-on-wlan`, `supports-airplay`, `has-play-on-roku`, `has-mobile-screensaver`, `supports-trc`** (values: closed) — XML boolean text. A strict boolean decoder fails the whole document on an empty one.
  Values: `true`, `false`.
- **`screen-size`, `panel-id`, `tuner-type`, `trc-version`, `trc-channel-version`, `supports-private-listening-dtv`, `supports-warm-standby`** (presence: optional) — Television only: absent from the stick.
- **`find-remote-is-possible`, `is-powered-by-tv`, `supports-cec-power-control`, `supports-cec-audio-volume-control`** (presence: optional) — Stick only: absent from the television.
- **`ecp-setting-mode`** (values: closed) — Which clients the set answers; mirrors the platform's four access modes.
  Values: `limited`, `enabled`, `disabled`, `permissive` (client-contract).
- **`user-profile-type`** (values: open) — Who is signed in on the set; the same TCL answered none and later adult.
  Values: `none`, `adult`, and possibly others.
- **`power-mode`** (values: open) — A sleeping set does not answer, so only PowerOn is captured.
  Values: `PowerOn`, `DisplayOff` (client-contract), `Headless` (client-contract), `Ready` (client-contract), and possibly others.

### A picture of the device.

- **The whole document** (serialization: media_type='image/png') — The one captured route that is not XML. The 15.2.4 stick answers 404 and offers /query/icon/<channel-id> as image/jpeg instead.

### The foreground channel.

- **`screensaver`** (presence: optional) — Present only while a screensaver runs, beside app rather than instead of it: the set answered app Roku both times.
- **The whole document** (behavior: ecp-setting-mode is disabled and the command arrives over plain HTTP -> 401 with an empty body) — Refused before the query is read, with neither words nor a Content-Type. The device documents, SSDP and an authenticated ecp-2 session keep working.

### The installed channels.

- **The whole document** (behavior: ecp-setting-mode is disabled and the command arrives over plain HTTP -> 401 with an empty body) — Refused before the query is read, with neither words nor a Content-Type. The device documents, SSDP and an authenticated ecp-2 session keep working.
- **The whole document** (behavior: the channel list is asked for over plain HTTP -> app elements carry id, type and version only) — Not a copy of the ecp-2 document: the envelope's gives every appl a subtype (ndka, rsga, sdka, and it moves -- Netflix answered ndka, then rsga) that the HTTP list of the same set leaves out.
- **The whole document** (behavior: ecp-setting-mode is limited and the query arrives over plain HTTP -> 403 text/plain "ECP command not allowed in Limited mode.") — Refused before the set looks for the document, so the channel it names does not matter. The authenticated ecp-2 session is not restricted.

### The player state.

- **The whole document** (behavior: ecp-setting-mode is limited and the query arrives over plain HTTP -> 403 text/plain "ECP command not allowed in Limited mode.") — Refused before the set looks for the document, so the channel it names does not matter. The authenticated ecp-2 session is not restricted.

### A channel's icon.

- **The whole document** (behavior: ecp-setting-mode is limited and the query arrives over plain HTTP -> 403 text/plain "ECP command not allowed in Limited mode.") — Refused before the set looks for the document, so the channel it names does not matter. The authenticated ecp-2 session is not restricted.

### One remote key over plain HTTP.

- **The whole document** (behavior: the key is neither a button name nor Lit_ and one character -> 400 with an empty body) — The key name is judged before the access mode, so an unknown key is 400 even where every key would be refused.
- **The whole document** (behavior: ecp-setting-mode is limited -> 403 with an empty body; the same key over ecp-2 is accepted) — Unlike a refused query, a refused key carries no words and no Content-Type.
- **The whole document** (behavior: ecp-setting-mode is disabled and the command arrives over plain HTTP -> 401 with an empty body) — Refused before the key name, so even an unknown key is 401 and not 400 is read, with neither words nor a Content-Type. The device documents, SSDP and an authenticated ecp-2 session keep working.
- **The whole document** (behavior: keyup names a key this client is not holding -> 202 with an empty body) — The same rule as ecp-2: releasing a key nobody pressed is accepted as 202.

### Launch a channel.

- **The whole document** (behavior: ecp-setting-mode is disabled and the command arrives over plain HTTP -> 401 with an empty body) — Refused before the channel id, so an unknown channel is 401 and not 404 is read, with neither words nor a Content-Type. The device documents, SSDP and an authenticated ecp-2 session keep working.
- **The whole document** (behavior: the channel id is not installed -> 404 with an empty body) — The set checks the id against its installed channels. The emulator accepts any id, so a driver's launch can be observed without a catalogue.

### The device inventory inside the envelope.

- **The whole document** (behavior: device-info is asked for over ecp-2 -> the document carries virtual-device-id) — Not a copy of the HTTP document: the envelope's adds virtual-device-id after udn, which HTTP /query/device-info of the same set leaves out.

### A held remote key, released.

- **The whole document** (behavior: the key is not held by this session -> status 202, status-msg Accepted) — The set tracks what is held, character keys included: releasing a key that went down answers 200.

### The unprompted frame as the ecp-2 socket opens.

- **`notify`** (values: closed) — A notification, not a reply: no response or status.
  Values: `authenticate`.
- **`param-methods[]`** (values: open) — The only param that is not a string. Older firmware sent none, so a client must not depend on it.
  Values: `client-id`, `jwt`, and possibly others.
- **`timestamp`** (constraint: pattern='[0-9]+\\.[0-9]{3}') — Device uptime in seconds as a decimal string; it resets on reboot.

### The answer to the challenge.

- **`request-id`** (values: closed) — The one request id the set prescribes.
  Values: `1`.

### A key press; key-down and key-up alike.

- **`param-key`** (values: open) — A button name, or Lit_ and exactly one raw UTF-8 character. Case is ignored, so a client that sends LIT_ works. Nothing is percent-decoded on this wire: Lit_%20 is 400 while a literal space is 200, although over HTTP /keypress/%48ome presses Home. Anything else, or a field spelled key, is 400.
  Values: `Home`, `home`, `Lit_a`, `LIT_a`, and possibly others.
- **`request-id`** (behavior: request-id or request is missing or not a string, or the frame is not a JSON object -> the set drops the session without a reply; the emulator sends close code 1002 first) — Any string, echoed as response-id and never validated -- a reused "1" included.

### The envelope every ecp-2 reply arrives in.

- **`response`** (values: closed) — Echoes the request name.
  Values: `authenticate`, `key-press`, `key-down`, `key-up`, `query-device-info`, `query-active-app`, `query-apps`, `query-media-player`, `query-textedit-state`, `query-audio-device`, `query-tv-channels`, `query-icon` (client-contract), `set-textedit-text` (client-contract), `query-info-for-voice-service` (client-contract), `send-voice-events` (client-contract), `request-events` (client-contract), `set-audio-output` (client-contract), `launch` (client-contract).
- **`status`** (values: closed) — A decimal string about the request, not the transport: a refusal arrives in a successful frame. 400 is an unusable parameter, 404 an unknown request name, 202 the release of a key not held.
  Values: `200`, `202`, `400` (probe), `404` (probe).
- **`status-msg`** (values: closed) — The status phrase only; the set never explains.
  Values: `OK`, `Accepted`, `Bad Request` (probe), `Not Found` (probe).
- **`content-type`** (serialization: charset=True) — Present only with content-data. Hardware spells it with a quoted charset (text/xml; charset="utf-8", application/json for textedit-state) and the emulator replays what the capture recorded; the 15.2.4 probe kept none.
- **The whole document** (serialization: json_separators=',:') — No space after either JSON separator, reproduced for drivers that compare or hash frames.
- **The whole document** (serialization: json_key_order='sorted') — Keys in sorted order, so content-data comes first in a frame that has one.
<!-- /generated -->

## What the claims above do not say

- **Text arrives one `Lit_<char>` keypress at a time.** The captured firmware has no text API
  and no keyboard-status route. `Lit_%2F` cannot be routed over HTTP, because the ECP path
  pattern excludes `/`; over `ecp-2` the same character is sent raw and works.
- **`Backspace` and `Enter` are ordinary remote keys.** They edit the field only while it has
  focus; with nothing focused a keypress is accepted and goes nowhere.
- **A missing captured document is 501, never a fabricated body.** Which routes answer
  depends on the selected television.

## Control by mobile apps

A physical Roku exposes this at **Settings › System › Advanced system settings › Control by
mobile apps › Network access**. All four values are reproduced on the wire, and they are
platform data: the dashboard cannot change what each one answers.

| Mode | Keys over HTTP | Queries over HTTP | Authenticated `ecp-2` | Off-network clients | SSDP |
|---|---|---|---|---|---|
| `enabled` (default) | Accepted | Served | Keys and queries | **403** | Answers |
| `permissive` | Accepted | Served | Keys and queries | Accepted | Answers |
| `limited` | **403**, no body | device-info and active-app only; the rest **403** | Keys and queries | **403** | Answers |
| `disabled` | **401**, no body | **401**, no body; the device documents still 200 | Keys and queries | **403** | Answers |

`limited` is what the Roku mobile app relies on: the set stays discoverable, and a session that
has completed the challenge keeps full control. Plain HTTP keeps the device documents,
`/query/device-info` and `/query/active-app`; channels, playback, icons, audio and the tuner
answer 403 with the text `ECP command not allowed in Limited mode.`, whether or not the
selected capture recorded the document. A key name is judged before the mode, so an unknown
key is still 400.

`disabled` is narrower than its name: it switches off plain HTTP control, not the set. Every
ECP command — any `/query/…` the set knows, keys, launch, search, input — is 401 with no body
before it is read, so a malformed key or an unknown channel is 401 too, while a route outside
ECP stays 404. The device description, SCPDs and icon still answer, SSDP still answers, and an
authenticated `ecp-2` session keeps full control. Measured on the TCL set on 15.3.4.

The emulator advertises one IPv4 address and cannot know the interface's real prefix length, so
"the TV's own network" is modelled as the `/24` containing that address. Loopback is always
local, which keeps single-machine checks usable. A request refused before it reaches a key is
recorded as an `access` event naming the mode responsible.

## Evidence and device profiles

Each directory under `src/tvemu/platforms/roku/evidence/` is one immutable capture:
`capture.json` holds provenance, identity and the ordered exchanges, and every body or frame
sits beside it byte for byte. A profile under `profiles/` only names a complete capture and
the exchanges it replays: a path for an HTTP document, an `ecp-2` request name for the document
the set carried inside its envelope. The two are kept apart because they differ — the
envelope's device-info adds `virtual-device-id` and its channel list gives every channel a
`subtype`. The 15.3.4 stick capture and the ecp-2 probe are evidence only: they feed the
claims above but have no discovery evidence, so they are never selectable.

The TCL was captured three times on 15.3.4, once per network-access value it was switched
through. Its profile replays `tcl-roku-tv-32s357-enabled`, the one mode in which every document
answers on both wires; `tcl-roku-tv-32s357-15-3-4` (Limited) and `tcl-roku-tv-32s357-disabled`
are the evidence for what the other modes refuse, which the emulator reproduces from mode data
rather than from a replay. Its 15.2.4 capture is evidence too.

To add a Roku, add one evidence directory and, if it is complete, a profile reference, then
run `tvemu --contract roku --check`. The dashboard's **Captured device** selector switches
profile live and closes existing sessions; `--device-profile <id>` overrides it for one launch.

## Settings profile

```json
{
  "schema_version": 2,
  "platform": "roku",
  "settings": {
    "device_profile": "tcl-roku-tv-32s357",
    "access_mode": "enabled",
    "protocols": {"ecp": true, "ssdp": true}
  }
}
```

An empty `access_mode` resolves to the platform's first; a mode of another platform is
rejected. Address and port are launch options and are not stored.

## Not emulated

Channel launch accepts any id for client validation without running anything, where the set
answers 404 for a channel that is not installed. The channel list, foreground channel, player
state, tuner and audio documents are the captured ones, not live state: a launch does not
change what `query-active-app` answers, and a volume key does not change `audio-device`.
`device-info` keeps the `ecp-setting-mode` it was captured with whichever access mode is
selected. There is no Cast and no rendered
screen. Other app and media endpoints answer **501**, and an unknown remote key is **400**. A
malformed escape such as `/keypress/Lit_%ZZ` is **404** on the set, whose URL parser rejects it
before routing; the emulator keeps the bytes and answers 200 or 400.

Where the TCL set on 15.3.4 answers differently and the emulator does not follow yet:

- A route the set does not have is **404** with no body there and **501** here.
- Every HTTP reply carries `Cache-Control: no-cache` and XML is `text/xml; charset="utf-8"`;
  the emulator sends neither. The `ecp-2` envelope does replay the captured type exactly.
- The icon and the developer diagnostics (`chanperf`, `registry`, `sgnodes`, `r2d2-bitmaps`,
  the beacons) answer on the set and are not captured here; the diagnostics answer 202 while
  no channel runs.

## Manual acceptance

- [ ] The phone finds the set over Wi-Fi with no change to the remote application.
- [ ] The remote connects and sends keys; responses and activity appear in the dashboard.
- [ ] The application recovers from disconnects and service toggles.
- [ ] Each network-access value matches the physical TV: permissive reachable across subnets,
      limited and disabled usable only by an authenticated session, disabled refusing even
      device-info over plain HTTP.
- [ ] Switching to the other captured device changes which routes answer, as the contract says.

## Open-source clients

Upstream Roku libraries run against this emulator, with the known gaps each one meets:
[Open-source clients: Roku](../clients/roku.md).

## Writing a Roku driver

The contract is committed beside this guide, so a driver (or a model writing one) can start
from it without running anything:

- [`docs/spec/roku.openapi.json`](../spec/roku.openapi.json) — ECP over HTTP;
- [`docs/spec/roku.asyncapi.json`](../spec/roku.asyncapi.json) — the `ecp-2` WebSocket;
- `tvemu --contract roku` — what the captures cannot say, including the closed value sets
  above.

[`tools/ecp_client.py`](../../tools/ecp_client.py) is the smallest complete `ecp-2` client:
open the socket, answer the challenge, press a key. Run it against the emulator, then check
what arrived with the example scenario:

```sh
tvemu --bind 127.0.0.1 --no-browser &
python tools/ecp_client.py 127.0.0.1:8060 Home      # Ctrl+C after the key
python -m tvemu.expect docs/spec/roku.scenario.json
```

[`docs/spec/roku.scenario.json`](../spec/roku.scenario.json) expects `ws.authenticate` with
200 and then `keypress/Home` over `ws`, and forbids any refused command. Copy it per step as
the driver grows: plain-HTTP keys arrive as `keypress/<Key>` over `http`, launches as
`app.launch/ecp`, and a query the selected device was never captured answering is logged as
`unsupported` with 501 — switch the captured device or the access mode and the same scenario
tells you what the driver must handle differently.

The general loop, for any television, is in [Writing a driver](../writing-a-driver.md).

## References

Claims marked `client-contract` record what ECP clients in the field expect, where no capture
can show it; no third-party emulator source was copied. See also [python-rokuecp](https://github.com/ctalkington/python-rokuecp) and
[Roku's mobile-app documentation](https://support.roku.com/article/install-the-mobile-app),
which describes the network-access values at feature level rather than at wire level.
