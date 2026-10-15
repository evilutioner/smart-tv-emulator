# Sony BRAVIA

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about Sony BRAVIA](https://marchik.dev).

Sony sets a client may drive in two unrelated ways: **Sony IP control** (ScalarWebAPI JSON-RPC,
IRCC and Simple IP Control) and **Android TV Remote v1**. Two sets were captured at the two ends
of that range — including one that can be discovered but not controlled.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| ScalarWebAPI | HTTP 80 | JSON-RPC: identity, power, volume, inputs, apps; PIN registration |
| IRCC | HTTP 80 | IR codes over SOAP |
| Simple IP Control | TCP 20060 | fixed-size frames, notifications to every connection |
| Android TV Remote v1 | TLS 6466 · 6467 | pairing with a four-symbol code, keys and intents |
| SSDP · UPnP · DIAL · Bonjour | UDP 1900 and per-set ports | four stacks on one set, two on the other |

## Captured devices

- **Sony KDL-55W807C** — BRAVIA 2015, Android 7.0
- **Sony KDL-32WD600** — BRAVIA 2016, Linux; discoverable, no remote protocol

## What the emulator reproduces

Behaviours of the captured firmware the emulator reproduces, named here without their
detail. The full guide gives each one, tied to the capture it came from.

- **Two generations**: the 2015 set's remote protocol, and the 2016 set that can be found but not controlled.
- **PIN registration and the auth cookie's lifetime**, as the set handles them.
- **Simple IP Control** as the set answers it, silences included.
- **Volume** as the set reports it.

## What the emulator lets you test

- [x] PIN registration, a wrong PIN, and returning without one
- [x] Which methods need the cookie, as the set decides it
- [x] Volume, mute, power, inputs and launches as live state across all three control paths
- [x] Remote v1 pairing, keys and intents
- [x] Simple IP Control frames, refusals and change notifications
- [x] The discoverable-but-uncontrollable case

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
