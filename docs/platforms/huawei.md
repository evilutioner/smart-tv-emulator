# Huawei MediaQ

> **N/A in this build.** Modelled from a third-party Android remote app; the emulator and the
> full driver guide are available on request — [ask about Huawei MediaQ](https://marchik.dev).

The LAN remote of the Huawei MediaQ set-top box (华为秘盒) as a third-party Android remote app
drives it: a TCP probe that tells the app it has found a Huawei box, and an HTTP route that
takes Android keycodes. **No Huawei box was measured, and no request was recorded off a wire**
— the behaviour follows what that app sends.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| huawei-remote | HTTP 8080 | key press and release |
| Probe | TCP 9001 | a connect, which is all the app does |

## Modelled devices

- **Huawei MediaQ (modelled)** — from a third-party Android remote app; no box measured

## What a driver gets wrong here

- There is **no discovery protocol**: the app connects to TCP 9001 on every address in the phone's ARP cache, or on its whole /24 only when that cache is empty.
- The key code is an **Android keycode in a header**, not in the path or the body.
- Every button is **two requests**, a press (`Action: 0`) and a release (`Action: 1`).
- Enter goes out as **DPAD_CENTER (23)**, never as 66.

## What the emulator lets you test

- [x] Discovery exactly as that app performs it
- [x] Every key that app sends, by its Android keycode
- [ ] Text, app launches, pointer (no client seen sending them)
- [ ] Anything a real MediaQ answers (not measured)

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
