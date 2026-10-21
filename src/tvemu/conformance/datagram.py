"""Explicit evidence scenarios over real UDP sockets.

These supplement selectable-profile replays. Partial captures remain partial: each recipe
names the exact steps it exercises, runtime binary parts, and any scenarios left uncovered.
Platform recipes own packet layouts and use this client's sockets, never adapter handlers.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

import aiohttp


@dataclass(frozen=True)
class Scenario:
    name: str
    profile: str
    capture: str
    exchange: str
    steps: tuple[int, ...]
    protocol: str
    runtime: frozenset[str]
    gap: str = ""


def scenarios(module, profile: str | None) -> tuple[Scenario, ...]:
    found = []
    names = set()
    rows = getattr(module, "DATAGRAM_SCENARIOS", ())
    if not isinstance(rows, (tuple, list)):
        raise ValueError("datagram evidence scenarios must be a list")
    for row in rows:
        required = {"name", "profile", "capture", "exchange", "steps", "protocol", "runtime"}
        if (not isinstance(row, dict) or required - set(row)
                or set(row) - required - {"gap"}
                or not all(isinstance(row[k], str) and row[k] for k in required - {"steps", "runtime"})
                or not isinstance(row["steps"], list) or not row["steps"]
                or not all(type(i) is int and i >= 0 for i in row["steps"])
                or row["steps"] != sorted(set(row["steps"]))
                or not isinstance(row["runtime"], list)
                or not all(isinstance(k, str) and k and k != "*" for k in row["runtime"])
                or not isinstance(row.get("gap", ""), str)):
            raise ValueError("malformed datagram evidence scenario")
        identity = (row["profile"], row["name"])
        if "/" in row["name"] or "\\" in row["name"]:
            raise ValueError("datagram scenario name must be one path segment")
        if identity in names:
            raise ValueError(f"duplicate datagram scenario {row['name']}")
        names.add(identity)
        if profile is not None and row["profile"] != profile:
            continue
        if not row.get("gap") and not callable(getattr(module, "datagram_scenario", None)):
            raise ValueError("datagram scenarios need a datagram_scenario function")
        found.append(Scenario(row["name"], row["profile"], row["capture"], row["exchange"],
                              tuple(row["steps"]), row["protocol"],
                              frozenset(row["runtime"]), row.get("gap", "")))
    return tuple(found)


class Endpoint(asyncio.DatagramProtocol):
    def __init__(self):
        self.queue = asyncio.Queue(maxsize=1024)
        self.transport = None
        self.error = None
        self.peers = set()
        self.received_at = 0.0

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, address):
        self.peers.add(address)
        try:
            self.queue.put_nowait((data, address, asyncio.get_running_loop().time()))
        except asyncio.QueueFull:
            self.error = ValueError("UDP evidence receiver overflowed")

    def error_received(self, error):
        self.error = error

    @property
    def address(self):
        return self.transport.get_extra_info("sockname")[:2]

    async def receive(self, timeout):
        if self.error:
            raise self.error
        data, address, self.received_at = await asyncio.wait_for(self.queue.get(), timeout)
        return data, address

    def send(self, data, address):
        self.transport.sendto(data, address)


class Client:
    """Network-only recipe surface, plus explicit comparisons and report notes."""
    def __init__(self, bound, authority, capture, scenario, timeout, result, reference, targets):
        self.bound, self.authority = bound, authority
        self.capture, self.scenario = capture, scenario
        self.reference = reference
        self.targets = targets
        self.timeout, self.result = timeout, result
        self.endpoints = []
        self.session = None
        self.used = set()
        self.compared_steps = set()

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(trust_env=False)
        return self

    async def __aexit__(self, *args):
        try:
            await self.session.close()
        finally:
            for endpoint in self.endpoints:
                endpoint.transport.close()

    async def listen(self, port=0):
        endpoint = Endpoint()
        await asyncio.get_running_loop().create_datagram_endpoint(
            lambda: endpoint, local_addr=(self.bound[0], port))
        self.endpoints.append(endpoint)
        return endpoint

    async def listen_pair(self):
        for _ in range(100):
            first = await self.listen()
            try:
                second = await self.listen(first.address[1] + 1)
                return first, second
            except (OSError, OverflowError):
                first.transport.close()
                await asyncio.sleep(0)
        raise ValueError("could not bind adjacent UDP client ports")

    def target(self, protocol):
        return self.targets[protocol]

    async def action(self, name, **data):
        """A dashboard action over the local management listener, not adapter internals."""
        if not name.isidentifier():
            raise ValueError("a control action must be one path segment")
        async with self.session.post(self.control_url + "api/v1/actions/" + name,
                                     headers={"Host": "127.0.0.1:8888"}, json=data) as response:
            self.require(response.status == 200, f"dashboard action {name} failed")
            return await response.json()

    @asynccontextmanager
    async def websocket(self, path, protocols=()):
        url = f"http://{self.bound[0]}:{self.bound[1]}{path}"
        async with self.session.ws_connect(url, protocols=protocols,
                                           headers={"Host": self.authority}) as socket:
            yield socket

    def step(self, index):
        if index not in self.scenario.steps:
            raise ValueError(f"step {index} is not declared by this evidence scenario")
        return self.capture.exchange(self.scenario.exchange).steps[index]

    def require(self, condition, message):
        if not condition:
            raise ValueError(message)

    def note(self, text):
        self.result.notes.append(text)

    def compare(self, index, expected: dict[str, bytes], actual: dict[str, bytes]):
        """All binary parts must be present; only named runtime parts may differ.

        A platform parser must account for the entire packet. Its recipe validates the
        runtime values (for example against an owned fixture) before calling this method.
        """
        self.step(index)
        self.require(set(expected) == set(actual), "binary part names differ")
        self.require(bool(expected), "a binary comparison cannot be empty")
        for name in expected:
            self.require(isinstance(expected[name], bytes) and isinstance(actual[name], bytes),
                         f"binary part {name} is not bytes")
            if name in self.scenario.runtime:
                self.used.add(name)
            elif expected[name] != actual[name]:
                self.result.problems.append(f"step {index}, binary part {name}: bytes differ")
        self.compared_steps.add(index)

    def finish(self):
        omitted = set(self.scenario.steps) - self.compared_steps
        unused = self.scenario.runtime - self.used
        if omitted:
            self.result.problems.append(f"evidence steps not exercised: {sorted(omitted)}")
        if unused:
            self.result.problems.append(f"runtime parts not exercised: {sorted(unused)}")
