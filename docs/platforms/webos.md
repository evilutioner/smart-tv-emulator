# webOS TV

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about webOS TV](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml).

A 2022 LG set running webOS: the SSAP control socket over TLS, the IME keyboard, the pointer
socket, a DLNA renderer, and the four independent SSDP stacks the set publishes. Four sets are
captured, two of them rebadged LG panels.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| SSAP | WSS 3001 | prompt and PIN pairing, `ssap://` requests, subscriptions |
| Pointer input socket | WSS 3001 | D-pad, OK, move and scroll |
| IME keyboard | over SSAP | focus, insert, delete, Enter |
| Second screen / DIAL / virtual service | HTTP, per-set ports | UPnP descriptions and DIAL app state |
| DLNA MediaRenderer | HTTP, per-set port | description, volume and mute actions |
| SSDP ×4 stacks | UDP 1900 | one reply per stack, each with its own UUID and `SERVER` |

## Captured devices

- **LG 43UQ81006LB**
- **LG 50UA75006LA**
- **Sencor SLE50Q871B**
- **Sencor SLE65Q871B**

## What a driver gets wrong here

A few of the firmware behaviours the emulator reproduces. The full guide covers every
message, pairing step and refusal, each one tied to the capture it came from.

- **Four SSDP stacks, not one**, each on its own randomly chosen description port — nothing may hard-code them.
- The client reads the webOS version from an **HTTP `Server` header**, not from the SSDP reply.
- A changed device UUID or TLS subject makes the client **treat the set as an imposter** and throw away its key.
- Direction keys have **no `ssap://` fallback** — they only travel over the pointer socket.
- The keyboard only answers a **subscription**; a plain request for it is an error.

## What the emulator lets you test

- [x] Discovery across all four stacks, per captured set
- [x] PROMPT, PIN and combined pairing, rejection, timeout and returning with a client key
- [x] Volume, mute, media, channel and power-off
- [x] The pointer socket and the on-screen keyboard, both ways
- [x] Application launches, observed with their exact payloads
- [x] Refusals for everything the set does not serve, instead of invented answers

## Get access

Commercial licence, private access to the emulator, or a driver built for your app:
[open a request](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml) and say what you are building.
