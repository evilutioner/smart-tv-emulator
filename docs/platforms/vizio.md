# Vizio SmartCast

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about Vizio SmartCast](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml).

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

## What a driver gets wrong here

A few of the firmware behaviours the emulator reproduces. The full guide covers every
message, pairing step and refusal, each one tied to the capture it came from.

- Success and failure travel in the **JSON body, not the HTTP status** — control routes answer 200 either way.
- An unknown route is **a 500 HTML crash page**, never a 404 — a driver that parses every answer as JSON breaks.
- The **community-documented app launch crashes** this firmware; it wants a different envelope.
- Pairing answers and every other route use **two different JSON serialisations**.

## What the emulator lets you test

- [x] Discovery and the device description
- [x] PIN pairing, a wrong PIN, cancellation and the auth token
- [x] Which routes need pairing and which never do
- [x] Remote keys, including unknown codes
- [x] Application launch, including the envelope that crashes
- [x] Disconnect clearing every token

## Get access

Commercial licence, private access to the emulator, or a driver built for your app:
[open a request](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml) and say what you are building.
