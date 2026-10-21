# Roku

Emulates the network contract a Roku remote application speaks: SSDP discovery, the captured
device documents, HTTP ECP commands, and the authenticated `ecp-2` WebSocket. Two physical
devices are captured — a TCL Roku TV 32S357 on 15.3.4, captured in each of its network-access
modes, and a Roku Streaming Stick 4K on the same firmware — and they differ in ways a driver has
to handle: the stick has no tuner, so it answers the `tv-channels` queries 404, and its
device-info carries the stick-only elements. The TCL is the default. An older 12.0.0 stick
capture, with no `/query/device-info`, is kept as evidence only.

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
| `POST` | `/search/browse` | computed | — |
| `POST` | `/input` | computed | — |
| `POST` | `/input/{app_id}` | computed | — |
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

- `plugin-ui-run` (from the set) — A subscribed channel-start notification.
- `plugin-ui-run-script` (from the set) — A captured channel-script notification; requires a profile template.
- `plugin-ui-exit` (from the set) — A subscribed channel-exit notification.
- `textedit-opened` (from the set) — A measured native text field opened.
- `textedit-changed` (from the set) — Native text and collapsed cursor changed.
- `textedit-closed` (from the set) — The native text field closed.
- `param-challenge` (from the set) — The authentication challenge, sent unprompted as the socket opens.
- `authenticate` (to the set) — The answer to the challenge, the only request before it succeeds.
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
- `launch` (to the set) — Launch a channel, with its params as one JSON string.
- `input` (to the set) — Hand params to a channel, launching it if it is not running.
- `request-events` (to the set) — Subscribe to notifications, +name or -name, comma separated.
- `set-audio-output` (to the set) — Start prepared private-listening test audio.
- `mobile-sas-disconnect` (to the set) — Stop this client's SAS stream.
- `set-textedit-text` (to the set) — A whole-field write; no native field captured yet.
- `query-themes` (to the set) — Captured theme catalogue.
- `query-screensavers` (to the set) — Captured screensaver catalogue.
- `query-av-sync-offset` (to the set) — Captured AV synchronization offsets.
- `query-curr-audio-format` (to the set) — Captured audio format.
- `query-tv-active-channel` (to the set) — The active tuner channel, or a captured refusal.
- `query-tv-channels-ex` (to the set) — Extended tuner channels, or a captured refusal.
- `query-tv-active-input` (to the set) — The active TV input, or a captured refusal.
- `query-warm-standby` (to the set) — Warm standby, or a captured refusal.
- `query-pq-options` (to the set) — Picture options, or a captured refusal.
- `query-pq-picture-modes` (to the set) — Picture modes, or a captured refusal.
- `query-pq-picture-settings` (to the set) — Picture settings, or a captured refusal.
- `query-audio-settings` (to the set) — Audio settings, or a captured refusal.
- `check-link` (to the set) — Captured device-link status.

`rtcp` messages:

- `reply` (from the set) — XDLY and NCLI replies sent to the client RTCP port.
- `feedback` (to the set) — Private-listening RTCP APP and receiver feedback.

`rtp` messages:

- `audio` (from the set) — A prepared 48 kHz Opus test tone in RTP packets.

`sas` messages:

- `feedback` (to the set) — Receiver timing status establishes a constant audio clock offset.
- `audio` (from the set) — An experimental Opus test tone with SAS format-5 parity.
<!-- /generated -->

## What a driver must know

Generated from `src/tvemu/platforms/roku/contract.py` and checked against every capture —
`tvemu --contract roku` prints the same thing.

<!-- generated:contract -->
Checked against 21 captures: `roku-audio-state-3820eu2-2026-10-18`, `roku-ecp2-probe-15-2-4`, `roku-ecp2-probe-3820eu2-15-3-4`, `roku-ecp2-surface-3820eu2-2026-10-18`, `roku-rtcp-handshake-3820eu2-2026-10-18`, `roku-rtp-clock-3820eu2-2026-10-18`, `roku-sas-clock-3820eu2-2026-10-18`, `roku-sas-fec5-3820eu2-2026-10-18`, `roku-streaming-stick-4k-12-0-0`, `roku-streaming-stick-4k-15-3-4`, `roku-streaming-stick-4k-3820eu2-15-3-4`, `roku-streaming-stick-4k-3820eu2-2026-10-18`, `roku-streaming-stick-4k-3820eu2-native-2026-10-18`, `roku-text-focus-3820eu2-2026-10-18`, `roku-text-limits-3820eu2-2026-10-18`, `roku-text-write-3820eu2-2026-10-18`, `tcl-roku-tv-32s357-15-2-4`, `tcl-roku-tv-32s357-15-3-4`, `tcl-roku-tv-32s357-disabled`, `tcl-roku-tv-32s357-enabled`, `tcl-roku-tv-32s357-standby`.

