# Adding your television

A television you own and want emulated can get here in two ways: you describe it and the
maintainer measures it with you, or you record it yourself and send a capture. Either way the
emulator ends up answering with the bytes your set sent, not with what someone expected it to
send.

This page covers a new **device** on a television family the emulator already speaks (a
different model or firmware) and a new **family** altogether. The code side of a new family is
in [Architecture: adding a television](architecture.md#adding-a-television).

## Describe it

Open an [issue with the television form](https://github.com/evilutioner/smart-tv-emulator/issues/new?template=television.yml), which asks for:

- the **brand, model number and firmware version**, from the set's own settings screen;
- the **remote app** you drive it with, and its version;
- whether you can **run commands on the same network** as the set (see below);
- what you need it for: a driver you are writing, an app you are testing, a library you
  maintain.

A family the build does not include yet, rather than a new device of an included one, goes
to the request link in the [README](../README.md#the-other-televisions) instead.

## What a capture is

A capture is one directory under `src/tvemu/platforms/<id>/evidence/<capture-id>/`: a
`capture.json` and, beside it, every body the set sent, byte for byte. `capture.json` says:

- **where it came from** — `source.kind` (`captured` off a set), the date, and a description
  of anything changed or left out;
- **who the set is** — display name, model, firmware, and the identifiers it announces;
- **which ports it used** — the protocols, which one is primary, the other ports found open;
- **how it is discovered** — the discovery answer it gave, or `platform.discovery` saying
  `none` (searched, nothing answered) or `pending` (still to be recorded);
- **the exchanges** — each request and the answer to it, in order, with status and headers.

Roku's captures under `src/tvemu/platforms/roku/evidence/` are complete worked examples, and
the [Roku guide](platforms/roku.md#evidence-and-device-profiles) explains how they are used.

## Recording one

You need a computer on the same network as the set, the set's address, and the set's remote
setting at its default.

1. **Discovery.** Send the search the family answers (for SSDP, an `M-SEARCH` to
   `239.255.255.250:1900` with its search target) and keep the full answer, headers included.
   No answer is a result too: write it down as `none`.
2. **Every document the protocol serves.** Request each one with `curl -i` (or the family's
   socket client) and keep the answer exactly as it arrived: status, headers and body, saved
   to a file without reformatting, re-indenting or re-encoding.
3. **The refusals.** An unknown key, a malformed request, a route that does not exist, and
   each value of the set's remote-control setting, if it has one. What a set refuses, and how,
   is as much a part of it as what it answers.
4. **What the app sends.** Point the app at the emulator running the nearest existing device,
   and read the `unsupported` events: each one is a request still to be measured on the set.
   The method is in [Manual validation](manual-validation.md#method).

## Before you send it

Every file in this repository is public, and the build fails on some of what a raw capture
carries. Replace, consistently across every file of the capture:

- **network addresses** — the set's LAN address is replaced wherever it appears; the SSDP
  `LOCATION` header, for example, becomes the `{location}` placeholder the emulator fills in;
- **hardware addresses** — a MAC becomes a locally administered one (`02:00:00:…`);
- **serial numbers, device ids, UDNs, account and session tokens** — with stable fake values
  of the same shape and length;
- **anything that names you or your household** — the set's friendly name, installed
  third-party apps you would rather not list.

Say in the capture's description what you replaced or removed. Never send a private key or a
certificate taken from the set.

## From capture to a selectable device

What happens to your capture after you send it:

1. The capture goes in as **evidence**. An incomplete one stays evidence only: it informs the
   contract but is never selectable.
2. A complete one gets a `profiles/<device-id>/profile.json` that references it, and appears
   under **Captured device** in the dashboard.
3. `tvemu --contract <id> --check` must pass. If your set contradicts a claim, the claim is
   fixed or narrowed; your capture is not edited.
4. The replay harness, `python -m tvemu.conformance`, sends each captured request to the
   emulator and compares the answer with your capture byte for byte.
5. The device is listed in the README's table as **captured**, and as **validated** only after a
   session with a real app ([ledger](manual-validation.md#ledger)).

## Not written yet

> **Gap:** a recording tool that walks a set's known documents and writes a `capture.json`
> directly; today the steps above are done by hand.

> **Gap:** a checker that scans a capture directory for real addresses and identifiers before
> it is sent, the way the build checks shipped files.

> **Gap:** licence terms for submitted captures. Until they are written, get in touch before
> sending one ([Contributing](../CONTRIBUTING.md)).
