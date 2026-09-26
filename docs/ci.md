# Running your app's tests against the emulator in CI

The emulator is one Python process with no hardware and no network beyond loopback, so it
runs on an ordinary CI runner. Your tests talk to it as they would to a television, and the
job asserts on what arrived with `python -m tvemu.expect`.

## GitHub Actions

```yaml
jobs:
  tv-driver:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install the emulator
        run: python -m pip install "git+https://github.com/evilutioner/smart-tv-emulator"

      - name: Start it
        run: |
          tvemu --platform <id> --bind 127.0.0.1 --no-browser > tvemu.log 2>&1 &
          for attempt in $(seq 30); do
            curl -sf http://127.0.0.1:8888/api/v1/state > /dev/null && exit 0
            sleep 1
          done
          cat tvemu.log; exit 1

      - name: Your tests
        run: ./run-driver-tests.sh 127.0.0.1      # whatever drives your code

      - name: Check what arrived
        run: python -m tvemu.expect tests/tv/scenario.json

      - name: Keep the event log
        if: always()
        run: curl -s http://127.0.0.1:8888/api/v1/events/export > tv-events.jsonl
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: tv-events
          path: tv-events.jsonl
```

## Between test cases

Each case should start from a known state. The management API does that without a restart:

```sh
H='Content-Type: application/json'
curl -s -X POST -H "$H" -d '{}' http://127.0.0.1:8888/api/v1/actions/reset       # counters, power, volume
curl -s -X POST -H "$H" -d '{}' http://127.0.0.1:8888/api/v1/actions/clear-log   # a clean log to assert on
curl -s -X POST -H "$H" -d '{}' http://127.0.0.1:8888/api/v1/actions/disconnect  # drop sessions and pairing
curl -s -X PATCH -H "$H" -d '{"device_profile": "<profile>"}' http://127.0.0.1:8888/api/v1/settings
```

Switching the captured device inside one job is how a driver is tested against several
firmwares: the same test, one `PATCH` per profile.

Every mutation must be sent as `application/json`, and the API answers only on `127.0.0.1` or
`localhost`, so a browser page cannot reach it.

## Checking an exported log instead

A log saved as an artifact can be checked later, or on another machine:

```sh
python -m tvemu.expect tests/tv/scenario.json --events tv-events.jsonl
```

## Limits worth knowing

- **Discovery on loopback.** SSDP and mDNS answer on the bound interface. A driver that only
  connects by address needs nothing more; one that discovers must run where multicast works.
- **Ports.** A runner may refuse a privileged port a television uses. `--port` moves the
  primary protocol; the platform guide says which ports stay fixed.
- **Time.** Prompts time out as on the set. Answer them from the test with the management API
  rather than waiting.