### The UPnP device description.

- **`device.UDN`** (presence: required) — The UDN is the stable identity of a UPnP device.
- **The whole document** (behavior: ecp-setting-mode is disabled -> 200 as usual) — Served in every access mode, Disabled included.

### The ECP device inventory.

- **`serial-number`** (behavior: a client decodes a successful device-info document -> serial-number must be present for the Roku mobile app) — The Roku mobile app requires this field in a successful document. A refused HTTP query has no document to decode.
- **The whole document** (behavior: ecp-setting-mode is disabled and the command arrives over plain HTTP -> 401 with an empty body) — Refused before the query is read, with neither words nor a Content-Type. The device documents, SSDP and an authenticated ecp-2 session keep working.
- **The whole document** (serialization: xml-text=True) — Every element is optional and names are case sensitive (has-wifi-5G-support). Every value is XML text: numeric-looking elements are strings, and av-sync-calibration-enabled answers "3.0".
- **`is-tv`, `is-stick`, `mobile-has-live-tv`, `supports-ethernet`, `has-wifi-5G-support`, `secure-device`, `time-zone-auto`, `supports-suspend`, `supports-find-remote`, `supports-audio-guide`, `supports-rva`, `has-hands-free-voice-remote`, `developer-enabled`, `device-automation-bridge-enabled`, `search-enabled`, `search-channels-enabled`, `voice-search-enabled`, `supports-private-listening`, `supports-private-listening-dtv`, `supports-warm-standby`, `headphones-connected`, `supports-audio-settings`, `supports-ecs-textedit`, `supports-ecs-microphone`, `supports-wake-on-wlan`, `supports-airplay`, `has-play-on-roku`, `has-mobile-screensaver`, `supports-trc`** (values: closed) — XML boolean text. A strict boolean decoder fails the whole document on an empty one.
  Values: `true`, `false`.
- **`screen-size`, `panel-id`, `tuner-type`, `trc-version`, `trc-channel-version`, `supports-private-listening-dtv`, `supports-warm-standby`** (presence: optional) — Television only: absent from the stick.
- **`find-remote-is-possible`, `is-powered-by-tv`, `supports-cec-power-control`, `supports-cec-audio-volume-control`** (presence: optional) — Stick only: absent from the television.
- **`ecp-setting-mode`** (values: closed) — Which clients the set answers; mirrors the platform's four access modes. The emulator writes the selected mode here, over HTTP and inside the envelope.
  Values: `limited`, `enabled`, `disabled`, `permissive` (client-contract).
- **`user-profile-type`** (values: open) — Who is signed in on the set; the same TCL answered none and later adult.
  Values: `none`, `adult`, and possibly others.
- **`power-mode`** (values: open) — A television in standby keeps answering: the TCL said Ready after PowerOff, over both wires, and PowerOn again after PowerOn. The emulator writes it from the power state where the profile gives both values; the stick's standby is not measured, so it stays as captured.
  Values: `PowerOn`, `Ready`, `DisplayOff` (client-contract), `Headless` (client-contract), and possibly others.

### A picture of the device.

- **The whole document** (serialization: media_type='image/png') — The one captured route that is not XML. The 15.2.4 stick answers 404 and offers /query/icon/<channel-id> as image/jpeg instead.

### The foreground channel.

- **`screensaver`** (presence: optional) — Present only while a screensaver runs, beside app rather than instead of it: the set answered app Roku both times.
- **The whole document** (behavior: ecp-setting-mode is disabled and the command arrives over plain HTTP -> 401 with an empty body) — Refused before the query is read, with neither words nor a Content-Type. The device documents, SSDP and an authenticated ecp-2 session keep working.
- **The whole document** (behavior: a launched channel is running -> app names that channel, with its id, type, version and name) — The type is appl and ui-location is the channel id, where the home screen answers type home and ui-location home. The emulator replays the captured document whatever was launched.

### The installed channels.

- **The whole document** (behavior: ecp-setting-mode is disabled and the command arrives over plain HTTP -> 401 with an empty body) — Refused before the query is read, with neither words nor a Content-Type. The device documents, SSDP and an authenticated ecp-2 session keep working.
- **The whole document** (behavior: the channel list is asked for over plain HTTP -> app elements carry id, type and version only) — Not a copy of the ecp-2 document: the envelope's gives every appl a subtype (ndka, rsga, sdka, and it moves -- Netflix answered ndka, then rsga) that the HTTP list of the same set leaves out.
- **The whole document** (behavior: ecp-setting-mode is limited and the query arrives over plain HTTP -> 403 text/plain "ECP command not allowed in Limited mode.") — Refused before the set looks for the document, so the channel it names does not matter. The authenticated ecp-2 session is not restricted.

### The player state.

