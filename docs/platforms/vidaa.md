# VIDAA (Hisense)

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about VIDAA (Hisense)](https://marchik.dev).

On a VIDAA set **the television is an MQTT broker**, behind TLS, and a remote app is just
another MQTT client. Captured end to end from one physical Hisense set, including a live TV
panel for the tuner.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| VIDAA MQTT | MQTT over TLS 36669 | PIN pairing, access and refresh tokens, keys, apps, sources, volume, state |
| UPnP MediaRenderer | HTTP 18400 | the description a client probes for its capabilities |

## Captured devices

- **Hisense 32A3HE** — VIDAA U7, firmware V0007.09.60U.Q0609

## What the emulator reproduces

Behaviours of the captured firmware the emulator reproduces, named here without their
detail. The full guide gives each one, tied to the capture it came from.

- **No discovery**: the set answers no SSDP and no mDNS, so a client reaches it by address.
- **Pairing for three firmware families**, each as its own captures show it.
- **Subscription refusals**, topic by topic, as the broker sends them.
- **No channel list**, whatever the client asks for.

## What the emulator lets you test

- [x] Connecting with the right and the wrong credential family
- [x] PIN pairing, tokens, reconnecting with a token and refreshing it
- [x] Subscription refusals exactly as the set gives them
- [x] Keys, volume, source changes and the state broadcast
- [x] Live TV channel changes on the tuner source
- [x] Application launches with their exact payloads

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
