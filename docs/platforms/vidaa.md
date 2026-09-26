# VIDAA (Hisense)

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about VIDAA (Hisense)](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml).

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

## What a driver gets wrong here

A few of the firmware behaviours the emulator reproduces. The full guide covers every
message, pairing step and refusal, each one tied to the capture it came from.

- **There is no discovery.** The set answers no SSDP and no mDNS; a client reaches it by address.
- Credentials are **derived, not stored**, and three firmware families accept three different derivations.
- A capability block hidden in the **UPnP `modelDescription`** tells a client which one to use.
- The broker refuses **wildcards, other clients' topics and unknown topics**, topic by topic, inside an otherwise granted subscription.
- The firmware serves **no channel list** at all, whatever the client asks for.

## What the emulator lets you test

- [x] Connecting with the right and the wrong credential family
- [x] PIN pairing, tokens, reconnecting with a token and refreshing it
- [x] Subscription refusals exactly as the set gives them
- [x] Keys, volume, source changes and the state broadcast
- [x] Live TV channel changes on the tuner source
- [x] Application launches with their exact payloads

## Get access

Commercial licence, private access to the emulator, or a driver built for your app:
[open a request](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml) and say what you are building.
