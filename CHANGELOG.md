# Changelog

All notable changes to the public build are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/evilutioner/smart-tv-emulator/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/evilutioner/smart-tv-emulator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/evilutioner/smart-tv-emulator/releases/tag/v0.1.0
