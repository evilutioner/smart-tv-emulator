"""Rendering the declared surface and the contract, for whoever is writing a driver.

Nothing here is a source of truth. The surface comes from the route declarations beside the
handlers, and the contract from each platform's `contract.py` measured against its own
captures, so a report cannot describe a television the emulator does not actually serve.

OpenAPI 3.2 is the HTTP projection and AsyncAPI 3.1 is the message-channel projection. Both
come from the same evidence-derived IR and typed curated claims; neither drives the emulator.

Captures decide which fields and wire types exist. Claims decide semantic requiredness,
closed value sets, constraints, serialization and conditional behaviour. Repetition across
captures never makes a field required.
"""
from __future__ import annotations

from importlib import import_module
import re
from typing import Any

from .claims import (
    BehaviorClaim, ConstraintClaim, OperationClaims, PresenceClaim, SerializationClaim,
    ValueSetClaim,
)
from .evidence import Capture, load_captures
from .ir import ContractIR, WireNode, build_ir, paths_of, schema_for, values_at
from .routing import Surface

# aiohttp names a path variable with an inline pattern; OpenAPI wants the bare name.
TEMPLATE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::[^}]*)?\}")


def captures_of(platform_id: str) -> dict[str, Capture]:
    return load_captures(f"tvemu.platforms.{platform_id}")


def _operation_claims(platform_id: str) -> dict[str, OperationClaims]:
    module = import_module(f"tvemu.platforms.{platform_id}.contract")
    return getattr(module, "OPERATION_CLAIMS", {})


def surface_of(platform_id: str) -> Surface | None:
    """The declared surface of one platform, without binding a single port."""
    from tvemu.core import Core
    from tvemu.platforms import create_platform, platform_descriptor

    return create_platform(platform_id, Core(platform_descriptor(platform_id))).surface()



def render_surface(surface: Surface) -> str:
    lines = [f"{surface.platform}: {len(surface.routes)} routes, "
             f"{len(surface.messages)} messages", ""]
    width = max((len(item.path) for item in surface.routes), default=4)
    for item in surface.routes:
        source = ("captured " + item.captured if item.captured else "computed")
        if item.refuses:
            source = f"always {item.refuses}"
        refusal = f" -> {item.missing} when uncaptured" if item.missing else ""
        lines.append(f"  {item.method:6} {item.path:{width}}  {source}{refusal}"
                     f"{'  [auth]' if item.auth else ''}")
        if item.summary:
            lines.append(f"  {'':6} {'':{width}}  {item.summary}")
    if surface.messages:
        lines += ["", "  messages"]
        for item in surface.messages:
            arrow = "<-" if item.direction == "out" else "->"
            lines.append(f"    {item.channel} {arrow} {item.name}: {item.summary}")
    return "\n".join(lines)


def render_contract(platform_id: str, surface: Surface) -> str:
    """The curated claims, then anything that makes them disagree with the evidence."""
    captures = captures_of(platform_id)
    lines = [f"{platform_id}: {len(captures)} capture{'' if len(captures) == 1 else 's'} "
             f"({', '.join(sorted(captures))})", ""]
    for operation in _operation_claims(platform_id).values():
        block = _claims_block(operation)
        if block:
            lines += block + [""]
    for item in contract_problems(platform_id, surface):
        lines.append(f"  PROBLEM  {item}")
    return "\n".join(lines)


def contract_problems(platform_id: str, surface: Surface) -> tuple[str, ...]:
    """Everything that makes the evidence, curated claims and surface disagree."""
    captures = captures_of(platform_id)
    observed = build_ir(captures.values())
    problems: list[str] = []
    declared_operations = {item.operation_id for item in (*surface.routes, *surface.messages)}
    for operation_id in observed.operations.keys() - declared_operations:
        problems.append(f"{operation_id}: captured operation has no executable declaration")
    operation_claims = _operation_claims(platform_id)
    for operation_id, declared in operation_claims.items():
        operation = observed.operation(operation_id)
        if operation is None:
            problems.append(f"{operation_id}: claims reference no captured operation")
            continue
        problems.extend(claim_problems(operation_id, operation, declared, captures))
    for operation_id, operation in observed.operations.items():
        statuses = {sample.metadata.get("status", 200)
                    for sample in operation.samples_for("out")
                    if "status" in sample.metadata}
        claims = operation_claims.get(operation_id)
        if len(statuses) > 1 and not any(isinstance(claim, BehaviorClaim)
                                         for claim in (claims.claims if claims else ())):
            problems.append(f"{operation_id}: multiple observed response statuses "
                            f"{sorted(statuses)} need a BehaviorClaim")
    return tuple(dict.fromkeys(problems))


