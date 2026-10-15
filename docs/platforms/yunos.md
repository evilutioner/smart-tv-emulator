# YunOS / AliTV

> **N/A in this build.** Modelled; the emulator and the full driver guide are available on
> request — [ask about YunOS / AliTV](https://marchik.dev).

The LAN remote of an Alibaba YunOS (AliTV) set-top box: an SSDP search for the YunOSTV device
type, a TCP probe, and a binary session that logs in and then carries Android keycodes. **No
YunOS box was measured, and no frame was recorded off a wire** — the behaviour is modelled.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| AliTV helper | TCP 13510 | login, key frames, heartbeats |
| SSDP | UDP 1900 | the answer to the app's YunOSTV search |

## Modelled devices

- **YunOS / AliTV box (modelled)** — no box measured

## What a driver gets wrong here

- The search's lines end in a **bare LF**, not CR LF; a strict SSDP stack ignores it.
- Every frame after the login carries a **session copied out of the login answer**.
- The key code is an **Android keycode**, one frame per button, with **no release**.
- Nothing is answered after the login, so a missing answer is **not** an error.

## What the emulator lets you test

- [x] Discovery exactly as the remote app performs it
- [x] Every key the remote app sends, by its Android keycode
- [ ] Text, app launches, pointer (no client seen sending them)
- [ ] Anything a real YunOS box answers (not measured)

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
