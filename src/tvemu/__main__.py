from __future__ import annotations

import argparse
import json
import asyncio
import ipaddress
import signal
import socket
import sys
import tomllib
import webbrowser
from dataclasses import replace
from pathlib import Path

from aiohttp import web

from .control import control_app
from .core import Core, Settings, read_settings
from .platforms import (create_platform, default_platform, platform_descriptor,
                        platform_ids, restrict_to)
from .runtime import Runtime


def detect_address() -> str:
    # UDP connect only asks the OS for a route; no packet is sent to this address.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("192.0.2.1", 9))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def ipv4(value):
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise argparse.ArgumentTypeError("A local IPv4 address is required") from exc
    if address.is_unspecified or address.is_multicast or str(address) == "255.255.255.255":
        raise argparse.ArgumentTypeError("Specify an interface address, for example 192.168.1.20")
    return str(address)


def port_number(value):
    result = int(value)
    if not 1 <= result <= 65535:
        raise argparse.ArgumentTypeError("Port must be between 1 and 65535")
    return result


async def serve(args):
    saved_platform, settings = read_settings(args.config)
    platform_id = args.platform or saved_platform or default_platform()
    descriptor = platform_descriptor(platform_id)
    if saved_platform is not None and saved_platform != platform_id:
        # The saved captured device and access mode belong to another platform;
        # let this adapter resolve both to its own defaults.
        settings = replace(settings, device_profile="", access_mode="")
    if args.device_profile:
        settings = Settings.parse({"device_profile": args.device_profile}, settings)
    core = Core(descriptor, settings)
    core.host = args.bind or detect_address()
    core.service_port = args.service_port or descriptor.default_port
    core.service_port_pinned = args.service_port is not None
    runtime = Runtime(core, create_platform(platform_id, core))
    panel = web.AppRunner(control_app(runtime, args.config, args.ui_port), shutdown_timeout=1)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    signals = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stopped.set)
            signals.append(sig)
        except NotImplementedError:
            pass
    try:
        await panel.setup()
        try:
            await web.TCPSite(panel, "127.0.0.1", args.ui_port).start()
        except OSError as exc:
            raise ValueError(f"Could not bind dashboard at 127.0.0.1:{args.ui_port}: {exc}") from exc
        await runtime.start()
        url = f"http://127.0.0.1:{args.ui_port}"
        print(f"Smart TV Emulator · {descriptor.display_name}\nDashboard: {url}\n"
              f"Device: {descriptor.service_scheme}://{core.host}:{core.service_port}\n"
              f"Profile: {core.settings.device_profile}\n"
              f"Settings: {args.config.resolve()}\nStop: Ctrl+C", flush=True)
        if core.host == "127.0.0.1":
            print("Warning: loopback is not reachable from a phone. Use --bind <LAN IPv4>.", flush=True)
        if core.discovery_error:
            print(f"Discovery unavailable: {core.discovery_error}. The device and dashboard remain available.",
                  flush=True)
        if not args.no_browser:
            await asyncio.to_thread(webbrowser.open, url)
        await stopped.wait()
    finally:
        await runtime.close()
        await panel.cleanup()
        for sig in signals:
            loop.remove_signal_handler(sig)


# A build manifest beside the source tree names a smaller set of platforms than this
# checkout holds, so `--build <name>` previews that build without a separate checkout. The
# names come from the manifest, never from here: shared code still knows no television.
BUILD_MANIFESTS = {"public": "PUBLIC.toml"}


def manifest_path(name):
    """The build manifest for `name`, or None when this tree carries no such file."""
    filename = BUILD_MANIFESTS.get(name)
    if filename is None:
        return None
    # src/tvemu/__main__.py -> the repository root. An installed wheel has no manifest,
    # which is correct: a wheel already contains exactly the platforms its build ships.
    candidate = Path(__file__).resolve().parents[2] / filename
    return candidate if candidate.is_file() else None


