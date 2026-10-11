"""Evidence-derived intermediate representation of observed wire messages."""
from __future__ import annotations

import json
import plistlib
from dataclasses import dataclass, field
from typing import Any, Iterable
from xml.etree import ElementTree

from .claims import ConstraintClaim, OperationClaims, ValueSetClaim
from .evidence import Capture, EvidenceRef


@dataclass
class WireNode:
    """A lossless-enough logical node with explicit wire-format metadata."""

    types: set[str] = field(default_factory=set)
    properties: dict[str, "WireNode"] = field(default_factory=dict)
    items: "WireNode | None" = None
    wire: dict[str, Any] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    evidence: set[tuple[str, str]] = field(default_factory=set)
    values: list[Any] = field(default_factory=list)

    def merged(self, other: "WireNode") -> "WireNode":
        if "array" in self.types or "array" in other.types:
            left = self.items if "array" in self.types else self
            right = other.items if "array" in other.types else other
            return WireNode(types={"array"}, items=left.merged(right),
                            wire={**self.wire, **other.wire},
                            evidence=self.evidence | other.evidence,
                            values=_unique((*self.values, *other.values)))
        result = WireNode(types=self.types | other.types,
                          wire={**self.wire, **other.wire},
                          order=list(dict.fromkeys((*self.order, *other.order))),
                          evidence=self.evidence | other.evidence,
                          values=_unique((*self.values, *other.values)))
        for name in dict.fromkeys((*self.properties, *other.properties)):
            if name in self.properties and name in other.properties:
                result.properties[name] = self.properties[name].merged(other.properties[name])
            else:
                result.properties[name] = (self.properties[name] if name in self.properties
                                           else other.properties[name])
        return result


@dataclass(frozen=True)
class MessageSample:
    capture_id: str
    exchange_id: str
    media_type: str
    node: WireNode
    direction: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ObservedOperation:
    id: str
    transport: str
    samples: tuple[MessageSample, ...]

    def samples_for(self, direction: str | None = None) -> tuple[MessageSample, ...]:
        return tuple(sample for sample in self.samples
                     if direction is None or sample.direction == direction)

    def node(self, direction: str | None = None) -> WireNode:
        samples = self.samples_for(direction)
        if not samples:
            raise ValueError(f"{self.id}: no {direction or 'wire'} samples")
        found = samples[0].node
        for sample in samples[1:]:
            found = found.merged(sample.node)
        return found

    def media_types(self, direction: str | None = None) -> tuple[str, ...]:
        return tuple(dict.fromkeys(sample.media_type for sample in self.samples_for(direction)))


@dataclass(frozen=True)
class ContractIR:
    operations: dict[str, ObservedOperation]

    def operation(self, operation_id: str) -> ObservedOperation | None:
        return self.operations.get(operation_id)


def build_ir(captures: Iterable[Capture]) -> ContractIR:
    grouped: dict[str, list[MessageSample]] = {}
    transports: dict[str, str] = {}
    for capture in captures:
        for exchange in capture.exchanges.values():
            for step in exchange.steps:
                if step.payload is None:
                    continue
                media_type = _content_type(step.metadata)
                reference = EvidenceRef("capture", capture.id, exchange.id)
                node = parse_payload(step.payload, media_type, reference)
                operation_id = step.operation_id or exchange.operation_id
                grouped.setdefault(operation_id, []).append(
                    MessageSample(capture.id, exchange.id, media_type, node,
                                  step.direction, dict(step.metadata)))
                transports.setdefault(operation_id, exchange.transport)
    return ContractIR({operation_id: ObservedOperation(
        operation_id, transports[operation_id], tuple(samples))
        for operation_id, samples in grouped.items()})


def parse_payload(payload: bytes, media_type: str, evidence: EvidenceRef) -> WireNode:
    text = payload.decode("utf-8", "replace").lstrip()
    marker = {(evidence.capture, evidence.exchange)}
    # A binary plist holds the same scalar and container types JSON does.
    if "plist" in media_type or payload.startswith(b"bplist"):
        try:
            return _json_node(plistlib.loads(payload), marker)
        except (plistlib.InvalidFileException, ValueError):
            pass
    if "json" in media_type or text[:1] in ("{", "["):
        try:
            return _json_node(json.loads(text), marker)
        except ValueError:
            pass
    if "xml" in media_type or text[:1] == "<":
        try:
            return _xml_node(ElementTree.fromstring(text), marker, root=True)
        except ElementTree.ParseError:
            pass
    return WireNode(types={"blob"}, wire={"media_type": media_type}, evidence=marker)


def _json_node(value: Any, evidence: set[tuple[str, str]]) -> WireNode:
    if isinstance(value, dict):
        node = WireNode(types={"object"}, evidence=set(evidence))
        for name, item in value.items():
            node.properties[str(name)] = _json_node(item, evidence)
            node.order.append(str(name))
        return node
    if isinstance(value, list):
        item = WireNode()
        for value_item in value:
            parsed = _json_node(value_item, evidence)
            item = parsed if not item.types else item.merged(parsed)
        return WireNode(types={"array"}, items=item if item.types else WireNode(types={"unknown"}),
                        evidence=set(evidence))
    kind = ("null" if value is None else "boolean" if type(value) is bool else
            "integer" if type(value) is int else "number" if type(value) is float else
            "string" if isinstance(value, str) else "unknown")
    return WireNode(types={kind}, evidence=set(evidence), values=[value])


