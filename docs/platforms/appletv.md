# Apple TV

> **N/A in this build.** Built from an Apple TV 4K recorded with pyatv; the emulator and the
> full driver guide are available on request — [ask about Apple TV](https://marchik.dev).

An Apple TV as a remote-control client sees it on the LAN: the Companion link, the protocol
behind the iPhone's Control Center remote and libraries such as pyatv. Pairing by a PIN on
screen, pair-verify on every connection, and a sealed session of OPACK messages carrying
buttons, touch, text input, apps and power. It replays **a session recorded off an Apple TV 4K
(3rd generation) on tvOS 26.5**; the set's pairing keys are made when the emulator starts.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| Companion link | TCP 49153 | PIN pairing, pair-verify, buttons, touch, Remote Text Input, apps, accounts, power state, volume |
| Bonjour | UDP 5353 | `_companion-link._tcp` with the set's TXT record |

## Captured devices

- **Apple TV 4K (3rd generation)**, AppleTV14,1, tvOS 26.5 — Companion link recorded off the set

## What a driver gets wrong here

- **Wake does not wake the set**; Home does. Sleep acts on the **release**.
- A request the set does not know is **answered with an error**, not dropped.
- Text needs a **text session** and a focused field; the set announces focus with an event.

## What the emulator lets you test

- [x] Pairing by PIN, a wrong PIN, and credentials the set never paired
- [x] Buttons, touch, text into a focused field, app and account lists, app launch
- [x] Sleep, the attention state, and the events a registered client is sent
- [ ] AirPlay and the MediaRemote tunnel: now playing, artwork, media commands beyond buttons

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
