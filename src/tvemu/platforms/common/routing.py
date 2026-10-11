"""Route declarations that sit next to the handler they describe.

The whole emulated surface of a television used to be legible only by reading every
`app.add_routes` call in its package. Here a handler carries its own declaration -- what it
answers with, which captured document it replays, what it does when the capture lacks one --
and `attach` builds the aiohttp routes from those declarations. The registry cannot drift from
the code, because it is the code.

HTTP is the smaller half of this product. A WebSocket envelope or a discovery target is
declared with `Message`, so a surface map shows the whole television rather than the part that
happens to travel over HTTP.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator

from aiohttp import web

from .reply import ReplyStyle

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "*")


@dataclass(frozen=True)
class RouteSpec:
    """One HTTP route of one emulated television."""

    method: str
    path: str
    operation_id: str = ""
    summary: str = ""
    # The key this route replays out of the captured profile; "" when the body is computed.
    captured: str = ""
    # What this firmware answers when the selected capture has no fixture for the route.
    missing: int = 0
    style: ReplyStyle | None = None
    auth: bool = False
    # Which of a platform's HTTP applications serves this route. A television that binds
    # several ports declares them all in one place and `attach` takes the group it is building.
    group: str = ""
    # The status a route answers with every time, for one this television refuses outright.
    # Declared, because "this set will not serve it" is a fact about the set, not a gap here.
    refuses: int = 0
    # aiohttp answers HEAD off every GET route; a firmware that tells the two apart says so.
    head: bool = True
    handler: str = ""

    def __post_init__(self) -> None:
        if self.refuses and self.captured:
            raise ValueError(f"{self.path}: a route that always refuses replays nothing")
        if self.method not in METHODS:
            raise ValueError(f"{self.path}: unknown method {self.method}")
        if not self.path.startswith("/"):
            raise ValueError(f"{self.path}: a route path starts with /")
        if self.missing and not self.captured:
            raise ValueError(f"{self.path}: only a captured route has a missing status")
        if not self.operation_id:
            raise ValueError(f"{self.path}: a route needs a stable operation_id")


@dataclass(frozen=True)
class Message:
    """One envelope on a surface that is not HTTP: a WebSocket frame, a discovery target."""

    channel: str
    name: str
    direction: str             # "in" | "out"
    summary: str = ""
    operation_id: str = ""
    handler: str = ""

    def __post_init__(self) -> None:
        if self.direction not in ("in", "out"):
            raise ValueError(f"{self.name}: direction must be in or out")
        if not self.operation_id:
            object.__setattr__(self, "operation_id", f"{self.channel}.{self.name}")


def _declare(method: str, path: str, **spec: Any) -> Callable:
    def decorate(function):
        declared = getattr(function, "wire_routes", ())
        options = dict(spec)
        operation_id = options.pop("operation_id", "") or (
            f"http.{function.__name__}." + path.strip("/").replace("/", ".")
            .replace("{", "").replace("}", "").replace(":", "-")
        ).rstrip(".")
        # Decorators apply bottom-up, so prepending keeps the source order of a stacked handler.
        function.wire_routes = (RouteSpec(method=method, path=path,
                                          operation_id=operation_id,
                                          handler=function.__name__, **options), *declared)
        return function
    return decorate


def get(path: str, **spec: Any) -> Callable: return _declare("GET", path, **spec)
def post(path: str, **spec: Any) -> Callable: return _declare("POST", path, **spec)
def put(path: str, **spec: Any) -> Callable: return _declare("PUT", path, **spec)
def patch(path: str, **spec: Any) -> Callable: return _declare("PATCH", path, **spec)
def delete(path: str, **spec: Any) -> Callable: return _declare("DELETE", path, **spec)
def any_method(path: str, **spec: Any) -> Callable: return _declare("*", path, **spec)


def message(channel: str, name: str, direction: str, **spec: Any) -> Callable:
    """Declare a non-HTTP message on the function that sends or handles it."""
    def decorate(function):
        declared = getattr(function, "wire_messages", ())
        options = dict(spec)
        operation_id = options.pop("operation_id", "") or f"{channel}.{name}"
        function.wire_messages = (Message(channel, name, direction,
                                           operation_id=operation_id,
                                           handler=function.__name__, **options), *declared)
        return function
    return decorate


def declarations(surface: type | object, group: str | None = None
                 ) -> Iterator[tuple[RouteSpec, str]]:
    """Every route a surface declares, in the order its class body declares them.

    Order is the contract: a catch-all route must stay last, and the class body is where that
    is visible. Python keeps class attributes in definition order, so nothing has to say it
    twice.
    """
    owner = surface if isinstance(surface, type) else type(surface)
    for klass in reversed(owner.__mro__):
        for name, attribute in vars(klass).items():
            for spec in getattr(attribute, "wire_routes", ()):
                if group is None or spec.group == group:
                    yield spec, name


def message_declarations(surface: type | object) -> Iterator[tuple[Message, str]]:
    owner = surface if isinstance(surface, type) else type(surface)
    for klass in reversed(owner.__mro__):
        for name, attribute in vars(klass).items():
            for spec in getattr(attribute, "wire_messages", ()):
                yield spec, name


def attach(app: web.Application, surface: object, group: str = "") -> web.Application:
    """Register the declared routes of one group of `surface` on `app`."""
    app.add_routes([web.route(spec.method, spec.path, getattr(surface, name),
                              **({} if spec.head or spec.method != "GET"
                                 else {"allow_head": False}))
                    for spec, name in declarations(surface, group)])
    return app


@dataclass(frozen=True)
class Surface:
    """Everything one platform answers, HTTP and otherwise, as declared."""

    platform: str
    routes: tuple[RouteSpec, ...] = ()
    messages: tuple[Message, ...] = ()
