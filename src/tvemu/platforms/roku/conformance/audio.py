"""Partial UDP evidence, exercised over authenticated ecp-2 and actual datagrams."""
from __future__ import annotations

import base64
import json
from importlib.resources import files

from tvemu.platforms.roku.ecp import auth_response
from tvemu.platforms.common.evidence import load_capture

PROFILE = "roku-streaming-stick-4k-3820eu2"
SAS_CAPTURE = "roku-sas-clock-3820eu2-2026-10-18"
RTP_CAPTURE = "roku-rtp-clock-3820eu2-2026-10-18"

SCENARIOS = [
    {"name": "sas-clock", "profile": PROFILE, "capture": SAS_CAPTURE,
     "exchange": "clock-start", "steps": [0, 1, 2], "protocol": "ecp",
     "runtime": ["network_sequence", "audio_sequence", "sample_position", "stream_id",
                 "payload_size", "payload", "sync_clock"]},
    {"name": "rtp-framing", "profile": PROFILE, "capture": RTP_CAPTURE,
     "exchange": "rtp-start", "steps": [0, 1, 2], "protocol": "ecp",
     "runtime": ["timestamp", "payload"]},
    {"name": "rtcp-captured-handshake", "profile": PROFILE, "capture": RTP_CAPTURE,
     "exchange": "rtp-start", "steps": [3, 4], "protocol": "ecp", "runtime": []},
    {"name": "rtcp-ordered", "profile": PROFILE,
     "capture": "roku-rtcp-handshake-3820eu2-2026-10-18",
     "exchange": "rtcp-handshake", "steps": [0, 1, 2, 3], "protocol": "ecp", "runtime": []},
]


# Keep the earlier partial stream visible, including its separate parity datagrams.
for number in (0, 2, 4, 6):
    SCENARIOS.append({
        "name": f"sas-start-{number:02}", "profile": PROFILE,
        "capture": "roku-ecp2-surface-3820eu2-2026-10-18",
        "exchange": f"sas-{number:02}", "steps": [0], "protocol": "ecp",
        "runtime": list(SCENARIOS[0]["runtime"]),
    })
for number in (1, 3, 5, 7):
    SCENARIOS.append({
        "name": f"sas-fec-{number:02}", "profile": PROFILE,
        "capture": "roku-ecp2-surface-3820eu2-2026-10-18",
        "exchange": f"sas-{number:02}", "steps": [0], "protocol": "ecp",
        "runtime": ["fec_size", "fec_payload"],
    })

SCENARIOS.append({
    "name": "sas-fec-history", "profile": PROFILE,
    "capture": "roku-sas-fec5-3820eu2-2026-10-18", "exchange": "fec-start",
    "steps": list(range(10)), "protocol": "ecp",
    "runtime": [*SCENARIOS[0]["runtime"], "fec_size", "fec_payload"],
})


def sas_parts(data):
    if (len(data) < 37 or data[9:12] != b"\x93\x40\x0c"):
        raise ValueError("SAS packet does not have the measured main-audio layout")
    end = 26 + int.from_bytes(data[24:26], "little")
    if len(data) != end + 11:
        raise ValueError("SAS packet length does not match its audio payload")
    return {"version": data[:1], "network_sequence": data[1:5],
            "audio_sequence": data[5:9], "presence": data[9:11],
            "header_size": data[11:12], "sample_position": data[12:18],
            "stream_id": data[18:22], "codec_flags": data[22:24],
            "payload_size": data[24:26], "payload": data[26:end],
            "sync_size": data[end:end + 1], "sync_clock": data[end + 1:end + 7],
            "sync_delay_flags": data[end + 7:end + 10], "direct_fec": data[end + 10:]}


def rtp_parts(data):
    if len(data) < 12 or data[0] != 0x80:
        raise ValueError("RTP packet does not have the captured header layout")
    return {"version_flags": data[:1], "payload_type": data[1:2], "sequence": data[2:4],
            "timestamp": data[4:8], "ssrc": data[8:12], "payload": data[12:]}


