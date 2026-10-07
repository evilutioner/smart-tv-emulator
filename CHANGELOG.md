# Changelog

All notable changes to the public build are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-10-07

The first release whose shape is meant to hold. From here on the version follows Semantic
Versioning across the management API (`/api/v1`), the event log, the `tvemu`, `tvemu.expect`
and `tvemu.clients` command lines, and the run-record format under `docs/clients/`.

### Added

- Overview of one more television this build does not include: **Panasonic VIERA**, with two
  modelled devices, an older one that takes plain commands (NRC-2) and a newer one that pairs
  a remote with a four-digit PIN and encrypts its commands (NRC-4). It serves the remote
  service, the media renderer's volume and mute, the PAC channel for inputs and picture modes,
  UPnP events and a touchpad and gamepad socket. The official **Panasonic TV Remote 2** (iOS
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
  their repositories; and 🔬 our own unit tests and the byte-for-byte replay of its captures.
  Each one links to its report. A test report per television, `docs/tests/<id>.md`, is
  written by `tools/test_reports.py` from a clean tree and ships for every television. Whether a television is in this build
  now sits under its name. A badge counts the open-source clients. The catalogue
  carries `apps` and `clients`, held by tests to the manual validation ledger and to the
  clients whose latest recorded run passes.
- The default Roku device is the **TCL Roku TV 32S357** on Roku OS 15.3.4. The 12.0.0 stick
  capture has no `/query/device-info`, which every open-source Roku client reads first, so a
  first launch now answers what Home Assistant and the other clients need. The stick stays
  selectable.
- Asking about a television this build does not include, from the docs or the dashboard, now
  leads to [marchik.dev](https://marchik.dev). The GitHub request form is gone.

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

[Unreleased]: https://github.com/evilutioner/smart-tv-emulator/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/evilutioner/smart-tv-emulator/compare/v0.2.0...v1.0.0
[0.2.0]: https://github.com/evilutioner/smart-tv-emulator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/evilutioner/smart-tv-emulator/releases/tag/v0.1.0
