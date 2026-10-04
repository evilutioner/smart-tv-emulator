# Manual validation against real apps

The emulator's answers come from captures of physical hardware, and most of them were probed
by hand. That proves a set answers a request; it does not prove a real remote app sends that
request, in that shape, with those values. Manual validation closes the gap: a person drives
the emulator with the app a user actually has, and the event log says what arrived.

This page is the ledger of those sessions and the method for adding one. A test that passes
here means a real client worked against the emulator on that date. It is not a claim about
every firmware or every app version.

## Ledger

One row per platform and app. A newer session on the same app replaces its row; the older one
stays in the platform's own guide.

| Television | App | Date | Profile | Status |
|---|---|---|---|---|
| Fire TV | Amazon Fire TV for iOS **4.8.0 (1226009657)**, iPhone | 2026-09-29 | `fire-tv-stick-vega-aftca002` | **Full support** of the remote surface the app uses; channel buttons not told apart from a swipe, listed in the [Fire TV guide](platforms/firetv.md#support-and-validation) |
| Fire TV | the same app | 2026-09-29 | `fire-tv-stick-fireos-aftma08c15` | **Full support** on this profile too, voice included: the app opens the same 9090 WebSocket |
| Android TV / Google TV | Google TV for iOS **3.33.00001**, iPhone | 2026-09-30 | `google-chromecast-hd` | **Supported**: pairing, remote buttons and voice; text and app links not validated, listed in the [Android TV guide](platforms/androidtv.md#support-and-validation) |
| Android TV / Google TV | the same app | 2026-09-30 | `xiaomi-mitv-moeu0` | **Supported** too: the app opens the advertised wake port 6465 before its 6466 session |
| Philips JointSpace | Philips TV Remote for iOS, build **20979** (`com.tpvison.pst`), iPhone | 2026-09-30 | `philips-32phs6000-12` | **Supported**: discovery, PIN pairing, remote buttons and the state long poll, listed in the [Philips guide](platforms/philips.md#support-and-validation) |

Platforms with no row have not been recorded here yet, which says nothing about whether they
work.

## What a session establishes

Each session ends with every behaviour of the app in one of three states, and the platform
guide lists them under those names:

- **Validated**: the app sent it, the emulator answered, and the app carried on. The event
  log shows the exchange.
- **Observed, unconfirmed**: the app sent it and the emulator accepted it, but what the real
  device does with it was not measured. The emulator's behaviour is a stated assumption.
- **Not exercised**: nobody pressed the button. Nothing is claimed.

A behaviour is never moved to *validated* on the strength of a test written by the emulator's
author. Only a session with the app can do that.

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
5. **Turn each finding into evidence or a claim**, never into a guess: a new shape goes into a
   test that names the app and the date, and into the platform guide. A value that identifies
   the person or the session (an account id, a session id, a token) is masked by the emulator
   and is never copied into a test, a guide or this page.
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
