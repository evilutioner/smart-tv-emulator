# Fire TV

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about Fire TV](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml).

Everything a Fire TV remote app speaks: DIAL discovery and launch, the Turnstile control API over
TLS with on-screen PIN pairing, and — on Fire OS — Bonjour and the legacy ADB shell. Two
physical sticks are modelled; every difference between them is capture data.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| Turnstile — control API, PIN pairing | HTTPS 8080 | pairing, keys, media, text, voice start/stop, app launch |
| Voice audio — WebSocket | WSS 9090, both sticks | frames counted and logged, format detected; client half only |
| ADB — legacy shell | TCP 5555, off by default | public-key authorization, key events, launches |
| DIAL | HTTP 8009 | app state and launch |
| UPnP `dd.xml` | HTTP 60000 | device description |
| SSDP | UDP 1900 | the DIAL search target |
| Bonjour `_amzn-wplay._tcp` | mDNS 5353 | WhisperPlay registration, Fire OS only |

## Captured devices

- **Fire TV Stick (Vega)** — AFTCA002
- **Fire TV Stick (Fire OS)** — AFTMA08C15, Fire OS 8.1.8.2

## What a driver gets wrong here

A few of the firmware behaviours the emulator reproduces. The full guide covers every
message, pairing step and refusal, each one tied to the capture it came from.

- The control port is **closed at boot** and opens only after a DIAL launch — probe it cold and the stick looks dead.
- A **wrong PIN is answered 200**, not 403, and a new PIN silently invalidates the previous one.
- Authorization failures come in a fixed order, each with its own message, so the message tells you what is missing.
- A **declined ADB key leaves the connection open with no reply**, as the stick does.
- An unknown URI is **403, never 404**.

## What the emulator lets you test

- [x] Discovery over SSDP and Bonjour, with the stick's own records
- [x] The DIAL warm-up before the control port opens
- [x] PIN pairing, including a wrong PIN and re-pairing
- [x] Keys, media keys, text, voice start/stop and application launch
- [x] ADB key approval and refusal, shell key events and launch commands
- [x] Each protocol switched off on its own, and a bind error on one port only

## Support and validation

Fire TV is **fully supported** on both sticks for everything the official app does
(Amazon Fire TV for iOS **4.8.0**), validated by hand on **2026-09-29**: discovery, pairing,
remote and media keys, text, the microphone, and application and title launches. The channel
up and down buttons were never told apart from a swipe. The
[manual validation ledger](../manual-validation.md) has the row; the full guide lists each
behaviour.

## Get access

Commercial licence, private access to the emulator, or a driver built for your app:
[open a request](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml) and say what you are building.
