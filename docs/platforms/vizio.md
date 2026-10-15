# Vizio SmartCast

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about Vizio SmartCast](https://marchik.dev).

The local SmartCast REST API over HTTPS and its DIAL/SSDP discovery, captured from one physical
set. Every answer, error shapes included, was captured or probed live rather than taken from
community documentation — which is out of date for this firmware.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| SmartCast REST | HTTPS 7345 | PIN pairing, device state, keys, app launch |
| UPnP `dd.xml` | HTTP 56790 | DIAL device description |
| SSDP | UDP 1900 | the DIAL search target |

## Captured devices

- **Vizio D24f-J09** — firmware 3.3.3-2538.0001

## What the emulator reproduces

Behaviours of the captured firmware the emulator reproduces, named here without their
detail. The full guide gives each one, tied to the capture it came from.

- **Results and errors** in the set's own envelopes.
- **Unknown routes**, answered as the firmware answers them.
- **App launch**, in the form this firmware accepts and the form it refuses.
- **Pairing and control answers**, each serialised exactly as captured.

## What the emulator lets you test

- [x] Discovery and the device description
- [x] PIN pairing, a wrong PIN, cancellation and the auth token
- [x] Which routes need pairing and which never do
- [x] Remote keys, including unknown codes
- [x] Application launch, including the envelope that crashes
- [x] Disconnect clearing every token

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
