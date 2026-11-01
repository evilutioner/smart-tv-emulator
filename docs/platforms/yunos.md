# YunOS / AliTV

> **N/A in this build.** Modelled; the emulator and the full driver guide are available on
> request — [ask about YunOS / AliTV](https://marchik.dev).

The LAN remote of an Alibaba YunOS (AliTV) set-top box: an SSDP search, and a binary TCP
session that logs in, carries Android keycodes and keeps itself alive. **No YunOS box was measured, and no
frame was recorded off a wire** — the behaviour is modelled.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| AliTV helper | TCP 13510 | login, keys, heartbeats; optional AES-128-CBC bodies |
| SSDP | UDP 1900 | the answer to the Tiqiaa remote's search |

## Modelled devices

- **YunOS / AliTV box (modelled)** — no box measured

## What the emulator reproduces

- **The Tiqiaa remote's SSDP search is not strictly well-formed**; a strict SSDP stack ignores
  it. Alibaba's own helper finds a box another way, which is not emulated.
- **Every message after the login depends on the login answer.**
- **AES offers receive a clear negotiation reply, then encrypted bodies.** The emulator
  reflects the client’s wrapped seed; this is inferred from the helper's client contract and has not
  been validated with the app. Legacy clients keep their plain session.
- **One message per button**, with no release; keep-alives are answered, buttons are not.

## What the emulator lets you test

- [x] Discovery exactly as the Tiqiaa remote performs it
- [x] Every key the remote apps send, by its Android keycode
- [x] AES v1 negotiation and encrypted frames, inferred from the helper's client contract; app validation pending
- [ ] Text, app launches, pointer (no client seen sending them)
- [ ] Anything a real YunOS box answers (not measured)

## Support and validation

ZaZa Remote for Android 5.4.5 was run against the emulator by hand on 2026-10-21. Validated:
listing the box, the twelve buttons of the box remote and the keep-alive while it stays open.
The app shows its box remote only with its language set to Chinese, and its search needs a
network that passes multicast between the phone and the emulator; on the test network it did
not, and the search answer was relayed to the phone by hand. Text, app management and anything
a real box answers were not validated. The [manual validation ledger](../manual-validation.md)
has the row.

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
