# XGIMI

> **N/A in this build.** Modelled; the emulator and the full driver guide are available on
> request — [ask about XGIMI](https://marchik.dev).

The LAN remote of an XGIMI projector as the vendor's own phone app drives it: a UDP
broadcast to find the projector, a command channel over UDP on older firmware or TCP on newer
firmware, and a separate UDP key port. **No XGIMI projector was measured, and no packet was
recorded off a wire** — the behaviour is modelled.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| XGIMI discovery | UDP 16752 | the search and its answer |
| Key port | UDP 16735 | every key the app sends |
| Command channel, older firmware | UDP 16750 | binding with a code on screen, heartbeat, text, apps, volume |
| Command channel, newer firmware | TCP 13145 | the same commands and keys |

## Modelled devices

- **XGIMI projector, older firmware (modelled)** — commands over UDP, no projector measured
- **XGIMI projector, newer firmware (modelled)** — commands over TCP, no projector measured

## What the emulator reproduces

- **The discovery answer goes to a fixed phone port**, not to the port the search came from.
- **The projector chooses UDP or TCP** in its discovery answer, not by model name.
- **A new phone must enter the code shown on the projector** before it is connected.
- **The power key opens the power menu**; it does not switch the projector off.

## What the emulator lets you test

- [x] Discovery exactly as the vendor app performs it
- [x] Binding, the code on screen and the heartbeat, over UDP and over TCP
- [x] Every key the app sends, on the key port and over the TCP session
- [x] Text, app launch, volume and mute moving the simulated projector
- [ ] Anything a real XGIMI projector answers beyond binding (not measured)
- [ ] Android TV based XGIMI models

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