def fec_parts(data):
    if len(data) < 21 or data[9:11] != b"\x80\x40":
        raise ValueError("SAS packet does not have the measured format-5 layout")
    end = 13 if data[11] & 128 else 12
    size = (data[11] & 127) | (data[12] << 7) if end == 13 else data[11]
    if len(data) != end + size or data[end] != 5:
        raise ValueError("SAS parity length or format differs from the capture")
    return {"version": data[:1], "network_sequence": data[1:5],
            "audio_sequence": data[5:9], "presence": data[9:11],
            "fec_size": data[11:end], "format": data[end:end + 1],
            "distances": data[end + 1:end + 5], "base": data[end + 5:end + 9],
            "fec_payload": data[end + 9:]}


def validate_fec(client, raw, history):
    """Independent polynomial oracle; never calls the sender's parity encoder."""
    parts = fec_parts(raw)
    base = int.from_bytes(parts["base"], "little")
    client.require(base == int.from_bytes(parts["audio_sequence"], "little"),
                   "FEC base differs from its audio number")
    client.require(int.from_bytes(parts["network_sequence"], "little") == base * 2,
                   "FEC network number is not the following even packet")
    client.require(parts["distances"] == bytes(range(1, min(base, 5)))
                   + bytes(max(0, 5 - base)), "FEC history distances are discontinuous")
    # Native coefficient rows, independently applied without the production lookup table.
    rows = ("0301060501020e06", "0d08070706080805", "02060d020107080f", "030c0c0a0a010b08",
            "0f010f030c0d0e01", "060c0c05060f0b0f", "0a060e0407040e07", "07060a030d090301")
    coefficients = bytes.fromhex(rows[base % 8])

    def multiply(a, b):
        product = 0
        for bit in range(4):
            if b & (1 << bit):
                product ^= a << bit
        for bit in range(6, 3, -1):
            if product & (1 << bit):
                product ^= 0x13 << (bit - 4)
        return product

    terms = [base, *(base - d for d in parts["distances"] if d)]
    vectors = []
    for number in terms:
        client.require(number in history, "FEC refers to a main packet absent from this session")
        main = history[number]
        prefix = main[:26 + int.from_bytes(main[24:26], "little")]
        vectors.append((number, len(prefix).to_bytes(2, "little") + prefix))
    parity = bytearray(max(len(vector) for _, vector in vectors))
    for number, vector in vectors:
        coefficient = coefficients[number % 8]
        for index, value in enumerate(vector):
            parity[index] ^= multiply(coefficient, value & 15) | (multiply(coefficient, value >> 4) << 4)
    client.require(parts["fec_payload"] == parity, "SAS parity does not protect the received main history")
    return parts


def frames(client):
    wire = ("fec-start" if client.scenario.name == "sas-fec-history" else
            "fec" if client.scenario.name.startswith("sas-fec-") else
            "sas" if client.scenario.name.startswith("sas-") else "rtp")
    declared = client.reference.runtime["audio"]["wire_substitutions"][wire]
    client.require(set(declared) == client.scenario.runtime,
                   "binary runtime substitutions differ from the selected profile")
    name = client.reference.runtime["audio"]["fixture"]
    fixture = json.loads(files("tvemu.platforms.roku").joinpath("fixtures", name).read_text())
    client.require(fixture["sample_rate"] == 48000 and fixture["samples_per_packet"] == 480,
                   "test fixture format differs from the measured 10 ms Opus contract")
    return tuple(base64.b64decode(packet, validate=True) for packet in fixture["packets"])


async def configure(client, socket, endpoint, mode):
    challenge = await socket.receive_json(timeout=client.timeout)
    await socket.send_json({"request": "authenticate", "request-id": "0",
                            "param-response": auth_response(challenge["param-challenge"])})
    response = await socket.receive_json(timeout=client.timeout)
    client.require(response.get("status") == "200", "audio setup authentication failed")
    source = client.reference.capture.exchange(
        client.reference.replays["action.set-audio-output"])
    request = json.loads(source.steps[0].payload)
    host, port = endpoint.address
    request.update({"request-id": "audio", "param-audio-output": mode})
    if mode == "mobile-sas":
        request.update({"param-sas-ip-address": host, "param-sas-port": str(port),
                        "param-guid": "conformance-audio"})
    else:
        request = {"request": "set-audio-output", "request-id": "audio",
                   "param-audio-output": mode, "param-devname": f"{host}:{port}:97:960"}
    await socket.send_json(request)
    response = await socket.receive_json(timeout=client.timeout)
    client.require(response.get("status") == "200", "audio setup was refused")


