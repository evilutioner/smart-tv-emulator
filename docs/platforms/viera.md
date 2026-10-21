# Panasonic VIERA

> **N/A in this build.** The emulator, its session and the full driver guide are available on
> request — [ask about Panasonic VIERA](https://marchik.dev).

The network remote control VIERA sets expose to a phone remote: SSDP discovery, UPnP
descriptions and SOAP control services. **No VIERA set was measured**; the behaviour follows
the public protocol the community clients use and what the official apps send.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| Network remote control (UPnP SOAP) | HTTP 55000 | keys, text, app list and launch, state queries, PIN pairing on the newer device |
| Rendering control | HTTP 55000 | volume and mute, with events |
| Inputs and picture | HTTP 55000 | inputs and picture modes |
| UPnP eventing | HTTP 55000 | screen, input, keyboard, running app, volume |
| Pointer socket | TCP 55010 | touchpad and gamepad, recorded |
| SSDP | UDP 1900 | the searches the official apps send |

## Modelled devices

- **Panasonic VIERA, no PIN (modelled)** — older firmware: plain commands
- **Panasonic VIERA, PIN (modelled)** — firmware from about 2018: a four-digit PIN pairs a
  remote, then every command is encrypted

Both come from the public protocol and the official apps' traffic; no set was measured. They are
two entries of the device picker, because a set is one or the other.

## What the emulator reproduces

- **The official apps ask for a PIN only when the description says the set needs one.**
- **The PIN device refuses a plain command** and wants every command in a paired session.
- **Volume and mute are not remote-control commands**: they live on the renderer service.
- **Launching an app answers a session value** the official apps require.

## What the emulator lets you test

- [x] Discovery and the UPnP descriptions
- [x] Every remote key the official apps send
- [x] PIN pairing, a wrong-PIN refusal and encrypted sessions (PIN device)
- [x] Volume, mute and their events; inputs and picture modes
- [x] App list, app launch and text entry
- [x] Touchpad and gamepad
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

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