def _xml_node(element, evidence: set[tuple[str, str]], root: bool = False) -> WireNode:
    namespace, name = _qname(element.tag)
    children = list(element)
    wire = {"xml": {"name": name, "namespace": namespace, "node": "element"}}
    if not children and not element.attrib:
        return WireNode(types={"string"}, wire=wire, evidence=set(evidence),
                        values=[(element.text or "")])
    node = WireNode(types={"object"}, wire=wire, evidence=set(evidence))
    attribute_names = [_qname(raw_name)[1] for raw_name in element.attrib]
    for raw_name, value in element.attrib.items():
        attr_namespace, attr_name = _qname(raw_name)
        property_name = f"@{raw_name if attribute_names.count(attr_name) > 1 else attr_name}"
        node.properties[property_name] = WireNode(
            types={"string"}, evidence=set(evidence),
            values=[value],
            wire={"xml": {"name": attr_name, "namespace": attr_namespace,
                           "node": "attribute"}})
        node.order.append(property_name)
    text = (element.text or "").strip()
    if text:
        node.properties["#text"] = WireNode(
            types={"string"}, evidence=set(evidence),
            values=[text],
            wire={"xml": {"name": "#text", "node": "text"}})
        node.order.append("#text")
    qnames = [_qname(child.tag) for child in children]
    grouped: dict[str, list[Any]] = {}
    for child in children:
        namespace, child_name = _qname(child.tag)
        local_namespaces = {found_namespace for found_namespace, found_name in qnames
                            if found_name == child_name}
        property_name = child_name if len(local_namespaces) == 1 else child.tag
        grouped.setdefault(property_name, []).append(child)
        node.order.append(property_name)
    for property_name, members in grouped.items():
        _namespace, child_name = _qname(members[0].tag)
        parsed = _xml_node(members[0], evidence)
        for member in members[1:]:
            parsed = parsed.merged(_xml_node(member, evidence))
        if len(members) > 1:
            parsed = WireNode(types={"array"}, items=parsed,
                              wire={"xml": {"name": child_name, "wrapped": False}},
                              evidence=set(evidence))
        node.properties[property_name] = parsed
    return node


def _qname(value: str) -> tuple[str, str]:
    if value.startswith("{"):
        namespace, _, name = value[1:].partition("}")
        return namespace, name
    return "", value


def _content_type(metadata: dict[str, Any]) -> str:
    headers = metadata.get("headers", {})
    if isinstance(headers, dict):
        for name, value in headers.items():
            if str(name).lower() == "content-type":
                return str(value).partition(";")[0].strip()
    return "application/octet-stream"


def schema_for(node: WireNode, claims: OperationClaims | None = None,
               path: str = "") -> dict[str, Any]:
    """Render an observed node as an OpenAPI/JSON Schema object.

    Presence is never inferred.  Only an explicit PresenceClaim contributes to `required`.
    """
    if node.types == {"array"}:
        result = {"type": "array", "items": schema_for(node.items or WireNode(types={"unknown"}),
                                                         claims, path + "[]")}
    elif node.properties or "object" in node.types:
        properties = {}
        for name, child in node.properties.items():
            child_path = f"{path}.{name}" if path else name
            properties[name] = schema_for(child, claims, child_path)
        result = {"type": "object", "properties": properties}
        required = sorted(name for name in node.properties
                          if claims is not None
                          and (f"{path}.{name}" if path else name) in claims.required_paths())
        if required:
            result["required"] = required
    else:
        kinds = sorted("string" if item in ("blob", "unknown") else item for item in node.types)
        result = {"type": kinds[0] if len(kinds) == 1 else kinds}
        if "blob" in node.types:
            result["contentMediaType"] = node.wire.get("media_type", "application/octet-stream")
    if node.wire.get("xml"):
        xml = {key: value for key, value in node.wire["xml"].items()
               if key in ("name", "namespace", "wrapped") and value not in ("", None)}
        if node.wire["xml"].get("node") == "attribute":
            xml["attribute"] = True
        if xml:
            result["xml"] = xml
    for claim in claims.at(path) if claims is not None else ():
        if isinstance(claim, ValueSetClaim):
            result["enum" if claim.closed else "examples"] = [v.literal for v in claim.values]
        elif isinstance(claim, ConstraintClaim):
            keyword = {"min_length": "minLength", "max_length": "maxLength",
                       "minimum": "minimum", "maximum": "maximum",
                       "pattern": "pattern"}.get(claim.constraint)
            if keyword:
                result[keyword] = claim.value
    rationales = [claim.rationale for claim in claims.at(path)] if claims is not None else []
    if rationales:
        result["description"] = "\n".join(dict.fromkeys(rationales))
    return result


def paths_of(node: WireNode, prefix: str = "") -> dict[str, frozenset[str]]:
    """Comparable path/type projection used only for drift detection."""
    found: dict[str, frozenset[str]] = {}
    if node.types == {"array"}:
        return paths_of(node.items or WireNode(types={"unknown"}), prefix + "[]")
    if node.properties:
        if prefix:
            found[prefix] = frozenset(node.types or {"object"})
        for name, child in node.properties.items():
            here = f"{prefix}.{name}" if prefix else name
            found.update(paths_of(child, here))
    else:
        found[prefix or "."] = frozenset(node.types)
    return found


def values_at(node: WireNode, path: str) -> tuple[Any, ...]:
    """Observed scalar values at one claim path."""
    current = node
    if not path or path == ".":
        return tuple(current.values)
    for raw in path.split("."):
        name = raw.removesuffix("[]")
        if name:
            current = current.properties.get(name)  # type: ignore[assignment]
            if current is None:
                return ()
        if raw.endswith("[]"):
            current = current.items if current is not None else None  # type: ignore[assignment]
            if current is None:
                return ()
    return tuple(current.values)


def _unique(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if not any(value == existing and type(value) is type(existing) for existing in result):
            result.append(value)
    return result
