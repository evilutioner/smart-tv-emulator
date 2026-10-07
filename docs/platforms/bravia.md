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

## What a driver gets wrong here

A few of the firmware behaviours the emulator reproduces. The full guide covers every
message, pairing step and refusal, each one tied to the capture it came from.

- The 2015 set speaks **Remote v1 only**; a v2 client is disconnected without a word.
- Volume is an **integer on the wire** where a common client expects a string, so it cannot read it.
- **Sending the auth cookie back to registration revokes it** — exactly what a cookie jar does.
- Some Simple IP Control queries are **never answered**; a client waiting for them waits forever.
- The 2016 set **can be found but not controlled** — a driver must explain that, not time out.

## What the emulator lets you test

- [x] PIN registration, a wrong PIN, and returning without one
- [x] Which methods need the cookie, as the set decides it
- [x] Volume, mute, power, inputs and launches as live state across all three control paths
- [x] Remote v1 pairing, keys and intents
- [x] Simple IP Control frames, refusals and change notifications
- [x] The discoverable-but-uncontrollable case

## Get access

Commercial licence, private access to the emulator, or a driver built for your app:
[get in touch](https://marchik.dev) and say what you are building.
