# Contributing

The emulator is one Python process on aiohttp, with no build step. This page covers changing
it. [Adding your television](docs/adding-your-television.md) covers sending a capture, and
[Architecture](docs/architecture.md) explains how the parts fit together.

## Layout

```text
src/tvemu/
  core.py            shared state, settings, events, command results
  runtime.py         platform lifecycle and switching
  control.py         the local /api/v1 management API and the dashboard server
  expect.py          scenario check over the event log (python -m tvemu.expect)
  mcp.py             stdio MCP server over /api/v1 (tvemu-mcp)
  clients/           runs open-source client libraries against the emulator
  conformance/       byte-for-byte replay of captured client traffic
  platforms/
    base.py          PlatformDescriptor and the adapter contract
    catalogue.json   every television the project models, with its README row
    common/          shared adapter, evidence, contract, SSDP and mDNS responders
    <id>/            one television: wire protocol, descriptor, contract and evidence
  web/               the dashboard; web/platforms/<id>.js adds per-television UI
```

## Shared code names no television

Anything specific to one television lives in `platforms/<id>/` or `web/platforms/<id>.js`.
Shared code reads what a television declares in its `PlatformDescriptor` (protocols, access
modes, keyboard, key effects) and does not branch on a platform id or a profile id. The
differences between two devices of the same brand are capture and profile data.
`catalogue.json` is the one shared file that names televisions, because it is data.

Device state follows the same rule. Power, volume and mute change only through the key-effect
table a platform declares, applied by `Core.apply`.

Tests that are not about one television pick a platform by what it declares, through
`tests/support.py`, and skip when this checkout has none. The stub platforms in
`tests/extra/` cover switching, text and voice when only one television is present.

## Evidence, contract, replay

- `evidence/<capture-id>/` holds what a real device sent, in order, unchanged.
- `contract.py` adds what a capture cannot show, such as which fields are required or which
  values are allowed. Each claim states where it came from.
- `profiles/<device-id>/profile.json` makes a complete capture selectable, and lists the only
  places the emulator may change the replayed bytes at runtime.

Handlers answer with `ReplyStyle.ok()` or raise `WireError`, so a device's serialisation
oddities are declared and reproduced rather than normalised.

## Generated files

`docs/spec/`, the television tables in `README.md` and `docs/televisions.md`, the test reports
in `docs/tests/` and the client pages in `docs/clients/` are generated. To change them, edit
`catalogue.json`, `contract.py` or the code, then run the generator:

```sh
python tools/render_docs.py
python tools/test_reports.py
```

## Checks

```sh
python -m compileall -q src
python -m unittest discover -s tests
python -m tvemu.conformance --all --gate
python -m build
```

Run `node --check` on any JavaScript you changed, saved with a `.mjs` suffix. A new capture
should also pass `tvemu --contract <id> --check`. If you changed a television that has
declared clients, run `python -m tvemu.clients run <id>/<client>`; this downloads the client.

## Pull requests

Licence terms for submitted captures are not written yet, so get in touch through the contact
link in the issue chooser before sending a capture. Fixes to the shared code, the dashboard and
the Roku adapter are welcome as pull requests. They are Apache-2.0, like the rest of this
repository.