def claim_problems(operation_id: str, operation, declared: OperationClaims,
                   captures: dict[str, Any]) -> tuple[str, ...]:
    """Validate typed claims against their evidence-derived operation."""
    problems: list[str] = []
    observed_paths = set().union(*(paths_of(sample.node) for sample in operation.samples))
    for claim in declared.claims:
        for reference in claim.evidence:
            if reference.kind != "capture":
                continue
            capture = captures.get(reference.capture)
            if capture is None or reference.exchange not in capture.exchanges:
                problems.append(f"{operation_id}: missing evidence "
                                f"{reference.capture}/{reference.exchange}")
            elif operation_id not in {
                step.operation_id or capture.exchanges[reference.exchange].operation_id
                for step in capture.exchanges[reference.exchange].steps
            }:
                problems.append(f"{operation_id}: evidence {reference.capture}/"
                                f"{reference.exchange} belongs to another operation")
        # A claim on a field no capture carries is a typo or a field the emulator writes
        # live; only the second is legitimate, and it says so with `scope="served"`.
        live = isinstance(claim, PresenceClaim) and (claim.scope == "served"
                                                     or claim.presence == "absent")
        if claim.path and not live and claim.path not in observed_paths:
            problems.append(f"{operation_id}: {claim.path} is in no capture")
        if isinstance(claim, PresenceClaim) and claim.presence == "required":
            for sample in operation.samples:
                if claim.path not in paths_of(sample.node):
                    problems.append(f"{operation_id}: required {claim.path} is absent from "
                                    f"{sample.capture_id}/{sample.exchange_id}")
        elif isinstance(claim, PresenceClaim) and claim.presence == "absent" \
                and claim.scope == "all":
            for sample in operation.samples:
                if claim.path in paths_of(sample.node):
                    problems.append(f"{operation_id}: absent {claim.path} is present in "
                                    f"{sample.capture_id}/{sample.exchange_id}")
        elif isinstance(claim, ValueSetClaim) and claim.closed:
            allowed = [value.literal for value in claim.values]
            for sample in operation.samples:
                for value in values_at(sample.node, claim.path):
                    if not any(value == item and type(value) is type(item) for item in allowed):
                        problems.append(f"{operation_id}: {claim.path} observed unknown "
                                        f"closed-set value {value!r} in "
                                        f"{sample.capture_id}/{sample.exchange_id}")
        elif isinstance(claim, ConstraintClaim):
            problems.extend(_constraint_problems(operation_id, operation, claim))
    return tuple(problems)


def _qualifier(claim) -> str:
    if isinstance(claim, PresenceClaim):
        return f"{claim.kind}: {claim.presence}"
    if isinstance(claim, ValueSetClaim):
        return f"{claim.kind}: {'closed' if claim.closed else 'open'}"
    if isinstance(claim, ConstraintClaim):
        return f"{claim.kind}: {claim.constraint}={claim.value!r}"
    if isinstance(claim, SerializationClaim):
        return f"{claim.kind}: {claim.feature}={claim.value!r}"
    if isinstance(claim, BehaviorClaim):
        return f"{claim.kind}: {claim.condition} -> {claim.outcome}"
    return claim.kind


def _grouped(claims) -> list[tuple[list[str], Any]]:
    """Consecutive claims that say the same thing about several fields, as one entry."""
    groups: list[tuple[list[str], Any]] = []
    for claim in claims:
        last = groups[-1][1] if groups else None
        if last is not None and _gist(last) == _gist(claim):
            groups[-1][0].append(claim.path)
        else:
            groups.append(([claim.path], claim))
    return groups


def _gist(claim) -> tuple:
    literals = tuple(value.literal for value in getattr(claim, "values", ()))
    return _qualifier(claim), claim.rationale, literals


