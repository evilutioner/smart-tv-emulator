# webOS TV

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about webOS TV](https://marchik.dev).

A 2022 LG set running webOS: the SSAP control socket over TLS, the IME keyboard, the pointer
socket, a DLNA renderer, and the four independent SSDP stacks the set publishes. Four sets are
captured, two of them rebadged LG panels.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| SSAP | WSS 3001 | prompt and PIN pairing, requests, subscriptions |
| Pointer input socket | WSS 3001 | D-pad, OK, move and scroll |
| IME keyboard | over SSAP | focus, insert, delete, Enter |
| Voice input | WSS, a port the set names per press | the button, and the audio socket it opens |
| Second screen / DIAL / virtual service | HTTP, per-set ports | UPnP descriptions and DIAL app state |
| DLNA MediaRenderer | HTTP, per-set port | description, volume and mute actions |
| SSDP ×4 stacks | UDP 1900 | one reply per stack, each with its own identity |

## Captured devices

- **LG 43UQ81006LB**
- **LG 50UA75006LA**
- **Sencor SLE50Q871B**
- **Sencor SLE65Q871B**

## What the emulator reproduces

Behaviours of the captured firmware the emulator reproduces, named here without their
detail. The full guide gives each one, tied to the capture it came from.

- **Discovery from four independent SSDP stacks**, as the set runs them.
- **Pairing by prompt and by PIN**, a refused prompt, and a second pairing while a code is on screen.
- **Permissions per registration**, as the set grants them.
- **The pointer socket, the keyboard and voice input**, each on the channel the set uses.
- **App launch and close**, the closes the set refuses included.

## What the emulator lets you test

- [x] Discovery across all four stacks, per captured set
- [x] PROMPT, PIN and combined pairing, rejection, timeout and returning with a client key
- [x] Volume, mute, media, channel and power-off
- [x] The pointer socket and the on-screen keyboard, both ways
- [x] LG ThinQ's voice button: the audio socket opens on a fresh port, the stream is
  measured, and none of the audio is kept
- [x] Application launches, observed as the app sends them
- [x] Refusals for everything the set does not serve, instead of invented answers
- [x] Every answer in the set's own bytes, checked against the capture frame by frame
- [x] Driven end to end by the open-source clients aiowebostv, bscpylgtv, lgtv2 and pywebostv

## Support and validation

The official **LG ThinQ** app (iOS build 162) was validated against the emulator by hand on
2026-10-13, after the same session had been relayed to the 43UQ81006LB so that every answer it
gets is the set's own. The [manual validation ledger](../manual-validation.md) has the row.

- **Validated**: discovery, PIN pairing with the code from the dashboard, the add-device flow,
  volume, channel up and down, application launches, power-off, the pointer socket's keys,
  touchpad and scroll wheel, and the voice button's audio stream.
- **Observed, unconfirmed**: a few requests the set never answers; the emulator stays silent
  too. The foreground and recent application lists are served as captured and do not follow a
  launch.
- **Not exercised**: power-on, which ThinQ does by Wake-on-LAN; the emulator does not listen
  for it.
- **Not emulated**: the end of a spoken phrase, which the set detects and the emulator does
  not, so ThinQ keeps streaming until its own timer ends.

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
