# Panasonic VIERA

> **N/A in this build.** The emulator, its session and the full driver guide are available on
> request — [ask about Panasonic VIERA](https://marchik.dev).

The network remote control VIERA sets expose to a phone remote: SSDP discovery, a UPnP
description and a SOAP control URL that takes `NRC_*` key names. **No VIERA set was measured**;
the behaviour follows the public protocol the community clients use and the official apps' own code.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| NRC SOAP | HTTP 55000 | description, SCPD, keys, text, app list and launch, state queries; plain commands, or a PIN pairing and encrypted sessions on the newer device |
| Renderer control | HTTP 55000 | `/dmr` RenderingControl: volume and mute, with `LastChange` events |
| PAC | HTTP 55000 | `/pac` inputs and picture modes |
| Events | HTTP 55000 | UPnP eventing: screen, input mode, keyboard type, running app, volume |
| Pointer socket | TCP 55010 | touchpad and gamepad frames, recorded |
| SSDP | UDP 1900 | `p00NetworkControl`, `p00RemoteController`, `upnp:rootdevice`, and a search by UDN |

## Modelled devices

- **Panasonic VIERA, no PIN (modelled)** — the older NRC-2 firmware: plain commands
- **Panasonic VIERA, PIN (modelled)** — the NRC-4 firmware from about 2018: a four-digit PIN
  pairs a remote, then every command is encrypted

Both come from the public protocol and the official apps' code; no set was measured. They are
two entries of the device picker, because a set is one or the other.

## What a driver gets wrong here

- Keys are **`NRC_<name>-ONOFF` strings**, not numeric codes.
- The official apps ask for a PIN **only when the description says `NRC-4.0` or newer**; the PIN
  device refuses a plain command and wants a **three-step pairing**, then a session id and a
  **strictly increasing sequence number** per command.
- Volume and mute are **not NRC**: they are read and written on the renderer at `/dmr`.
- The app list is **one string**: entries closed by `>`, fields by `'`.
- `X_LaunchApp` answers an **`X_SessionId`** the official apps require.

## What the emulator lets you test

- [x] Discovery and the UPnP descriptions
- [x] Every remote key by its `NRC_*` name
- [x] PIN pairing, a wrong-PIN refusal and encrypted sessions (PIN device)
- [x] Volume, mute and their events; inputs and picture modes
- [x] App list, app launch and text entry
- [x] Touchpad and gamepad frames
- [ ] Cast photo and video (DLNA), VOD lists, the TV browser

## Support and validation

The official **Panasonic TV Remote 2** (iOS 2.73) and **Panasonic TV Remote 3** (iOS 1.01)
were validated against the emulator by hand on 2026-10-05, on both devices: discovery,
including a cold start; every remote key; the App Launcher; and, on the PIN device, the PIN
dialog, pairing and the encrypted session. Launching an app, text entry, the touchpad and
gamepad, and cast photo and video were not validated. The
[manual validation ledger](../manual-validation.md) has the rows; the full guide lists each
behaviour.

## Get access

Commercial licence, private access to the emulator, or a driver built for your app:
[get in touch](https://marchik.dev) and say what you are building.
