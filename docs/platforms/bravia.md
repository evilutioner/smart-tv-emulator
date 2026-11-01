# Sony BRAVIA

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about Sony BRAVIA](https://marchik.dev).

Sony sets a client may drive in two unrelated ways: **Sony IP control** (ScalarWebAPI JSON-RPC,
IRCC and Simple IP Control) and **Android TV Remote** (v1 on the older set, v2 on the 2023 one).
Three sets were captured across that range — including one that can be discovered but not
controlled, and one that was only read as an unregistered client.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| ScalarWebAPI | HTTP 80 | JSON-RPC: identity, power, volume, inputs, apps; PIN registration |
| IRCC | HTTP 80 | IR codes over SOAP |
| Simple IP Control | TCP 20060 | fixed-size frames, notifications to every connection |
| Android TV Remote v1 | TLS 6466 · 6467 | pairing with a four-symbol code, keys and intents |
| Android TV Remote v2 | TLS 6466 · 6467 | pairing with a six-character code, keys; its answers are inherited, not measured |
| SSDP · UPnP · DIAL · Bonjour | UDP 1900 and per-set ports | four stacks on one set, two on the other |

## Captured devices

- **Sony KDL-55W807C** — BRAVIA 2015, Android 7.0
- **Sony KDL-32WD600** — BRAVIA 2016, Linux; discoverable, no remote protocol
- **Sony XR-65A80L** — BRAVIA 2023, Google TV; read in standby as an unregistered client, the
  authenticated answers and Remote v2 inherited from other captures

## What the emulator reproduces

Behaviours of the captured firmware the emulator reproduces, named here without their
detail. The full guide gives each one, tied to the capture it came from.

- **Two generations**: the 2015 set's remote protocol, and the 2016 set that can be found but not controlled.
- **PIN registration and the auth cookie's lifetime**, as the set handles them.
- **Simple IP Control** as the set answers it, silences included.
- **Volume** as the set reports it.
- **A set read only as an unregistered client**: what it answers without the cookie is its own,
  and every other answer says in the profile that it is borrowed.

## What the emulator lets you test

- [x] PIN registration, a wrong PIN, and returning without one
- [x] Which methods need the cookie, as the set decides it
- [x] Volume, mute, power, inputs and launches as live state across all three control paths
- [x] Remote v1 pairing, keys and intents
- [x] Simple IP Control frames, refusals and change notifications
- [x] The discoverable-but-uncontrollable case
- [x] Remote v2 pairing and keys on the 2023 set, against inherited answers

## Support and validation

Google's **Android TV Remote Control for Android 1.1.0** drove the KDL-55W807C profile over
Remote v1 on **2026-10-21**: Bonjour discovery, pairing with the code on screen, the D-pad, OK,
Back, Home, Play and volume keys, and a connection that stays up while idle. Text entry, which
this app sends through the set's input method, is not emulated; voice, the touchpad and app
launches were not exercised. The app does not pair again by itself once a set has forgotten it.
The [manual validation ledger](../manual-validation.md) has the row.

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
