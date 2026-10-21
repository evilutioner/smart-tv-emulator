"""A test-tone sender for the two mobile private-listening transports.

RTP and SAS framing follow the audio receiver of the Roku mobile app for Android
14.1.2 and the 2026-10-18 stick probe. SAS includes measured format-5 parity;
retry requests and adaptive delay remain unimplemented. No audio encoder runs here.
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import secrets
import struct
from dataclasses import dataclass
from importlib.resources import files

from tvemu.platforms.common import routing as route
from .sas_fec import SasFecEncoder


def sas_packet(payload: bytes, sequence: int, samples: int, stream_id: int,
               version: int = 45, clock_offset: int | None = None) -> bytes:
    # PacketHeader: version, packet number and audio packet number, little-endian.
    # Presence bits 0/1/4/14: main header, payload, sync and the measured empty extension.
    # The audio header the Roku mobile app's receiver reads: unsigned 48-bit sample position,
    # stream id, codec, flags. The receiver compares the stream id and resets on a change.
    header = ((samples & ((1 << 48) - 1)).to_bytes(6, "little")
              + struct.pack("<I BB", stream_id & 0xffffffff, 30, 9))
    clock = -(1 << 47) if clock_offset is None else clock_offset
    sync = clock.to_bytes(6, "little", signed=True) + b"\x00\x00\xff"
    return (struct.pack("<BII", version, sequence & 0xffffffff, sequence & 0xffffffff)
            + b"\x93\x40" + bytes([len(header)]) + header
            + struct.pack("<H", len(payload)) + payload + bytes([len(sync)]) + sync + b"\x00")


def rtp_packet(payload: bytes, sequence: int, timestamp: int, ssrc: int,
               payload_type: int = 97) -> bytes:
    return struct.pack("!BBHII", 0x80, payload_type, sequence & 0xffff,
                       timestamp & 0xffffffff, ssrc) + payload


def rtcp_app(name: bytes, payload: bytes = b"", ssrc: int = 0) -> bytes:
    if len(name) != 4 or len(payload) % 4:
        raise ValueError("RTCP APP needs a four-byte name and word-aligned data")
    return struct.pack("!BBHI", 0x80, 204, (8 + len(payload)) // 4, ssrc) + name + payload


def opus_pair(first: bytes, second: bytes) -> bytes:
    """Two equal-sized 10 ms CBR frames, in one 20 ms Opus packet."""
    if not first or first[0] & 3 or first[0] != second[0] or len(first) != len(second):
        raise ValueError("Only equal CBR single-frame packets can be paired")
    return bytes([first[0] | 1]) + first[1:] + second[1:]


@dataclass
class AudioSession:
    owner: str
    mode: str
    address: tuple[str, int]
    guid: str
    version: int
    samples: int
    payload_type: int
    transport: asyncio.DatagramTransport
    task: asyncio.Task | None = None
    packets: int = 0
    bytes: int = 0
    feedback: int = 0
    position: int = 0
    clock_offset: int | None = None


class AudioOutput(asyncio.DatagramProtocol):
    def __init__(self, core, profile, warm_up=None, bind_host=None):
        self.core, self.profile, self.warm_up = core, profile, warm_up
        self.bind_host = bind_host or (lambda: core.host)
        self.rtcp_transport = None
        self.sessions: dict[str, AudioSession] = {}
        fixture = json.loads(files(__package__).joinpath("fixtures", "test-tone.json").read_text())
        self.frames = tuple(base64.b64decode(p, validate=True) for p in fixture["packets"])

    def connection_made(self, transport):
        self.rtcp_transport = transport

    def connection_lost(self, exc):
        self.rtcp_transport = None

    @route.message("rtcp", "reply", "out", operation_id="roku.rtcp.reply",
                   summary="XDLY and NCLI replies sent to the client RTCP port.")
    @route.message("rtcp", "feedback", "in", operation_id="roku.rtcp.feedback",
                   summary="Private-listening RTCP APP and receiver feedback.")
    def datagram_received(self, data, addr):
        # RTCP can be compound. A malformed member must not cost the whole listener.
        offset = 0
        while offset + 4 <= len(data):
            version, kind, words = struct.unpack_from("!BBH", data, offset)
            size = (words + 1) * 4
            if version >> 6 != 2 or offset + size > len(data):
                return
            packet = data[offset:offset + size]
            offset += size
            for session in tuple(self.sessions.values()):
                if (session.mode != "datagram" or addr[0] != session.address[0]
                        or addr[1] not in (session.address[1], session.address[1] + 1)):
                    continue
                session.feedback += 1
                if kind == 203:  # BYE
                    if session.task:
                        session.task.cancel()
                elif kind == 204 and len(packet) >= 12 and self.rtcp_transport:
                    name, payload = packet[8:12], packet[12:]
                    if name == b"VDLY" and len(payload) == 4:
                        self.rtcp_transport.sendto(rtcp_app(b"XDLY", payload),
                                                   (session.address[0], session.address[1] + 1))
                    elif name == b"CVER" and len(payload) == 4:
                        self.rtcp_transport.sendto(rtcp_app(b"NCLI"),
                                                   (session.address[0], session.address[1] + 1))

    def target(self, data, peer):
        mode = data.get("param-audio-output")
        if mode == "datagram":
            devname = data.get("param-devname", "")
            if not isinstance(devname, str):
                raise ValueError("datagram requires a string destination")
            parts = devname.split(":")
            if len(parts) not in (4, 6):
                raise ValueError("datagram requires ip:port:payload-type:samples[:flags:duration]")
            host, port, pt, samples = parts[:4]
            port, pt, samples = int(port), int(pt), int(samples)
            if samples not in (480, 960) or not 0 <= pt <= 127:
                raise ValueError("The test fixture supports 480 or 960 samples per packet")
            samples = min(samples, self.profile().runtime["audio"]["rtp_packet_samples"])
            guid, version = data.get("param-guid", ""), 0
        elif mode == "mobile-sas":
            config = self.profile().runtime.get("audio", {})
            low = max(int(data["param-sas-min-version"]), config["sas_min_version"])
            high = min(int(data["param-sas-max-version"]), config["sas_max_version"])
            if low > high:
                raise ValueError("No common SAS version")
            host, port = data["param-sas-ip-address"], int(data["param-sas-port"])
            guid = data["param-guid"]
            if not isinstance(guid, str) or not guid:
                raise ValueError("SAS requires a client guid")
            version, pt, samples = high, 97, 480
        else:
            raise ValueError("No captured audio output for this destination")
        address = ipaddress.ip_address(host)
        if address.version != 4 or address != ipaddress.ip_address(peer) or not 1 <= port <= (65534 if mode == "datagram" else 65535):
            raise ValueError("Audio destination must be this connection's IPv4 peer and a UDP port")
        return mode, (str(address), port), guid, version, samples, pt

    async def start(self, data, owner, peer):
        values = self.target(data, peer)
        if not self.profile().runtime.get("audio"):
            raise ValueError("No private-listening evidence for the selected profile")
        if self.warm_up:
            await self.warm_up()
        await self.stop(owner)
        class Feedback(asyncio.DatagramProtocol):
            def datagram_received(_, packet, address):
                self.receive_sas_feedback(packet, address, owner)
            def error_received(_, error):
                self.core.record("audio", "private-listening.error", transport="udp",
                                 detail=str(error))
                self.cancel(owner)
        transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
            Feedback, local_addr=(self.bind_host(), 0))
        session = AudioSession(owner, *values[:3], values[3], values[4], values[5], transport)
        self.sessions[owner] = session
        session.task = asyncio.create_task(self.stream(session))
        self.core.record("audio", "private-listening.start", transport="udp", peer=peer,
                         detail=f"{session.mode}; test tone; {session.samples} samples/packet")
        self.publish(session)

    @route.message("sas", "feedback", "in", operation_id="roku.sas.feedback",
                   summary="Receiver timing status establishes a constant audio clock offset.")
    def receive_sas_feedback(self, packet, address, owner):
        session = self.sessions.get(owner)
        if session and address == session.address:
            session.feedback += 1
            # Measured v45 MainAudioStatus + MainAudioTiming. Keep the offset
            # constant: rebasing each feedback packet would move queued audio.
            if (session.mode == "mobile-sas" and session.clock_offset is None
                    and len(packet) >= 80 and packet[0] == session.version
                    and packet[25:27] == b"\x4c\x0e" and packet[41] == 38):
                playhead = int.from_bytes(packet[48:56], "little", signed=True)
                lead = self.profile().runtime["audio"]["sas_start_lead_samples"]
                offset = session.position - playhead - lead
                if -(1 << 47) < offset < (1 << 47):
                    session.clock_offset = offset

    def publish(self, session):
        connection = self.core.connections.get(session.owner)
        if connection is not None:
            connection["audio"] = {"transport": session.mode, "state": ("syncing" if session.mode == "mobile-sas"
                                             and session.clock_offset is None else "streaming"),
                                   "packets": session.packets, "bytes": session.bytes,
                                   "feedback": session.feedback,
                                   "experimental": session.mode == "mobile-sas",
                                   "clock_ready": session.clock_offset is not None}
            self.core.publish()

    @route.message("rtp", "audio", "out", operation_id="roku.rtp.audio",
                   summary="A prepared 48 kHz Opus test tone in RTP packets.")
    @route.message("sas", "audio", "out", operation_id="roku.sas.datagram",
                   summary="An experimental Opus test tone with SAS format-5 parity.")
    async def stream(self, session):
        loop = asyncio.get_running_loop()
        origin = loop.time()
        packet = 0
        frame = 0
        config = self.profile().runtime["audio"]
        ssrc = config["rtp_ssrc"] if session.mode == "datagram" else (secrets.randbits(32) or 1)
        fec = SasFecEncoder() if session.mode == "mobile-sas" else None
        try:
            while True:
                payload = self.frames[frame % len(self.frames)]
                frame += 1
                if session.samples == 960:
                    payload = opus_pair(payload, self.frames[frame % len(self.frames)])
                    frame += 1
                position = packet * session.samples
                session.position = position
                data = (rtp_packet(payload, packet,
                                    int((loop.time() - origin) * config["rtp_timestamp_rate"]),
                                    ssrc, session.payload_type)
                        if session.mode == "datagram" else
                        sas_packet(payload, packet + 1, position,
                                   ssrc, session.version, session.clock_offset))
                if fec is not None:
                    # Main and parity have separate network numbers and share an audio number.
                    data = data[:1] + struct.pack("<I", (packet * 2 + 1) & 0xffffffff) + data[5:]
                    datagrams = (data, fec.packet(data, packet * 2 + 2))
                else:
                    datagrams = (data,)
                for datagram in datagrams:
                    session.transport.sendto(datagram, session.address)
                    session.packets += 1
                    session.bytes += len(datagram)
                packet += 1
                if packet % 50 == 0:
                    self.publish(session)
                await asyncio.sleep(max(0, origin + packet * session.samples / 48000 - loop.time()))
        except asyncio.CancelledError:
            raise
        except (OSError, RuntimeError) as error:
            self.core.record("audio", "private-listening.error", transport="udp", detail=str(error))
        finally:
            session.transport.close()
            if self.sessions.get(session.owner) is session:
                self.sessions.pop(session.owner, None)
                connection = self.core.connections.get(session.owner)
                if connection is not None:
                    connection.pop("audio", None)
                self.core.record("audio", "private-listening.stopped", transport="udp",
                                 detail=f"{session.mode}; {session.packets} packets")

    def cancel(self, owner):
        # Release ownership and the socket before yielding. A request handler can be
        # cancelled while awaiting disconnect cleanup; it must not leave UDP sending.
        session = self.sessions.pop(owner, None)
        if session is None:
            return None
        session.transport.close()
        if session.task:
            session.task.cancel()
        connection = self.core.connections.get(owner)
        if connection is not None:
            connection.pop("audio", None)
        self.core.record("audio", "private-listening.stopped", transport="udp",
                         detail=f"{session.mode}; {session.packets} packets")
        return session.task

    async def stop(self, owner):
        task = self.cancel(owner)
        if task:
            await asyncio.gather(task, return_exceptions=True)

    async def disconnect(self, detail=None):
        for owner in tuple(self.sessions):
            await self.stop(owner)
