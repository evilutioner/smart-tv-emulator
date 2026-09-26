# Changelog

All notable changes to the public build are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/evilutioner/smart-tv-emulator/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/evilutioner/smart-tv-emulator/releases/tag/v0.1.0
