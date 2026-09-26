# Samsung Smart TV (2014–15)

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about Samsung Smart TV (2014–15)](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml).

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

## What a driver gets wrong here

A few of the firmware behaviours the emulator reproduces. The full guide covers every
message, pairing step and refusal, each one tied to the capture it came from.

- A frame under the **wrong key, or for an unknown session, gets no answer at all** — the socket just stays open.
- The DIAL `Application-URL` **names the port twice**; a client following it reaches nothing.
- The pairing request and its reply **spell the same key differently**.
- The application probe **never reports a launched app as running**, even with it on screen.

## What the emulator lets you test

- [x] The PIN page, the full key exchange and the issued session
- [x] Encrypted key events with click, press and release
- [x] Silence for undecryptable frames and unknown sessions
- [x] Application probes and launches
- [x] A key that survives its socket, and Disconnect forgetting every key

## Get access

Commercial licence, private access to the emulator, or a driver built for your app:
[open a request](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml) and say what you are building.
