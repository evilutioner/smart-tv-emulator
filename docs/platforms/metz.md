# Metz Classic

> **N/A in this build.** Modelled from the vendor's remote app; the
> emulator, its session and the full driver guide are available on request —
> [ask about Metz Classic](https://marchik.dev).

The Remote Control Receiver that Metz Classic sets expose to the vendor's remote app: SSDP
discovery, a UPnP description and a SOAP control service for keys and text. As with the other
platforms marked 📱 Modelled, **no Metz television was measured**: the behaviour is what the
vendor's app was seen to send and to need.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| Remote Control Receiver (UPnP SOAP) | HTTP 49200 | description, service description, keys, text |
| SSDP | UDP 1900 | the app's search |
| MECA-I | TCP 1938 | not emulated: channel lists, EPG, timers |

## Modelled devices

- **Metz Classic (modelled)** — from the vendor's iOS remote app; no set measured

## What the emulator reproduces

- **The app lists a set only for one exact device type**; any other is silently dropped.
- **A dropped device is remembered**, so fixing its description alone does not bring it back.
- **Text is sent as a whole string**, not one keypress per character.

## What the emulator lets you test

- [x] Discovery exactly as the official app performs it
- [x] Every remote key the app sends
- [x] Text entry from the app's keyboard
- [ ] Channel lists, EPG and timers (MECA-I, not emulated)

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
