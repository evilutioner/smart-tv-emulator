# Dashboard and management API

Both are served on `127.0.0.1:8888` by default, independent of the television being
emulated; the television itself answers on the LAN address.

## The dashboard

![The Smart TV Emulator dashboard emulating a Roku Streaming Stick 4K](images/dashboard.png)

- **Configuration** — the emulated television and the captured device it wears; the access
  modes that firmware offers; one switch per protocol the captured device exposes, with its
  wire family, port or multicast group, and live state (`listening`, `off`, `armed`, or the
  bind error that stopped it); forced disconnect and state reset.
- **Device state** — advertised address, connections, last button, button indicators and
  counters, power, volume, mute, keyboard and voice state, and the application catalogue plus
  the last observed launch.
- **Event log** — requests, transports, responses, rejection reasons, forced disconnects,
  resets, and JSONL export.

<img alt="One switch per protocol, each with its port and live state" src="images/protocols.png" width="342">

Each protocol starts and stops on its own: switching one off closes only its port and drops
only its sessions, and one that cannot bind is reported in its own row while the rest keep
serving. Only the primary protocol failing to bind is fatal.

![The event log, showing each request with its transport, response and detail](images/event-log.png)

## Management API

Mutations require `application/json`; browser requests with a foreign `Origin` or `Host` are
rejected.

| Method | Path | Result |
|---|---|---|
| GET | `/api/v1/state` | Active television, device, settings and recent events |
| PATCH | `/api/v1/settings` | Apply a validated partial settings update |
| POST | `/api/v1/platform` | Switch the emulated television; body `{"platform": "<id>"}` |
| GET / WS | `/api/v1/events` | Initial and updated full snapshots |
| GET | `/api/v1/events/export` | Latest 500 events as JSONL |
| POST | `/api/v1/settings/save` | Persist current settings; body `{}` |
| POST | `/api/v1/actions/disconnect` | Terminate active clients; body `{}` |
| POST | `/api/v1/actions/reset` | Reset simulated device state; body `{}` |
| POST | `/api/v1/actions/clear-log` | Clear event entries; body `{}` |
| POST | `/api/v1/actions/text` | Type into the focused field |
| POST | `/api/v1/actions/field` | Focus or blur a field on the emulated device |
| GET | `/api/v1/openapi.json` | The declared shape of this API, including the snapshot |

Every event carries a monotonic id, UTC timestamp, kind, transport, client address,
operation, status, details and an optional protocol request id. Asking to switch to a
television this build does not include answers **501** with a machine-readable
`"reason": "n/a"`.

The same API backs `python -m tvemu.expect` and the `tvemu-mcp` server; see
[Writing a driver](writing-a-driver.md) and [CI](ci.md).