- **The whole document** (behavior: ecp-setting-mode is limited and the query arrives over plain HTTP -> 403 text/plain "ECP command not allowed in Limited mode.") — Refused before the set looks for the document, so the channel it names does not matter. The authenticated ecp-2 session is not restricted.

### The tuner's channel list.

- **The whole document** (behavior: the set is not a television (is-tv false) -> 404 with an empty body) — A stick has no tuner, and the route is not there at all: the same answer over ecp-2 is a 404 frame.

### The tuned channel.

- **The whole document** (behavior: the set is not a television (is-tv false) -> 404 with an empty body) — A stick has no tuner, and the route is not there at all: the same answer over ecp-2 is a 404 frame.

### A channel's icon.

- **The whole document** (behavior: ecp-setting-mode is limited and the query arrives over plain HTTP -> 403 text/plain "ECP command not allowed in Limited mode.") — Refused before the set looks for the document, so the channel it names does not matter. The authenticated ecp-2 session is not restricted.

### One remote key over plain HTTP.

- **The whole document** (behavior: the key is neither a button name nor Lit_ and one character -> 400 with an empty body) — The key name is judged before the access mode, so an unknown key is 400 even where every key would be refused.
- **The whole document** (behavior: ecp-setting-mode is limited -> 403 with an empty body; the same key over ecp-2 is accepted) — Unlike a refused query, a refused key carries no words and no Content-Type.
- **The whole document** (behavior: ecp-setting-mode is disabled and the command arrives over plain HTTP -> 401 with an empty body) — Refused before the key name is read, with neither words nor a Content-Type. An unknown key is 401 too, not 400. The device documents, SSDP and an authenticated ecp-2 session keep working.
- **The whole document** (behavior: keyup names a key this client is not holding -> 202 with an empty body) — The same rule as ecp-2: releasing a key nobody pressed is accepted as 202.

### Launch a channel.

- **The whole document** (behavior: ecp-setting-mode is disabled and the command arrives over plain HTTP -> 401 with an empty body) — Refused before the channel id is read, with neither words nor a Content-Type. An unknown channel is 401 too, not 404. The device documents, SSDP and an authenticated ecp-2 session keep working.
- **The whole document** (behavior: the channel id is not installed -> 404 with an empty body) — The set checks the id against its installed channels. The emulator accepts any id, so a driver's launch can be observed without a catalogue.
- **The whole document** (behavior: the channel id is installed -> 200 with an empty body) — The channel comes to the foreground; see active-app.

### Open the search screen.

- **The whole document** (behavior: a keyword search is asked for -> 200 with an empty body) — The search screen belongs to the home channel, so active-app still answers the home screen afterwards.

### Parameters for the foreground channel.

- **The whole document** (behavior: any parameters are posted -> 200 with an empty body) — Accepted on the home screen too, where nothing consumes it.

### Parameters for one channel by id.

- **The whole document** (behavior: the channel id is not installed -> 404 with an empty body) — Play on Roku (15985) is a channel like any other: this TCL does not have it installed. The emulator accepts any id, as it does for launch.

### Any other route.

- **The whole document** (behavior: the set has no such route -> 404 with an empty body) — A query name the set does not know is no different from any other unknown path. The emulator answers 501 for every route it holds no capture of, which keeps a gap in the emulator distinguishable from the set's answer.

### The device inventory inside the envelope.

- **The whole document** (behavior: device-info is asked for over ecp-2 -> the document carries virtual-device-id) — Not a copy of the HTTP document: the envelope's adds virtual-device-id after udn, which HTTP /query/device-info of the same set leaves out.

### A held remote key, released.

- **The whole document** (behavior: the key is not held by this session -> status 202, status-msg Accepted) — The set tracks what is held, character keys included: releasing a key this session did not press answers 202, where releasing a held one answers 200.

### The unprompted frame as the ecp-2 socket opens.

- **`notify`** (values: closed) — A notification, not a reply: no response or status.
  Values: `authenticate`.
- **`param-methods[]`** (values: open) — The only param that is not a string. Older firmware sent none, so a client must not depend on it.
  Values: `client-id`, `jwt`, and possibly others.
- **`timestamp`** (constraint: pattern='[0-9]+\\.[0-9]{3}') — Device uptime in seconds as a decimal string; it resets on reboot.

### The answer to the challenge.

- **`request-id`** (values: open) — Any string, echoed as response-id like every other request's: the set prescribes no value. The official Roku app for Android numbers its requests from 0, so its authenticate carries "0"; other clients start at 1.
  Values: `1`, `0`, `abc`, and possibly others.
