# Samsung Tizen

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about Samsung Tizen](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml).

A Samsung Smart TV running Tizen: the `samsung.remote.control` WebSocket over TLS, the
unauthenticated device API a client polls for power, and the DIAL receiver description. Three
physical sets are captured.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| `samsung.remote.control` | WSS 8002 | Allow prompt and token, keys, text, app list, launch |
| Device API | HTTP 8001 | identity and power, REST app launch |
| DIAL description | HTTP 7678 | receiver description with Samsung's extensions |

## Captured devices

- **Samsung UE65U8072F** — 25_KSUE_UB
- **Samsung UE55DU7172U** — 24_KANTSU2E_UB
- **Samsung UE43CU7172U** — 23_KSUE_UB_T09

## What a driver gets wrong here

A few of the firmware behaviours the emulator reproduces. The full guide covers every
message, pairing step and refusal, each one tied to the capture it came from.

- There is **no pairing message**: everything follows from which event the set sends first.
- The token is a **string of exactly eight digits** — a number breaks common clients.
- A refused prompt and an **expired** prompt are **different events** with different meanings.
- Client ids look like UUIDs but **are not always valid UUIDs**; a strict parser fails now and then.
- "Off" has no field of its own — **the request simply fails**.

## What the emulator lets you test

- [x] The Allow prompt: accept, deny, timeout, and returning with a token
- [x] Keys with click, press and release, and text input
- [x] The installed-application list and both ways to launch
- [x] Power on, standby and off as a client sees them
- [x] Revoking every token on disconnect

## Get access

Commercial licence, private access to the emulator, or a driver built for your app:
[open a request](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml) and say what you are building.
