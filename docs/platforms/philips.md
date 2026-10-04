# Philips JointSpace

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about Philips JointSpace](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml).

JointSpace 6.1 on a Linux-based Philips set: PIN pairing, Digest authentication, the control
API, a UPnP MediaRenderer description and the Cast wake endpoint. The interesting thing about
this set is how much it refuses — in three different ways that mean three different things.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| JointSpace v6 | HTTPS 1926 | PIN pairing, Digest auth, control API |
| JointSpace v6 | HTTP 1925 | version probes, long-poll state |
| UPnP MediaRenderer | HTTP 49152 | device description |
| Cast wake | HTTP 8008 | the wake endpoint before a power request |
| SSDP · Bonjour | UDP 1900 · mDNS 5353 | `_philipstv_rpc._tcp`, `_philipstv_s_rpc._tcp` |

## Captured devices

- **Philips 32PHS6000/12** — JointSpace 6.1

## What a driver gets wrong here

A few of the firmware behaviours the emulator reproduces. The full guide covers every
message, pairing step and refusal, each one tied to the capture it came from.

- The power-state route **answers 404** even though the long poll reports power in the same session.
- Some routes answer **403 with valid credentials** — it is not a pairing failure.
- App launch is **405 on a Linux set**; the identity probe tells you which generation you are talking to.
- **Volume counts to 60, not 100.** A driver that assumes a percentage sets roughly half.
- There is **no power-on key**; the set is woken another way.

## What the emulator lets you test

- [x] Discovery, API version detection and PIN pairing
- [x] Digest-authenticated requests and credential reconnects
- [x] Every refusal the set gives, each with its own meaning
- [x] Keys, text entry, volume and mute, channels and Ambilight state
- [x] The long-poll state bundle with live values
- [x] Wake, an incorrect PIN and revoked credentials

## Support and validation

The official **Philips TV Remote** app (iOS build 20979) was validated against the emulator
by hand on 2026-09-30: discovery, PIN pairing, the remote buttons and the state long poll.
The [manual validation ledger](../manual-validation.md) has the row; the full guide lists each
behaviour.

## Get access

Commercial licence, private access to the emulator, or a driver built for your app:
[open a request](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml) and say what you are building.
