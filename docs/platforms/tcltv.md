# TCL

> **N/A in this build.** The nScreen set is written and tested against physical hardware; the
> T-Cast sets are modelled. The emulator, its captures and the full driver guide are available
> on request — [ask about TCL](https://marchik.dev).

The two LAN remotes of TCL's own firmware, which is neither the Roku ECP of a TCL Roku TV nor
the Android TV Remote of a TCL Google TV:

- **nScreen**, which TCL's MediaTek **Linux** sets answer over TCP 4123.
- **T-Cast** (MagiConnect), which TCL's own phone apps drive: a UDP broadcast finds the set,
  then one TCP connection carries buttons, text and app launches, encrypted when the set asks
  for it. **No TCL set was measured for T-Cast, and no frame was recorded off a wire.**

A set can run both side by side. Each emulated device runs the remote its evidence shows.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| nScreen remote | TCP 4123 | keys, commands, keep-alive; no pairing |
| T-Cast remote | TCP 6553 | session set-up, heartbeat, keys, text, pointer, app list and launch |
| T-Cast discovery | UDP 6537 | the answer to the app's broadcast |
| UPnP MediaRenderer | HTTP 49152 | description, service descriptions and the read-only calls captured |
| UPnP device description | HTTP 56790 | the description that points at DIAL |
| DIAL | HTTP 56789 | application state; a launch is refused |
| SSDP | UDP 1900 | the set's two discovery stacks |

## Devices

- **TCL H32S5916** — captured; Linux 3.10, MediaTek MT5655; nScreen, DLNA, DIAL, SSDP
- **TCL set, older T-Cast (modelled)** — plaintext session
- **TCL set, newer T-Cast (modelled)** — encrypted session

## What the emulator reproduces

- **nScreen acknowledges everything the same way**, so a driver cannot tell whether a key landed.
- **nScreen answers per TCP read, not per message.**
- **Discovery is two unrelated SSDP stacks**, and one ignores the catch-all search.
- **The DLNA renderer's volume is not the level the remote keys move.**
- **A silent T-Cast link must keep a heartbeat**, or the app drops it.

## What the emulator lets you test

- [x] nScreen discovery through both stacks, then the description each one points at
- [x] Every key the community nScreen clients send, as live power, volume and mute state
- [x] The keep-alive, an announced client name, and a connection that outlives a disconnect
- [x] DIAL application state and its refusals
- [x] T-Cast discovery exactly as TCL's phone SDK performs it
- [x] Both the plaintext and the encrypted T-Cast session
- [x] Every T-Cast button TCL's apps send, text, pointer moves, the app list and launches
- [ ] nScreen power and the rest of its key table, and DIAL launch (not exercised on the set)
- [ ] T-Cast voice, screenshots, casting and app install (not modelled)
- [ ] Anything a real set answers over T-Cast (not measured)

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
