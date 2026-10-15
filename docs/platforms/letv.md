# LeTV / LeEco

> **N/A in this build.** Modelled; the emulator and the full driver guide are available on
> request — [ask about LeTV / LeEco](https://marchik.dev).

The LAN remote of a LeTV (LeEco) television: a TCP probe that tells a remote app it has found
a LeTV set, and one JSON datagram per button over UDP. **No LeTV set was measured, and no
packet was recorded off a wire** — the behaviour is modelled.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| LeTV control | UDP 9900 | every button the app sends; its helper-install request, logged |
| Probe | TCP 13489 | the connect, and the `getDeviceInfo` line the app writes there |

## Modelled devices

- **LeTV / LeEco set (modelled)** — no set measured

## What a driver gets wrong here

- There is **no discovery protocol**: the app connects to TCP 13489 on every address in the phone's ARP cache, or on its whole /24 only when that cache is empty.
- Keys go over **UDP**, not over the TCP port the set was found on.
- A key is an **action name** (`ok`, `return`, `volume_up`), not a keycode, and has **no release**.
- Nothing answers a key, so a missing answer is **not** an error.

## What the emulator lets you test

- [x] Discovery exactly as the remote app performs it
- [x] Every key the remote app sends, by its action name
- [ ] Text, app launches, pointer (no client seen sending them)
- [ ] Anything a real LeTV set answers (not measured)

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
