"""Small, dependency-free multicast DNS responder for captured profiles."""
from __future__ import annotations

import asyncio
import random
import socket
import struct
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from tvemu.core import Core

GROUP = "224.0.0.251"
PORT = 5353
HEADER = struct.Struct("!6H")
IN, PTR, TXT, A, SRV, ANY = 1, 12, 16, 1, 33, 255
ENUMERATION = (b"_services", b"_dns-sd", b"_udp", b"local")


@dataclass(frozen=True)
class MDNSAdvertisement:
    """One DNS-SD service published by a captured device."""

    service_type: tuple[bytes, ...]
    instance: bytes
    target: str
    port: int
    txt: tuple[bytes, ...]


class MDNSProfile(Protocol):
    id: str
    def mdns_advertisements(self, host: str, service_port: int
                            ) -> tuple[MDNSAdvertisement, ...]: ...


def encode_name(labels: Sequence[bytes]) -> bytes:
    out = bytearray()
    for label in labels:
        if not 1 <= len(label) <= 63:
            raise ValueError("invalid DNS label")
        out += bytes((len(label),)) + label
    return bytes(out + b"\x00")


def decode_name(packet: bytes, offset: int) -> tuple[tuple[bytes, ...], int]:
    labels, jumps, seen = [], 0, set()
    end = None
    size = 1
    while True:
        if offset >= len(packet):
            raise ValueError("truncated DNS name")
        length = packet[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet):
                raise ValueError("truncated DNS pointer")
            pointer = ((length & 0x3F) << 8) | packet[offset + 1]
            if pointer >= offset or pointer in seen or jumps >= 64:
                raise ValueError("invalid DNS pointer")
            seen.add(pointer); jumps += 1
            if end is None:
                end = offset + 2
            offset = pointer
            continue
        if length & 0xC0 or length > 63:
            raise ValueError("invalid DNS label")
        offset += 1
        if length == 0:
            return tuple(labels), end if end is not None else offset
        if offset + length > len(packet):
            raise ValueError("truncated DNS label")
        label = packet[offset:offset + length]
        size += length + 1
        if size > 255:
            raise ValueError("DNS name too long")
        labels.append(label)
        offset += length


def _record(name, qtype, qclass, ttl, data):
    return encode_name(name) + struct.pack("!HHIH", qtype, qclass, ttl, len(data)) + data


def _advertisements(profile: MDNSProfile, host: str,
                    service_port: int | None = None) -> tuple[MDNSAdvertisement, ...]:
    if service_port is None:
        service_port = getattr(profile, "mdns_port", 0)
    return profile.mdns_advertisements(host, service_port)


def _records(advertisement: MDNSAdvertisement, host: str, ttl: int | None = None):
    service = advertisement.service_type
    instance = (advertisement.instance,) + service
    target = tuple(label.encode() for label in advertisement.target.rstrip(".").split("."))
    shared_ttl = 4500 if ttl is None else ttl
    address_ttl = 120 if ttl is None else ttl
    return {
        "ptr": _record(service, PTR, IN, shared_ttl, encode_name(instance)),
        "srv": _record(instance, SRV, 0x8001, shared_ttl,
                       struct.pack("!HHH", 0, 0, advertisement.port) + encode_name(target)),
        # RFC 6763 §6.1: a TXT record with no keys is one empty string, never empty rdata.
        "txt": _record(instance, TXT, 0x8001, shared_ttl,
                       b"".join(bytes((len(item),)) + item for item in advertisement.txt)
                       or b"\x00"),
        "a": _record(target, A, 0x8001, address_ttl, socket.inet_aton(host)),
        "enum": _record(ENUMERATION, PTR, IN, shared_ttl, encode_name(service)),
    }