- **`request-id`** (behavior: request-id is a number or is missing -> the set drops the connection without a reply; the emulator sends close code 1002 first) — The same framing rule as after authenticating.
- **`param-response`** (behavior: the answer is not the one the challenge asks for -> status 601, status-msg Invalid Credentials; the socket stays open) — A wrong answer does not end the session: the client may answer the same challenge again, and a right answer then authenticates it.
- **The whole document** (behavior: the session has not authenticated 10.5 s after it opened -> the set drops the connection with no close frame) — The deadline runs from the open, whatever the client sent meanwhile; an authenticated session idle for 80 s stayed open.
- **The whole document** (behavior: authenticate arrives on a session that has already authenticated -> status 404, status-msg Not Found) — Once authenticated, authenticate is no longer a request the session has.

### Subscribe to notifications.

- **`param-events`** (values: open) — Comma-separated entries, each + or - and an event name; empty entries are skipped. Names are case sensitive and nothing is trimmed. A stick takes the television's tuner and input events too. The list the official Roku app for Android sends is the one captured.
  Values: `+language-changed,+language-changing,+media-player-state-changed,+plugin-ui-run,+plugin-ui-run-script,+plugin-ui-exit,+screensaver-run,+screensaver-exit,+plugins-changed,+sync-completed,+power-mode-changed,+volume-changed,+textedit-opened,+textedit-closed,+textedit-changed,+device-name-changed,+device-location-changed,+audio-setting-changed,+audio-settings-invalidated,+user-profile-changed,+tv-power-volume-control-changed`, `+volume-changed,+no-such-event`, `+VOLUME-CHANGED`, and possibly others.
- **`param-events`** (behavior: some entries name a known event and some do not -> status 202, status-msg Accepted) — Part of the list is taken.
- **`param-events`** (behavior: no entry names a known event with its sign, or the list is empty -> status 404, status-msg Not Found) — Nothing is taken.
- **The whole document** (behavior: param-events is missing -> status 400, status-msg Bad Request) — The parameter is required.

### Launch a channel.

- **`param-params`** (values: open) — One string holding a JSON object; the official Roku app for Android always sends its gc_run_source keys. Missing, empty and {} are all no params.
  Values: `{}`, `not json`, and possibly others.
- **The whole document** (behavior: the channel is in the foreground and there are no params -> status 204, status-msg No Content) — The set leaves a running channel alone; the official Roku app for Android reads 204 as already launched.
- **The whole document** (behavior: the channel is in the foreground and params are given -> status 200; the channel exits and runs again) — With params, a running channel is restarted.
- **`param-channel-id`** (behavior: the channel is not installed -> status 404 on the set; 200 from the emulator) — The emulator does not follow: like the HTTP launch, it accepts any id.
- **The whole document** (behavior: param-channel-id is missing or param-params is not JSON -> status 400, status-msg Bad Request) — Both parameters are checked before anything runs.

### Hand params to a channel.

- **The whole document** (behavior: the channel is installed but not in the foreground -> status 200; the channel runs) — A channel that is not running is launched to take them.
- **`param-channel-id`** (behavior: the channel is not installed -> status 404 on the set; 200 from the emulator) — The emulator does not follow, as for launch.

### A key press; key-down and key-up alike.

- **`param-key`** (values: open) — A button name, or Lit_ and exactly one raw UTF-8 character. Case is ignored, so a client that sends LIT_ works. Nothing is percent-decoded on this wire: Lit_%20 is 400 while a literal space is 200, although over HTTP /keypress/%48ome presses Home. Anything else, or a field spelled key, is 400.
  Values: `Home`, `home`, `Lit_a`, `LIT_a`, `Stop` (probe), `Guide` (probe), `LiveTV` (probe), `Exit` (probe), `ClosedCaption` (probe), `Red` (probe), `Green` (probe), `Yellow` (probe), `Blue` (probe), and possibly others.
- **`param-key`** (behavior: param-key is a digit, ".", Keyboard, TextSearch or VoiceSearch -> status 400, status-msg Bad Request) — Names the official Roku app for Android has that the set does not take.
- **`request-id`** (behavior: request-id or request is missing or not a string, or the frame is not a JSON object -> the set drops the session without a reply; the emulator sends close code 1002 first) — Any string, echoed as response-id and never validated -- a reused "1" included.

### The envelope every ecp-2 reply arrives in.

