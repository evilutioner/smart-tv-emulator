# Xiaomi Mi TV (GiTV)

> **N/A in this build.** Modelled; the emulator and the full driver guide are available on
> request — [ask about Xiaomi Mi TV (GiTV)](https://marchik.dev).

The local remote service of a Chinese Xiaomi Mi TV or Mi Box: plain HTTP on port 6095, no
pairing, one `GET` per button. **No Xiaomi set was measured, and no request was recorded off
a wire**: the behaviour is modelled from the open-source client pymitv. International Xiaomi
televisions run Android TV or Google TV and belong to the Android TV platform instead.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| GiTV remote | HTTP 6095 | `isalive`, every key pymitv sends, the HDMI input change, the volume read |

## Modelled devices

- **Xiaomi Mi TV (GiTV) (modelled)** — no set measured

## What a driver gets wrong here

- There is **no discovery protocol**: the client sends `isalive` to every address of its /24.
- `isalive` answers **in standby too**, so it says nothing about power.
- `power` is a **toggle**.
- A key is a **lower-case name** (`enter`, `volumeup`), not a keycode, and has **no release**.
- The volume read is spelled **`getVolum`**, and its `data` is **JSON text inside a string**, not an object.

## What the emulator lets you test

- [x] Discovery exactly as pymitv performs it, one address at a time
- [x] Every key pymitv sends, by its keycode
- [x] The live volume, read the way pymitv reads it
- [ ] Mute, text, app list, app launch, pointer (no modelled client sends them)
- [ ] Anything a real Xiaomi set answers beyond `isalive` (not measured)

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