def responses_for(packet: bytes, profile: MDNSProfile, host: str,
                  source_port: int = PORT, service_port: int | None = None
                  ) -> list[tuple[bytes, bool]]:
    if len(packet) < HEADER.size or len(packet) > 9000:
        return []
    try:
        query_id, flags, qdcount, _, _, _ = HEADER.unpack_from(packet)
        if flags & 0x8000 or qdcount > 64:
            return []
        offset = HEADER.size
        questions = []
        for _ in range(qdcount):
            name, offset = decode_name(packet, offset)
            if offset + 4 > len(packet):
                raise ValueError("truncated DNS question")
            qtype, qclass = struct.unpack_from("!HH", packet, offset); offset += 4
            questions.append((name, qtype, qclass))
    except (ValueError, struct.error):
        return []
    legacy = source_port != PORT
    answers, additionals, unicast = [], [], legacy
    for name, qtype, qclass in questions:
        if (qclass & 0x7FFF) != IN:
            continue
        unicast |= bool(qclass & 0x8000)
        for advertisement in _advertisements(profile, host, service_port):
            records = _records(advertisement, host, 10 if legacy else None)
            service = advertisement.service_type
            instance = (advertisement.instance,) + service
            target = tuple(label.encode() for label in advertisement.target.rstrip(".").split("."))
            if name == service and qtype in (PTR, ANY):
                answers.append(records["ptr"])
                additionals += [records["srv"], records["txt"], records["a"]]
            elif name == instance:
                previous = len(answers)
                if qtype in (SRV, ANY): answers.append(records["srv"])
                if qtype in (TXT, ANY): answers.append(records["txt"])
                if len(answers) > previous:
                    additionals += [record for key, record in records.items()
                                    if key in ("srv", "txt", "a") and record not in answers]
            elif name == target and qtype in (A, ANY):
                answers.append(records["a"])
            elif name == ENUMERATION and qtype in (PTR, ANY):
                answers.append(records["enum"])
    if not answers:
        return []
    answers = list(dict.fromkeys(answers)); additionals = list(dict.fromkeys(additionals))
    response = HEADER.pack(query_id, 0x8400, 0, len(answers), 0, len(additionals))
    return [(response + b"".join(answers + additionals), unicast)]


def announcement(profile: MDNSProfile, host: str, ttl: int | None = None,
                 service_port: int | None = None) -> bytes:
    values = []
    for advertisement in _advertisements(profile, host, service_port):
        records = _records(advertisement, host, ttl)
        values += [records[key] for key in ("ptr", "srv", "txt", "a")]
    values = list(dict.fromkeys(values))
    return HEADER.pack(0, 0x8400, 0, len(values), 0, 0) + b"".join(values)


class MDNSResponder(asyncio.DatagramProtocol):
    name = "mdns"

    def __init__(self, core: Core, current_profile: Callable[[], MDNSProfile], *,
                 event_prefix: str = "mdns"):
        self.core, self.current_profile = core, current_profile
        self.event_prefix = event_prefix
        self.transport = None
        self.active = False
        self.replies: set[asyncio.TimerHandle] = set()

    def connection_made(self, transport) -> None:
        self.transport = transport

    async def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            sock.bind(("", PORT))
            interface = socket.inet_aton(self.core.host)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(GROUP) + interface)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, interface)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
            sock.setblocking(False)
            await asyncio.get_running_loop().create_datagram_endpoint(lambda: self, sock=sock)
        except BaseException:
            sock.close(); raise
        self.active = True
        self._send(announcement(self.current_profile(), self.core.host,
                                service_port=self.core.service_port), (GROUP, PORT))
        loop = asyncio.get_running_loop()
        holder = []

        def again():
            self.replies.discard(holder[0])
            self._scheduled_announce()
        handle = loop.call_later(1, again)
        holder.append(handle)
        self.replies.add(handle)
        self.core.record("discovery", f"{self.event_prefix}.started",
                         detail=f"{self.core.host} · captured profile: {self.current_profile().id}")

    def _scheduled_announce(self):
        if self.active:
            self._send(announcement(self.current_profile(), self.core.host,
                                    service_port=self.core.service_port), (GROUP, PORT))

    def _send(self, packet, address):
        if self.transport:
            self.transport.sendto(packet, address)

    def datagram_received(self, packet, address):
        results = self.responses_for(packet, self.core.host, address[1])
        if not self.active or not results or len(self.replies) >= 128:
            return
        for response, unicast in results:
            destination = address if unicast else (GROUP, PORT)
            delay = 0 if unicast else random.uniform(.02, .12)
            holder = []
            def send(response=response, destination=destination, holder=holder):
                self.replies.discard(holder[0]); self._send(response, destination)
            holder.append(asyncio.get_running_loop().call_later(delay, send))
            self.replies.add(holder[0])

    def responses_for(self, packet: bytes, host: str,
                      source_port: int = PORT) -> list[tuple[bytes, bool]]:
        return responses_for(packet, self.current_profile(), host, source_port,
                             self.core.service_port)

    def error_received(self, exc):
        self.core.discovery_error = f"{self.name}: {exc}"
        self.core.record("discovery", f"{self.event_prefix}.error", detail=str(exc))

    async def stop(self):
        if self.active:
            self._send(announcement(self.current_profile(), self.core.host, 0,
                                    self.core.service_port), (GROUP, PORT))
        self.active = False
        for handle in self.replies: handle.cancel()
        self.replies.clear()
        if self.transport: self.transport.close(); self.transport = None
        self.core.record("discovery", f"{self.event_prefix}.stopped")