- **`response`** (values: closed) — Echoes the request name.
  Values: `authenticate`, `key-press`, `key-down`, `key-up`, `query-device-info`, `request-events`, `launch`, `input`, `query-active-app`, `query-apps`, `query-media-player`, `query-textedit-state`, `query-audio-device`, `query-tv-channels`, `commit-av-sync-offset` (client-contract), `query-av-sync-offset` (client-contract), `reset-av-sync-offset-all` (client-contract), `set-av-sync-offset` (client-contract), `query-curr-audio-format` (client-contract), `check-link` (client-contract), `input` (client-contract), `key-down` (client-contract), `key-press` (client-contract), `key-up` (client-contract), `launch` (client-contract), `mobile-sas-disconnect` (client-contract), `query-tv-active-channel` (client-contract), `query-audio-setting` (client-contract), `query-audio-settings` (client-contract), `capture-screen` (client-contract), `query-device-info` (client-contract), `generate-issue-id` (client-contract), `query-icon` (client-contract), `query-info-for-voice-service` (client-contract), `query-pq-color-space-settings` (client-contract), `query-pq-color-temp-settings` (client-contract), `query-pq-options` (client-contract), `query-pq-picture-modes` (client-contract), `query-pq-picture-settings` (client-contract), `query-screensavers` (client-contract), `query-themes` (client-contract), `query-tv-active-input` (client-contract), `query-tv-channels-ex` (client-contract), `query-warm-standby` (client-contract), `authenticate` (client-contract), `request-events` (client-contract), `reset-audio-setting` (client-contract), `reset-audio-settings` (client-contract), `get-mobile-pl-headset-delay` (client-contract), `set-mobile-pl-headset-delay` (client-contract), `send-intent` (client-contract), `send-voice-events` (client-contract), `set-audio-output` (client-contract), `set-audio-setting` (client-contract), `set-pq-color-space-settings` (client-contract), `set-pq-color-temp-settings` (client-contract), `set-pq-picture-mode` (client-contract), `set-pq-picture-settings` (client-contract), `set-screensaver` (client-contract), `set-textedit-text` (client-contract), `set-warm-standby` (client-contract), `sync-channels` (client-contract), `initiate-becp-pairing` (client-contract), `remove-ble-device` (client-contract).
- **`status`** (values: closed) — A decimal string about the request, not the transport: a refusal arrives in a successful frame. 400 is an unusable parameter, 404 an unknown request name, 202 the release of a key not held, 401 a request before authenticating and 601 a wrong challenge answer.
  Values: `200`, `202`, `204`, `401`, `601`, `400` (probe), `404` (probe).
- **`status`** (behavior: any other request arrives before a successful authenticate -> status 401, status-msg Unauthorized; the socket stays open) — Nothing but authenticate is served before it succeeds.
- **`status-msg`** (values: closed) — The status phrase only; the set never explains.
  Values: `OK`, `Accepted`, `No Content`, `Unauthorized`, `Invalid Credentials`, `Bad Request` (probe), `Not Found` (probe).
- **`content-type`** (serialization: charset=True) — Present only with content-data. Hardware spells it with a quoted charset (text/xml; charset="utf-8", application/json for textedit-state) and the emulator replays what the capture recorded; the 15.2.4 probe kept none.
- **The whole document** (serialization: json_separators=',:') — No space after either JSON separator, reproduced for drivers that compare or hash frames.
- **The whole document** (serialization: json_key_order='sorted') — Keys in sorted order, so content-data comes first in a frame that has one.

### Current audio destinations.

- **`global.destination-list`, `destinations.destination.@name`, `rtp-info.rtp-address`** (presence: optional) — Profile-declared live destination state. A single active transport follows the measured transitions; with multiple independent senders the last-started view is emulator-owned.
- **The whole document** (behavior: private listening starts or stops -> hdmi changes to mobile-sas or datagram and returns to hdmi; RTP address names the datagram destination only) — Ordered Stick audio-state capture, separately measured over HTTP and ecp-2.

### Current audio destinations.

- **`content-data::global.destination-list`, `content-data::destinations.destination.@name`, `content-data::rtp-info.rtp-address`** (presence: optional) — Profile-declared live destination state. A single active transport follows the measured transitions; with multiple independent senders the last-started view is emulator-owned.
- **The whole document** (behavior: private listening starts or stops -> hdmi changes to mobile-sas or datagram and returns to hdmi; RTP address names the datagram destination only) — Ordered Stick audio-state capture, separately measured over HTTP and ecp-2.

### The native field backed by the shared text buffer.

- **`content-data::textedit-state.textedit-id`, `content-data::textedit-state.textedit-type`, `content-data::textedit-state.text`, `content-data::textedit-state.masked`, `content-data::textedit-state.max-length`, `content-data::textedit-state.selection-start`, `content-data::textedit-state.selection-end`** (presence: optional) — Live only on a profile with measured native full fields while the dashboard field is focused; textedit-id is none otherwise.

### Replace the focused native full field.

- **The whole document** (behavior: selection-end is supplied -> cursor collapses to that position clamped to 0..text length; selection-start is ignored; missing end uses text length, invalid numeric text uses zero) — Measured unmasked full field only. Android String.length uses UTF-16, but this field counts Unicode codepoints.
- **The whole document** (behavior: id is unknown or replacement exceeds the character limit -> 200 with unchanged field and no textedit-changed notification) — The advertised full-field maximum was 75 characters.

### Subscribed native textedit transition.

- **`param-textedit-id`** (presence: optional) — Live field identity increments on opening; closing names the former id.
- **The whole document** (behavior: a measured native field changes focus or text -> send the corresponding captured textedit event to subscribed clients) — Subscribed connections have independent notification queues.

