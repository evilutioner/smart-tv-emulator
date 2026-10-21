# Samsung

> **N/A in this build.** Written and tested against physical hardware; the emulator,
> its captures and the full driver guide are available on request —
> [ask about Samsung](https://marchik.dev).

Samsung televisions from 2011 to 2025, one profile per remote generation: the legacy remote on
TCP 55000, the 2014–16 PIN pairing with an encrypted companion channel, and the Tizen remote
channel with its Allow prompt. Four sets are captured; the rest are modelled from the apps
and libraries that drive them, and from what owners of real sets reported.

## Protocols

| Protocol | Generation | Transport · port | What is emulated |
|---|---|---|---|
| Tizen remote channel | 2015–25 | WSS 8002, WS 8001 | Allow prompt, token, keys, text, keyboard events, voice, applications |
| Device API | 2015–25 | HTTP 8001 | identity, power state, application launch |
| DIAL and MediaRenderer | 2015–25 | HTTP 7678, 8080, 9197 | descriptions and application documents |
| PIN pairing | 2014–16 | HTTP 8080 | the on-screen PIN |
| Companion channel | 2014–16 | Socket.IO on 8000 | encrypted keys and text |
| UPnP and MainTVAgent2 | 2014–15 | HTTP 7676, 9090 | descriptions, read-only actions behind their own Allow prompt, channel list |
| Legacy remote | 2011–13 | TCP 55000 | Allow prompt, keys, text and touch |
| Legacy HTTP remote | 2014, modelled | HTTP 8080 | keys, text, pointer and keyboard polling |
| Wake and SSDP | all | UDP 2014, 1900 | wake from standby; each set's own discovery stacks |

## Captured devices

- **Samsung UE65U8072F** — Tizen, 2025
- **Samsung UE55DU7172U** — Tizen, 2024
- **Samsung UE43CU7172U** — Tizen, 2023
- **Samsung UE48H6200** — 2014 H series, PIN pairing

## Modelled devices

No set of these was measured here. Each is built from the client contracts of the apps that
drive one and from owner reports of real sets, and every answer is emulator-owned.

- **2011 D, UE40D5700** — legacy remote on 55000
- **2012 E, UE40ES5700** — legacy remote on 55000 with encrypted text
- **2013 F, UE40F6400** — legacy remote with an encrypted session
- **2013 F, UE46F8000 + SEK-2000** — Evolution Kit: PIN pairing and the companion channel,
  like a 2014 set
- **2014 H, UE40H6400** — **experimental**: the legacy HTTP remote
- **2014 H, UN40H5203** — pairs, but offers no remote, like the low-end sets of that year
- **2015 J, UE48JU6400** — PIN pairing; the Tizen channel admits and refuses every key
- **2016 K, UE43KU6079** — Allow prompt without a token
- **2016 K, UN55KU6290** — PIN pairing; the Tizen channel times out at once. Smart View 2.1
  takes every 2016 set to that channel and fails, as on the real set; samsungtvws pairs by PIN

The 2013 F models were checked with Smart View 2.1 on Android: discovery, the Allow prompt or
the PIN, keys, the keyboard, text and reconnecting worked. No physical 2013 set was measured.

## What the emulator reproduces

Behaviours of the real firmware the emulator reproduces, named here without their detail. The
full guide gives each one, tied to the capture or report it came from.

- **One remote per generation**, chosen by the profile, not guessed from the OS or the year.
- **The Allow prompt, refused and expired**, as two different answers.
- **2015–16 sets that admit a client and still refuse it**, or time out instead of asking.
- **Requests the set ignores** stay unanswered rather than refused.
- **Low-end sets with no remote at all**, as their owners found them.

## What the emulator lets you test

- [x] The Allow prompt: accept, deny, timeout, and returning with a token
- [x] PIN pairing and the encrypted companion channel
- [x] Re-pairing after a cold boot, and retrying while the companion channel starts
- [x] Keys, text and the keyboard on every generation
- [x] Application lists, probes and launches
- [x] Power on, standby and off, and waking a set that is off
- [x] Discovery and the UPnP descriptions each generation serves
- [x] Telling 2014–16 sets apart by how they answer, not by their model year

## Support and validation

Samsung Smart View for Android was run against the emulator by hand, and the
[manual validation ledger](../manual-validation.md) has the rows: the 2011 and 2012 legacy
remotes, the 2014 H6200's PIN pairing and the 2015 J model's. The open-source clients
samsungctl and samsungtvws are run against it as well.

## Get access

Commercial licence, private access to the emulator, or help wiring it into your tests:
[get in touch](https://marchik.dev) and say what you are building.
