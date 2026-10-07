"""A build must not carry artifacts, addresses or keys it has no business shipping.

Deliberately generic. In a build that runs every catalogued television the "absent" set is
empty and those assertions are vacuously true, so this one file states the same rules in
the private repository and the published one.

The manifest cases run only where `PUBLIC.toml` exists, which is the repository that
produces the public build. There, "shipped" means the files that manifest names; in the
published repository itself, "shipped" means everything git tracks.
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

from tests.support import STUB_IDS
from tvemu.core import Core
from tvemu.platforms import create_platform, platform_descriptor, platform_ids
from tvemu.platforms.catalogue import catalogue_entries, catalogue_entry, catalogue_ids

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tools"))

try:
    import public_manifest
except ImportError:                       # the published repository ships no manifest
    public_manifest = None

# A private address in published text is somebody's real network, unless it is the one
# block reserved here for examples. Captures came off other blocks, so the distinction is
# real: an address outside 192.168.1.0/24 in a shipped file is a leak, not an illustration.
EXAMPLE_LAN = "192.168.1."
PRIVATE_ADDRESS = re.compile(
    r"\b(?:192\.168\.\d{1,3}\.\d{1,3}"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")
# Six octets standing alone. The guards on either side matter: a SHA-256 fingerprint
# is written the same way, and its first six octets are not a hardware address.
HARDWARE_ADDRESS = re.compile(
    r"(?<![0-9A-Fa-f:])[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}(?![0-9A-Fa-f:])")
PRIVATE_KEY = re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")


def leaked_addresses(text: str) -> list[str]:
    return [found for found in PRIVATE_ADDRESS.findall(text)
            if not found.startswith(EXAMPLE_LAN)]


def leaked_hardware_addresses(text: str) -> list[str]:
    """Hardware addresses that are not locally administered.

    A replaced address should have the locally-administered bit set, which is what makes it
    unable to collide with any real vendor-assigned one. A shipped address without that bit
    came off real hardware.
    """
    return [found for found in HARDWARE_ADDRESS.findall(text)
            if not int(found.split(":")[0], 16) & 0x02]

TEXT_SUFFIXES = frozenset({".py", ".js", ".css", ".html", ".json", ".xml", ".md", ".toml",
                           ".yml", ".yaml", ".txt", ".cfg", ".ini", ""})

# The catalogue names every television this product models, including the ones a build
# cannot run. That is the whole point of it, so it is exempt from the name scan.
NAME_SCAN_EXEMPT = frozenset({"src/tvemu/platforms/catalogue.json"})


def git_tracked() -> list[str]:
    result = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                            capture_output=True, check=True)
    return [name for name in result.stdout.decode().split("\0") if name]


class BuildContentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shipped_platforms = set(platform_ids()) - set(STUB_IDS)
        if public_manifest is not None:
            files, manifest = public_manifest.resolve(ROOT)
            cls.shipped = sorted(files)
            cls.manifest = manifest
            cls.build_platforms = set(manifest.get("platforms") or [])
        else:
            cls.shipped = git_tracked()
            cls.manifest = None
            cls.build_platforms = cls.shipped_platforms
        cls.absent = set(catalogue_ids()) - cls.build_platforms

    def text_files(self):
        for name in self.shipped:
            path = ROOT / name
            if path.suffix.lower() in TEXT_SUFFIXES and path.is_file():
                yield name, path.read_text(encoding="utf-8", errors="ignore")

    # ── what the build may contain ────────────────────────────────────────────────────
    def test_no_files_survive_for_a_platform_the_build_does_not_ship(self):
        for platform_id in sorted(self.absent):
            with self.subTest(platform=platform_id):
                for name in self.shipped:
                    self.assertFalse(
                        name.startswith(f"src/tvemu/platforms/{platform_id}/")
                        or name == f"src/tvemu/web/platforms/{platform_id}.js"
                        or name == f"src/tvemu/web/platforms/{platform_id}.css"
                        or name.startswith(f"tests/test_{platform_id}"),
                        f"{name} belongs to {platform_id}, which this build does not ship")

    def test_no_key_material_is_shipped_outside_a_shipped_platform(self):
        allowed = {f"src/tvemu/platforms/{pid}/tls/" for pid in self.build_platforms}
        for name in self.shipped:
            if name.endswith(".pem"):
                self.assertTrue(any(name.startswith(prefix) for prefix in allowed), name)

    def test_no_shipped_code_names_a_platform_the_build_does_not_ship(self):
        if not self.absent:
            self.skipTest("this build ships every catalogued platform")
        patterns = {pid: re.compile(rf"\b{re.escape(pid)}\b", re.IGNORECASE)
                    for pid in self.absent}
        for name, text in self.text_files():
            # Prose names every television on purpose; that is the point of publishing it.
            if not name.startswith("src/tvemu/") or name in NAME_SCAN_EXEMPT:
                continue
            for platform_id, pattern in patterns.items():
                with self.subTest(file=name, platform=platform_id):
                    self.assertIsNone(pattern.search(text),
                                      f"{name} names {platform_id}")

    # ── what no build may contain ─────────────────────────────────────────────────────
    def test_no_shipped_file_carries_a_real_network_or_hardware_address(self):
        for name, text in self.text_files():
            for label, found in (("a private address", leaked_addresses(text)),
                                 ("a real hardware address",
                                  leaked_hardware_addresses(text))):
                with self.subTest(file=name, kind=label):
                    self.assertEqual(found, [], f"{name} carries {label}")

    def test_no_shipped_file_carries_a_private_key(self):
        for name, text in self.text_files():
            with self.subTest(file=name):
                self.assertIsNone(PRIVATE_KEY.search(text), name)

    # ── the catalogue and the manifest agree with the tree ────────────────────────────
    def test_every_platform_this_build_runs_is_catalogued(self):
        self.assertLessEqual(self.shipped_platforms, set(catalogue_ids()))

    def test_the_catalogue_describes_what_this_build_runs(self):
        """The catalogue is where every published count comes from, so it is checked here.

        A platform the build cannot run is not checked, because there is nothing to check
        it against; a build that runs it is the one that keeps its entry honest.
        """
        for platform_id in sorted(self.shipped_platforms):
            entry = catalogue_entry(platform_id)
            descriptor = platform_descriptor(platform_id)
            adapter = create_platform(platform_id, Core(descriptor))
            with self.subTest(platform=platform_id):
                self.assertEqual(entry.display_name, descriptor.display_name)
                self.assertEqual(entry.protocols, len(descriptor.protocols))
                self.assertEqual(sorted(entry.profile_ids), sorted(adapter.profile_ids()))

    def test_a_validated_device_is_one_the_ledger_records(self):
        """The README marks a device validated from the catalogue; only a session can earn it.

        Both directions: a flag with no ledger row is a claim nobody made, and a ledger row
        whose device is not flagged is a session the published table does not show.
        """
        ledger = (ROOT / "docs" / "manual-validation.md").read_text(encoding="utf-8")
        section = ledger.split("## Ledger", 1)[1].split("\n## ", 1)[0]
        recorded = {profile for row in section.splitlines() if row.startswith("|")
                    for profile in re.findall(r"`([a-z0-9-]+)`", row.split("|")[4])}
        flagged = {profile for entry in catalogue_entries() for device in entry.captured
                   if device.validated for profile in device.profiles}
        self.assertEqual(flagged, recorded)

    def test_the_apps_a_television_was_tested_with_are_the_ledger_s(self):
        """The README's "Tested with" names a vendor app only when a ledger row records it."""
        ledger = (ROOT / "docs" / "manual-validation.md").read_text(encoding="utf-8")
        section = ledger.split("## Ledger", 1)[1].split("\n## ", 1)[0]
        rows = [[cell.strip() for cell in row.split("|")[1:3]] for row in section.splitlines()
                if row.startswith("|") and not row.startswith(("| Television", "|---"))]
        for entry in catalogue_entries():
            sessions = [app for television, app in rows
                        if television == entry.display_name and app != "the same app"]
            with self.subTest(platform=entry.id):
                apps = [app.name for app in entry.apps]
                for app in entry.apps:
                    self.assertTrue(app.url.startswith("https://"), f"{app.name} needs its store page")
                for app in apps:
                    self.assertTrue(any(app in session for session in sessions),
                                    f"{app!r} has no ledger row for {entry.display_name}")
                for session in sessions:
                    self.assertTrue(any(app in session for app in apps),
                                    f"the ledger's {session!r} is not in the catalogue's apps")

    def test_the_manifest_names_only_paths_that_exist(self):
        if public_manifest is None:
            self.skipTest("this repository ships no build manifest")
        self.assertEqual(public_manifest.missing(ROOT), [])

    def test_every_shared_module_is_in_the_manifest(self):
        """A new shared file that nobody listed is a red test, not a surprise at export."""
        if public_manifest is None:
            self.skipTest("this repository ships no build manifest")
        listed = set(self.shipped) | set(self.manifest.get("private") or [])
        platform_dirs = tuple(f"src/tvemu/platforms/{pid}/" for pid in catalogue_ids())
        for name in git_tracked():
            if not name.startswith(("src/tvemu/", "tests/")):
                continue
            if name.startswith(platform_dirs) or name.startswith("src/tvemu/web/platforms/"):
                continue
            if name.startswith("tests/test_") and not name.startswith("tests/test_public"):
                continue          # per-platform and per-feature test files travel separately
            with self.subTest(file=name):
                self.assertIn(name, listed, f"{name} is not named in PUBLIC.toml")


if __name__ == "__main__":
    unittest.main()
