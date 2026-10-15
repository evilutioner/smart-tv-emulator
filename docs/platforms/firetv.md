# Fire TV

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about Fire TV](https://marchik.dev).

Everything a Fire TV remote app speaks: DIAL discovery and launch, the Turnstile control API over
TLS with on-screen PIN pairing, and — on Fire OS — Bonjour and the legacy ADB shell. Three
physical sticks are captured; every difference between them is capture data.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| Turnstile — control API, PIN pairing | HTTPS 8080 | pairing, keys, media, text, voice start/stop, app launch |
| Voice audio — WebSocket | WSS 9090, every stick | frames counted and logged, format detected; client half only |
| ADB — legacy shell | TCP 5555, off by default | public-key authorization, key events, launches |
| DIAL | HTTP 8009 | app state and launch |
| UPnP `dd.xml` | HTTP 60000 | device description |
| SSDP | UDP 1900 | the DIAL search target |
| Bonjour `_amzn-wplay._tcp` | mDNS 5353 | WhisperPlay registration, Fire OS only |

## Captured devices

- **Fire TV Stick (Vega)** — AFTCA002
- **Fire TV Stick (Fire OS)** — AFTMA08C15, Fire OS 8.1.8.2
- **Fire TV Stick 4K Max** — AFTKA, Fire OS; ADB off on the captured unit

## What the emulator reproduces

Behaviours of the captured firmware the emulator reproduces, named here without their
detail. The full guide gives each one, tied to the capture it came from.

- **A cold start**: the control port as it is right after the stick boots.
- **PIN pairing**, wrong PINs and repeated PINs, answered as the stick answers them.
- **Every authorization failure** with the stick's own status and message.
- **ADB key approval and refusal**, with ADB off by default.
- **Unknown requests**, refused with the stick's own status.

## What the emulator lets you test

- [x] Discovery over SSDP and Bonjour, with the stick's own records
- [x] The DIAL warm-up before the control port opens
- [x] PIN pairing, including a wrong PIN and re-pairing
- [x] Keys, media keys, text, voice start/stop and application launch
- [x] ADB key approval and refusal, shell key events and launch commands
- [x] Each protocol switched off on its own, and a bind error on one port only

## Support and validation

Fire TV is **supported** on the Vega and Fire OS 8 sticks for everything the official app does
(Amazon Fire TV for iOS **4.8.0**), validated by hand on **2026-09-29**: discovery, pairing,
remote and media keys, text, the microphone, and application and title launches. The one gap:
the channel up and down buttons were never told apart from a swipe. The
[manual validation ledger](../manual-validation.md) has the row; the full guide lists each
behaviour.

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
