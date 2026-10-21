# Testing a remote app by hand

This page is for a tester with a phone, a build of a remote-control app and no television on
the desk. The emulator stands in for the set: the app finds it, pairs with it and drives it as
it would a real one, and the dashboard shows what every tap sent. Nothing in the app changes
for the test.

What the emulator cannot tell you is how the picture on a real screen reacts: it records
commands and keeps simple state (power, volume, mute, the last application launched), it does
not render anything. Where a television's own guide says a document is *captured* rather than
live, it stays as it was recorded whatever the app does.

## Before the session

1. **Start it on an address the phone can reach.** `tvemu` picks one and shows it as
   `Device:` in the dashboard; pass `--bind <lan-ip>` when a VPN or a second adapter makes
   the choice ambiguous.
2. **Share one network with the phone.** The phone and the computer must be on the same Wi-Fi
   or LAN, and that network must let clients see each other and pass multicast: guest
   networks and *client isolation* (common on office and hotel Wi-Fi) hide the emulator from
   discovery.
3. **Take the real television off the network,** if there is one, so its own discovery answers
   cannot race the emulator's.
4. **Pick what the app should see.** In **Configuration**, choose the **TV platform** and the
   **Device**: each one is a real model on a real firmware, and switching between
   them is how one build is tested against several firmwares. Switching closes the app's
   open sessions, as unplugging a set would.
5. **Clear the event log,** so the export you attach to a bug holds only this session.

## What to go through

Work through the app's own screens rather than the emulator's list of keys, and press one
thing at a time, waiting for it to appear in the log before the next.

- [ ] **Discovery** — the app finds the set from cold, and again after the app is killed and
      reopened.
- [ ] **Pairing** — the first connection, the PIN or the prompt where the television has one,
      a wrong or cancelled PIN, and a second launch that should reuse the pairing.
- [ ] **Remote buttons** — every button on its own: the **Device state** card lights the button
      and counts it. A long press, where the app has one, should show as held.
- [ ] **Text entry** — with a field focused from the **Keyboard** tile, where the television
      has a keyboard.
- [ ] **Launching an application** — the dashboard shows the launch payload the app sent.
- [ ] **Voice** — where the television offers it: the log shows the audio channel open and close.
- [ ] **Recovery** — the app after a forced disconnect, after a protocol is switched off and on,
      and after the emulator is restarted.

The guide for each television (from the [table in the README](../README.md#televisions))
ends with a **Manual acceptance** list for that set; use it alongside this one.

## Reproducing conditions

These are the conditions a real set produces that are hard to stage with one in the room:

| To reproduce | In the dashboard |
|---|---|
| A set whose remote-control setting is restricted | The access-mode selector under **TV behaviour** (on Roku, **Control by mobile apps**), shown when the firmware has more than one mode; the television's guide says what each mode refuses |
| A port that is closed or a service that is off | Switch that one protocol off under **Protocols**; only its port closes and only its sessions drop |
| The connection dropping mid-session | **Disconnect device clients**; the port stays open for the app to reconnect |
| A set that was just switched on | **Reset device state** (counters, held keys, power and volume; settings stay) |
| A different model or firmware | **Device** |

Every one of them is also a call on the [management API](dashboard-and-api.md#management-api),
so a case found by hand can later become an automated one ([CI](ci.md)).

## Reading the log and filing a bug

Each line in the **Event log** is one thing that happened, with its kind, transport, client
address and status. The kinds worth reading first:

- `unsupported` — the app asked for something the emulator does not answer. The detail holds
  the method, path and the start of the body. This is either a gap in the emulator or a request
  a real set would refuse too; the television's guide usually says which.
- `rejected` and `access` — a refusal, and the reason or the access mode that caused it.
- `command`, `request` — a key or command, and what it carried besides its name.
- `pairing`, `connection`, `disconnect` — the session's life.

A bug report about the app is most useful with:

- the **exported log** (**Export** in the dashboard, or `GET /api/v1/events/export`), as JSONL;
- the **TV platform and captured device** it ran against, from the **Configuration** card;
- the **app version** (it is usually also in the `User-Agent` the log records);
- the **emulator version**: `pip show smart-tv-emulator`.

A bug in the emulator itself — an answer you can show a real set gives differently — goes to
the [bug form](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=bug.yml) with the same four
things.

## When the app does not find it

- `Device:` in the dashboard is not on the phone's network: restart with `--bind <lan-ip>`.
- The network isolates clients or blocks multicast: try a phone hotspot, or a network you
  control.
- A macOS or Windows firewall is blocking incoming connections for Python: allow it.
- The discovery protocol is switched off under **Protocols**.
- The app connects by address and never discovers: type in the address `Device:` shows.

## Not written yet

> **Gap:** network faults — added latency, dropped or slow answers, a pairing prompt that times
> out on demand — cannot be injected yet; only whole protocols can be switched off.

> **Gap:** test-case lists per television beyond each guide's **Manual acceptance**, kept
> as reusable checklists.

> **Gap:** several televisions at once, as a home with two sets would show the app.
