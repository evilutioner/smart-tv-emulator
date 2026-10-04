# TCL nScreen

> **N/A in this build.** Written and tested against physical hardware; the emulator, its
> captures and the full driver guide are available on request —
> [ask about TCL nScreen](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml).

The remote that TCL's MediaTek **Linux** sets answer, which is neither the Roku ECP of a TCL
Roku TV nor the Android TV Remote of a TCL Google TV. A client opens one TCP port, writes XML,
and gets one fixed acknowledgement back for everything it sends.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| nScreen remote | TCP 4123 | `setKey` and `sendCommand` actions, `noop` keep-alive, no pairing |
| UPnP MediaRenderer | HTTP 49152 | description, three SCPDs and the three read-only calls captured |
| UPnP tvdevice description | HTTP 56790 | `dd.xml` whose `Application-URL` names DIAL |
| DIAL | HTTP 56789 | YouTube and Netflix states; a launch is refused |
| SSDP | UDP 1900 | two stacks: the renderer's six targets, and DIAL on its own |

## Captured devices

- **TCL H32S5916** — Linux 3.10, MediaTek MT5655 (not Roku, not Android TV)

## What a driver gets wrong here

A few of the firmware behaviours the emulator reproduces. The full guide covers every
message and refusal, each one tied to the capture it came from.

- The remote **acknowledges every read the same way** — a key, a keep-alive, garbage, a key the
  set does not have. A driver cannot learn from the answer whether a key landed.
- The set answers **per TCP read, not per message**: two messages in one segment get one
  acknowledgement, and one message split over two segments gets two.
- DIAL's state document is a **stopped** state for both applications, and a browser's `OPTIONS`
  preflight is refused with **403**.
- Discovery is **two unrelated SSDP stacks**; the DIAL one ignores `ssdp:all`.
- The DLNA renderer reports the set's own volume and mute, **not** the level the remote keys move.

## What the emulator lets you test

- [x] Discovery through both stacks, then the description each one points at
- [x] Every key the community clients send, as live power, volume and mute state
- [x] The keep-alive, an announced client name, and a connection that outlives the disconnect command
- [x] DIAL application state and its refusals
- [ ] Power and the rest of the key table, text entry and DIAL launch (not exercised on the set)

## Get access

Commercial licence, private access to the emulator, or a driver built for your app:
[open a request](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television-request.yml) and say what you are building.
