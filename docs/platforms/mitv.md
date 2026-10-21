# Xiaomi Mi TV (GiTV)

> **N/A in this build.** Modelled; the emulator and the full driver guide are available on
> request — [ask about Xiaomi Mi TV (GiTV)](https://marchik.dev).

The local remote service of a Chinese Xiaomi Mi TV or Mi Box, as pymitv and Xiaomi's TV
Assistant app drive it. Newer firmware pairs a phone with an on-screen code. **No Xiaomi set
was measured, and no request was recorded off a wire**: the behaviour is modelled from pymitv
and the TV Assistant client contract. International Xiaomi televisions run Android TV or
Google TV and belong to the Android TV platform instead.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| GiTV remote | HTTP 6095 | reachability, keys, HDMI input selection, volume |
| TV Assistant | HTTP 9095 | reachability, volume, applications, device name |
| Service verification | TCP 6087 | the services the set advertises |
| Airkan | TCP 6088 | connections accepted and recorded |
| RC channel | TCP 6091 | session set-up, keys, heartbeat |
| Social RPC | TCP 9093 | version, pairing check, volume, heartbeat |
| LAN mirror keys | UDP 9527 | keys and heartbeat; off by default |
| Discovery | mDNS | the set's remote and Airkan services |

## Modelled devices

- **Xiaomi Mi TV (GiTV), older firmware (modelled)** — no pairing
- **Xiaomi Mi TV (GiTV), newer firmware (modelled)** — six-digit on-screen code

## What the emulator reproduces

- **The reachability check answers in standby too**, so it says nothing about power.
- **Power is a toggle**, and keys have no release.
- **Two discovery styles**: pymitv sweeps addresses, TV Assistant uses mDNS.
- **Pairing survives a disconnect** and clears when the device profile changes.

## What the emulator lets you test

- [x] Discovery exactly as pymitv and TV Assistant perform it
- [x] Every key pymitv and TV Assistant send
- [x] Volume reads and writes, the application list and launch, the device name
- [x] Pairing with the on-screen code, and reconnecting with the pairing kept
- [ ] Text, pointer, voice and media (not modelled)
- [ ] Anything a real Xiaomi set answers (not measured)

## Support and validation

Xiaomi TV Assistant for Android 2.7.6 was run against the emulator by hand on 2026-10-19.
Validated: discovery, remote keys and relative volume on both firmware generations, and code
pairing with reconnect on the newer one. Application listing and launching, power, text,
pointer, voice and media were not validated. The
[manual validation ledger](../manual-validation.md) has the rows.

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
