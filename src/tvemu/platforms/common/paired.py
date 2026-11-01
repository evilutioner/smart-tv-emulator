"""Client certificates a set has paired, kept across restarts as a television keeps them.

A set remembers a phone over reboots. An emulator that forgot on every restart left a client
holding a pairing the set no longer honoured: the TLS refusal is the one a set sends a stranger,
and the Android apps answer it by reconnecting, not by pairing again. The file lives beside the
settings file, one per platform, or one per named store when a set pairs two protocols with their own
certificates; without a settings directory, as in tests, pairings stay in memory. Forgetting them is the dashboard's disconnect action, which clears and rewrites the file.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from tvemu.core import Core

from .tls import certificate_fingerprint


def _path(core: Core, store: str = "") -> Path | None:
    if core.state_dir is None:
        return None
    name = f"{core.platform.id}.{store}" if store else core.platform.id
    return core.state_dir / "pairings" / f"{name}.json"


def load_paired(core: Core, store: str = "") -> tuple[dict[str, bytes], dict[str, dict]]:
    """The certificates and dashboard records saved for the active platform, or its named store."""
    certificates: dict[str, bytes] = {}
    records: dict[str, dict] = {}
    path = _path(core, store)
    if path is None or not path.exists():
        return certificates, records
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))["certificates"]
        for entry in entries:
            der = base64.b64decode(entry["der"])
            fingerprint = certificate_fingerprint(der)
            certificates[fingerprint] = der
            records[fingerprint] = {"fingerprint": fingerprint,
                                    "client_name": str(entry.get("client_name", "")),
                                    "peer": str(entry.get("peer", ""))}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        core.record("pairing", "pairings.unreadable", status=500,
                    detail=f"{path}: {exc}; starting with no paired clients")
        return {}, {}
    return certificates, records


def save_paired(core: Core, certificates: dict[str, bytes], records: dict[str, dict],
                store: str = "") -> None:
    path = _path(core, store)
    if path is None:
        return
    entries = [{"der": base64.b64encode(der).decode("ascii"),
                "client_name": records.get(fingerprint, {}).get("client_name", ""),
                "peer": records.get(fingerprint, {}).get("peer", "")}
               for fingerprint, der in certificates.items()]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"certificates": entries}, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        core.record("pairing", "pairings.unwritable", status=500, detail=f"{path}: {exc}")
