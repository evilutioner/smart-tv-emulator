# Android TV / Google TV

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about Android TV / Google TV](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml).

Android TV Remote Service v2 over mutual TLS with Polo pairing, plus DIAL, Google Cast launch
validation and AirPlay identity. Six sets are captured, from a Xiaomi TV to HDMI dongles, and
each profile exposes only the protocols and ports its set did.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| Remote v2 | mutual TLS 6466 | keys, IME text, app links, voice, power, volume, pings |
| Pairing v2 (Polo) | mutual TLS 6467 | six-character on-screen code, client certificate |
| Wake service | mutual TLS 6465 | the port the Google TV app uses when it is advertised |
| DIAL / Cast HTTP | HTTP 8008 (56790 on MediaTek sets) | description, app state and launch |
| Google Cast | TLS 8009 | receiver status and launch |
| Cast setup | HTTPS 8443 | setup identity |
| AirPlay | HTTP 7000 | read-only identity |
| SSDP · Bonjour | UDP 1900 · mDNS 5353 | `_androidtvremote2`, `_googlecast`, `_airplay` |

## Captured devices

- **Xiaomi MiTV-MOEU0** — Android 14
- **TCL Android TV** — C06, AR2101, Android 11
- **KIVI (MediaTek)** — two captures
- **Google Chromecast HD** — Google TV, Android 14
- **Nokia Streaming Stick 800** — SEI Robotics, Android 11

## What a driver gets wrong here

A few of the firmware behaviours the emulator reproduces. The full guide covers every
message, pairing step and refusal, each one tied to the capture it came from.

- The **Chromecast owns no volume**: volume keys produce no frame at all, however the level moves.
- The Nokia stick reports volume **only over Cast**, on a 15-step scale, as widened floats.
- On the dongles **every error frame is followed by the set closing the connection**; a key sent too early gets no answer.
- The MediaTek sets run **no Cast receiver** and serve DIAL on a different port and path.
- After a pairing error the TLS connection **stays open but ignores everything**.

## What the emulator lets you test

- [x] Discovery over Bonjour and SSDP with each set's own records
- [x] Polo pairing, wrong codes and certificate authorization
- [x] Keys, long presses, text both ways, app links and voice sessions
- [x] Power, volume and mute pushed back to every client
- [x] Keep-alive pings and the session closing when they go unanswered
- [x] DIAL and Cast launches recorded with their payloads

## Support and validation

Android TV is **supported for the official Google TV app** (iOS **3.33.00001**) on the
Chromecast HD and Xiaomi profiles: pairing, the remote buttons and the microphone, validated by
hand on **2026-09-30**. Text entry and application links were not exercised. The
[manual validation ledger](../manual-validation.md) has the row; the full guide lists each
behaviour.

## Get access

Commercial licence, private access to the emulator, or a driver built for your app:
[open a request](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml) and say what you are building.
