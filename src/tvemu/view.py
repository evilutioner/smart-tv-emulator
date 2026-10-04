"""The declared shape of `/api/v1/state`, which the dashboard reads and nothing validated.

`Core.snapshot()` builds the document; this file says what that document contains. The two are
kept honest by a test that walks a live snapshot against the declaration, so a field added to
one and not the other is a red test rather than a dashboard that silently reads `undefined`.

A schema rather than a set of dataclasses, for one reason: the `device` block is the captured
profile's own summary merged with the fields shared code adds, and which keys a profile
contributes is per-device data. A dataclass would have to either enumerate them -- naming
televisions in a shared file -- or carry an untyped bag that declares nothing. The schema says
exactly that much: these fields always, whatever the profile adds beside them.
"""
from __future__ import annotations

SCHEMA_VERSION = 2

# One entry per top-level key of the snapshot: its JSON type, and what it is for.
FIELDS: dict[str, tuple[str, str]] = {
    "schema_version": ("integer", "The shape of this document; bumped when it changes."),
    "revision": ("integer", "Increases on every publish, so a client can tell them apart."),
    "device": ("object", "Identity and address, the captured profile's summary merged with "
                         "the platform and the live address."),
    "device_profiles": ("array", "Every captured device this platform can become."),
    "platforms": ("array", "Every television the product models, including those this build "
                           "cannot run, which carry availability 'n/a'."),
    "settings": ("object", "The only block that is ever persisted."),
    "keys": ("array", "The remote keys this platform's set has."),
    "access_modes": ("array", "The 'who may control this TV' values this firmware offers."),
    "protocols": ("array", "One row per protocol the active device exposes."),
    "access": ("object", "The access mode in force."),
    "service_listening": ("boolean", "Whether the primary protocol is bound."),
    "discovery_active": ("boolean", "Whether any discovery responder is answering."),
    "discovery_error": ("string|null", "Why discovery is not answering, if it is not."),
    "connections": ("array", "Sessions currently open on the emulated device."),
    "held_keys": ("array", "Keys held down across every session."),
    "counts": ("object", "How many times each key has been accepted."),
    "accepted": ("integer", "Commands accepted since the last reset."),
    "rejected": ("integer", "Commands refused since the last reset."),
    "last_key": ("object|null", "The most recent remote key event; typed text is not one."),
    "keyboard": ("object|null", "Null when the platform declares no keyboard, which hides "
                                "the tile without anything naming a television."),
    "voice": ("object|null", "Null when the platform exposes no voice input. Counters, status "
                             "and `detected`, a description of the stream's format worked out "
                             "from it: received audio never reaches this document."),
    "applications": ("object|null", "Null when the platform has no app-launch surface."),
    "power": ("boolean", "Simulated device state."),
    "volume": ("integer", "Simulated device state, on the platform's own scale."),
    "muted": ("boolean", "Simulated device state."),
    "events": ("array", "The bounded event log, oldest first."),
    "limitations": ("string", "What this platform does not emulate, in one line."),
    "pairing": ("object|null", "Null when the platform needs no pairing."),
}

# Blocks whose own members are worth declaring, because the dashboard reads them by name.
ROW_FIELDS: dict[str, tuple[str, ...]] = {
    "protocols": ("id", "label", "kind", "summary", "control", "primary", "protocol_label",
                  "scheme", "port", "advertised_ports", "enabled", "listening", "armed",
                  "error"),
    "access": ("id", "label", "summary", "status_label", "badge", "discoverable"),
    "device": ("profile", "platform", "platform_name", "host", "port", "protocol",
               "transports", "scheme", "discovery"),
}


def json_type(value) -> str:
    if value is None:
        return "null"
    return {bool: "boolean", int: "integer", float: "number", str: "string",
            list: "array", dict: "object", tuple: "array"}.get(type(value), "unknown")


def conforms(name: str, value) -> bool:
    declared = FIELDS.get(name)
    return declared is not None and json_type(value) in declared[0].split("|")


def schema() -> dict:
    """The snapshot as JSON Schema, for whoever is reading the dashboard API."""
    properties = {}
    for name, (types, description) in FIELDS.items():
        entry: dict = {"description": description}
        options = types.split("|")
        entry["type"] = options if len(options) > 1 else options[0]
        if name in ROW_FIELDS:
            member = {key: {} for key in ROW_FIELDS[name]}
            if entry["type"] == "array":
                entry["items"] = {"type": "object", "properties": member}
            else:
                entry["properties"] = member
                entry["additionalProperties"] = name == "device"
        properties[name] = entry
    return {"type": "object", "required": sorted(FIELDS), "properties": properties}


def openapi() -> dict:
    """The local management API, which unlike a television is a contract we control."""
    snapshot = {"$ref": "#/components/schemas/Snapshot"}
    ok = {"200": {"description": "The whole state of the emulator.",
                  "content": {"application/json": {"schema": snapshot}}}}
    return {
        "openapi": "3.1.0",
        "info": {"title": "Smart TV Emulator management API", "version": str(SCHEMA_VERSION),
                 "description": "Local, loopback-only. Not the emulated television: "
                                "`tvemu --api-map <platform>` describes that."},
        "paths": {
            "/api/v1/state": {"get": {"summary": "The current snapshot.", "responses": ok}},
            "/api/v1/settings": {"patch": {"summary": "Change settings and re-reconcile.",
                                           "responses": ok}},
            "/api/v1/platform": {"post": {
                "summary": "Switch the emulated television.",
                "responses": {**ok, "501": {
                    "description": "A television this product models that this build does "
                                   "not include; the body carries reason 'n/a'."}}}},
            "/api/v1/settings/save": {"post": {"summary": "Persist the settings block.",
                                               "responses": {"200": {"description": "Saved."}}}},
            "/api/v1/actions/{name}": {"post": {"summary": "Run one dashboard action.",
                                                "responses": ok}},
            "/api/v1/events": {"get": {"summary": "A WebSocket pushing a snapshot per "
                                                  "revision.",
                                       "responses": {"101": {"description": "Switching."}}}},
            "/api/v1/events/export": {"get": {
                "summary": "The event log as newline-delimited JSON.",
                "responses": {"200": {"description": "An attachment."}}}},
            "/api/v1/openapi.json": {"get": {"summary": "This document.",
                                             "responses": {"200": {"description": "Itself."}}}},
        },
        "components": {"schemas": {"Snapshot": schema()}},
    }
