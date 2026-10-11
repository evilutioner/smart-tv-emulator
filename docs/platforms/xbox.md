# Xbox

> **N/A in this build.** Built from a recorded console session and the OpenXbox SmartGlass
> client; the emulator and the full driver guide are available on request —
> [ask about Xbox](https://marchik.dev).

An Xbox One or Series console as a SmartGlass client sees it: a discovery request broadcast to
UDP 5050, an ECDH connect against the console's certificate, and an encrypted session that
carries gamepad input, media commands and system text. The handshake, channels and heartbeats
replay **a session recorded with a console**; gamepad, media and text, which that session did
not exercise, follow the OpenXbox project's layouts. The console's key is made when the
emulator starts.

## Protocols

| Protocol | Transport · port | What is emulated |
|---|---|---|
| SmartGlass | UDP 5050 | discovery, power-on, connect, acks and heartbeats, input, media and text channels, title launch, power-off |
| DLNA renderer | TCP 2869 | description, SCPDs, icons and read-only SOAP calls, as the console answered them |
| SSDP | UDP 1900 | the renderer's six search targets and `ssdp:all` |

## Captured devices

- **Xbox console**, OS 10.0.26100 — anonymous session captured; input and text modelled from OpenXbox

## What a driver gets wrong here

- Two common client mistakes in the key exchange and in message encryption are each refused
  as the console refuses them; the full guide says which.
- Every need-ack message is **acknowledged on its own channel**; a heartbeat nobody
  acknowledges ends the session, and the **console heartbeats too**.
- Text input needs a **text session the console announced** when a field gained focus.
- A seek position is a **u64**.
- The console is **two devices on the LAN**: a SmartGlass console on UDP 5050 and a DLNA
  MediaRenderer found over SSDP. It answers no mDNS.

## What the emulator lets you test

- [x] Discovery, an anonymous connect, and a refusal when only signed-in profiles may connect
- [x] Every gamepad button as a press and release, every media command
- [x] A text session opened from the dashboard, typed into and submitted from the client
- [x] Power-off and power-on by Live ID
- [ ] Xbox Live sign-in (a token is accepted unverified), titles, media state, Nano streaming

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
