# Manual validation against real apps

The emulator's answers come from captures of physical hardware, and most of them were probed
by hand. That proves a set answers a request; it does not prove a real remote app sends that
request, in that shape, with those values. Manual validation closes the gap: a person drives
the emulator with the app a user actually has, and the event log says what arrived.

This page is the ledger of those sessions and the method for adding one. A test that passes
here means a real client worked against the emulator on that date. It is not a claim about
every firmware or every app version.

Open-source client libraries are run against the emulator too, automatically and with a record
per run; that is a different kind of fact, *exercised* rather than validated, and it lives in
[Open-source clients](open-source-clients.md), never in this ledger.

## Ledger

One row per app and profile. A newer session with the same app replaces its row; earlier
sessions stay in the television's full driver guide.

| Television | App | Date | Profile | Status |
|---|---|---|---|---|
| Amazon Fire TV | Amazon Fire TV for iOS **4.8.0 (1226009657)**, iPhone | 2026-09-29 | `fire-tv-stick-vega-aftca002` | **Full support** of the remote surface the app uses; channel buttons not told apart from a swipe, listed in the [Fire TV guide](platforms/firetv.md#support-and-validation) |
| Amazon Fire TV | the same app | 2026-09-29 | `fire-tv-stick-fireos-aftma08c15` | **Full support** on this profile too, voice included |
| Android TV / Google TV | Google TV for iOS **3.33.00001**, iPhone | 2026-09-30 | `google-chromecast-hd` | **Supported**: pairing, remote buttons and voice; text and app links not validated, listed in the [Android TV guide](platforms/androidtv.md#support-and-validation) |
| Android TV / Google TV | the same app | 2026-09-30 | `xiaomi-mitv-moeu0` | **Supported** too, including the app's wake step before the remote session |
| Philips | Philips TV Remote for iOS, build **20979** (`com.tpvison.pst`), iPhone | 2026-09-30 | `philips-32phs6000-12` | **Supported**: discovery, PIN pairing, remote buttons and the state long poll, listed in the [Philips guide](platforms/philips.md#support-and-validation) |
| Panasonic VIERA | Panasonic TV Remote 3 for iOS **1.01 (1.02.05)**, iPhone | 2026-10-05 | `panasonic-viera-nrc` | **Supported**: cold-start discovery, remote buttons and the App Launcher list; launching an app not confirmed, cast photo needs a DLNA renderer, listed in the [VIERA guide](platforms/viera.md#support-and-validation) |
| Panasonic VIERA | the same app | 2026-10-05 | `panasonic-viera-pin-nrc` | **Supported**: the PIN dialog, pairing, the encrypted session and remote buttons; the pairing outlives an emulator restart |
| Panasonic VIERA | Panasonic TV Remote 2 for iOS **2.73 (2.73.01)**, iPhone | 2026-10-05 | `panasonic-viera-nrc` | **Supported**: discovery and remote buttons; touchpad and gamepad not validated |
| LG webOS | LG ThinQ for iOS, build **162** (`com.lgeha.nuts`), iPhone | 2026-10-13 | `lg-webos-tv-uq81006lb` | **Supported**: discovery, PIN pairing, adding the set, the remote (pointer buttons, touchpad, volume, channels), app launches, power-off and the voice button; power-on is Wake-on-LAN, which the emulator does not answer, listed in the [webOS guide](platforms/webos.md#support-and-validation) |
| Roku | Roku for Android **14.1.2**, phone | 2026-10-17 | `tcl-roku-tv-32s357` | **Supported**: discovery, the `ecp-2` session (its `authenticate` carries request id `"0"`), the remote buttons, volume, channel launches and reconnecting; channel icons, private listening and the text field not emulated, listed in the [Roku guide](platforms/roku.md#support-and-validation) |
| Roku | Roku for Android **14.1.2.10730047**, phone | 2026-10-18 | `roku-streaming-stick-4k-3820eu2` | **Partially validated**: discovery, authentication, Headphone Mode with an audible test tone, then audible playback and switching it off. Recovery under packet loss, RTP, text and additional settings not validated; details in the [Roku guide](platforms/roku.md#support-and-validation) |
| Roku | Roku for Android **14.1.2.10730047**, phone | 2026-10-19 | `roku-streaming-stick-4k-3820eu2` | **Partially validated**: opening the set's own text field, whole-text writes from the app, Unicode updates from the dashboard to the app, closing and reopening the field. With no field open the app sends text as literal keys, in order when typed at a normal pace. Hidden fields and other field types not validated; details in the [Roku guide](platforms/roku.md#support-and-validation) |
| Xiaomi Mi TV | Xiaomi TV Assistant for Android **2.7.6 (2023111014)**, phone | 2026-10-19 | `xiaomi-mitv-tva-modelled` | **Partially validated**: discovery, the remote screen, arrows, OK, Home, Back and volume. The installed-apps list is not emulated; no physical TV measured. See the [Mi TV guide](platforms/mitv.md#support-and-validation) |
| Xiaomi Mi TV | the same app | 2026-10-19 | `xiaomi-mitv-airkan-modelled` | **Partially validated**: PIN pairing, reconnecting, arrows, OK, Home, Back, Menu and volume. The installed-apps list is not emulated; no physical TV measured. See the [Mi TV guide](platforms/mitv.md#support-and-validation) |
| Samsung | Samsung Smart View for Android **2.1.0.112 (2018083061)**, phone | 2026-10-19 | `samsung-iapp-tv-modelled` | **Partially validated**: discovery, the Allow prompt, keys, volume and mute, opening the keyboard, submitting text and closing it. No physical TV measured; the year mapping is representative. See the [Samsung guide](platforms/samsung.md#support-and-validation) |
| Samsung | the same app | 2026-10-19 | `samsung-iapp-aes-tv-modelled` | **Partially validated**: the Allow prompt, opening and closing the keyboard, submitting text and Unicode text shown back in the app. No physical TV measured. See the [Samsung guide](platforms/samsung.md#support-and-validation) |
| Samsung | Samsung Smart View for Android **2.1.0.112 (2018083061)**, phone | 2026-10-20 | `samsung-orsay-tv-ue48h6200` | **Partially validated**: discovery, PIN pairing, the remote connection, volume up and down, mute and arrows. Keyboard, touch, media and app launch not validated. See the [Samsung guide](platforms/samsung.md#support-and-validation) |
| Samsung | the same app | 2026-10-20 | `samsung-tizen-pin-tv-ue48ju6400-modelled` | **Partially validated**: discovery of the modelled UE48JU6400, PIN pairing and the remote: volume up and down, mute, Home and arrows. No physical J-series set measured; keyboard, touch and launch not exercised. See the [Samsung guide](platforms/samsung.md#support-and-validation) |
| Samsung | Samsung Smart View for Android **2.1.0.112 (2018083061)**, phone | 2026-10-20 | `samsung-iapp-improved-tv-modelled` | **Partially validated**: discovery, the Allow prompt, volume, mute and arrows, the keyboard, Unicode text and submitting it, and reconnecting after an app restart. No physical TV measured; touch and other apps not exercised. See the [Samsung guide](platforms/samsung.md#support-and-validation) |
| Samsung | Samsung Smart View for Android **2.1.0.112 (2018083061)**, phone | 2026-10-20 | `samsung-orsay-tv-ue46f8000-sek2000-modelled` | **Partially validated**: discovery, PIN pairing, the remote connection, volume up and down, mute, arrows, Smart Hub and channel up. No physical Evolution Kit measured; reconnecting with a saved PIN after an app restart, keyboard, touch and media not exercised. See the [Samsung guide](platforms/samsung.md#support-and-validation) |

Platforms with no row have not been recorded here yet, which says nothing about whether they
work.

## What a session establishes

Each session ends with every behaviour of the app in one of three states, and the
television's full driver guide lists them under those names:

- **Validated**: the app sent it, the emulator answered, and the app carried on. The event
  log shows the exchange.
- **Observed, unconfirmed**: the app sent it and the emulator accepted it, but what the real
  device does with it was not measured. The emulator's behaviour is a stated assumption.
- **Not exercised**: nobody pressed the button. Nothing is claimed.

Only a session with the app moves a behaviour to *validated*; the project's own tests do not.

## Method

1. **Restart the emulator** on the build under test, on the LAN address the phone can reach:
   `python -m tvemu --platform <id> --bind <lan-ip>`. A running process keeps the code it
   started with, and a session against an old one proves nothing about the new one.
2. **Clear the event log** in the dashboard, so the export holds only the session.
3. **Work through the app's own surface, screen by screen**, not the emulator's list of keys:
   pairing, every remote button, media controls, text entry with a field open, the microphone,
   opening a title or an application, discovery after the app is closed and reopened. Press
   each button on its own, as well as in a sequence, so a request can be tied to a button.
4. **Export the log** (`Export` in the dashboard, or `GET /api/v1/events/export`) and read, in
   this order:
   - `unsupported` events: a route, action or body the app used and the emulator refused. The
     detail carries the method, path, query, content type and the start of the body;
   - `request` events: what a key or command carried besides its name;
   - `application`, `voice` and `text` events: the launch payload, the audio channel and the
     text that arrived.
5. **Turn each finding into evidence or a claim**, not a guess: a new shape goes into a test
   that names the app and the date, and into the television's guide. A value that identifies
   the person or the session (an account id, a session id, a token) is masked by the emulator
   and is not copied into a test, a guide or this page.
6. **Record the session here**: the app and its version, the date, the profile, and the
   validated, observed and not-exercised lists.

## Notes for the person driving

- The phone and the emulator must share a network where multicast works if the app discovers
  the device; an app that connects by address needs nothing more.
- Switch the real television or stick off, or take it off the network, before the session, so
  its own discovery answers cannot race the emulator's.
- Press one thing, wait for the log to show it, then press the next. A log of five buttons
  pressed together cannot say which one sent what.
- The app's version is on its settings screen, and the client also says it in the
  `User-Agent` the emulator logs.