### Subscribed native textedit transition.

- **`param-textedit-id`** (presence: optional) — Live field identity increments on opening; closing names the former id.
- **The whole document** (behavior: a measured native field changes focus or text -> send the corresponding captured textedit event to subscribed clients) — Subscribed connections have independent notification queues.

### Subscribed native textedit transition.

- **`param-textedit-id`** (presence: optional) — Live field identity increments on opening; closing names the former id.
- **The whole document** (behavior: a measured native field changes focus or text -> send the corresponding captured textedit event to subscribed clients) — Subscribed connections have independent notification queues.
<!-- /generated -->

## What the claims above do not say

- **Two text paths exist in the Android client.** It uses `set-textedit-text` after a native
  `textedit-opened` notification, and can fall back to `Lit_<char>`. Our captures contain
  `query-textedit-state` with id `none`, but no native field-opening notification. The stick
  accepts a well-typed full-text write with no field and discards it; that does not establish
  how a focused field behaves. `Lit_%2F` cannot be routed over HTTP, because the ECP path
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
selected capture recorded the document. The refusal is spelled like the set's documents,
`text/plain; charset="utf-8"` with `Cache-Control: no-cache`. A key name is judged before
the mode, so an unknown key is still 400.

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
`subtype`. The other 15.3.4 stick capture (`roku-streaming-stick-4k-15-3-4`) and the two ecp-2
probes are evidence only: they feed the claims above but have no discovery evidence, so they are
never selectable. `roku-ecp2-probe-3820eu2-15-3-4` was taken off the Streaming Stick 4K on
2026-10-17: how `authenticate` takes any request id and refuses a wrong answer, what is served before it succeeds, `request-events`,
and ecp-2 `launch` and `input`.

The TCL was captured three times on 15.3.4, once per network-access value it was switched
through. Its profile replays `tcl-roku-tv-32s357-enabled`, the one mode in which every document
answers on both wires; `tcl-roku-tv-32s357-15-3-4` (Limited) and `tcl-roku-tv-32s357-disabled`
are the evidence for what the other modes refuse, which the emulator reproduces from mode data
rather than from a replay. Its 15.2.4 capture is evidence too, and so is
`tcl-roku-tv-32s357-standby`: device-info after `PowerOff`, a launch and what followed it,
search, input and two routes the set does not have. Its standby `power-mode` reaches the
profile through `runtime`, with that capture named as the source.

To add a Roku, add one evidence directory and, if it is complete, a profile reference, then
run `tvemu --contract roku --check`. The dashboard's **Device** selector switches
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

Channel launch, and `input` to a channel by id, accept any id for client validation without
running anything, where the set answers 404 for a channel that is not installed. Over `ecp-2`
the emulator keeps which channel it last launched, so a repeated launch without params is 204
as on the set, and `Home` clears it; nothing else follows from it. Search and
`input` to the foreground channel answer 200 with no body, as the set does, and change nothing
the queries show. The channel list, foreground channel, player state and tuner
documents are captured snapshots: a launch does not change what
`query-active-app` answers, although on the set the launched channel comes to the foreground,
and a volume key does not change `audio-device`. `device-info` is the captured document except
`ecp-setting-mode`, which names the selected access mode on both wires, and, on the TCL,
`power-mode`, which reads `Ready` after `PowerOff` as the set did and `PowerOn` again after
`PowerOn`. The stick's standby is not measured, so its `power-mode` stays as captured.
The extended stick profile sends captured `plugin-ui-run` and `plugin-ui-exit` notifications
only to sessions subscribed to them. Launch and Home also work from the dashboard without
coalescing transitions. Power, volume and player notifications still need captures.
The Stick profile now also sends native textedit-opened/changed/closed for dashboard focus
and edits through the shared text buffer. An unmasked `full` field was measured with maximum
75 Unicode codepoints. Whole-field replacement preserves spaces; an unknown id or an
over-limit string receives 200 without changing text. The cursor collapses to selection-end
clamped in Unicode codepoints, although Android sends UTF-16 lengths. Missing selection-end
uses the text length; invalid numeric text uses zero. Field ids increment on reopening.
No-field writes are accepted and discarded. Hidden fields and other native types remain
unmeasured. The complete `roku-streaming-stick-4k-3820eu2-native-2026-10-18` capture retains
the earlier baseline bytes and adds the native query and notification templates from the
separate field captures. Runtime edits replace their declared values rather than generating
a document from a field schema. Channel icons over `ecp-2` (`query-icon`) still answer 404.
There is no Cast and no rendered screen. Other app and media endpoints answer **501**, and an unknown
remote key is **400**. A malformed escape such as `/keypress/Lit_%ZZ` is **404** on the set,
whose URL parser rejects it before routing; the emulator keeps the bytes and answers 200 or 400.

