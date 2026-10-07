# Metz Classic

> **N/A in this build.** Written and tested against the official MetzRemote app; the
> emulator, its session and the full driver guide are available on request —
> [ask about Metz Classic](https://marchik.dev).

The Remote Control Receiver that Metz Classic sets expose to the MetzRemote app: SSDP
discovery, a UPnP description and a SOAP control URL for keys and text. Unlike every other
platform here, **no Metz television was measured** — the behaviour is what the official app
was seen to need, cross-checked against the protocol library it ships.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| RCRService SOAP | HTTP 49200 | description, SCPD, keys, text |
| SSDP | UDP 1900 | the `upnp:rootdevice` search |
| MECA-I | TCP 1938 | not emulated: channel lists, EPG, timers |

## Modelled devices

- **Metz Classic (modelled)** — from the MetzRemote iOS app; no set measured

## What a driver gets wrong here

- The app lists a set **only for one exact deviceType**; any other description is fetched and silently dropped.
- A dropped device is **remembered by its UDN**, so fixing the description alone does not make it appear.
- Text is **one SOAP call carrying the whole string**, not one keypress per character.
- Channels, EPG and the Functions tab are **a second, binary protocol** on another port, not SOAP.

## What the emulator lets you test

- [x] Discovery exactly as the official app performs it
- [x] Every remote key the app sends, by its Metz key code
- [x] Text entry from the app's keyboard
- [ ] Channel lists, EPG and timers (MECA-I, not emulated)

## Get access

Commercial licence, private access to the emulator, or a driver built for your app:
[get in touch](https://marchik.dev) and say what you are building.
