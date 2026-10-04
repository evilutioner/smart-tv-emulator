# Smart TV Emulator — agent notes

A local test bench that emulates Smart TV network protocols behind one dashboard.
One Python process, aiohttp only, no build step. See `README.md` for the full picture.

## Layout

```text
src/tvemu/
  core.py            shared state, settings, events, command results  (no platform names)
  runtime.py         platform lifecycle + set_platform()              (no platform names)
  control.py         local /api/v1 and dashboard server               (no platform names)
  expect.py          scenario check over the event log (python -m tvemu.expect)
  mcp.py             stdio MCP server over /api/v1 (tvemu-mcp)       (no platform names)
  platforms/
    __init__.py      registry, discovered from the packages in this directory
    base.py          PlatformDescriptor + PlatformAdapter contract
    catalogue.py     reads catalogue.json; locked = catalogued minus present
    catalogue.json   every platform this product models  (the one shared file that names them)
    common/          shared adapter, evidence/IR/claims, SSDP and mDNS responders
      reply.py       ReplyStyle / WireError: the declared type of every answer
      routing.py     route declarations that live beside their handler
      evidence.py    immutable captures and ordered wire exchanges
      ir.py          observed message structure derived from capture payloads
      claims.py      typed curated claims with per-claim provenance
      report.py      contract check, OpenAPI 3.2 and AsyncAPI 3.1 projections
    <id>/            wire protocol, descriptor and evidence; exports PLATFORM + ADAPTER
      contract.py    this platform's curated claims
      evidence/      every capture, complete or partial
      profiles/      selectable devices; references complete captures
  web/
    index.html  style.css  app.js  dom.js    shared shell             (no platform names)
                                             cards: config, device state, keyboard, log
    platforms/<id>.js  <id>.css              per-TV UI contributions
```

## The one rule

**A platform name never appears in a shared file.** Anything platform-shaped lives in
`platforms/<id>/` or `web/platforms/<id>.js`. Differences between TVs are expressed as
`PlatformDescriptor` data, a `common/` hook, or a UI module — never an `if platform == …`.
Per-device differences are evidence/profile data, never `if profile_id == …` branches.

The single exception is `platforms/catalogue.json`, which is data: it names every television
this product models so a build can present one it cannot run. `tests/test_public_build.py`
enforces the rule over everything else under `src/tvemu/`.

Device state moves the same way. Power, volume and mute change only through the key-effect
table a platform declares and `Core.apply`; nothing outside `core.py` assigns `core.power`.

## Dashboard platform module

`web/platforms/<id>.js` default-exports any subset of:

```js
{ primaryKeys: [...], keyLabels: {...}, stylesheet: "/platforms/<id>.css",
  mount(root), mountSettings(root), update(state), unmount() }
```

`app.js` imports it by the snapshot's platform id, calls `update(state)` after every shared
render, and swaps it live when the platform changes. `update` may override shared fields.
`mount` gets the live-state slot in the **Device state** card; `mountSettings` gets the slot in
the **Configuration** card's platform-behaviour group.

## What ships

`catalogue.json` names every television this product models; the registry knows only the
packages present. A catalogued platform with no package is *derived* as not included —
nothing stores that state — and the API answers its id with 501 and `"reason": "n/a"`.

`tests/test_public_build.py` fails when a shipped file carries a real LAN or hardware
address or key material, or when a shipped module names a platform this build does not
include.

## Notes

- Platform is runtime state (like host and port), not a `Settings` field. Only the
  `Settings` block is ever persisted, and only when the user presses **Save settings**.
- Access modes are platform data: a platform declares the `AccessMode` values its firmware
  offers, and shared code only reads them. A platform with one mode hides the selector.
- Every protocol is one `ProtocolSpec` in the descriptor plus one binding in the capture a
  profile references. Its on/off state is `Settings.protocols[<id>]`, and `common/` starts and stops it
  from a `ProtocolListener` the platform registers by id — one switch never moves another.
- A binding says which port the capture used, which protocol is primary, whether the device
  ships with it off, and whether the device opens it lazily (`warm_up`).
- SSDP answers a tuple of `SSDPAdvertisement` records, so a device running several discovery
  stacks describes each one as capture data. One stack is the default and needs no extra keys.
- A selectable capture carries discovery evidence, or states why it has none in
  `platform.discovery`: `none` when the set was searched and answered nothing, `pending` when
  the answer is still to be recorded off the set. `pending` is a TODO, never an observation.
- Keyboard support is a `KeyboardSpec` on the descriptor plus captured profile data: the spec
  says how text reaches the device (a text API, or one `literal_prefix` keypress per character
  with its own `delete_key` and `enter_key`), while which field types exist is per-device
  capture published through `Core.set_content_types`. A platform that declares no keyboard
  keeps the old refusals and the **Keyboard** tile stays hidden. Shared code never names a
  remote key: `delete_key` and `enter_key` belong to one platform's key set — including a
  text prefix, which a keyboardless platform whose own wire makes such keys declares as
  `text_key_prefixes` so the refusal can say out of scope rather than unknown.