def validate_sas(client, parts, fixture):
    position = int.from_bytes(parts["sample_position"], "little")
    number = int.from_bytes(parts["audio_sequence"], "little")
    client.require(position % 480 == 0 and position == (number - 1) * 480,
                   "SAS sample position is not continuous 480-sample audio")
    client.require(parts["payload"] == fixture[(position // 480) % len(fixture)],
                   "SAS payload is not the profile-declared prepared test fixture")
    return position


async def sas_clock(client):
    fixture = frames(client)
    endpoint = await client.listen()
    async with client.websocket("/ecp-session", ("ecp-2",)) as socket:
        await configure(client, socket, endpoint, "mobile-sas")
        raw, peer = await endpoint.receive(client.timeout)
        initial = sas_parts(raw)
        position = validate_sas(client, initial, fixture)
        client.require(position == 0, "first SAS packet did not start at sample zero")
        client.require(int.from_bytes(initial["sync_clock"], "little", signed=True) == -(1 << 47),
                       "SAS startup did not carry the captured unknown-clock sentinel")
        client.compare(0, sas_parts(client.step(0).payload), initial)
        history = {1: raw}
        # The receiver's stream id belongs to this newly opened session. All other status
        # bytes are the captured receiver input, including its arbitrary playhead origin.
        recorded = client.step(1).payload
        feedback = bytearray(recorded)
        feedback[27:31] = initial["stream_id"]
        client.compare(1, {"stream_id": recorded[27:31], "status": recorded[:27] + recorded[31:]},
                       {"stream_id": bytes(feedback[27:31]),
                        "status": bytes(feedback[:27] + feedback[31:])})
        endpoint.send(feedback, peer)
        skipped = 0
        for _ in range(100):
            raw, address = await endpoint.receive(client.timeout)
            client.require(address == peer, "SAS sender changed its UDP endpoint")
            if raw[9:11] == b"\x80\x40":
                validate_fec(client, raw, history)
                skipped += 1
                continue
            parts = sas_parts(raw)
            history[int.from_bytes(parts["audio_sequence"], "little")] = raw
            current = validate_sas(client, parts, fixture)
            client.require(parts["stream_id"] == initial["stream_id"], "SAS stream id changed")
            clock = int.from_bytes(parts["sync_clock"], "little", signed=True)
            if clock == -(1 << 47):
                skipped += 1
                continue
            playhead = int.from_bytes(recorded[48:56], "little", signed=True)
            lead = client.reference.runtime["audio"]["sas_start_lead_samples"]
            client.require(position <= clock + playhead + lead <= current,
                           "finite clock does not schedule samples against receiver playhead")
            client.compare(2, sas_parts(client.step(2).payload), parts)
            client.note(f"partial clock capture: {skipped} intervening datagrams were not "
                        "byte-compared; parity is checked against received main history; "
                        "loss recovery and continuous timing are not covered")
            break
        else:
            raise ValueError("receiver timing never produced a finite SAS clock")


async def rtp_framing(client):
    fixture = frames(client)
    endpoint = await client.listen()
    async with client.websocket("/ecp-session", ("ecp-2",)) as socket:
        await configure(client, socket, endpoint, "datagram")
        initial_time = initial_arrival = None
        for index in client.scenario.steps:
            raw, _ = await endpoint.receive(client.timeout)
            parts = rtp_parts(raw)
            sequence = int.from_bytes(parts["sequence"], "big")
            client.require(parts["payload"] == fixture[sequence % len(fixture)],
                           "RTP payload differs from the prepared 10 ms fixture")
            timestamp = int.from_bytes(parts["timestamp"], "big")
            if initial_time is None:
                initial_time, initial_arrival = timestamp, endpoint.received_at
            else:
                ticks = (timestamp - initial_time) % (1 << 32)
                elapsed = endpoint.received_at - initial_arrival
                rate = client.reference.runtime["audio"]["rtp_timestamp_rate"]
                client.require(abs(ticks - elapsed * rate) <= 250,
                               "RTP timestamps do not advance on the measured millisecond scale")
            client.compare(index, rtp_parts(client.step(index).payload), parts)
        client.note("Only captured RTP framing steps are compared; RTCP answers are a "
                    "separate scenario with a later ordered capture of the incoming bytes")


async def sas_start(client):
    fixture = frames(client)
    endpoint = await client.listen()
    async with client.websocket("/ecp-session", ("ecp-2",)) as socket:
        await configure(client, socket, endpoint, "mobile-sas")
        raw, _ = await endpoint.receive(client.timeout)
        parts = sas_parts(raw)
        client.require(validate_sas(client, parts, fixture) == 0, "SAS startup skipped sample zero")
        client.require(int.from_bytes(parts["sync_clock"], "little", signed=True) == -(1 << 47),
                       "SAS startup clock is not the captured sentinel")
        client.compare(0, sas_parts(client.step(0).payload), parts)
        client.note("Partial silent main-audio capture; captured audio is replaced only "
                    "by the profile-declared owned test fixture")


async def sas_fec(client):
    fixture = frames(client)
    endpoint = await client.listen()
    ordered = client.scenario.name == "sas-fec-history"
    expected = fec_parts(client.step(9 if ordered else 0).payload)
    target = int.from_bytes(expected["base"], "little")
    history = {}
    async with client.websocket("/ecp-session", ("ecp-2",)) as socket:
        await configure(client, socket, endpoint, "mobile-sas")
        for number in range(1, target + 1):
            main, peer = await endpoint.receive(client.timeout)
            parts = sas_parts(main)
            validate_sas(client, parts, fixture)
            client.require(int.from_bytes(parts["audio_sequence"], "little") == number,
                           "main audio numbers are discontinuous")
            client.require(int.from_bytes(parts["network_sequence"], "little") == number * 2 - 1,
                           "main network number is not the preceding odd packet")
            history[number] = main
            if ordered:
                client.compare((number - 1) * 2, sas_parts(client.step((number - 1) * 2).payload), parts)
            raw, address = await endpoint.receive(client.timeout)
            client.require(address == peer, "FEC was sent from a different UDP endpoint")
            actual = validate_fec(client, raw, history)
            if ordered:
                index = number * 2 - 1
                client.compare(index, fec_parts(client.step(index).payload), actual)
            elif number == target:
                client.compare(0, expected, actual)
    client.note("Only the selected capture steps are byte-compared; parity equations also "
                "check all preceding received main packets. Receiver loss recovery is not covered.")


async def rtcp_handshake(client, ordered):
    audio, control = await client.listen_pair()
    source = load_capture("tvemu.platforms.roku", "roku-rtcp-handshake-3820eu2-2026-10-18")
    steps = source.exchange("rtcp-handshake").steps
    async with client.websocket("/ecp-session", ("ecp-2",)) as socket:
        await configure(client, socket, audio, "datagram")
        for index in (0, 2):
            request = steps[index].payload
            if ordered:
                client.compare(index, {"packet": client.step(index).payload}, {"packet": request})
            audio.send(request, client.target("private-listening"))
            received, _ = await control.receive(client.timeout)
            target = index + 1 if ordered else 3 + index // 2
            client.compare(target, {"packet": client.step(target).payload}, {"packet": received})
    if not ordered:
        client.note("The earlier out-only answers are reached using request bytes measured "
                    "in the later ordered RTCP capture, not reconstructed probe traffic")


async def run(name, client):
    if name == "sas-clock":
        await sas_clock(client)
    elif name.startswith("sas-start-"):
        await sas_start(client)
    elif name.startswith("sas-fec-"):
        await sas_fec(client)
    elif name == "rtp-framing":
        await rtp_framing(client)
    elif name in ("rtcp-ordered", "rtcp-captured-handshake"):
        await rtcp_handshake(client, name == "rtcp-ordered")
    else:
        raise ValueError(f"unknown datagram scenario {name}")
