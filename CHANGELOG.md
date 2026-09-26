# Changelog

All notable changes to the public build are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- **Licence: Apache License 2.0**, replacing PolyForm Noncommercial 1.0.0. The shared core,
  the dashboard, the management API, the MCP server and the Roku adapter may now be used
  commercially. `NOTICE` added.
- Televisions that are catalogued but not in this build are labelled **N/A** instead of
  "soon": in the README, the platform overviews, the dashboard selector, and the management
  API, whose 501 body and `platforms[].availability` now carry `"n/a"` instead of `"soon"`.
  A client that matched `"soon"` has to match `"n/a"`.
- The Roku contract describes client-side expectations generically; claims keep their
  `client-contract` provenance kind.
- README: a new headline, an *About the author* section, and a link to this changelog.

### Removed

- `platforms/common/polo.py` from the public build: no platform shipped here uses it.

### Security

- The TCL Roku TV channel lists (`/query/apps` and the `ecp-2` `query-apps` envelope, in
  the Enabled, Limited and Disabled captures) no longer name three third-party channels,
  and the sideloaded development channel carries a neutral name, as the stick capture
  already did. Each capture's `source.description` records the change.

## [0.1.0] - 2026-09-26

First public build.

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
- Overviews of the nine televisions this build does not include.

[Unreleased]: https://github.com/evilutioner/smart-tv-emulator/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/evilutioner/smart-tv-emulator/releases/tag/v0.1.0