- How a firmware matches a key name is data too. `fold_key_case` says the set ignores case,
  and `Core.key_name` resolves what arrived to the declared spelling, so counters, held keys
  and key effects never split across two casings. A platform that has not been measured
  leaves it off rather than assuming.
- The registry discovers platforms from the packages under `platforms/`: a package that
  exports `PLATFORM` and `ADAPTER` is a platform, and the directory listing is the id list.
  `PlatformDescriptor.order` sets the selector order; the lowest is the build's default.
- Cross-cutting tests name no platform. They pick one by declared capability through
  `tests/support.py` (`TEXT_API`, `NO_KEYBOARD`, `LITERAL_KEYS`, `VOICE_STREAM`, …) and skip
  when a build has none. Two stub platforms under `tests/extra/` keep switch, text and voice
  machinery covered in a build that ships one television. Platform-specific wire facts belong
  in that platform's own test file.
- The product is the contract, built in three layers. `evidence/<capture-id>/` owns immutable
  ordered wire exchanges and raw payload/frame files. `common/ir.py` derives message structure,
  native scalar/container/null types, XML names/attributes/order/repetition and opaque binary.
  `contract.py` adds only typed facts evidence cannot prove: `PresenceClaim`, `ValueSetClaim`,
  `ConstraintClaim`, `SerializationClaim` and `BehaviorClaim`.
- Every curated claim owns its provenance: an exact capture exchange, a named live probe, or
  a client contract. Requiredness is semantic and manual; repetition across N captures never
  makes a field required. A required claim that a later capture violates is stale and fails CI.
- Value sets are written by hand and never inferred. A closed set rejects a new observed value;
  an open set accepts it as another observation. Constraints carry the observed violation when
  one exists. A claim on a path no capture carries fails the check, unless it is a field the
  emulator writes live (`PresenceClaim(scope="served")`).
- A handler returns `ReplyStyle.ok()` or raises `WireError`; it never builds a `web.Response`.
  Serialisation is platform data, so an observed oddity — `json.dumps` spacing, a `charset`, a
  crash page where a 404 belongs — is declared and reproduced, never normalised.
- HTTP routes and non-HTTP messages have stable `operation_id` values and are decorated on the
  function that actually dispatches or sends them. OpenAPI 3.2 is the HTTP projection; AsyncAPI
  3.1 is the WebSocket/MQTT projection. Both are deterministic exports of the common IR, never
  sources of truth and never inputs to the emulator. Where two ports answer the same request
  the OpenAPI export is one document per port (`report.openapi_documents`).
- A profile owns no raw response. Its schema-v3 `profile.json` references one local complete
  capture, maps replay names to exchanges, and lists the only runtime substitutions handlers
  may make. What is emulator-owned rather than measured — a token, a representative list, a
  block inherited from a sibling set — sits in its `runtime` object with its own provenance,
  never in a capture. An incomplete capture remains evidence but is never selectable. There is
  no dump entity: an unreferenced capture is the cheap evidence-only form.
- The emulator replays capture bytes, not schema-generated messages. Byte differences are
  permitted only at profile-declared runtime substitutions. Capture provenance lives in
  `evidence/<id>/capture.json`; claim provenance lives on each claim.
- What the emulator writes live into a replayed body is a `PresenceClaim(scope="served")`, and
  `tests/support.undeclared_live_paths` checks both directions against a real response: a path
  served but undeclared is a field a driver receives that no rendering of the contract
  mentions, and a declaration the handler stopped honouring is a claim that has gone stale.
- Writing a driver *against* the emulator (not changing it): `docs/writing-a-driver.md`,
  the committed specs in `docs/spec/`, `python -m tvemu.expect` and `tvemu-mcp`.
  `tools/render_docs.py` writes `docs/spec/`; never edit those files by hand.
- Counts and lists across televisions — the README's badges and television table, the
  request form's checkboxes — are generated from `catalogue.json` by `tools/render_docs.py`
  between `generated:` markers. Edit the catalogue, never the output, and do not write such
  a number in prose.
- A television is not called supported on the strength of tests we wrote. `docs/manual-validation.md`
  is the ledger of sessions with a real app; a session moves a behaviour to validated, observed
  or not exercised in that platform's guide, and a value that names a person or a session is
  never copied out of a log.
- Adding a platform: `README.md#adding-a-television`; one page per TV in `docs/platforms/`.
- Gates: `python -m compileall -q src`, `python -m unittest discover -s tests`,
  `node --check` on changed JS (as `.mjs`), `python -m build`,
  `python -m tvemu.conformance --all --gate`. Before committing a new capture, also
  `tvemu --contract <id> --check`.
- `python -m tvemu.conformance` replays each profile's captured client traffic through the
  real listeners and compares the answers byte for byte. A replay it cannot run is listed
  as uncovered with its reason, never skipped. What a television needs for it -- WebSocket
  channels, client-owned values recomputed per session, exchanges declared `stateful` or
  `transcribed`, `COVERAGE = "complete"` -- lives in `platforms/<id>/conformance/`.
