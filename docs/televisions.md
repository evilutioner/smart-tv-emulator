# Televisions and protocols

Every television this product models, the wire protocols each one speaks, and how each
device is known. The [README](../README.md#televisions) has the short version.

## How a device is known

| Mark | Meaning |
|---|---|
| 📡 **Captured** | Replayed from packet captures of a physical set. Version strings are the values the captured firmware itself reports. |
| 📱 **Modelled** | Built from the traffic of the vendor's own remote app; no set of that make was measured. The answers are the app's contract, not a television's. |
| ✅ **Validated** | A real remote app has been driven against this device and the session is recorded in [Manual validation](manual-validation.md). Its absence says nothing either way. |
| **Included** | Runs in this build. |
| **N/A** | Written and tested against hardware, with its own profiles and regression tests, but not available in this build. See [The other televisions](../README.md#the-other-televisions). |

## By television

<!-- generated:television_details -->
| Television | In this build | Remote control | Discovery | Pairing | Devices | Tested with |
|---|---|---|---|---|---|---|
| **[Roku](platforms/roku.md)** | **Included** | ECP over HTTP **8060** + authenticated `ecp-2` WebSocket | SSDP `roku:ecp` | ECP-2 challenge–response | 📡 **Roku Streaming Stick 4K** — 3820EU2, Roku OS 12.0.0<br>📡 **TCL Roku TV 32S357** — hw H104X, Roku OS 15.3.4 | 🧪 [rokuecp](https://github.com/ctalkington/python-rokuecp) · [report](clients/roku.md#rokuecp)<br>🧪 [python-roku](https://github.com/jcarbaugh/python-roku) · [report](clients/roku.md#python-roku)<br>🧪 [roku-client](https://github.com/bschlenk/node-roku-client) · [report](clients/roku.md#roku-client)<br>🔬 [unit and replay tests](tests/roku.md) |
| **[Fire TV](platforms/firetv.md)** | N/A | Turnstile over HTTPS **8080**; legacy ADB shell **5555**, off by default | DIAL/SSDP; Bonjour `_amzn-wplay._tcp` on Fire OS | On-screen PIN and client token; ADB public-key approval | 📡✅ **Fire TV Stick (Vega)** — AFTCA002, fw 2101020054720<br>📡✅ **Fire TV Stick (Fire OS)** — AFTMA08C15, Fire OS 8.1.8.2 | ✅ [Amazon Fire TV for iOS](https://apps.apple.com/app/id947984433) · [report](manual-validation.md#ledger)<br>🔬 [unit and replay tests](tests/firetv.md) |
| **[webOS TV](platforms/webos.md)** | N/A | SSAP over WSS **3001**, IME keyboard, pointer socket, DLNA renderer | SSDP from **four independent stacks**, each with its own UUID and ports | On-screen prompt, client key | 📡 **LG 43UQ81006LB**<br>📡 **LG 50UA75006LA**<br>📡 **Sencor SLE50Q871B**<br>📡 **Sencor SLE65Q871B** | 🔬 [unit and replay tests](tests/webos.md) |
| **[Android TV / Google TV](platforms/androidtv.md)** | N/A | Remote v2 over mutual TLS **6466**; DIAL and Cast launch validation; AirPlay identity | Bonjour `_androidtvremote2._tcp`, `_googlecast._tcp`, `_airplay._tcp`; DIAL/SSDP | Polo pairing on **6467** — six hex characters and a client certificate | 📡✅ **Xiaomi MiTV-MOEU0** — fw 7.00.956317615<br>📡 **TCL Android TV** — C06, AR2101<br>📡 **KIVI Mediatek MTXXXX** (2 captures)<br>📡✅ **Google Chromecast HD** — Google TV, Android 14<br>📡 **Nokia Streaming Stick 800** — SEI Robotics, Android 11 | ✅ [Google TV for iOS](https://apps.apple.com/app/id746894884) · [report](manual-validation.md#ledger)<br>🧪 [androidtvremote2](https://github.com/tronikos/androidtvremote2) · [report](clients/androidtv.md#androidtvremote2)<br>🔬 [unit and replay tests](tests/androidtv.md) |
| **[Vizio SmartCast](platforms/vizio.md)** | N/A | SmartCast REST over HTTPS **7345** | DIAL/SSDP, description on **56790** | Four-digit PIN, then `AUTH_TOKEN` | 📡 **Vizio D24f-J09** — fw 3.3.3-2538.0001 | 🔬 [unit and replay tests](tests/vizio.md) |
| **[VIDAA (Hisense)](platforms/vidaa.md)** | N/A | MQTT over TLS **36669** — keys, app and source lists, Live TV channels | **None.** The set answers no SSDP and no mDNS; a client reaches it by address after probing the UPnP description on **18400** | On-screen PIN, then access and refresh tokens | 📡 **Hisense 32A3HE** — VIDAA U7, fw V0007.09.60U.Q0609 | 🔬 [unit and replay tests](tests/vidaa.md) |
| **[Philips JointSpace](platforms/philips.md)** | N/A | JointSpace v6 over HTTPS **1926** and HTTP **1925** | SSDP/UPnP; Bonjour `_philipstv_rpc._tcp` | Four-digit PIN, then HTTP Digest | 📡✅ **Philips 32PHS6000/12** — JointSpace 6.1 | ✅ [Philips TV Remote for iOS](https://apps.apple.com/gb/app/philips-smart-tv/id1479155903) · [report](manual-validation.md#ledger)<br>🔬 [unit and replay tests](tests/philips.md) |
| **[Samsung Tizen](platforms/tizen.md)** | N/A | `samsung.remote.control` over WSS **8002**, base64 text input; device API **8001** | **None captured.** The sets run SSDP, but the ordered headers were never saved, so a client reaches them by address | On-screen Allow prompt, then an eight-digit token | 📡 **Samsung UE65U8072F** — 25_KSUE_UB<br>📡 **Samsung UE55DU7172U** — 24_KANTSU2E_UB<br>📡 **Samsung UE43CU7172U** — 23_KSUE_UB_T09 | 🔬 [unit and replay tests](tests/tizen.md) |
| **[Samsung Smart TV (2014–15)](platforms/orsay.md)** | N/A | Encrypted Socket.IO 0.9 companion channel **8000**; multiscreen API **8001** | SSDP: four captured stacks, descriptions on **7676** | Four-digit on-screen PIN, then SPC key exchange on **8080** | 📡 **Samsung UE48H6200** — 14_X14, MSF 2.0.24 | 🔬 [unit and replay tests](tests/orsay.md) |
| **[Sony BRAVIA](platforms/bravia.md)** | N/A | ScalarWebAPI JSON-RPC and IRCC over HTTP **80**; Simple IP Control **20060**; Android TV Remote **v1 only** over TLS **6466** | SSDP: four captured stacks; Bonjour `_androidtvremote._tcp` (no `_androidtvremote2`) | Four-digit PIN for an `auth` cookie; Polo v1 on **6467** — four hex symbols and a client certificate | 📡 **Sony KDL-55W807C** — BRAVIA 2015, Android 7.0<br>📡 **Sony KDL-32WD600** — BRAVIA 2016, Linux; discoverable, no remote protocol | 🔬 [unit and replay tests](tests/bravia.md) |
| **[Metz Classic](platforms/metz.md)** | N/A | RCRService SOAP over HTTP **49200** | SSDP `upnp:rootdevice`, deviceType `RemoteControlReceiver:1` | None | 📱 **Metz Classic** — MetzRemote iOS app, no set measured | 🔬 [unit and replay tests](tests/metz.md) |
| **[TCL nScreen](platforms/nscreen.md)** | N/A | nScreen XML actions over TCP **4123**; no pairing | SSDP: two captured stacks (MediaRenderer on **49152**, DIAL description on **56790**) | None | 📡 **TCL H32S5916** — Linux 3.10, MediaTek MT5655 (not Roku, not Android TV) | 🔬 [unit and replay tests](tests/nscreen.md) |
| **[Panasonic VIERA](platforms/viera.md)** | N/A | NRC, renderer volume and PAC over HTTP **55000**; pointer and gamepad frames on TCP **55010** | SSDP `urn:panasonic-com:service:p00NetworkControl:1`, `p00RemoteController:1`, or a search by UDN | None on the older device; a four-digit PIN with AES-encrypted sessions on the newer one | 📱✅ **Panasonic VIERA, no PIN** — NRC-2 firmware; Panasonic TV Remote 2 (2.73) and 3 (1.01) for iOS, no set measured<br>📱✅ **Panasonic VIERA, PIN** — NRC-4 firmware with a PIN and encrypted sessions; Panasonic TV Remote 3 for iOS, no set measured | ✅ [Panasonic TV Remote 3 for iOS](https://apps.apple.com/app/id1435893441) · [report](manual-validation.md#ledger)<br>✅ [Panasonic TV Remote 2 for iOS](https://apps.apple.com/app/id590335696) · [report](manual-validation.md#ledger)<br>🔬 [unit and replay tests](tests/viera.md) |
<!-- /generated -->

Between them they cover Roku's ECP-2 challenge–response, Amazon's PIN and client token, LG's
on-screen prompt and client key, Android TV's Polo certificate exchange, Vizio's PIN and
`AUTH_TOKEN`, VIDAA's access and refresh tokens, Philips' PIN and HTTP Digest, Samsung's
Allow prompt and eight-digit token, Sony's PIN and auth cookie — plus the captured failures
rather than only the happy path: the Philips set that answers 404 for `powerstate`, the
Fire TV that accepts a wrong PIN with 200, the Turnstile port that stays shut until a DIAL
launch opens it.

Each television has an overview under [`platforms/`](platforms): its protocols and ports, the
captured devices, the firmware behaviours a driver usually gets wrong, and what the emulator
lets you test.

## By wire protocol

Every wire protocol the emulator speaks, and which television speaks it.

| Wire protocol | Television | Transport · port | What is served |
|---|---|---|---|
| **ECP** (External Control Protocol) | Roku | HTTP 8060 | `keypress`/`keydown`/`keyup`, `launch`, captured UPnP and SCPD documents |
| **ecp-2** | Roku | WebSocket on 8060, subprotocol `ecp-2` | Challenge–response auth, serialized commands, device queries, ping/pong |
| **SSDP** `roku:ecp` | Roku | UDP 239.255.255.250:1900 | M-SEARCH replies in the captured header order |
| **Turnstile** | Fire TV · N/A | HTTPS 8080 | Amazon control API, PIN pairing, app launch; the port stays shut until a DIAL launch opens it |
| **ADB** (legacy shell) | Fire TV · N/A | TCP 5555 | `am start` / `monkey -p`, public-key authorization; off by default, as on a shipped stick |
| **DIAL** | Fire TV · N/A | HTTP 8009 | App state `GET`, launch `POST` |
| **UPnP `dd.xml`** | Fire TV · N/A | HTTP 60000 | The device description the DIAL search target points at |
| **Bonjour / mDNS** `_amzn-wplay._tcp` | Fire TV · N/A | UDP 5353, advertises 39187 | WhisperPlay registration with captured TXT records |
| **SSAP** | webOS · N/A | WSS 3001 | `register`, `ssap://` requests, subscriptions, IME keyboard, pointer input socket |
| **Second screen** UPnP | webOS · N/A | HTTP 1948 / 1382 / 1406 / 1102 | `urn:lge-com:service:webos-second-screen:1` description |
| **DIAL** | webOS · N/A | HTTP 1633 / 1209 / 1985 / 1475 | Device description and the `Application-URL` header |
| **DIAL apps** | webOS · N/A | HTTP 36866 | Captured per-application state documents |
| **DLNA MediaRenderer** | webOS · N/A | HTTP 1384 / 1431 / 1678 / 1175 | Description, SCPDs, and the volume and transport actions that move device state |
| **Virtual service** `urn:lge:device:tv:1` | webOS · N/A | HTTP 1998 / 1574 / 1708 / 1848 | The fourth description the set publishes |
| **SSDP** ×4 stacks | webOS · N/A | UDP 1900 | One reply per stack, each with its own UUID and `SERVER` header |
| **Android TV Remote Service v2** | Android TV · N/A | mutual TLS 6466 | Protobuf keys, IME text, state updates, voice, keepalive |
| **Wake service** | Android TV · N/A | TLS 6465 | Reproduces the captured certificate-rejection boundary |
| **Pairing v2** (Polo) | Android TV · N/A | mutual TLS 6467 | Six-hex on-screen code, client certificate exchange |
| **AirPlay** | Android TV · N/A | HTTP 7000 | Read-only `/info` identity |
| **Cast HTTP / DIAL** | Android TV · N/A | HTTP 8008, or 56790 on the KIVI sets | DIAL description, app root, Cast setup identity |
| **Google Cast** | Android TV · N/A | TLS 8009 | Receiver status and application launch |
| **Cast setup** | Android TV · N/A | HTTPS 8443 | Detailed setup identity |
| **Bonjour / mDNS** | Android TV · N/A | UDP 5353 | `_androidtvremote2._tcp`, `_googlecast._tcp`, `_airplay._tcp` with their live ports |
| **SmartCast REST** | Vizio · N/A | HTTPS 7345 | Pairing, device state, key commands, app launch |
| **UPnP `dd.xml`** | Vizio · N/A | HTTP 56790 | DIAL device description |
| **VIDAA MQTT/TLS** | VIDAA · N/A | MQTT over TLS 36669 | PIN pairing, access and refresh tokens, keys, app and source lists, broadcast state |
| **UPnP `dd.xml`** (`#CAP#`) | VIDAA · N/A | HTTP 18400 | The MediaRenderer description whose `#CAP#` block tells a client which credential dialect this firmware accepts |
| **JointSpace v6** | Philips · N/A | HTTPS 1926 | PIN pairing, Digest auth, control API |
| **JointSpace v6** | Philips · N/A | HTTP 1925 | Public version probes, authenticated `notifychange` |
| **UPnP MediaRenderer** | Philips · N/A | HTTP 49152 | Captured device description |
| **Cast wake** | Philips · N/A | HTTP 8008 | The wake endpoint used before a JointSpace power request |
| **Bonjour / mDNS** | Philips · N/A | UDP 5353 | `_philipstv_rpc._tcp` 1925, `_philipstv_s_rpc._tcp` 1926, `_googlecast._tcp` 8009 |
| **`samsung.remote.control`** | Tizen · N/A | WSS 8002 | Allow prompt and the eight-digit token, keys, base64 text input, installed-app list, `ed.apps.launch` |
| **Samsung device API** | Tizen · N/A | HTTP 8001 | Unauthenticated `/api/v2/` identity document, REST app launch |
| **DIAL description** | Tizen · N/A | HTTP 7678 | Captured receiver description with the `sec:` extensions |
| **SPC pairing** | Samsung 2014–15 · N/A | HTTP 8080 | DIAL `CloudPINPage`, the three-step PIN-keyed key exchange, session ids |
| **Samsung companion channel** | Samsung 2014–15 · N/A | Socket.IO 0.9 on 8000 | AES-128-ECB `callCommon` / `receiveCommon` events, `SendRemoteKey`, heartbeat |
| **Samsung multiscreen API** | Samsung 2014–15 · N/A | HTTP 8001 | `/ms/1.0/` and `/api/v2/` identity, application probe, launch and close |
| **Sony ScalarWebAPI** | Sony BRAVIA · N/A | HTTP 80 | JSON-RPC for identity, power, volume, inputs and applications; `actRegister` PIN registration and its cookie |
| **IRCC** | Sony BRAVIA · N/A | HTTP 80 | `X_SendIRCC` SOAP with the codes `getRemoteControllerInfo` lists |
| **Simple IP Control** | Sony BRAVIA · N/A | TCP 20060 | 24-byte frames for power, volume, mute, input and picture mute; notifications to every connection |
| **Android TV Remote v1** | Sony BRAVIA · N/A | TLS 6466 | Binary key and intent frames with the paired certificate |
| **Pairing v1** (Polo) | Sony BRAVIA · N/A | TLS 6467 | JSON Polo, four-hex on-screen code |
| **RCRService SOAP** | Metz · N/A | HTTP 49200 | Description, SCPD, keys by Metz key code, whole-string text |
| **SSDP** `upnp:rootdevice` | Metz · N/A | UDP 1900 | The one deviceType the MetzRemote app lists |
| **nScreen remote** | TCL nScreen · N/A | TCP 4123 | `setKey` and `sendCommand` XML actions, `noop` keep-alive, one acknowledgement per read |
| **UPnP MediaRenderer** | TCL nScreen · N/A | HTTP 49152 | Description, three SCPDs and the read-only calls captured |
| **DIAL** | TCL nScreen · N/A | HTTP 56789, description on 56790 | Application state; a launch is refused |
| **SSDP** ×2 stacks | TCL nScreen · N/A | UDP 1900 | The renderer's six targets, and DIAL on its own |
| **NRC SOAP** | Panasonic VIERA · N/A | HTTP 55000 | `NRC_*` keys, text, app list and launch; PIN pairing and encrypted sessions on the newer device |
| **Renderer, PAC and events** | Panasonic VIERA · N/A | HTTP 55000 | Volume and mute on `/dmr`, inputs and picture modes on `/pac`, UPnP eventing |
| **Pointer socket** | Panasonic VIERA · N/A | TCP 55010 | Touchpad and gamepad frames, recorded |
| **SSDP** | Panasonic VIERA · N/A | UDP 1900 | `p00NetworkControl`, `p00RemoteController`, `upnp:rootdevice`, and a search by UDN |

Also spoken, as part of the rows above: **UPnP/SSDP**, **DIAL**, **mDNS/Bonjour (DNS-SD)**,
**DLNA**, **Google Cast**, **AirPlay**, **Polo pairing**, **HTTP Digest**, **MQTT**,
**WebSocket**, **mutual TLS** and **ADB**.
