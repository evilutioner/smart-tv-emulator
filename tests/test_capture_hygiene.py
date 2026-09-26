"""No committed capture may identify the physical television it came from.

`test_public_build.py` states the same rule, but only over the files a build ships. Every
other platform's captures are in this repository too, and they are the ones that would leak
first, so the rule is applied here to all of them.

It is applied structurally. A test that writes the real serial number down in order to assert
that the profile does not contain it has put the serial number in the repository, which is the
thing the rule exists to prevent. So nothing here names a secret.

A capture is scrubbed in one of two ways, and both are deliberate. Zeroing the unit while
keeping the vendor OUI stays faithful to a client that reads the OUI; setting the
locally-administered bit makes the address unable to collide with any real one at all. An
address in neither shape still identifies the set it came off. `test_public_build.py` requires
the stricter second form of everything a build ships.

Network addresses are checked in the bytes a client would receive, not in the provenance a
profile records about itself. Where a capture was taken is a note to whoever maintains it and
never reaches the wire; `test_public_build.py` is what keeps it out of anything published.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from test_public_build import HARDWARE_ADDRESS, leaked_addresses
from tests.support import STUB_IDS
from tvemu.platforms import platform_ids

PROFILES = Path(__file__).parents[1] / "src" / "tvemu" / "platforms"
# Binary captures carry no text to scan, and any byte sequence in one can match by accident.
BINARY = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bin"})

# Vendor OUI kept, unit zeroed.
ZEROED_UNIT = re.compile(r"^(?:[0-9A-Fa-f]{2}:){3}00:00:[0-9A-Fa-f]{2}$")


def scrubbed(address: str) -> bool:
    return bool(ZEROED_UNIT.match(address)) or bool(int(address.split(":")[0], 16) & 0x02)


def unscrubbed_hardware_addresses(text: str) -> list[str]:
    """Addresses that still carry the unit bytes of the set they came off."""
    return [found for found in HARDWARE_ADDRESS.findall(text) if not scrubbed(found)]


# Raw bytes live under evidence; a profile holds only its reference, which can still name an
# identifier in its runtime block, so both roots are scanned.
ROOTS = ("profiles", "evidence")


def captured_files():
    """Every committed profile reference and evidence capture, shipped or not."""
    for platform_id in platform_ids():
        if platform_id in STUB_IDS:
            continue
        for kind in ROOTS:
            root = PROFILES / platform_id / kind
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.suffix.lower() not in BINARY:
                    yield platform_id, path


def strip_provenance(value):
    """The same document with every `source` note removed, at any depth."""
    if isinstance(value, dict):
        return {k: strip_provenance(v) for k, v in value.items() if k != "source"}
    if isinstance(value, list):
        return [strip_provenance(item) for item in value]
    return value


def without_provenance(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix != ".json":
        return text
    try:
        return json.dumps(strip_provenance(json.loads(text)))
    except ValueError:
        return text


class CaptureHygieneTests(unittest.TestCase):
    def test_every_capture_is_scanned(self):
        """A rule applied to nothing passes. This is what stops that being silent."""
        found = list(captured_files())
        self.assertTrue(found)
        self.assertEqual(sorted({platform for platform, _ in found}),
                         sorted(set(platform_ids()) - set(STUB_IDS)))
        # And every root that exists is reached, so adding evidence to a platform cannot leave
        # them unscanned while the platform itself still passes on its profiles alone.
        for platform_id in set(platform_ids()) - set(STUB_IDS):
            for kind in ROOTS:
                root = PROFILES / platform_id / kind
                if root.is_dir():
                    with self.subTest(platform=platform_id, root=kind):
                        self.assertTrue(any(path.is_relative_to(root) for _, path in found),
                                        f"{root} holds captures nothing scans")

    def test_no_capture_identifies_the_unit_it_came_off(self):
        for platform_id, path in captured_files():
            with self.subTest(platform=platform_id, file=path.name):
                leaked = unscrubbed_hardware_addresses(
                    path.read_text(encoding="utf-8", errors="replace"))
                self.assertEqual(leaked, [], f"{path} carries an unscrubbed address")

    def test_no_served_body_carries_a_real_private_network_address(self):
        for platform_id, path in captured_files():
            with self.subTest(platform=platform_id, file=path.name):
                leaked = leaked_addresses(without_provenance(path))
                self.assertEqual(leaked, [],
                                 f"{path} would serve somebody's real network address")


if __name__ == "__main__":
    unittest.main()
