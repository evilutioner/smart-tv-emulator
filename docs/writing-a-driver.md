# Writing a driver against the emulator

For a person or a coding agent writing the code that discovers, pairs with and controls a
television. The emulator is the other end of the wire: it answers as the captured set did,
and it tells you exactly what your code sent. Work in small steps and check each one against
the event log rather than against your own reading of the code.

## 1. Read the contract before writing code

| What | Where | Why |
|---|---|---|
| The HTTP surface | `docs/spec/<id>.openapi.json` (or `tvemu --api-map <id> --format openapi`) | Every route, with a response schema wherever a capture showed one |
| The message surface | `docs/spec/<id>.asyncapi.json` (or `--format asyncapi`) | WebSocket and MQTT messages, both directions |
| What a capture cannot prove | `tvemu --contract <id>` | Which fields are required, which value sets are closed, the quirks |
| The platform guide | `docs/platforms/<id>.md` | Pairing, refusals and access modes, in prose |

Two rules that save most of the debugging:

- **A field is required only when a claim says so.** Seeing it in every capture does not make
  it required; parse the ones the contract marks optional as optional.
- **A closed value set means exactly those values.** An open one means more will turn up in the
  field, so keep a fallback branch.

## 2. Start the emulator

```sh
tvemu --platform <id> --bind 127.0.0.1 --no-browser
```

Loopback is enough for a driver running on the same machine; use a LAN address and a phone for
discovery end to end. The dashboard is at <http://127.0.0.1:8888>, and every action on it is
also in the management API (`GET /api/v1/openapi.json`).

## 3. Build it in this order, and check each step

1. **Discovery** — find the set, read its description.
2. **Pairing** — the on-screen PIN, prompt or code appears on the dashboard, and so do refusals.
3. **Keys** — one key, then held keys, then the whole key set.
4. **Text** — focus the field from the dashboard (or `POST /api/v1/actions/field`) first.
5. **Launch** — the launch card shows the exact id and payload that arrived.
6. **Failure paths** — wrong PIN, disconnect (`POST /api/v1/actions/disconnect`), protocol
   switched off, access mode restricted. A driver is finished when these are handled too.

After each step, clear the log, run your code, and check what arrived:

```sh
curl -s -X POST -H 'Content-Type: application/json' -d '{}' \
  http://127.0.0.1:8888/api/v1/actions/clear-log
# … run your driver …
python -m tvemu.expect my-step.json
```

A scenario lists the events you expect, in order, and the ones that must not appear:

```json
{"description": "one key after pairing",
 "expect": [{"kind": "command", "operation": "keypress/Home", "status": 200}],
 "forbid": [{"status": 403}]}
```

A pattern matches an event when every field it names is equal; a string ending in `*` is a
prefix. When a check fails it prints the unmet expectation and the last events it looked at,
which is usually the answer: a refusal with its reason in `detail`, a key under a different
name, or nothing at all because the request went to the wrong port.

## 4. With an agent: the MCP server

`tvemu-mcp` exposes the same loop to a coding agent over the Model Context Protocol:

```sh
claude mcp add tvemu -- tvemu-mcp
```

| Tool | Use |
|---|---|
| `state` | Platform, captured device, address, protocols and ports, pairing, keys, power, volume |
| `api_map`, `contract` | The surface and the claims, without leaving the conversation |
| `clear_log`, `events`, `expect` | Start clean, read what arrived, assert on it |
| `reset`, `disconnect`, `configure`, `switch_platform` | Move the set into the state a test needs |
| `focus_field`, `type_text` | Play the viewer at the set |

A useful instruction for the agent: *"Before changing the driver, read `contract`. After every
change, `clear_log`, run the app, then `expect` the events the change should produce. Do not
report a step done until `expect` passes."*

## 5. In CI

See [`docs/ci.md`](ci.md): the same scenarios, run on every push.

A worked example for one television, with its spec, a twenty-line client and a scenario, is
in the [Roku guide](platforms/roku.md#writing-a-roku-driver).