Where the TCL set on 15.3.4 answers differently and the emulator does not follow:

- A route the set does not have is **404** with no body there and **501** here. This one is
  deliberate: the emulator cannot tell a route the set lacks from one it was never captured
  answering, and 501 keeps the second visible.
- The channel icon (`image/jpeg`) and the developer diagnostics (`chanperf`, `registry`,
  `sgnodes`, `r2d2-bitmaps`, the beacons) answer on the set and are not captured here: an icon
  is a channel's trademark artwork. The diagnostics answer 202 while no channel runs.

## Private listening and client inventory

The Streaming Stick profile includes an on-demand **Private listening** listener. An
authenticated `set-audio-output` starts a prepared stereo Opus test signal: alternating
440/660 Hz tones. No encoder or system-audio capture runs in the emulator.

- `datagram`: RTP, payload type from `param-devname`, 48 kHz Opus and measured 480-sample
  packets, even when the destination declares capacity 960. The stick uses SSRC 0 and
  header timestamps that advance about 1000 ticks per second, distinct from decoded
  sample rate. These observed choices are profile runtime data. RTCP on UDP 5150 answers
  `VDLY` with `XDLY`, `CVER` with `NCLI`, and handles `BYE`; replies go to the declared
  RTP port plus one, including when feedback originates at the RTP port. Silent startup
  datagrams are retained in `roku-rtp-clock-3820eu2-2026-10-18`.
- `mobile-sas`: experimental UDP sender for versions 43–45. Framing follows the audio
  receiver of the Roku mobile app and silent v45 packets measured on the stick. A stream identifier stays
  constant while sample positions advance. Receiver timing status establishes a constant
  finite clock offset after the initial sentinel; a prepared 500 ms buffer schedules the
  test signal against the phone playhead. This transition is necessary for Android to
  decode audio. The sender emits format-5 GF(16) parity over each main frame and up to
  four preceding frames. Retransmission and adaptive delay remain unimplemented. Version 45
  test-tone playback was checked against the Roku mobile app by playback; versions
  43/44 and adverse-network behaviour are not validated.
- `mobile-sas-disconnect` stops the owning session; closing its WebSocket, disconnecting
  clients, switching profile or stopping the audio listener also releases its socket/task.
  Audio cannot be directed at an address other than the authenticated connection's peer.
- The TCL profile is unchanged: its audio control/stream still needs a measured session.
  The dashboard shows transport, clock synchronization state and packet/byte/feedback
  counts on the stick profile. Two local clients have independent sessions; stopping one
  does not stop the other. Physical-device conflict policy, receiver loss while a
  WebSocket remains open, FEC recovery and adaptive delay still need measured scenarios.

`src/tvemu/platforms/roku/client-contract.json` records the client contract of the Roku
mobile app for Android 14.1.2: its request list and parameters, the fields of each response
model it decodes, selection units (UTF-16), audio transport choice and evidence status. The
app prefers SAS when advertised versions overlap and no RTP address is active. That is why
RTP alone cannot complete the app's private listening. `secret` is an open value in the
request list, not a request named `secret`, and `shutdown` is never sent on the wire; both
are excluded from wire requests.

The new stick evidence adds themes, screensavers, AV-sync offsets, current audio format and
link status. Tuner, warm-standby, picture and audio-setting queries replay the stick's
captured 404 envelopes rather than manufacturing settings for a stick that does not have
them. Unmeasured setters, voice setup/audio, headset-delay commands and icons remain gaps.
The foreground/player queries remain captured snapshots. The Stick audio query now follows
measured hdmi/mobile-sas/datagram transitions on both wires, including destination name and
the RTP endpoint. With multiple independent emulator audio sessions its query shows the
last-started session; physical conflict arbitration remains unmeasured.

BLE-ECP remains outside the network emulator. The Android client is a GATT peripheral and
requires JWT for BLE; it forbids the `client-id` fallback allowed by Wi-Fi ecp-2. It also has
a no-Wi-Fi pairing branch. No BLE capability is added to captured device-info, and no cloud
JWT issuer or physical Bluetooth transport is emulated.

The JSON response models in the client contract include the audio setting `id` and
`value`, the range option `value`, the host device `tv_inputs` and the voice configuration
`name`. Voice-event requests also serve ordinary shortcuts: captions and sleep timer;
sleep-timer visibility reads `supported_fulfillers` from query-info-for-voice-service.
Those shortcuts still need device captures; they do not require speech recognition.

## Remaining capture dependencies

