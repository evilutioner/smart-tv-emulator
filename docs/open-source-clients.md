# Open-source clients

Open-source remote libraries were written against real televisions by people who owned them.
Running them against the emulator is a cheap second opinion: an independent reading of the
same protocol, re-run whenever either side changes. This page explains how such a run works,
what it establishes and how to add a client. The results are listed per television under
[`docs/clients/`](clients).

## What a run establishes

A passing run means the client, at that version, did what its binding asked against the
emulator at that version. Every request it sent has a captured answer, or is a declared gap,
and the event log shows what the binding expected.

It does **not** make a behaviour *validated*. Validation takes a session with the app a user
actually has; that is the [manual validation ledger](manual-validation.md), and the project's
own tests, bindings included, do not move a row there. A client run is a third kind of fact,
beside *captured* and *validated*: the behaviour was **exercised** by a named client at a
named version on a named date.

## Running one

```sh
python -m tvemu.clients list
python -m tvemu.clients run roku/rokuecp                    # the last green version
python -m tvemu.clients run roku/rokuecp --version latest   # whatever upstream ships today
python -m tvemu.clients run roku/rokuecp --record           # keep it under docs/clients/
python -m tvemu.clients report                              # re-render the pages
```

A run downloads the client, so it is never part of the offline gates. It creates one
temporary directory and removes it afterwards:

- **The client** is installed in a fresh virtual environment, or for an npm client a fresh
  private npm project with install scripts switched off. Either holds the client and its
  dependencies and nothing of the emulator. The upstream source is never copied into this
  repository.
- **The emulator** runs as its own `tvemu` process on loopback, with a settings file of its
  own, exactly as anybody starts it. The two meet only on the wire and at `/api/v1`.
- **The binding** runs with a minimal environment: no credentials, no proxy settings and
  no user site-packages, only the device address, the management API and a results file.

`--events DIR` keeps each profile's event log. `--profile` drives one profile; such a run
cannot be recorded, because a record covers every profile the client declares.

## The verdict

A run is judged from three sides, per profile:

1. **The client.** Each step the binding reports: the library call returned and what it
   parsed matches the emulator's state.
2. **The emulator.** The client's `expect.json`, checked over the event log with
   [`tvemu.expect`](writing-a-driver.md).
3. **The wire.** Every `unsupported` event: a request the client sent that no capture
   answers.

| Step status | Meaning |
|---|---|
| `ok` | The step did what it says. |
| `fail` | It did not, and nothing declared explains why. Fails the run. |
| `known gap` | It failed only because the client asked for something no capture answers, and that request is declared as a gap. |
| `known failure` | It failed for a reason declared in advance: the emulator answers, but not as this client expects, and the evidence to fix it has not been recorded. |
| `not offered` | The client has no way to do this. A fact about the client, not a failure. |

The declarations keep themselves honest. An undeclared `unsupported` event fails the run. A
declared gap that no profile it covers met in the run is stale and fails it, and so does a
known failure that passes. When a new client version stops sending a request, or a fix
lands, the declaration has to go.

A gap is never closed by inventing an answer. It is closed by capturing the request off a
set, the same way every other answer in the emulator was made.

## Coverage

A verdict says a run held together; coverage says how much of the client it held. All of it
is counted by `python -m tvemu.clients report` from the run records; nothing in it is written
by hand. Each platform's page has three parts:

- **Heatmap.** Zones down the side, every emulated television of the platform across, every
  client folded into one cell: the best share any client passed of what it offers in that
  zone, how many clients passed anything there, and ⚠ how many times they met the emulator's
  gap or wrong answer. It answers what real clients have confirmed of each television, and it
  grows by a column per television, never per client.
- **Backlog.** Everything that did not pass, as work for whoever moves next: captures to
  record, wrong answers from the emulator, blocked televisions, client bugs, and tests to write.
  Each item says how many client × television runs it touches, the most first, and why in
  one sentence; items met on the same runs share a line, and a reason they share is said once.
  The full reason stays in `client.toml`.
- **Each client in detail.** Its last three runs, then zone by zone, for each group of
  televisions it did alike on, what passed and by name what did not, with the client's own
  error.

The zones group the step actions:

| Zone | Actions |
|---|---|
| discovery | `discover` |
| identity | `identify` |
| auth | `pair`, `reject` |
| session | `connect`, `reconnect`, `keepalive`, `disconnect`, `protocol-switch` |
| keys | `key`, `key-long` |
| text | `text` |
| pointer | `pointer` |
| voice | `voice` |
| state | `query-state` |
| volume | `volume` |
| power | `power` |
| apps | `launch`, `search`, `cast` |

The denominator is what the client offers in a zone. The binding says so with
`harness.offers(zone, items)`, reading the items from the client wherever it publishes them:
its key table, the fields of what it parsed (`Harness.names(value)`), its method names when
nothing better exists. Each step names the items it exercised with `covers`. A cell then reads
*passed / offered*, and the rest is split by what happened; the name says whose move it is:

| Part | Whose | Meaning |
|---|---|---|
| **untested** | the binding's | the client offers it and no step exercises it: a test to write |
| **blocked** | whoever owns the stop | offered, but a required step stopped the run before it was reached |
| **unsupported by emulator** | the emulator's | the client asked and no capture answers it (a known gap): evidence to record |
| **wrong answer from emulator** | the emulator's | the emulator answers, not as the set does (a known failure with `side = "emulator"`) |
| **client bug** | the client's | the client parses a correct answer wrongly (a known failure with `side = "client"`) |
| **no API** | the client's | the client has no way to do it at all (`[not_offered]` in `client.toml`) |
| **failed** | nobody's yet | failed for no declared reason; the run fails until someone says whose |

