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
| Command channel, older firmware | UDP 16750 | binding with or without a code on screen, heartbeat, text, apps, volume, device information |
| Command channel, newer firmware | TCP 13145 | the same commands and keys |
| Reachability | TCP 554 | open while the projector is on, the power read of Home Assistant's integration |
| App list | HTTP 16741 | the installed apps, where owners and the 2018 app look for them |

## Modelled devices

- **XGIMI projector, 2018 firmware (modelled)** — commands over UDP, no code, as the vendor's 2018 app expects; no projector measured
- **XGIMI projector, older firmware (modelled)** — commands over UDP, no projector measured
- **XGIMI projector, newer firmware (modelled)** — commands over TCP, no projector measured

## What the emulator reproduces

- **The discovery answer goes to a fixed phone port**, not to the port the search came from.
- **The projector chooses UDP or TCP** in its discovery answer, not by model name.
- **A new phone must enter the code shown on the projector** before it is connected; the
  2018 device connects the vendor's 2018 app, which has no code screen, at once.
- **Text waits for the projector's keyboard**: the projector tells the phone when a field
  takes focus, and the 2018 app sends text only then.
- **The power key opens the power menu**; it does not switch the projector off. Code 30 does.
- **Port 554 is open only while the projector is on**, which is how Home Assistant's
  integration tells on from off.
- **Commands that are not strict JSON** (single quotes, unquoted values) are read as
  Android's JSON reader reads them, as open-source drivers rely on.
- **Power off and on by command**, as HomeKit's plugin sends them.

## What the emulator lets you test

- [x] Discovery exactly as the vendor app performs it
- [x] Binding, the code on screen and the heartbeat, over UDP and over TCP
- [x] Every key the app sends, on the key port and over the TCP session
- [x] Text, app launch, volume and mute moving the simulated projector
- [x] The vendor's 2018 app end to end: discovery, connecting, its device panel, the remote,
      text and the app list
- [x] Home Assistant's XGIMI integration: keys, mute, power-off and its power read on 554
- [x] homebridge-xgimi-tv: keys, volume, app launches and power off and on
- [ ] Anything a real XGIMI projector answers beyond binding (not measured)
- [ ] Android TV based XGIMI models

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
