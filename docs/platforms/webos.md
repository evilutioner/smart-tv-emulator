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
| SSAP | WSS 3001 | prompt and PIN pairing, `ssap://` requests, subscriptions |
| Pointer input socket | WSS 3001 | D-pad, OK, move and scroll |
| IME keyboard | over SSAP | focus, insert, delete, Enter |
| Voice input | WSS, a port the set names per press | the button's edges, the set's p2p frames, the audio socket's 101 |
| Second screen / DIAL / virtual service | HTTP, per-set ports | UPnP descriptions and DIAL app state |
| DLNA MediaRenderer | HTTP, per-set port | description, volume and mute actions |
| SSDP ×4 stacks | UDP 1900 | one reply per stack, each with its own UUID and `SERVER` |

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
- **Requests the set leaves unanswered** stay unanswered.
- **App launch and close**, the closes the set refuses included.

## What the emulator lets you test

- [x] Discovery across all four stacks, per captured set
- [x] PROMPT, PIN and combined pairing, rejection, timeout and returning with a client key
- [x] Volume, mute, media, channel and power-off
- [x] The pointer socket and the on-screen keyboard, both ways
- [x] LG ThinQ's voice button: the audio socket opens on a fresh port, frames are counted
  and the format shown, and none of the audio is kept
- [x] Application launches, observed with their exact payloads
- [x] Refusals for everything the set does not serve, instead of invented answers
- [x] Every answer in the set's own bytes, checked against the capture frame by frame
- [x] Driven end to end by the open-source clients aiowebostv, bscpylgtv, lgtv2 and pywebostv

## Support and validation

The official **LG ThinQ** app (iOS build 162) was validated against the emulator by hand on
2026-10-13, after the same session had been relayed to the 43UQ81006LB so that every answer it
gets is the set's own. The [manual validation ledger](../manual-validation.md) has the row.

- **Validated**: SSDP discovery, PIN pairing with the code from the dashboard, the add-device
  flow (about 30 reads, including the cloud headers and `sdx/send` answers the set relays),
  volume, channel up and down, application launches from the Apps list, power-off, and on the
  pointer socket the arrows, OK, Back, Home, digits, colour keys, GUIDE, QMENU, PLAY, MUTE,
  the touchpad cursor and the scroll wheel. Voice: the button opens the audio socket the
  set's `p2p` frame names, ThinQ streams to it and shows no error, and releasing the button
  ends the stream.
- **Observed, unconfirmed**: `verification` and `p2p` frames and `cis/sendR2Rkey`, which the set
  never answers; the emulator stays silent too, and what the set does with them is not visible.
  `getForegroundApps` and `getRecentsAppList` are served as captured and do not follow a launch.
- **Not exercised**: power-on. ThinQ wakes the set with Wake-on-LAN, magic packets on UDP 9 to
  both MAC addresses `connectionmanager/getinfo` reported; the emulator has no Wake-on-LAN
  listener, so after power-off it stays off until the dashboard resets it.
- **Not emulated**: the end of a spoken phrase. The set hears it and sends `restartTimer` and
  `stopStreaming` unprompted (`ws.voice.set-ends`); the emulator recognises no speech, so
  ThinQ keeps streaming until its own timer releases the button.

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
