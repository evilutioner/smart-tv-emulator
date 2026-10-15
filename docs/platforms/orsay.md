# Samsung Smart TV (2014–15)

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about Samsung Smart TV (2014–15)](https://marchik.dev).

The Samsung generation before Tizen took over the remote: a four-digit PIN over an
encrypted key exchange, then remote keys as AES-encrypted events on a Socket.IO companion
channel. One physical set was recorded end to end, pairing included.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| Companion channel | Socket.IO 0.9 on 8000 | encrypted key events and their answers, heartbeat |
| SPC pairing · DIAL | HTTP 8080 | PIN page and the three-step key exchange |
| Multiscreen API | HTTP 8001 | identity, application probe, launch and close |
| UPnP | HTTP 7676 | the four device descriptions |
| SSDP ×4 stacks | UDP 1900 | every search the set answers |

## Captured devices

- **Samsung UE48H6200** — H series, 14_X14, MSF 2.0.24

## What the emulator reproduces

Behaviours of the captured firmware the emulator reproduces, named here without their
detail. The full guide gives each one, tied to the capture it came from.

- **Frames the set ignores** stay unanswered rather than refused.
- **DIAL as the set serves it**, faults included.
- **PIN pairing** as the set answers it.
- **The application probe**, reporting what the set reports.

## What the emulator lets you test

- [x] The PIN page, the full key exchange and the issued session
- [x] Encrypted key events with click, press and release
- [x] Silence for undecryptable frames and unknown sessions
- [x] Application probes and launches
- [x] A key that survives its socket, and Disconnect forgetting every key

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