def _values_line(claim) -> str:
    if not isinstance(claim, ValueSetClaim):
        return ""
    # A value no capture carries says where it came from; a captured one needs no note.
    listed = ", ".join(
        f"`{value.literal}`" + next((f" ({ref.kind})" for ref in value.evidence
                                     if ref.kind != "capture"), "")
        for value in claim.values)
    return f"Values: {listed}{'' if claim.closed else ', and possibly others'}."


def _claims_block(operation: OperationClaims) -> list[str]:
    if not operation.claims:
        return []
    lines = [f"  {operation.operation_id} -- {operation.summary}"]
    for paths, claim in _grouped(operation.claims):
        lines.append(f"    {', '.join(path or '(document)' for path in paths)}  "
                     f"[{_qualifier(claim)}]")
        lines += [f"      {line}" for line in _wrap(claim.rationale, 76)]
        if _values_line(claim):
            lines.append(f"      {_values_line(claim)}")
        sources = ", ".join(
            f"{ref.capture}/{ref.exchange}" if ref.kind == "capture"
            else f"{ref.kind}: {ref.detail}" for ref in claim.evidence)
        lines.append(f"      evidence: {sources}")
    return lines


def _wrap(text: str, width: int) -> list[str]:
    out: list[str] = []
    line = ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return [*out, line]


def openapi_documents(platform_id: str, surface: Surface) -> dict[str, dict]:
    """One OpenAPI document, or one per port when two ports answer the same request.

    A television that binds several HTTP applications can serve `GET /` on each of them, and
    one OpenAPI document has a single entry per method and path: folding them together would
    keep whichever came last. Only then is the export split by group, so a television whose
    ports share no route still reads as one document.
    """
    seen: dict[tuple[str, str], str] = {}
    shared = False
    for item in surface.routes:
        for method in _methods(item):
            key = (method, TEMPLATE.sub(r"{\1}", item.path))
            if seen.setdefault(key, item.group) != item.group:
                shared = True
    if not shared:
        return {"": openapi(platform_id, surface)}
    groups = dict.fromkeys(item.group for item in surface.routes)
    return {group: openapi(platform_id, surface, group=group) for group in groups}


def _methods(item) -> list[str]:
    return ["get", "post", "put", "patch", "delete"] if item.method == "*" \
        else [item.method.lower()]


def openapi(platform_id: str, surface: Surface, group: str | None = None) -> dict:
    """The HTTP half, in a shape Swagger UI and Postman already read.

    `group` narrows the document to the routes of one of the television's HTTP applications.
    """
    observed = _ir_of(platform_id)
    paths: dict[str, dict] = {}
    for item in surface.routes:
        if group is not None and item.group != group:
            continue
        path = TEMPLATE.sub(r"{\1}", item.path)
        methods = _methods(item)
        for method in methods:
            answer = ({str(item.refuses): {"description": "This television refuses this "
                                            "route; the description says why."}}
                      if item.refuses else _responses(platform_id, observed, item))
            operation_id = item.operation_id if len(methods) == 1 else \
                f"{item.operation_id}.{method}"
            entry = {"operationId": operation_id,
                     "summary": item.summary or item.path, "responses": answer}
            if item.missing:
                entry["responses"][str(item.missing)] = {
                    "description": "The selected capture has no fixture for this route."}
            if item.auth:
                entry["security"] = [{"deviceAuth": []}]
            paths.setdefault(path, {})[method] = entry
        for name in TEMPLATE.findall(item.path):
            paths[path].setdefault("parameters", []).append(
                {"name": name, "in": "path", "required": True,
                 "schema": {"type": "string"}})
    title = f"{surface.platform} emulated television"
    if group:
        title += f" ({group})"
    return {
        "openapi": "3.2.0",
        "info": {"title": title,
                 "version": "1",
                 "description": ("Generated from the emulator's route declarations. It "
                                 "describes the HTTP surface only: this television also "
                                 "answers on transports OpenAPI cannot express, which "
                                 "`tvemu --api-map` lists in full.")},
        "paths": paths,
        "components": {"securitySchemes": {"deviceAuth": {
            "type": "http", "scheme": "digest",
            "description": "Whatever pairing this television requires."}}},
    }


