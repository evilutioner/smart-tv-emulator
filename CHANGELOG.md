# Changelog

All notable changes to the public build are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.3.0] - 2026-10-21

### Added

- **Roku private listening** on the Roku Streaming Stick 4K, recorded off the stick: the
  official Roku app for Android can start Headphone Mode and hear a prepared test tone,
  over RTP or the stick's own stream, while `query-audio-device` follows each transition.
  Partially validated with the app; see the [Roku guide](docs/platforms/roku.md#support-and-validation).

- **Roku native text field** on the Roku Streaming Stick 4K, measured on the stick: focusing
  the dashboard's text field opens it, `set-textedit-text` replaces it, and subscribed
  ecp-2 sessions receive `textedit-opened`, `textedit-changed` and `textedit-closed`.
  Partially validated with the official Roku app for Android.

- Roku's ecp-2 session answers `request-events`, `launch` and `input` as the stick does,
  including 204 for a channel already running, and the read-only queries the official app
  sends (themes, screensavers, picture and audio settings, AV sync, tuner and input) from
  captured answers or captured refusals.

- **Samsung**: the 2011–13 legacy remote and the 2014–16 sets modelled from the apps and
  libraries that drive them, and a client page, `docs/clients/samsung.md`, for seven
  open-source clients.

- The dashboard follows the system's **dark appearance**.

- **JMGO** projectors, modelled with no projector measured: discovery and remote keys.

- **Xiaomi Mi TV**: pairing and remote keys on newer firmware, modelled with no set measured.

- **XGIMI** projectors, modelled with no projector measured: discovery, remote keys and
  pairing with a code on screen, on older and newer firmware.

- **T-Cast**, the LAN remote of TCL's own phone apps, modelled with no set measured: an older
  and a newer protocol generation.

### Changed

- Roku's ecp-2 `authenticate` takes any string request id, as the set does; the official
  Roku app for Android sends `"0"`, which the emulator used to refuse. A wrong answer is
  601 and leaves the session open, any other request before it is 401, and a session that
  has not authenticated 10.5 s after it opened is dropped, as the stick does. The Roku app
  for Android 14.1.2 is now in the [validation ledger](docs/manual-validation.md).

- The dashboard's selector is now **Platform**, grouped into TVs, Projectors and Consoles and
  sorted by name; the catalogue declares each platform's `kind` and which one is the
  default, and the state snapshot carries `version`, `device.platform_kind` and each
  platform's `kind`. Platform names read "Vendor Product": **Amazon Fire TV**,
  **Hisense VIDAA**, **LeEco (LeTV)**, **LG webOS**, **Metz**, **Philips** and
  **Xiaomi Mi TV**.

- **Samsung Tizen** and **Samsung Smart TV (2014–15)** are now **Samsung**, one television
  whose devices each serve their own generation's protocols: the three captured Tizen sets,
  the captured 2014–15 UE48H6200 and the modelled ones. Its overview moved to `docs/platforms/samsung.md`.

- **TCL nScreen** is now **TCL**, one television with three devices: the captured H32S5916 on
  the nScreen remote and the two T-Cast sets. Its overview moved to `docs/platforms/tcltv.md`.

### Fixed

- A tester disconnect on Roku's ecp-2 drops the connection, as the set does, instead of
  closing it with code 1001.

- With `--bind 127.0.0.1` on a machine that is also on a LAN, SSDP answers a search sent
  from the same machine by the default multicast route, which leaves through the LAN
  interface rather than loopback. Searches from other hosts are still ignored.

## [1.2.0] - 2026-10-15

### Added

- Overviews of two more televisions this build does not include: **Apple TV**, its
  Companion link recorded off an Apple TV 4K on tvOS 26.5 and exercised with **pyatv**; and
  **Xiaomi Mi TV (GiTV)**, modelled from **pymitv** with no set measured. Both have a client
  page under `docs/clients/`.
- The **TCL Roku TV 32S357** in standby, recorded off the set on Roku OS 15.3.4: `power-mode`
  follows the emulated power state on that profile, over plain HTTP and over ecp-2, and a
  channel launch, a keyword search and input to a channel are part of its evidence.
- Roku answers `POST /search/browse`, `/input` and `/input/{id}` with their status alone, and
  refuses them in Limited and Disabled as it refuses a launch. The three Roku clients no
  longer report search and input as gaps.
- [CONTRIBUTING.md](CONTRIBUTING.md), for people changing the emulator.

### Changed

- Roku `/query/device-info` names the access mode selected on the dashboard in
  `ecp-setting-mode`, on both wires.
- The Roku Limited refusal for a query carries the set's own `Content-Type` and
  `Cache-Control`, and a captured bodiless 404 no longer gains a `Content-Type` the set never
  sent.
- The replay conformance harness checks a declared substitution inside XML, and inside a
  base64 document carried in a JSON string, instead of excusing the whole body. It keeps a
  trailing space in a header value, which some UPnP servers write, instead of trimming it.
- The last five clients, **samsungtvws**, **pybravia**, **ha-philipsjs**, **panasonic-viera**
  and **pyvizio**, say what they offer per zone, read from each library's own tables, and
  which zones they have no API for. Their key steps now press every key the client offers.
  Known failures where the emulator answers exactly as the set does are attributed to the
  client.
- A client step the client does not offer is no longer counted as a failure on its
  television's page.
- Raw client run records ship only for the televisions this build includes; the rendered
  page per television stays the published evidence.
- The overviews of televisions this build does not include name what the emulator
  reproduces rather than each firmware quirk.

### Fixed

- The audio sniffer no longer reads quiet 16-bit samples as full-scale unsigned 8-bit stereo.
  A reading too quiet to judge is reported as 16-bit mono with confidence `guess`.

## [1.1.0] - 2026-10-11

### Added

- Overviews of four more televisions this build does not include: **Xbox One**, as a
  SmartGlass client and a DLNA renderer sees it, replayed from a recorded console session;
  and three modelled, with no set measured:
  **Huawei MediaQ**, **YunOS / AliTV** and **LeTV / LeEco**.
- Open-source clients for more televisions: the libraries behind Home Assistant's webOS,
  Tizen, Bravia, VIZIO, Philips and VIERA integrations (**aiowebostv**, **samsungtvws**,
  **pybravia**, **pyvizio**, **ha-philipsjs**, **panasonic-viera**), **androidtvremote2**
  on every Android TV profile, and two Fire TV clients, **androidtv** over ADB and
  **uc-intg-firetv**. Their recorded runs ship under `docs/clients/`.
- Client coverage: a run says what the client offers per zone and what each step exercised,
  and every item that did not pass is attributed — untested, blocked, unsupported by the
  emulator, a wrong answer from the emulator, or a client bug. Each television's client page
  is a heatmap and a backlog counted from the runs. Run records move to schema 2, which adds
  `offers`, `covers` and the error statuses the emulator sent; schema 1 records still read.
- `client.toml` takes `install.prerequisites` for an upstream whose build imports its own
  dependencies, `[not_offered]` zones, and a `side` on each known failure.
- [Testing an app](docs/testing-an-app.md) and
  [Adding your television](docs/adding-your-television.md), and issue templates for bugs and
  television requests.

### Changed

- The **Roku Streaming Stick 4K** profile now replays a complete capture of the stick on Roku
  OS 15.3.4: SSDP, the device documents and icon, every query over plain HTTP and over an
  authenticated ecp-2 session, and key handling. It answers `/query/device-info`, so the
  three open-source Roku clients no longer stop at their first request on it, and it answers
  the tuner queries 404 as a stick does. The 12.0.0 capture stays as evidence only, renamed
  `roku-streaming-stick-4k-12-0-0`.
- A profile can replay a captured non-200 answer.
- The ecp-2 seed is written as it is used, with the public article that documents it,
  instead of being derived at runtime.
- The vendor logos on the captured device images are painted out; each capture's description
  says so. The README and `NOTICE` say the project is independent and that product names
  only describe compatibility.
- Shared SSDP: a discovery stack's header may carry its own separator, a reply may carry the
  firmware's own status phrase and no `Content-Type`, and a profile may accept search lines
  ended by a bare LF.
- A protocol listener may be a datagram source, bound on the wildcard address so broadcasts
  reach it, and a capture may state its discovery as in-band.

### Fixed

- `tvemu.expect` fails a check whose range of the event log has lost events, rather than
  passing on what was retained. Each event carries `log_start_id`, the last explicit clear,
  so a JSONL export is checked by the same rule offline.

## [1.0.0] - 2026-10-07

The first release whose shape is meant to hold. From here on the version follows Semantic
Versioning across the management API (`/api/v1`), the event log, the `tvemu`, `tvemu.expect`
and `tvemu.clients` command lines, and the run-record format under `docs/clients/`.

### Added

- Overview of one more television this build does not include: **Panasonic VIERA**, with two
  modelled devices, an older one without pairing and a newer one that pairs a remote with a
  PIN on screen. It covers remote keys, volume and mute, inputs and picture modes, and a
  touchpad and gamepad. The official **Panasonic TV Remote 2** (iOS
  2.73) and **TV Remote 3** (iOS 1.01) were validated against it by hand; see the
  [ledger](docs/manual-validation.md).
- The dashboard's pairing panel is shared by every platform that publishes `Core.pairing`.
- Open-source clients: `python -m tvemu.clients` installs an upstream client library in its
  own virtual environment, drives the emulator with it through the library's public API, and
  judges the run from the client's steps, the event log and every request no capture answers.
  Known gaps and failures are declared with their reasons and go stale when they stop
  happening. `--record` keeps each run under `docs/clients/` with the exact client,
  environment and emulator version, and renders one page per television. The first client is
  **rokuecp**, the library behind Home Assistant's Roku integration:
  [Open-source clients](docs/open-source-clients.md).
- Two more Roku clients, **python-roku** and the npm package **roku-client**. Clients can now
  come from npm, with a JavaScript binding beside a harness of the same shape, and a gap can
  name a prefix (`query/icon/*`). A weekly workflow runs every client at its last green
  version and at the latest, so a failure says whether the emulator or the client changed.
  All three Roku clients meet the same gaps: search, application icons and, on the 12.0.0
  stick, device-info; python-roku also meets touch and sensor input.

### Changed

- `KeyEffect("volume", "set", amount=N)` sets the simulated volume outright, for protocols
  that write a level rather than step it.
- The README is shorter and aimed at people driving the emulator. How it works, the contract
  and adding a television moved to [Architecture](docs/architecture.md); the dashboard and the
  management API to [Dashboard and API](docs/dashboard-and-api.md); ports, pairing and every
  wire protocol to [Televisions and protocols](docs/televisions.md).
- Every device in the television table says how it is known: captured from a set, modelled
  from the vendor's app, and validated with a real app. The catalogue carries `validated`,
  held to the [manual validation ledger](docs/manual-validation.md) by a test.
- The README's television table ends with what each television was tested with, in place of
  the *In this build* column: ✅ the vendors' own remote apps, driven by hand, linked to their
  store pages, and 🧪 the open-source client libraries run against it every week, linked to
  their repositories; and 🔬 the project's own unit tests and the byte-for-byte replay of its captures.
  Each one links to its report. A test report per television, `docs/tests/<id>.md`, is
  written by `tools/test_reports.py` from a clean tree and ships for every television.
  Whether a television is in this build now sits under its name. A badge counts the open-source clients. The catalogue
  carries `apps` and `clients`, held by tests to the manual validation ledger and to the
  clients whose latest recorded run passes.
- The default Roku device is the **TCL Roku TV 32S357** on Roku OS 15.3.4. The 12.0.0 stick
  capture has no `/query/device-info`, which every open-source Roku client reads first, so a
  first launch now answers what Home Assistant and the other clients need. The stick stays
  selectable.
- Asking about a television this build does not include, from the docs or the dashboard, now
  leads to [marchik.dev](https://marchik.dev). The GitHub request form for them is gone.

## [0.2.0] - 2026-10-04

### Added

- Replay conformance: `python -m tvemu.conformance` starts each captured profile's real
  adapter on loopback, replays the captured client traffic over HTTP, HTTPS and WebSocket,
  and compares every answer with the capture byte for byte — status, every captured header
  and the body — allowing a difference only inside a declared runtime substitution. A replay
  it cannot run yet is listed as uncovered with its reason, never skipped. CI runs one
  conformance job per television with `--gate`.
- Voice stream detection: the emulator works out what an incoming audio stream is from the
  bytes alone (a container header, or sample width, byte order and channels for bare PCM, and
  the arrival rate) and reports it as `voice.detected` with its confidence and basis. The
  dashboard shows it live with a level meter. Audio is held only as a short in-memory window.
- [Manual validation](docs/manual-validation.md): the ledger of sessions with real remote
  apps, and the method for recording one.
- Profiles may carry a `label`, the line the dashboard's device picker shows, so two devices
  of one product line read differently.
- Overviews of two more televisions this build does not include: **Metz Classic**, modelled
  from the vendor's remote app with no set measured, and **TCL nScreen**.

### Changed

- Roku ECP documents are served with every header the set sent, not only its `Content-Type`,
  and a `Content-Type` that carries parameters goes out exactly as captured.
- The device details line says *software* rather than *OS* for a set's reported version
  string, which on several televisions is an API or service version.
- The voice log records the first audio chunk as an event and the totals at the end, instead
  of one event per chunk.

### Fixed

- An mDNS TXT record with no keys is sent as one empty string, as RFC 6763 requires, rather
  than as empty rdata.

## [0.1.0] - 2026-09-26

First public build, under the [Apache License 2.0](LICENSE); see [`NOTICE`](NOTICE).

### Added

- The shared core: platform registry and descriptor contract, per-protocol listeners with
  their own switches, access modes as platform data, simulated power, volume and mute, the
  event log with JSONL export, and the `/api/v1` management API with its OpenAPI document.
- The dashboard: configuration, device state, keyboard, application launches and the event
  log, with per-television modules.
- The **Roku** adapter: ECP over HTTP on 8060, the authenticated `ecp-2` WebSocket, SSDP
  `roku:ecp`, all four *Control by mobile apps* network-access modes, and two captured
  devices (Roku Streaming Stick 4K 3820EU2 and TCL Roku TV 32S357).
- The evidence-first contract: immutable captures, the IR derived from them, curated claims
  with per-claim provenance, `tvemu --contract <id> --check`, and OpenAPI 3.2 and
  AsyncAPI 3.1 exports committed under `docs/spec/`.
- Driver tooling: `python -m tvemu.expect` scenario checks, the `tvemu-mcp` MCP server,
  `tools/ecp_client.py`, and guides for writing a driver and running it in CI.
- Overviews of the televisions this build does not include. They are labelled **N/A** in
  the README and the dashboard selector; the management API lists them with
  `"availability": "n/a"` and answers a switch to one with 501 and `"reason": "n/a"`.

[Unreleased]: https://github.com/evilutioner/smart-tv-emulator/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/evilutioner/smart-tv-emulator/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/evilutioner/smart-tv-emulator/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/evilutioner/smart-tv-emulator/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/evilutioner/smart-tv-emulator/compare/v0.2.0...v1.0.0
[0.2.0]: https://github.com/evilutioner/smart-tv-emulator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/evilutioner/smart-tv-emulator/releases/tag/v0.1.0