def build_names():
    return tuple(name for name in BUILD_MANIFESTS if manifest_path(name) is not None)


def apply_build(argv=None):
    """Honour `--build` before the real parser reads `--platform`'s choices.

    The choices for `--platform` are fixed when the parser is built, so the restriction has
    to be in force by then; a throwaway parser reads just this one option first.
    """
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--build")
    name = pre.parse_known_args(argv)[0].build
    if not name or name == "full":
        return
    path = manifest_path(name)
    if path is None:
        raise SystemExit(f"No manifest for build {name!r}; this tree cannot preview it.")
    manifest = tomllib.loads(path.read_text(encoding="utf-8"))
    platforms = manifest.get("platforms")
    if not isinstance(platforms, list) or not all(isinstance(item, str) for item in platforms):
        raise SystemExit(f"{path.name} must list the build's platforms as `platforms = [...]`.")
    restrict_to(platforms)


def report(args) -> int:
    """Answer `--api-map` or `--contract` and exit, without binding anything."""
    from .platforms.common import report as reports

    platform_id = args.api_map or args.contract
    surface = reports.surface_of(platform_id)
    if surface is None:
        print(f"{platform_id} does not declare its surface yet.", file=sys.stderr)
        return 1
    if args.contract:
        print(reports.render_contract(platform_id, surface))
        if args.check:
            problems = reports.contract_problems(platform_id, surface)
            if problems:
                print("\nContract check failed:", file=sys.stderr)
                for problem in problems:
                    print(f"  - {problem}", file=sys.stderr)
                return 1
    elif args.format == "json":
        print(json.dumps(reports.surface_json(surface), indent=2))
    elif args.format == "openapi":
        documents = reports.openapi_documents(platform_id, surface)
        # Several ports answering the same request print one document per port, keyed by it.
        print(json.dumps(documents[""] if list(documents) == [""] else documents, indent=2))
    elif args.format == "asyncapi":
        print(json.dumps(reports.asyncapi(platform_id, surface), indent=2))
    else:
        print(reports.render_surface(surface))
    return 0


def main():
    apply_build()
    parser = argparse.ArgumentParser(description="Smart TV protocol emulator + local tester dashboard")
    parser.add_argument("--build", choices=("full", *build_names()), default="full",
                        help="serve only the platforms a named build ships, to preview that "
                             "build from this source tree (default: full)")
    parser.add_argument("--platform", choices=platform_ids(),
                        help="TV platform to emulate at startup; overrides the saved platform "
                             f"(default: {default_platform()}). Platforms this build does not "
                             "serve are listed in the dashboard")
    parser.add_argument("--bind", type=ipv4,
                        help="IPv4 address of the interface used by the device and discovery")
    parser.add_argument("--port", dest="service_port", type=port_number,
                        help="device protocol port for the platform started at launch; a switch "
                             "from the dashboard uses the new platform default")
    parser.add_argument("--device-profile",
                        help="captured device profile id (overrides the saved selection for this run)")
    parser.add_argument("--ui-port", type=port_number, default=8888)
    parser.add_argument("--config", type=Path, default=Path(".tvemu/settings.json"))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--api-map", metavar="PLATFORM", choices=platform_ids(),
                        help="print everything this platform answers, from the route "
                             "declarations beside its handlers, and exit")
    parser.add_argument("--contract", metavar="PLATFORM", choices=platform_ids(),
                        help="print this platform's curated claims and any disagreement "
                             "with its captures, and exit")
    parser.add_argument("--check", action="store_true",
                        help="with --contract, fail when a claim disagrees with the evidence")
    parser.add_argument("--format", choices=("text", "json", "openapi", "asyncapi"),
                        default="text",
                        help="with --api-map: text and json cover every transport, openapi "
                             "covers HTTP and asyncapi covers message channels (default: text)")
    args = parser.parse_args()
    if args.check and not args.contract:
        parser.error("--check requires --contract")
    if args.api_map or args.contract:
        sys.exit(report(args))
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError) as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
