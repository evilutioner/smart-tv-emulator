# Huawei MediaQ

> **N/A in this build.** Modelled; the emulator and the full driver guide are available on
> request — [ask about Huawei MediaQ](https://marchik.dev).

The LAN remote of the Huawei MediaQ set-top box (华为秘盒): a TCP probe that tells a remote app
it has found a Huawei box, and an HTTP route that takes Android keycodes. **No Huawei box was
measured, and no request was recorded off a wire** — the behaviour is modelled.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| Huawei remote | HTTP 8080 | key press and release |
| Probe | TCP 9001 | a connect, which is all the app does |

## Modelled devices

- **Huawei MediaQ (modelled)** — no box measured

## What the emulator reproduces

- **No discovery protocol**: the app probes the addresses it already knows, or sweeps its subnet.
- **Every button is two requests**, a press and a release.
- **Keys are Android keycodes**, with Enter sent as the D-pad centre key.

## What the emulator lets you test

- [x] Discovery exactly as the remote app performs it
- [x] Every key the remote app sends, by its Android keycode
- [ ] Text, app launches, pointer (no client seen sending them)
- [ ] Anything a real MediaQ answers (not measured)

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
