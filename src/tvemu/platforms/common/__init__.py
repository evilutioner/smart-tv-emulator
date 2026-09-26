"""Implementation shared by every Smart TV platform adapter."""

from .adapter import BaseAdapter
from .claims import (
    BehaviorClaim, ClaimedValue, ConstraintClaim, OperationClaims, PresenceClaim,
    SerializationClaim, ValueSetClaim,
)
from .evidence import Capture, EvidenceRef, Exchange, Step
from .mdns import MDNSAdvertisement
from .profile import CapturedProfile, ProtocolBinding
from .reply import ErrorFormat, ReplyStyle, WireError, missing_capture
from .routing import Message, RouteSpec, Surface
from .ssdp import SSDPResponder, search_target
from .tls import TLSStream, certificate_fingerprint, server_context

__all__ = [
    "BaseAdapter", "BehaviorClaim", "Capture", "CapturedProfile", "ClaimedValue",
    "ConstraintClaim", "ErrorFormat", "EvidenceRef", "Exchange",
    "MDNSAdvertisement",
    "Message", "ProtocolBinding", "ReplyStyle", "RouteSpec", "SSDPResponder",
    "OperationClaims", "PresenceClaim", "SerializationClaim", "Step", "Surface",
    "TLSStream", "ValueSetClaim", "WireError", "certificate_fingerprint",
    "missing_capture", "search_target", "server_context",
]
