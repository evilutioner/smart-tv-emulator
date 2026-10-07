"""Install an upstream client in isolation and drive the emulator with it.

The emulator runs as its own process on loopback, exactly as `tvemu` starts for anybody, and
the client runs in a fresh virtual environment that holds the client and nothing of the
emulator. The two meet only on the wire and at `/api/v1`, so a dependency of one can never
mask a defect of the other, and what passes here is what a user of that client would see.

Everything the run downloads or creates lives in one temporary directory, removed afterwards.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
import platform as host
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request
import venv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import tvemu

from .model import RECORD_SCHEMA_VERSION, ClientSpec, judge, stale_gaps

HARNESS = Path(__file__).resolve().parent / "harness"
SOURCE = Path(tvemu.__file__).resolve().parents[1]          # the directory holding `tvemu`
STARTUP_TIMEOUT = 20.0
TAIL_LINES = 15


def repository_root() -> Path | None:
    """The checkout this emulator runs from, or None for an installed wheel."""
    root = SOURCE.parent
    return root if (root / ".git").exists() else None


def _run(command: list[str], *, cwd: Path, timeout: int = 600, env: dict | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True,
                               timeout=timeout, check=False)
    output = completed.stdout + completed.stderr
    if completed.returncode:
        raise RuntimeError(f"{' '.join(command[:4])} … exited {completed.returncode}\n"
                           + _tail(output))
    return completed.stdout


def _tail(text: str) -> str:
    return "\n".join(text.strip().splitlines()[-TAIL_LINES:])


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class Scrubber:
    """Keep the workspace and the home directory out of anything a record keeps."""

    def __init__(self, workspace: Path) -> None:
        self.pairs = sorted({(str(workspace.resolve()), "<workspace>"), (str(workspace), "<workspace>"),
                             (str(Path.home()), "~")}, key=lambda pair: -len(pair[0]))

    def __call__(self, value):
        if isinstance(value, str):
            for found, replacement in self.pairs:
                value = value.replace(found, replacement)
            return value
        if isinstance(value, list):
            return [self(item) for item in value]
        if isinstance(value, dict):
            return {key: self(item) for key, item in value.items()}
        return value


def emulator_identity() -> dict:
    root = repository_root()
    if root is not None:
        # A checkout's own version, not whatever an older install left in site-packages.
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        version = str(project.get("project", {}).get("version") or "")
    else:
        try:
            version = importlib.metadata.version("smart-tv-emulator")
        except importlib.metadata.PackageNotFoundError:
            version = ""
    # The version names what ran: the source tree and the published build carry the same one,
    # where a commit would name a tree only one of them has.
    identity = {"version": version, "clean": None}
    if root is None:
        return identity
    git = shutil.which("git")
    if git is None:
        return identity
    # What is under test is the emulator: its source and its packaging. A run record written
    # under docs/ by a previous client does not make the next run unreproducible.
    changes = _run([git, "status", "--porcelain", "--", "src", "pyproject.toml"], cwd=root)
    identity["clean"] = not changes.strip()
    return identity


# -- the client's environment -----------------------------------------------------------------

def _venv_python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


@dataclass
class Prepared:
    """An installed client: how to start its binding, and what exactly was installed."""

    command: list[str]
    cwd: Path
    environment: dict
    runtime: str                       # the binding's interpreter, e.g. "Python 3.13.1"
    info: dict


def prepare_client(spec: ClientSpec, version: str, workspace: Path) -> Prepared:
    requested = version or spec.last_green
    info = {"name": spec.name, "install": spec.install, "requested": requested or "latest",
            "upstream": spec.upstream, "license": spec.license, "version": "", "commit": "",
            "environment": []}
    if spec.install == "npm":
        return _prepare_npm(spec, requested, workspace, info)
    return _prepare_python(spec, requested, workspace, info)


def _prepare_python(spec: ClientSpec, requested: str, workspace: Path, info: dict) -> Prepared:
    """A virtual environment with the client installed."""
    environment = workspace / "venv"
    venv.EnvBuilder(with_pip=spec.install != "none").create(environment)
    python = _venv_python(environment)
    runtime = "Python " + _run([str(python), "-c", "import platform; print(platform.python_version())"],
                               cwd=workspace).strip()
    prepared = Prepared(
        command=[str(python), str(spec.binding)], cwd=workspace, runtime=runtime, info=info,
        environment={"PYTHONPATH": str(HARNESS), "PYTHONDONTWRITEBYTECODE": "1",
                     "PYTHONNOUSERSITE": "1"})
    if spec.install == "none":
        return prepared

    pip = [str(python), "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]
    if spec.install == "pypi":
        target = spec.package if requested in ("", "latest") else f"{spec.package}=={requested}"
        _run([*pip, target], cwd=workspace)
    else:
        source = workspace / "upstream"
        source.mkdir()
        git = shutil.which("git") or "git"
        ref = requested if requested not in ("", "latest") else spec.track
        _run([git, "init", "--quiet"], cwd=source)
        _run([git, "fetch", "--quiet", "--depth", "1", spec.upstream, ref], cwd=source, timeout=300)
        _run([git, "checkout", "--quiet", "FETCH_HEAD"], cwd=source)
        info["commit"] = _run([git, "rev-parse", "HEAD"], cwd=source).strip()
        _run([*pip, str(source)], cwd=workspace)

    info["version"] = _run([str(python), "-c",
                            "import importlib.metadata, sys; "
                            "print(importlib.metadata.version(sys.argv[1]))", spec.package],
                           cwd=workspace).strip()
    frozen = _run([str(python), "-m", "pip", "freeze", "--disable-pip-version-check"],
                  cwd=workspace).splitlines()
    pinned = f"{spec.package} @ git+{spec.upstream}@{info['commit']}"
    info["environment"] = sorted(pinned if " @ file:" in line else line
                                 for line in frozen if line.strip())
    return prepared


def _npm_tree(node: dict) -> set[str]:
    found = set()
    for name, child in (node.get("dependencies") or {}).items():
        if child.get("version"):
            found.add(f"{name}@{child['version']}")
        found |= _npm_tree(child)
    return found


def _prepare_npm(spec: ClientSpec, requested: str, workspace: Path, info: dict) -> Prepared:
    """A private npm project holding the client, with the binding and its harness beside it.

    Node resolves a package from the importing file's directory, so the binding runs from a
    copy inside the project rather than from the source tree. Install scripts are not run:
    a client's own code runs only when the binding calls it.
    """
    node, npm = shutil.which("node"), shutil.which("npm")
    if node is None or npm is None:
        raise RuntimeError(f"{spec.key} is installed from npm and needs Node.js 18+ on PATH")
    project = workspace / "node"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps({"private": True, "type": "module"}), encoding="utf-8")
    target = spec.package if requested in ("", "latest") else f"{spec.package}@{requested}"
    _run([npm, "install", "--no-audit", "--no-fund", "--ignore-scripts", "--loglevel=error",
          target], cwd=project, timeout=600)
    tree = json.loads(_run([npm, "ls", "--all", "--json"], cwd=project))
    info["version"] = tree["dependencies"][spec.package]["version"]
    info["environment"] = sorted(_npm_tree(tree))
    shutil.copy(spec.binding, project / "binding.mjs")
    shutil.copy(HARNESS / "tvemu_binding.mjs", project / "tvemu_binding.mjs")
    runtime = "Node " + _run([node, "--version"], cwd=project).strip().lstrip("v")
    return Prepared(command=[node, "binding.mjs"], cwd=project, runtime=runtime, info=info,
                    environment={})


# -- the emulator -----------------------------------------------------------------------------

class Emulator:
    """`tvemu` on loopback, in its own process, with a settings file of its own."""

    def __init__(self, spec: ClientSpec, profile: str, workspace: Path) -> None:
        self.spec, self.profile, self.workspace = spec, profile, workspace
        self.device_port, self.ui_port = _free_port(), _free_port()
        while self.ui_port == self.device_port:
            self.ui_port = _free_port()
        self.api = f"http://127.0.0.1:{self.ui_port}"
        self.log = workspace / f"emulator-{profile}.log"
        self.process: subprocess.Popen | None = None
        self._output = None

    def call(self, path: str):
        with urllib.request.urlopen(f"{self.api}{path}", timeout=5) as response:
            text = response.read().decode()
        if path.endswith("/export"):
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        return json.loads(text)

    def __enter__(self) -> "Emulator":
        config = self.workspace / f"settings-{self.profile}.json"
        config.write_text(json.dumps({
            "schema_version": 2, "platform": self.spec.platform,
            "settings": {**self.spec.settings, "device_profile": self.profile}}), encoding="utf-8")
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(SOURCE), *filter(None, [environment.get("PYTHONPATH")])])
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        self._output = self.log.open("w")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tvemu", "--platform", self.spec.platform,
             "--device-profile", self.profile, "--bind", "127.0.0.1",
             "--port", str(self.device_port), "--ui-port", str(self.ui_port),
             "--config", str(config), "--no-browser"],
            cwd=self.workspace, env=environment, stdout=self._output,
            stderr=subprocess.STDOUT)
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while True:
            if self.process.poll() is not None:
                raise RuntimeError(f"the emulator exited {self.process.returncode}\n"
                                   + _tail(self.log.read_text()))
            try:
                state = self.call("/api/v1/state")
                if state.get("service_listening"):
                    return self
            except OSError:
                pass
            if time.monotonic() >= deadline:
                self.__exit__(None, None, None)
                raise RuntimeError("the emulator did not start listening\n"
                                   + _tail(self.log.read_text()))
            time.sleep(0.1)

    def __exit__(self, *_exc) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.send_signal(signal.SIGINT if os.name != "nt" else signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self._output is not None:
            self._output.close()


# -- one run ----------------------------------------------------------------------------------

def run_profile(spec: ClientSpec, client: Prepared, profile: str, workspace: Path):
    results = workspace / f"steps-{profile}.jsonl"
    home = workspace / "home"
    home.mkdir(exist_ok=True)
    with Emulator(spec, profile, workspace) as emulator:
        state = emulator.call("/api/v1/state")
        since = int(state["events"][-1]["id"]) if state.get("events") else 0
        # Only what a binding needs: no credentials, no proxies, no user packages.
        environment = {
            "PATH": os.environ.get("PATH", ""), "HOME": str(home), "LANG": "C.UTF-8",
            **client.environment,
            "TVEMU_DEVICE_HOST": "127.0.0.1", "TVEMU_DEVICE_PORT": str(emulator.device_port),
            "TVEMU_PROFILE": profile, "TVEMU_API": emulator.api,
            "TVEMU_WORKSPACE": str(workspace), "TVEMU_RESULTS": str(results),
        }
        if os.name == "nt":
            environment["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
        exit_problem = ""
        try:
            completed = subprocess.run(client.command, cwd=client.cwd,
                                       env=environment, text=True, capture_output=True,
                                       timeout=spec.timeout, check=False)
            if completed.returncode:
                exit_problem = (f"binding exited {completed.returncode}: "
                                + _tail(completed.stdout + completed.stderr))
        except subprocess.TimeoutExpired:
            exit_problem = f"binding timed out after {spec.timeout} s"
        events = emulator.call("/api/v1/events/export")
    steps = ([json.loads(line) for line in results.read_text(encoding="utf-8").splitlines()
              if line.strip()] if results.is_file() else [])
    if not steps and not exit_problem:
        exit_problem = "the binding reported no steps"
    return judge(spec, profile, steps, events, since, exit_problem), events


def run(spec: ClientSpec, version: str = "", profiles: tuple[str, ...] = (),
        events_dir: Path | None = None) -> dict:
    """Install, drive every profile, and return the run record."""
    started = datetime.now(timezone.utc)
    clock = time.monotonic()
    emulator = emulator_identity()
    with tempfile.TemporaryDirectory(prefix=f"tvemu-client-{spec.name}-") as temporary:
        workspace = Path(temporary)
        scrub = Scrubber(workspace)
        prepared = prepare_client(spec, version, workspace)
        verdicts = []
        for profile in profiles or spec.profiles:
            verdict, events = run_profile(spec, prepared, profile, workspace)
            verdicts.append(verdict)
            if events_dir is not None:
                events_dir.mkdir(parents=True, exist_ok=True)
                (events_dir / f"{spec.platform}-{spec.name}-{profile}.events.jsonl").write_text(
                    "".join(json.dumps(scrub(event), ensure_ascii=False) + "\n" for event in events),
                    encoding="utf-8")
        stale = stale_gaps(spec, verdicts) if not profiles else []
        record = {
            "schema_version": RECORD_SCHEMA_VERSION,
            "run_id": started.strftime("%Y%m%dT%H%M%SZ"),
            "started_at": started.isoformat(timespec="seconds"),
            "duration_s": round(time.monotonic() - clock, 1),
            "platform": spec.platform,
            "client": prepared.info,
            "emulator": emulator,
            # `python` is the emulator's interpreter; `client` is what ran the binding.
            "runtime": {"client": prepared.runtime, "python": host.python_version(),
                        "implementation": host.python_implementation(),
                        "system": host.system(), "machine": host.machine()},
            "verdict": "pass" if all(v.verdict == "pass" for v in verdicts) and not stale else "fail",
            "stale_gaps": stale,
            "profiles": [verdict.as_record() for verdict in verdicts],
        }
        return scrub(record)