The physical TCL was unavailable during the 2026-10-18 work. Power/volume/mute and player
notifications, hidden native text fields and types other than the measured full field,
TV picture/audio/tuner settings and their setters still need their own ordered captures.
The existing stick evidence must not be promoted into claims about those TCL behaviours.
Icons, voice setup/audio, service setters and transport conflict/failure scenarios remain
listed as gaps in the client inventory. Neither the network inventory nor audible SAS
alone completes the full official-client plan. UDP captures above remain separate from
selectable device identity. Their declared conformance scenarios compare prepared-payload
RTP framing, SAS startup/clock transitions and ordered RTCP handshake bytes. Captured SAS
FEC headers and parity equations are covered, including an ordered five-pair silent
startup capture. Continuous timing, receiver recovery under actual loss and adaptive
delay are not established by these partial captures.

## Support and validation

On 2026-10-19 the Roku mobile app for Android 14.1.2 was connected to the updated Stick profile.
Opening a `full` field in the dashboard opened the app keyboard. An ASCII test string typed
in the app reached the shared buffer through `set-textedit-text`. Replacing it in the dashboard
with a string containing Latin, emoji, Cyrillic and CJK characters updated the app through
`textedit-changed`. Closing and reopening the field allowed another write with the new id.
These observations validate the unmasked native full-field path for this session; the Unicode
input direction from the phone, hidden fields and other field types were not validated.
With no native field, the app emitted literal keys. Paced input retained order. Fast
automated input produced a different order for two letters even though the app displayed the
intended string; request ids were already assigned in that order, which points at the app
rather than the emulator, though the cause is not isolated. The emulator preserves received
order rather than repairing text.

On 2026-10-18 the Roku mobile app for Android **14.1.2** was exercised against
`roku-streaming-stick-4k-3820eu2`. Discovery, authentication and opening Headphone Mode
were observed. Early SAS attempts returned feedback but remained inaudible; recordings
between the stick and the app isolated the missing transition to a finite clock offset.
With that in place the alternating test tone played from the standalone emulator through
the app. This validates clean-LAN SAS v45 test-tone playback. RTP was not exercised through
the app. A separate RTP/RTCP receiver and Opus decoder accepted 801 emulator packets,
decoded 384480 samples with nonzero signal, completed XDLY/NCLI and stopped on BYE; that
exercise is not app validation. The native-field keyboard and additional settings
were not validated in that audio session. Later native full-field captures exercise both
textedit and audio query transitions in conformance, but are not a separate app
validation. The partial clock exchange is retained separately in
`roku-sas-clock-3820eu2-2026-10-18`; it contains receiver status and silent packets only.
The conformance harness covers the profile HTTP/ecp-2 replays and separately declared
UDP evidence scenarios. Binary fields outside profile-declared runtime substitutions are
compared exactly; prepared payloads and clock offsets are checked separately. FEC parity
is independently recomputed from received main packets, and deliberate parity corruption
fails conformance. A follow-up on 2026-10-18 with a fresh authenticated session, Headphone Mode on and
finite clock feedback played the alternating tone with format-5 parity enabled. Turning
Headphone Mode off then removed the audio session.
Receiver recovery under actual packet loss has not been checked on the phone.
The earlier TCL session below is a separate result.

The official **Roku** app for Android, **14.1.2**, was validated against the emulator by hand on
2026-10-17 on profile `tcl-roku-tv-32s357`. It was the first Android app driven against any
television here. Every finding was measured on the Streaming Stick 4K on 15.3.4 before the
emulator changed. The [manual validation ledger](../manual-validation.md) has the row.

- **Validated**: SSDP discovery and the device description; the `ecp-2` session, whose
  `authenticate` the app sends with request id `"0"` (refused 401 until this session, now any
  string is echoed); the event subscription it sends next; device-info, apps, active-app,
  textedit-state and audio-device inside the envelope; `PowerOn` on connect; the arrows, OK,
  Back, Home (pressed and held), Info, Instant Replay, Rev, Play, Fwd, volume up and down,
  mute and Guide; channel launches from the channel list over `ecp-2` `launch`, a repeated one
  included; reconnecting after the dashboard's **Disconnect**, and after the app was closed and
  reopened.
- **Observed, unconfirmed**: typing, which arrives as `Lit_a`, `Lit_b` key presses because the
  emulator sent no `textedit-opened` in that earlier session; the keys reached it with no field focused.
- **Not exercised**: voice search, which the app shows for neither the emulator nor the stick;
  `set-textedit-text`, which the app sends only after `textedit-opened`.
- **Not emulated in that TCL session**: channel icons (`query-icon` is 404, so the channel
  list shows blank tiles, the channel name being part of the artwork) and private listening.
  The later stick test sender is described above and has separate acceptance criteria. An emulator restart drops the session; the app retries once at once, while the port is
  still closed, and then waits for a manual reconnect.

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

The contract is committed beside this guide, so a driver can start
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
can show it. See also [python-rokuecp](https://github.com/ctalkington/python-rokuecp) and
[Roku's mobile-app documentation](https://support.roku.com/article/install-the-mobile-app),
which describes the network-access values at feature level rather than at wire level.