def _responses(platform_id: str, observed: ContractIR, item) -> dict[str, dict]:
    operation = observed.operation(item.operation_id)
    outputs = operation.samples_for("out") if operation is not None else ()
    if not outputs:
        # A computed route: its reply style is all that is known before it runs.
        content = {"content": {item.style.content_type: {}}} if item.style else {}
        return {"200": {"description": "The computed answer.", **content}}
    result: dict[str, dict] = {}
    statuses = dict.fromkeys(str(sample.metadata.get("status", 200)) for sample in outputs)
    claims = _claims_for(platform_id, item)
    for status in statuses:
        samples = tuple(sample for sample in outputs
                        if str(sample.metadata.get("status", 200)) == status)
        node = _merged_node(samples)
        content = {media_type: {"schema": schema_for(node, claims)}
                   for media_type in dict.fromkeys(sample.media_type for sample in samples)}
        result[status] = {"description": "An answer observed in capture evidence.",
                          "content": content}
        headers = _observed_headers(samples)
        if headers:
            result[status]["headers"] = headers
    return result


def surface_json(surface: Surface) -> dict:
    """Everything, including the transports OpenAPI has no words for."""
    return {
        "platform": surface.platform,
        "routes": [{"method": item.method, "path": item.path,
                    "operation_id": item.operation_id, "summary": item.summary,
                    "captured": item.captured, "missing": item.missing or None,
                    "refuses": item.refuses or None,
                    "auth": item.auth, "group": item.group or None,
                    "style": item.style.id if item.style else None}
                   for item in surface.routes],
        "messages": [{"channel": item.channel, "name": item.name,
                      "operation_id": item.operation_id,
                      "direction": item.direction, "summary": item.summary}
                     for item in surface.messages],
    }


def asyncapi(platform_id: str, surface: Surface) -> dict:
    """The message-driven half: WebSocket, MQTT and other declared channels."""
    observed = _ir_of(platform_id)
    channels: dict[str, dict] = {}
    messages: dict[str, dict] = {}
    operations: dict[str, dict] = {}
    for item in surface.messages:
        message_id = _component_name(item.operation_id)
        operation = observed.operation(item.operation_id)
        message: dict[str, Any] = {"name": item.name,
                                  "title": item.summary or item.name}
        samples = operation.samples_for(item.direction) if operation is not None else ()
        if samples:
            media_types = operation.media_types(item.direction)
            message["contentType"] = media_types[0]
            message["payload"] = schema_for(
                operation.node(item.direction), _claims_for(platform_id, item))
        messages[message_id] = message
        channel_id = _component_name(item.channel)
        channel = channels.setdefault(channel_id, {"address": item.channel, "messages": {}})
        channel["messages"][message_id] = {"$ref": f"#/components/messages/{message_id}"}
        operations[message_id] = {
            "action": "receive" if item.direction == "in" else "send",
            "channel": {"$ref": f"#/channels/{channel_id}"},
            "messages": [{"$ref": f"#/channels/{channel_id}/messages/{message_id}"}],
        }
    return {
        "asyncapi": "3.1.0",
        "info": {"title": f"{surface.platform} emulated television messages",
                 "version": "1",
                 "description": "Generated from executable message declarations and evidence."},
        "channels": channels,
        "operations": operations,
        "components": {"messages": messages},
    }


def _ir_of(platform_id: str) -> ContractIR:
    return build_ir(captures_of(platform_id).values())


def _claims_for(platform_id: str, item) -> OperationClaims:
    declared = _operation_claims(platform_id).get(item.operation_id)
    return OperationClaims(item.operation_id, item.summary or item.operation_id,
                           declared.claims if declared is not None else ())


def _component_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "-", value)


def _merged_node(samples) -> WireNode:
    node = samples[0].node
    for sample in samples[1:]:
        node = node.merged(sample.node)
    return node


