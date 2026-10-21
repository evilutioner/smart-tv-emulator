# YunOS / AliTV

> **N/A in this build.** Modelled; the emulator and the full driver guide are available on
> request — [ask about YunOS / AliTV](https://marchik.dev).

The LAN remote of an Alibaba YunOS (AliTV) set-top box: an SSDP search, and a binary TCP
session that logs in and then carries Android keycodes. **No YunOS box was measured, and no
frame was recorded off a wire** — the behaviour is modelled.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| AliTV helper | TCP 13510 | login, keys, heartbeats |
| SSDP | UDP 1900 | the answer to the app's search |

## Modelled devices

- **YunOS / AliTV box (modelled)** — no box measured

## What the emulator reproduces

- **The app's SSDP search is not strictly well-formed**; a strict SSDP stack ignores it.
- **Every message after the login depends on the login answer.**
- **One message per button**, with no release, and nothing answered after the login.

## What the emulator lets you test

- [x] Discovery exactly as the remote app performs it
- [x] Every key the remote app sends, by its Android keycode
- [ ] Text, app launches, pointer (no client seen sending them)
- [ ] Anything a real YunOS box answers (not measured)

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