A zone the binding says nothing about is **not written**. On a run a required step stopped,
everything after the stop is **blocked**, not untested: whether a step would have covered it is
unknown. An item two steps covered shows the worse outcome, so a problem one step met is never
hidden by another that passed. Under each group the page counts the error statuses the emulator
sent.

A step may only cover what the client offers in that zone: a stray item fails the run, so the
two lists cannot drift apart.

## Records

`--record` writes one JSON file per run to `docs/clients/<platform>/<client>/<run id>.json`
and re-renders `docs/clients/<platform>.md` from all of them. It refuses to record when `src/`
or `pyproject.toml` has uncommitted changes: a record names the emulator by its version, and
that version has to be the code that ran.

A record holds:

- the client's requested and installed version, the upstream commit for a git install and
  the full `pip freeze` of its environment;
- the emulator's version;
- the Python version, system and machine;
- every step with the event ids it covers, the gaps met, the `expect` result and the verdict.

The workspace path and the home directory are replaced before anything is kept, and the run
uses loopback only, so a record carries no address of anybody's network.

Every television's page is published, including the televisions not in this repository. The
records behind a page, like the clients themselves (`client.toml`, the binding and the
expectation), live with the television's own code.

The pages are derived, never edited: `python -m tvemu.clients report --check` and
`tests/test_clients.py` fail when a page no longer matches its records.

## Keeping it fresh

`--version latest` installs the newest release, or the tracked branch for a git install. When
it passes, the runner says so, and `last_green` in the client's `client.toml` can move to it.
When it fails, the record says which step, which request or which expectation, and the last
green version is still there to compare against.

`.github/workflows/clients.yml` does this every week for every declared client, at both
versions, and keeps each run record and event log as an artifact. The pair tells the two kinds
of failure apart:

| last green | latest | What changed |
|---|---|---|
| pass | pass | nothing to do; `last_green` can move |
| pass | fail | the client: a new request, a new expectation, or a bug of its own |
| fail | — | the emulator: it no longer does what that client version relied on |

A scheduled run records nothing in the repository. The maintainer reads it, then runs
`--record` from a clean checkout.

## Adding a client

A client lives beside the television it drives, in
`src/tvemu/platforms/<id>/clients/<name>/`:

```text
client.toml    where the upstream lives, how to install it, what it drives, what is known
binding.py     the scenario, through the client's public API only (binding.mjs for npm)
expect.json    optional: what the event log must show (a tvemu.expect scenario)
```

```toml
schema_version = 1
summary = "what the client is and who uses it"
upstream = "https://github.com/…"
license = "MIT"

[install]
kind = "pypi"              # pypi | git | npm | none
package = "the-package"
track = "main"             # git only: the branch `--version latest` follows
last_green = "1.2.3"       # a release, or a full commit for git
prerequisites = []         # optional: installed first, then the client is built against them
                           # (for an upstream whose build imports its own dependencies)
layout = "package"         # git only: "checkout" for an upstream with no packaging, whose
                           # requirements.txt is installed and whose checkout goes on the path

[run]
profiles = ["<profile id>", "…"]
settings = {}              # emulator settings for the run, e.g. a protocol switched off
timeout = 120

[[gaps]]
operation = "POST /search/browse"  # exact, or a prefix ending in `*`: "query/icon/*"
profiles = ["<profile id>"]        # optional; every profile when absent
reason = "why no capture answers it, and what would close it"

[[known_failures]]
step = "the step's name, as the binding reports it"
reason = "what the emulator answers instead, and what evidence would fix it"
side = "emulator"          # whose defect: "emulator" (default) or "client"

[not_offered]              # zones the client has no API for, each with the reason
voice = "the client has no voice API"
```

A binding imports `tvemu_binding`, which is put on its path alone and uses only the standard
library:

```python
from the_client import Client
from tvemu_binding import Harness

async def main(harness: Harness):
    client = Client(harness.device_host, port=harness.device_port)
    async with harness.step("press Home", "key", required=True):
        before = (await harness.state())["counts"].get("Home", 0)
        await client.press("Home")
        await harness.wait(lambda state: state["counts"].get("Home", 0) == before + 1,
                           "Home counted")

Harness.main(main)
```

An npm client's binding is `binding.mjs` and imports `./tvemu_binding.mjs`, which offers the
same calls in JavaScript (`await harness.step(name, action, async () => …, { required, covers })`,
`harness.offers`, `Harness.names`, `harness.wait`, `harness.notOffered`, `assert`). Both are
copied into the client's project, because Node resolves a package from the importing file's
directory. Node.js 18 or newer must be on `PATH`.

- **Use the client's public API only.** The point is what a user of the library gets.
- **Observe the emulator only through `/api/v1`**: `state()`, `events()`, `action()` and
  `settings()`, and `wait()` for a condition on its state. The binding never imports the
  emulator.
- **Say what the client offers** in each zone it has an API for, with `harness.offers()`,
  and what each step exercises, with `covers`. Read the offer from the client itself where
  it publishes one, so a new version that adds a key shows up as untested.
- **Name each step's action** from the shared vocabulary in `tvemu.clients.model.ACTIONS`,
  so one report can compare clients across televisions.
- **Mark a step `required`** when nothing after it can mean anything, such as identity or
  pairing; a failed required step stops the binding.
- **Call `harness.not_offered()`** for what the client cannot do at all.
- **A profile without a feature skips the step**; it does not report it.

`tests/test_clients.py` checks every declaration offline: the binding compiles (`node --check`
for JavaScript, when Node is present), the profiles exist, gaps have reasons and the
expectation parses.