def _observed_headers(samples) -> dict[str, dict]:
    found: dict[str, list[str]] = {}
    spelling: dict[str, str] = {}
    for sample in samples:
        headers = sample.metadata.get("headers", {})
        if not isinstance(headers, dict):
            continue
        for name, value in headers.items():
            key = str(name).casefold()
            if key == "content-type":
                continue
            spelling.setdefault(key, str(name))
            found.setdefault(key, [])
            if str(value) not in found[key]:
                found[key].append(str(value))
    return {spelling[key]: {"schema": {"type": "string"}, "examples": values}
            for key, values in found.items()}


def _constraint_problems(operation_id: str, operation, claim: ConstraintClaim) -> list[str]:
    problems: list[str] = []
    for sample in operation.samples:
        values = values_at(sample.node, claim.path)
        for value in values:
            invalid = False
            if claim.constraint == "min_length":
                invalid = not hasattr(value, "__len__") or len(value) < claim.value
            elif claim.constraint == "max_length":
                invalid = not hasattr(value, "__len__") or len(value) > claim.value
            elif claim.constraint == "minimum":
                invalid = not isinstance(value, (int, float)) or value < claim.value
            elif claim.constraint == "maximum":
                invalid = not isinstance(value, (int, float)) or value > claim.value
            elif claim.constraint == "pattern":
                invalid = not isinstance(value, str) or re.fullmatch(str(claim.value), value) is None
            elif claim.constraint == "nullable" and claim.value is False:
                invalid = value is None
            elif claim.constraint == "wire_type":
                actual = set(paths_of(sample.node).get(claim.path, ()))
                expected = {claim.value} if isinstance(claim.value, str) else set(claim.value)
                invalid = not actual or not actual <= expected
            if invalid:
                problems.append(f"{operation_id}: {claim.path} violates "
                                f"{claim.constraint}={claim.value!r} in "
                                f"{sample.capture_id}/{sample.exchange_id}")
    return problems


# ── the same two answers, as the markdown a platform guide embeds ──────────────────────

def markdown_surface(surface: Surface) -> str:
    """The surface table a guide carries, so nobody maintains it by hand."""
    # A television that binds several HTTP applications serves some paths on more than one of
    # them, and a table without the application would list the same row twice.
    grouped = len({item.group for item in surface.routes}) > 1
    lines = ["| Method | Path | Answers with | Auth |", "| --- | --- | --- | --- |"]
    if grouped:
        lines = ["| Application | Method | Path | Answers with | Auth |",
                 "| --- | --- | --- | --- | --- |"]
    for item in surface.routes:
        if item.refuses:
            answers = f"always **{item.refuses}**"
        elif item.captured == "*":
            answers = f"any other captured route, else **{item.missing}**"
        elif item.captured:
            answers = f"captured `{item.captured}`"
            if item.missing:
                answers += f", else **{item.missing}**"
        else:
            answers = "computed"
        # A route pattern may carry the character that ends a markdown cell.
        path = item.path.replace("|", "\\|")
        application = f"`{item.group or 'default'}` | " if grouped else ""
        lines.append(f"| {application}`{item.method}` | `{path}` | {answers} | "
                     f"{'yes' if item.auth else '—'} |")
    if surface.messages:
        channels = sorted({item.channel for item in surface.messages})
        for channel in channels:
            lines += ["", f"`{channel}` messages:", ""]
            for item in surface.messages:
                if item.channel != channel:
                    continue
                arrow = "from the set" if item.direction == "out" else "to the set"
                lines.append(f"- `{item.name}` ({arrow}) — {item.summary}")
    return "\n".join(lines)


def markdown_contract(platform_id: str, surface: Surface) -> str:
    """The curated claims, so a guide says nothing a reader could have assumed."""
    captures = captures_of(platform_id)
    lines = [f"Checked against {len(captures)} capture{'' if len(captures) == 1 else 's'}: "
             + ", ".join(f"`{name}`" for name in sorted(captures)) + "."]
    for operation in _operation_claims(platform_id).values():
        if not operation.claims:
            continue
        lines += ["", f"### {operation.summary}", ""]
        for paths, claim in _grouped(operation.claims):
            where = ", ".join(f"`{path}`" if path else "The whole document" for path in paths)
            lines.append(f"- **{where}** ({_qualifier(claim)}) — {claim.rationale}")
            if _values_line(claim):
                lines.append(f"  {_values_line(claim)}")
    return "\n".join(lines)
