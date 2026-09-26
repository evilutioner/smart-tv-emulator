"""IPv4 SSDP discovery shared by every platform that advertises over multicast."""
from __future__ import annotations

import asyncio
import random
import socket
import sys
from dataclasses import dataclass
from email.utils import formatdate
from typing import Callable, Protocol

from tvemu.core import Core

GROUP = "239.255.255.250"
PORT = 1900


@dataclass(frozen=True)
class SSDPAdvertisement:
    """One search target a captured device answers, with the reply it answers it with.

    A device may run several independent SSDP stacks, each with its own UUID, headers and
    description LOCATION, so a profile offers a tuple of these rather than a single target.
    """

    search_target: str
    headers: tuple[tuple[str, str], ...]
    location: str
    query_aliases: tuple[str, ...] = ()


class SSDPProfile(Protocol):
    """The profile fields an SSDP responder needs, regardless of platform."""

    id: str

    def ssdp_advertisements(self, host: str, service_port: int
                            ) -> tuple[SSDPAdvertisement, ...]: ...


def search_target(packet: bytes, expected_target: str) -> tuple[str, int] | None:
    if len(packet) > 8192:
        return None
    lines = packet.decode("ascii", errors="replace").split("\r\n")
    if not lines or lines[0].upper() != "M-SEARCH * HTTP/1.1":
        return None
    headers = {}
    for line in lines[1:]:
        key, separator, value = line.partition(":")
        if separator:
            headers[key.lower().strip()] = value.strip()
    if headers.get("man", "").lower() != '"ssdp:discover"':
        return None
    target = headers.get("st", "")
    if target != expected_target:
        return None
    try:
        mx = max(0, min(int(headers.get("mx", "1")), 5))
    except ValueError:
        return None
    return target, mx


class SSDPResponder(asyncio.DatagramProtocol):
    """Answers M-SEARCH probes with the captured headers of the active profile.

    Platforms differ only in the LOCATION they advertise, which the profile builds, and in the
    event names they record, which `event_prefix` supplies.
    """

    def __init__(self, core: Core, current_profile: Callable[[], SSDPProfile], *,
                 event_prefix: str):
        self.core = core
        self.current_profile = current_profile
        self.event_prefix = event_prefix
        self.transport = None
        self.replies: set[asyncio.TimerHandle] = set()
        self.active = False
        self.name = event_prefix

    def packet(self, advertisement: SSDPAdvertisement) -> bytes:
        headers = ["HTTP/1.1 200 OK"]
        for name, value in advertisement.headers:
            if value == "{location}":
                resolved = advertisement.location
            elif value == "{date}":
                resolved = formatdate(usegmt=True)
            else:
                resolved = value
            headers.append(f"{name}: {resolved}" if resolved else f"{name}:")
        return ("\r\n".join(headers) + "\r\n\r\n").encode()

    async def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # BSD/macOS requires SO_REUSEPORT to share a multicast listening port.
            if sys.platform == "darwin" and hasattr(socket, "SO_REUSEPORT"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            sock.bind(("", PORT))
            interface = socket.inet_aton(self.core.host)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                            socket.inet_aton(GROUP) + interface)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, interface)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.setblocking(False)
            await asyncio.get_running_loop().create_datagram_endpoint(lambda: self, sock=sock)
        except BaseException:
            sock.close()
            raise
        self.active = True
        self.core.discovery_error = None
        self.core.record("discovery", f"{self.event_prefix}.started",
                         detail=f"{self.core.host} · captured profile: {self.current_profile().id}")

    def connection_made(self, transport) -> None:
        self.transport = transport

    def error_received(self, exc) -> None:
        self.core.discovery_error = f"{self.name}: {exc}"
        self.core.record("discovery", f"{self.event_prefix}.error", detail=f"{self.name}: {exc}")

    def datagram_received(self, packet: bytes, address) -> None:
        profile = self.current_profile()
        if not self.active:
            return
        loop = asyncio.get_running_loop()
        # A stack answers only its own search target, so one probe may match more than one.
        for advertisement in profile.ssdp_advertisements(self.core.host, self.core.service_port):
            result = search_target(packet, advertisement.search_target)
            if result is None:
                for alias in advertisement.query_aliases:
                    result = search_target(packet, alias)
                    if result is not None:
                        break
            if not result or len(self.replies) >= 128:
                continue
            target, mx = result
            holder: list[asyncio.TimerHandle] = []

            def send(advertisement=advertisement, target=target, holder=holder) -> None:
                self.replies.discard(holder[0])
                if self.transport and self.active:
                    self.transport.sendto(self.packet(advertisement), address)
                    self.core.record("discovery", f"{self.event_prefix}.reply", transport="udp",
                                     peer=address[0], detail=f"{target} · {profile.id}")

            handle = loop.call_later(random.uniform(0, mx), send)
            holder.append(handle)
            self.replies.add(handle)

    async def stop(self) -> None:
        self.active = False
        for handle in self.replies:
            handle.cancel()
        self.replies.clear()
        if self.transport:
            self.transport.close()
            self.transport = None
        self.core.record("discovery", f"{self.event_prefix}.stopped")
