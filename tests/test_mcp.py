"""The MCP server answers the protocol and reaches the emulator through the local API."""
from __future__ import annotations

import io
import json
import socket
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from aiohttp.test_utils import TestServer

from tvemu import mcp
from tvemu.control import control_app
from tvemu.core import Core, Settings
from tests.support import quiet_protocols
from tvemu.platforms import create_platform, default_platform, platform_descriptor
from tvemu.runtime import Runtime


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = mcp.Server("http://127.0.0.1:1")   # nothing listens: protocol only

    async def call(self, method, params=None, ident=1):
        return await self.server.handle({"jsonrpc": "2.0", "id": ident, "method": method,
                                         "params": params or {}})

    async def test_initialize_names_the_server_and_offers_tools(self):
        result = (await self.call("initialize", {"protocolVersion": "2025-06-18"}))["result"]
        self.assertEqual(result["serverInfo"]["name"], "tvemu")
        self.assertIn("tools", result["capabilities"])

    async def test_every_listed_tool_is_implemented(self):
        tools = (await self.call("tools/list"))["result"]["tools"]
        self.assertEqual({tool["name"] for tool in tools}, set(mcp.TOOLS))
        for tool in tools:
            self.assertTrue(callable(getattr(self.server, tool["name"])), tool["name"])
            self.assertEqual(tool["inputSchema"]["type"], "object")

    async def test_a_notification_gets_no_answer(self):
        self.assertIsNone(await self.server.handle(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}))

    async def test_an_unknown_method_is_a_json_rpc_error(self):
        self.assertEqual((await self.call("resources/list"))["error"]["code"], -32601)

    async def test_an_unreachable_emulator_is_a_tool_error_not_a_crash(self):
        result = (await self.call("tools/call", {"name": "state"}))["result"]
        self.assertTrue(result["isError"])
        self.assertIn("not reachable", result["content"][0]["text"])

    async def test_the_contract_is_read_without_a_running_emulator(self):
        platform = default_platform()
        result = (await self.call("tools/call", {"name": "api_map",
                                                 "arguments": {"platform": platform}}))["result"]
        self.assertFalse(result["isError"], result)

    async def test_stdio_carries_one_message_per_line(self):
        requests = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 7, "method": "ping"}) + "\n")
        responses = io.StringIO()
        await mcp.serve(self.server, requests, responses)
        self.assertEqual(json.loads(responses.getvalue()), {"jsonrpc": "2.0", "id": 7,
                                                            "result": {}})


class LiveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        platform_id = default_platform()
        descriptor = platform_descriptor(platform_id)
        self.core = Core(descriptor, Settings())
        self.core.host = "127.0.0.1"
        self.core.service_port = free_port()
        self.core.settings = replace(self.core.settings, protocols=quiet_protocols(descriptor))
        self.runtime = Runtime(self.core, create_platform(platform_id, self.core))
        await self.runtime.start()
        self.addAsyncCleanup(self.runtime.close)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        port = free_port()
        self.http = TestServer(control_app(self.runtime, Path(temporary.name) / "s.json",
                                           port=port), host="127.0.0.1", port=port)
        await self.http.start_server()
        self.addAsyncCleanup(self.http.close)
        self.server = mcp.Server(f"http://127.0.0.1:{port}")

    async def tool(self, name, **arguments):
        response = await self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                             "params": {"name": name, "arguments": arguments}})
        return response["result"]

    async def test_state_is_the_snapshot_without_its_log(self):
        result = await self.tool("state")
        self.assertFalse(result["isError"], result)
        snapshot = json.loads(result["content"][0]["text"])
        self.assertEqual(snapshot["device"]["platform"], self.core.platform.id)
        self.assertNotIn("events", snapshot)

    async def test_expect_reads_what_arrived_and_fails_on_what_did_not(self):
        self.assertFalse((await self.tool("clear_log"))["isError"])
        self.core.record("command", "probe/one", status=200)
        passed = await self.tool("expect", expect=[{"operation": "probe/*", "status": 200}])
        self.assertFalse(passed["isError"], passed)
        failed = await self.tool("expect", expect=[{"operation": "probe/two"}])
        self.assertTrue(failed["isError"])
        self.assertFalse(json.loads(failed["content"][0]["text"])["ok"])

    async def test_events_since_an_id_are_only_the_new_ones(self):
        first = self.core.record("command", "probe/before")
        self.core.record("command", "probe/after")
        rows = json.loads((await self.tool("events", since_id=first["id"]))["content"][0]["text"])
        self.assertEqual([row["operation"] for row in rows], ["probe/after"])

    async def test_reset_goes_through_the_management_api(self):
        self.assertFalse((await self.tool("reset"))["isError"])

    async def test_bad_arguments_are_reported_to_the_agent(self):
        result = await self.tool("events", nonsense=1)
        self.assertTrue(result["isError"])


if __name__ == "__main__":
    unittest.main()
