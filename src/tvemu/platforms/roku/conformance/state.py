"""State transitions reached through ECP, UDP and the dashboard's real local API."""
import base64
import json
import re

from tvemu.platforms.common.evidence import load_capture
from tvemu.platforms.common.jsonbytes import replace_json_value
from tvemu.platforms.roku.ecp import auth_response

PROFILE = 'roku-streaming-stick-4k-3820eu2'
AUDIO = 'roku-audio-state-3820eu2-2026-10-18'
SCENARIOS = []
for capture, exchange, name, runtime in [
    (AUDIO, 'audio-states', 'audio-states', ['destination']),
    ('roku-text-write-3820eu2-2026-10-18', 'text-writes', 'text-writes', ['notification_clock']),
    ('roku-text-limits-3820eu2-2026-10-18', 'text-limits', 'text-limits', ['notification_clock']),
    ('roku-text-focus-3820eu2-2026-10-18', 'text-focus', 'text-focus', ['notification_clock']),
]:
    source = load_capture('tvemu.platforms.roku', capture).exchange(exchange)
    SCENARIOS.append({'name': name, 'profile': PROFILE, 'capture': capture,
                      'exchange': exchange, 'steps': list(range(len(source.steps))),
                      'protocol': 'ecp', 'runtime': runtime})
for phase in ('before', 'sas-running', 'sas-stopped', 'rtp-running', 'rtp-bye'):
    SCENARIOS.append({'name': 'audio-http-' + phase, 'profile': PROFILE, 'capture': AUDIO,
                      'exchange': 'http.' + phase, 'steps': [1], 'protocol': 'ecp',
                      'runtime': ['destination'] if phase == 'rtp-running' else []})


def wire(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()


async def authenticate(client, socket):
    challenge = await socket.receive_json(timeout=client.timeout)
    await socket.send_json({'request': 'authenticate', 'request-id': '0',
                            'param-response': auth_response(challenge['param-challenge'])})
    client.require((await socket.receive_json(timeout=client.timeout))['status'] == '200',
                   'state setup authentication failed')


def response_parts(raw, address):
    raw = raw.encode() if isinstance(raw, str) else raw
    value = json.loads(raw)
    parts = {}
    if 'timestamp' in value:
        if not isinstance(value['timestamp'], str) or not re.fullmatch(r'\d+\.\d{3}', value['timestamp']):
            raise ValueError('notification clock is not the measured decimal uptime string')
        parts['notification_clock'] = value['timestamp'].encode()
        raw = replace_json_value(raw, 'timestamp', b'"{clock}"')
    if value.get('response') == 'query-audio-device':
        body = base64.b64decode(value['content-data'])
        masked, destination = audio_parts(body, address)
        raw = replace_json_value(raw, 'content-data', json.dumps(base64.b64encode(masked).decode()).encode())
        if destination:
            parts['destination'] = destination
    parts['wire'] = raw
    return parts


def audio_parts(body, address):
    match = re.search(rb'<rtp-address>([^<]+)</rtp-address>', body)
    if not match:
        return body, b''
    if address is not None and match[1] != address.encode():
        raise ValueError('audio query did not report the actual RTP destination')
    return body[:match.start(1)] + b'{destination}' + body[match.end(1):], match[1]


async def audio_states(client):
    source = (client.capture if client.scenario.name == 'audio-states' else
              load_capture('tvemu.platforms.roku', AUDIO))
    steps = source.exchange('audio-states').steps
    endpoint = await client.listen()
    host, port = endpoint.address
    address = f'{host}:{port}'
    http_phase = client.scenario.exchange.removeprefix('http.')
    async with client.websocket('/ecp-session', ('ecp-2',)) as socket:
        await authenticate(client, socket)
        for index, step in enumerate(steps):
            original = json.loads(step.payload)
            if step.direction == 'in':
                value = dict(original)
                if value.get('request') == 'set-audio-output':
                    if value['param-audio-output'] == 'mobile-sas':
                        value.update({'param-sas-ip-address': host, 'param-sas-port': str(port)})
                    else:
                        value['param-devname'] = address + ':97:960'
                if step.metadata.get('phase') == 'rtp-bye':
                    import struct
                    endpoint.send(struct.pack('!BBHI', 0x81, 203, 1, 0),
                                  client.target('private-listening'))
                    # BYE is UDP: give the listener a turn before the next TCP query.
                    import asyncio
                    await asyncio.sleep(.02)
                outgoing = step.payload
                for field in ('param-sas-ip-address', 'param-sas-port', 'param-devname'):
                    if field in original:
                        outgoing = replace_json_value(outgoing, field, json.dumps(value[field]).encode())
                await socket.send_str(outgoing.decode())
                if client.scenario.name == 'audio-states':
                    expected, actual = step.payload, outgoing
                    parts_expected, parts_actual = {}, {}
                    for field in ('param-sas-ip-address', 'param-sas-port', 'param-devname'):
                        if field in original:
                            parts_expected[field], parts_actual[field] = original[field], value[field]
                            expected = replace_json_value(expected, field, b'"{destination}"')
                            actual = replace_json_value(actual, field, b'"{destination}"')
                    a, b = {'wire': expected}, {'wire': actual}
                    if parts_expected:
                        a['destination'], b['destination'] = wire(parts_expected), wire(parts_actual)
                    client.compare(index, a, b)
            else:
                raw = await socket.receive_str(timeout=client.timeout)
                if client.scenario.name == 'audio-states':
                    client.compare(index, response_parts(step.payload, None), response_parts(raw, address))
                elif (original.get('response') == 'query-audio-device'
                      and step.metadata.get('phase') == http_phase):
                    request = client.capture.exchange(client.scenario.exchange).steps[0]
                    method, path = request.metadata['method'], request.metadata['path']
                    url = f'http://{client.bound[0]}:{client.bound[1]}{path}'
                    async with client.session.request(method, url) as result:
                        body = await result.read()
                        client.require(result.status == client.step(1).metadata['status'],
                                       'HTTP audio query status differs')
                        client.require(result.headers.get('Content-Type') ==
                                       client.step(1).metadata['headers']['Content-Type'],
                                       'HTTP audio query content type differs')
                    expected, dest = audio_parts(client.step(1).payload, None)
                    actual, current = audio_parts(body, address)
                    a, b = {'body': expected}, {'body': actual}
                    if dest:
                        a['destination'], b['destination'] = dest, current
                    client.compare(1, a, b)
    client.note('Physical capture omitted UDP payloads. BYE input comes from the measured RTCP contract; destination endpoint is client-owned. Only the declared exchange is counted.')


async def text_state(client):
    async with client.websocket('/ecp-session', ('ecp-2',)) as socket:
        await authenticate(client, socket)
        await client.action('field', focused=True, content_type='full')
        for index in client.scenario.steps:
            step = client.step(index)
            payload = json.loads(step.payload)
            if step.direction == 'in':
                await socket.send_str(step.payload.decode())
                client.compare(index, {'wire': step.payload}, {'wire': step.payload})
            else:
                if client.scenario.name == 'text-focus' and payload.get('notify') in ('textedit-opened', 'textedit-closed'):
                    await client.action('field', focused=payload['notify'] == 'textedit-opened', content_type='full')
                raw = await socket.receive_str(timeout=client.timeout)
                client.compare(index, response_parts(step.payload, None), response_parts(raw, None))
    client.note('Opening/closing focus is emulator-owned dashboard setup; only recorded network steps are counted. Hidden fields and other native types remain unmeasured.')


async def run(name, client):
    if name.startswith('audio-'):
        await audio_states(client)
    else:
        await text_state(client)
