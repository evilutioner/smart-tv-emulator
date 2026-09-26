"""Rules about declared surfaces and contracts, stated for whichever platforms a build ships.

No television is named here. Every case walks the platforms that declare a surface and skips
when a build ships none, so this file says the same thing in the published repository as in
this one.
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

import support  # noqa: F401  -- registers the stub platforms
from support import STUB_IDS

from tvemu.core import Core
from tvemu.platforms import create_platform, platform_descriptor, platform_ids
from tvemu.platforms.common import report
from tvemu.platforms.common.claims import (
    ClaimedValue, OperationClaims, PresenceClaim, ValueSetClaim,
)
from tvemu.platforms.common.evidence import EvidenceRef
from tvemu.platforms.common.profile import DISCOVERY_STATEMENTS, has_discovery_evidence
from tvemu.platforms.common.ir import build_ir, paths_of, schema_for, values_at


PLATFORMS = Path(__file__).parents[1] / "src" / "tvemu" / "platforms"


def declared() -> list[tuple[str, object]]:
    found = []
    for platform_id in platform_ids():
        surface = report.surface_of(platform_id)
        if surface is not None:
            found.append((platform_id, surface))
    return found


DECLARED = declared()


def needs_declared(case):
    if not DECLARED:
        raise unittest.SkipTest("this build ships no platform that declares its surface")
    return DECLARED


def profiles_of(platform_id: str) -> dict:
    return create_platform(platform_id, Core(platform_descriptor(platform_id))).load_profiles()


class ContractTests(unittest.TestCase):
    def test_contract_check_is_the_merge_gate(self):
        """Stale claims, typos and bad evidence references are all blocking."""
        for platform_id, surface in needs_declared(self):
            with self.subTest(platform=platform_id):
                self.assertEqual(report.contract_problems(platform_id, surface), ())


class SurfaceTests(unittest.TestCase):
    def test_every_declared_route_reaches_a_handler_that_exists(self):
        for platform_id, surface in needs_declared(self):
            for item in surface.routes:
                with self.subTest(platform=platform_id, path=item.path):
                    self.assertTrue(item.handler)
                    self.assertTrue(item.summary, "a declared route says what it answers")

    def test_every_declared_message_reaches_a_handler_that_exists(self):
        for platform_id, surface in needs_declared(self):
            for item in surface.messages:
                with self.subTest(platform=platform_id, operation=item.operation_id):
                    self.assertTrue(item.handler)
                    self.assertTrue(item.summary)

    def test_the_declarations_are_the_routes_the_server_registers(self):
        """No route reaches the server except through a declaration, and none is lost."""
        for platform_id, surface in needs_declared(self):
            with self.subTest(platform=platform_id):
                registered = set()
                for app in _apps(platform_id):
                    for item in app.router.routes():
                        # aiohttp answers HEAD off every GET route of its own accord.
                        if item.method == "HEAD":
                            continue
                        registered.add((item.method, item.resource.canonical))
                declared_here = {(item.method, _canonical(item.path))
                                 for item in surface.routes}
                self.assertTrue(registered)
                self.assertEqual(registered, declared_here)

    def test_a_route_that_always_refuses_replays_nothing(self):
        for platform_id, surface in needs_declared(self):
            for item in surface.routes:
                with self.subTest(platform=platform_id, path=item.path):
                    self.assertFalse(item.refuses and item.captured)

    def test_every_rendering_names_the_platform_and_survives_its_own_data(self):
        for platform_id, surface in needs_declared(self):
            with self.subTest(platform=platform_id):
                self.assertIn(platform_id, report.render_surface(surface))
                self.assertIn(platform_id, report.render_contract(platform_id, surface))
                self.assertEqual(report.openapi(platform_id, surface)["openapi"], "3.2.0")
                self.assertEqual(report.asyncapi(platform_id, surface)["asyncapi"], "3.1.0")
                self.assertEqual(report.surface_json(surface)["platform"], platform_id)

    def test_openapi_covers_the_http_routes_and_says_it_covers_no_more(self):
        """A driver author must not read the OpenAPI file as the whole television."""
        for platform_id, surface in needs_declared(self):
            with self.subTest(platform=platform_id):
                documents = report.openapi_documents(platform_id, surface)
                for group, document in documents.items():
                    routes = [item for item in surface.routes
                              if list(documents) == [""] or item.group == group]
                    self.assertIn("HTTP surface only", document["info"]["description"])
                    self.assertEqual(len(document["paths"]),
                                     len({_canonical(item.path) for item in routes}))

    def test_no_route_is_lost_when_two_ports_answer_the_same_request(self):
        """One document per port only when needed, and never one operation for two."""
        for platform_id, surface in needs_declared(self):
            with self.subTest(platform=platform_id):
                documents = report.openapi_documents(platform_id, surface)
                exported = sum(len([method for method in path if method != "parameters"])
                               for document in documents.values()
                               for path in document["paths"].values())
                expected = {(item.group if len(documents) > 1 else "", method,
                             _canonical(item.path))
                            for item in surface.routes
                            for method in (["get", "post", "put", "patch", "delete"]
                                           if item.method == "*" else [item.method.lower()])}
                self.assertEqual(exported, len(expected))

    def test_exported_operation_ids_are_unique_and_async_refs_resolve(self):
        for platform_id, surface in needs_declared(self):
            with self.subTest(platform=platform_id):
                documents = report.openapi_documents(platform_id, surface)
                for openapi in documents.values():
                    operation_ids = [operation["operationId"]
                                     for path in openapi["paths"].values()
                                     for method, operation in path.items()
                                     if method != "parameters"]
                    self.assertEqual(len(operation_ids), len(set(operation_ids)))
                asyncapi = report.asyncapi(platform_id, surface)
                self.assertEqual(documents, report.openapi_documents(platform_id, surface))
                self.assertEqual(asyncapi, report.asyncapi(platform_id, surface))
                for channel in asyncapi["channels"].values():
                    for reference in channel["messages"].values():
                        message = reference["$ref"].removeprefix("#/components/messages/")
                        self.assertIn(message, asyncapi["components"]["messages"])
                for operation in asyncapi["operations"].values():
                    channel = operation["channel"]["$ref"].removeprefix("#/channels/")
                    self.assertIn(channel, asyncapi["channels"])
                    for reference in operation["messages"]:
                        prefix = f"#/channels/{channel}/messages/"
                        self.assertTrue(reference["$ref"].startswith(prefix))
                        message = reference["$ref"].removeprefix(prefix)
                        self.assertIn(message, asyncapi["channels"][channel]["messages"])


class EvidenceTests(unittest.TestCase):
    """A capture is evidence. Only a complete capture referenced by a profile is selectable."""

    def test_an_unprofiled_capture_is_never_a_selectable_television(self):
        for platform_id in platform_ids():
            profiles = profiles_of(platform_id)
            used = {getattr(profile, "capture_id", "") for profile in profiles.values()}
            captures = set(report.captures_of(platform_id)) - used
            if not captures:
                continue
            with self.subTest(platform=platform_id):
                self.assertEqual(sorted(captures & set(profiles)), [],
                                 "an unprofiled capture may not shadow a profile id")
                core = Core(platform_descriptor(platform_id))
                create_platform(platform_id, core).publish_profile()
                offered = {row["id"] for row in core.snapshot()["device_profiles"]}
                self.assertEqual(sorted(offered & captures), [],
                                 "an unprofiled capture reached the dashboard selector")

    def test_profiles_reference_complete_local_captures_and_replay_their_bytes(self):
        found = 0
        for platform_id in platform_ids():
            if platform_id in STUB_IDS:
                continue
            captures = report.captures_of(platform_id)
            for profile in profiles_of(platform_id).values():
                found += 1
                with self.subTest(platform=platform_id, profile=profile.id):
                    self.assertTrue(profile.capture_id, "a profile must reference a capture")
                    self.assertIn(profile.capture_id, captures)
                    capture = captures[profile.capture_id]
                    self.assertTrue(capture.platform.get("protocols"))
                    self.assertTrue(has_discovery_evidence(capture))
                    for name, body in profile.documents.items():
                        if profile.substitutions_for(name):
                            continue
                        # An exchange may carry many frames; any output step can be replayed.
                        self.assertIn(body, [step.payload
                                            for exchange in capture.exchanges.values()
                                            for step in exchange.outputs()])
        self.assertGreater(found, 0, "no evidence-backed profile is installed")

    def test_a_profile_directory_holds_only_its_reference(self):
        """Raw bytes live in evidence; a profile that kept one would replay it unchecked."""
        for platform_id in platform_ids():
            if platform_id in STUB_IDS:
                continue
            root = PLATFORMS / platform_id / "profiles"
            for directory in sorted(item for item in root.iterdir() if item.is_dir()):
                with self.subTest(platform=platform_id, profile=directory.name):
                    self.assertEqual(sorted(item.name for item in directory.iterdir()),
                                     ["profile.json"])

    def test_every_shipped_platform_declares_its_surface(self):
        for platform_id in platform_ids():
            if platform_id in STUB_IDS:
                continue
            with self.subTest(platform=platform_id):
                self.assertIsNotNone(report.surface_of(platform_id))

    def test_a_discovery_statement_says_why_and_is_one_of_the_known_kinds(self):
        """No discovery evidence must be either an observation or a named gap, never silence."""
        for platform_id in platform_ids():
            for capture in report.captures_of(platform_id).values():
                statement = capture.platform.get("discovery")
                if statement is None:
                    continue
                with self.subTest(platform=platform_id, capture=capture.id):
                    self.assertIn(statement.get("status"), DISCOVERY_STATEMENTS)
                    self.assertTrue(statement.get("detail"))

    def test_every_capture_builds_an_ir_and_every_payload_reference_exists(self):
        found = 0
        for platform_id in platform_ids():
            captures = report.captures_of(platform_id)
            if not captures:
                continue
            found += len(captures)
            ir = build_ir(captures.values())
            self.assertTrue(ir.operations)
            for capture in captures.values():
                for exchange in capture.exchanges.values():
                    for step in exchange.steps:
                        if step.payload_name:
                            self.assertIsNotNone(step.payload)
        self.assertGreater(found, 0)


class ObservedIRTests(unittest.TestCase):
    def samples(self, media: str):
        for platform_id in platform_ids():
            for operation in build_ir(report.captures_of(platform_id).values()).operations.values():
                for sample in operation.samples:
                    if media in sample.media_type:
                        yield operation, sample

    def json_objects(self):
        # Chosen by parsed shape, not header: a WebSocket frame carries no Content-Type.
        for operation, sample in self.samples(""):
            if sample.node.types == {"object"} and "xml" not in sample.node.wire:
                yield operation, sample

    def test_presence_is_optional_until_a_semantic_claim_requires_it(self):
        operation, sample = next(self.json_objects())
        node = sample.node
        path = next(iter(node.properties))
        reference = EvidenceRef("capture", sample.capture_id, sample.exchange_id)
        self.assertNotIn("required", schema_for(node))
        claims = OperationClaims(operation.id, "sample", (
            PresenceClaim(path, "The protocol addresses the record by this field.",
                          (reference,), presence="required"),
        ))
        self.assertEqual(schema_for(node, claims)["required"], [path])

    def test_xml_projection_preserves_namespace_attributes_text_order_and_repetition(self):
        samples = list(self.samples("xml"))
        self.assertTrue(samples, "no named XML exchange exercises the projector")
        roots = [sample.node for _, sample in samples]
        self.assertTrue(any(node.wire["xml"].get("namespace") for node in roots))

        all_nodes = []
        def visit(node):
            all_nodes.append(node)
            if node.items is not None:
                visit(node.items)
            for child in node.properties.values():
                visit(child)
        for node in roots:
            visit(node)
        self.assertTrue(any(node.types == {"array"} for node in all_nodes),
                        "no named exchange proves repeated XML elements")
        attribute = next(node for node in all_nodes
                         if node.wire.get("xml", {}).get("node") == "attribute")
        self.assertTrue(attribute.values)
        self.assertTrue(schema_for(attribute)["xml"]["attribute"])
        self.assertTrue(any(node.values for node in all_nodes
                            if node.wire.get("xml", {}).get("node") == "element"))
        self.assertTrue(any(node.order for node in all_nodes))

    def test_closed_value_sets_reject_new_values_while_open_sets_accept_them(self):
        operation, sample = next(self.json_objects())
        path = next(path for path in paths_of(sample.node) if values_at(sample.node, path))
        evidence = EvidenceRef("probe", detail="Synthetic claim-validation probe")
        value = ClaimedValue("__not_an_observed_value__", (evidence,))
        closed = OperationClaims(operation.id, "sample", (
            ValueSetClaim(path, "Only the probed value is accepted.", (evidence,),
                          (value,), closed=True),
        ))
        opened = OperationClaims(operation.id, "sample", (
            ValueSetClaim(path, "Other firmware may add values.", (evidence,),
                          (value,), closed=False),
        ))
        self.assertTrue(report.claim_problems(operation.id, operation, closed, {}))
        self.assertEqual(report.claim_problems(operation.id, operation, opened, {}), ())


def _canonical(path: str) -> str:
    """The path as aiohttp reports it, with each variable's inline pattern dropped."""
    return re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::[^}]*)?\}", r"{\1}", path)


def _apps(platform_id: str):
    """Every aiohttp application this platform builds from its declarations."""
    adapter = create_platform(platform_id, Core(platform_descriptor(platform_id)))
    for listener in adapter.listeners.values():
        if listener.app is not None:
            app = listener.app()
            if any(item.resource is not None for item in app.router.routes()):
                yield app


class GuideTests(unittest.TestCase):
    """A platform guide's generated blocks are the code's, not a reader's to maintain."""

    def test_no_guide_has_fallen_behind_the_code(self):
        tools = Path(__file__).parents[1] / "tools"
        if not (tools / "render_docs.py").is_file():
            raise unittest.SkipTest("this repository ships no documentation renderer")
        result = subprocess.run([sys.executable, str(tools / "render_docs.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
