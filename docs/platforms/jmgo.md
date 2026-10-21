# JMGO

> **N/A in this build.** Modelled; the emulator and the full driver guide are available on
> request — [ask about JMGO](https://marchik.dev).

The LAN remote of a JMGO (坚果) projector as the vendor's own phone app drives it: a UDP
broadcast to find the projector and Google TV Anymote over a plain TCP connection.
**No JMGO projector was measured, and no packet was recorded off a wire** — the behaviour is
modelled.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| JMGO discovery | UDP 9101 | the search and its answer |
| Anymote | TCP 9005 | keys, touchpad, text, app pages, device information |

## Modelled devices

- **JMGO projector, newer firmware (modelled)** — no projector measured
- **JMGO projector, older Arwen firmware (modelled)** — no projector measured
- **JMGO projector with ambient light (modelled)** — light controls on, no projector measured

## What the emulator reproduces

- **No TLS, no pairing and no handshake**: a key can be the first thing on the wire.
- **The power key differs by firmware**, chosen from what the projector reports, not its model name.
- **The app connects to a fixed port**, whatever the discovery answer names.
- **Each button is a key down and then up.**

## What the emulator lets you test

- [x] Discovery exactly as the vendor app performs it
- [x] Every key the app sends, including JMGO's focus, autofocus and power keys
- [x] Text, app pages and volume moving the simulated projector
- [x] The device information the app picks its screens and power key from
- [ ] The keepalive answer and anything else a real projector answers (not measured)
- [ ] Bluetooth remote and wake from standby

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
