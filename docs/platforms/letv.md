# LeTV / LeEco

> **N/A in this build.** Modelled; the emulator and the full driver guide are available on
> request — [ask about LeTV / LeEco](https://marchik.dev).

The LAN remote of a LeTV (LeEco) television: a UDP search and a TCP probe that tell a remote
app it has found a LeTV set, one datagram per button over UDP, and app launch over HTTP. **No
LeTV set was measured, and no packet was recorded off a wire** — the behaviour is modelled
from what the remote apps send, and every answer is the emulator's own.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| LeTV control | UDP 9900 | every button the apps send; touchpad moves and clicks, logged; a helper-install request, logged |
| Probe | TCP 13489 | the connect, and the device information request answered with the app port |
| LeTV discovery | UDP 8008 | the search a remote app broadcasts, answered with what it looks for |
| App port | HTTP 4004 | the installed-app list and launching an app |

## Modelled devices

- **LeTV / LeEco set (modelled)** — no set measured

## What the emulator reproduces

- **Two ways to be found**: one app broadcasts a search to UDP 8008, another probes the
  addresses it already knows, or sweeps its subnet, on TCP 13489.
- **The device information answer** names the port apps are launched on, and nothing else.
- **Keys go over UDP**, not over the TCP port the set was found on.
- **A key is a named action** with no release, and nothing answers it.
- **Vendor vocabulary**: channels, digits, settings and source from LeEco's own action list
  are accepted too; its cursor, wheel and playback actions are logged, not pressed.
- **A touchpad** sends relative moves and a click as datagrams on the same port; the emulator
  logs each one and draws no cursor.
- **Apps launch** by a DLNA message carrying an Android start intent from the app list.

## What the emulator lets you test

- [x] Discovery exactly as the remote app performs it
- [x] Every key the remote app sends
- [x] Pointer moves and clicks as Wukong-family remotes send them
- [x] The app list and app launches as Wukong sends them
- [ ] Text (no client seen sending it over the LAN)
- [ ] Anything a real LeTV set answers (not measured)

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
