"""The frozen Agent OS host contract.

Everything a host (OpenCode, and later other agents) exchanges with the
engine goes through this package. The wire format is JSON with a
``schema_version``; the shape is defined here once and validated on both
sides so a change cannot silently break a host.
"""

from aos.contract.schema import (
    CONTRACT_VERSION,
    SUPPORTED_VERSIONS,
    ValidationError,
    unread_request_fields,
    validate_request,
)
from aos.contract.preflight import build_preflight, fallback_preflight, validate_preflight
from aos.contract.postflight import build_postflight, fallback_postflight, validate_postflight
from aos.contract.legacy import to_adapter_context

__all__ = [
    "CONTRACT_VERSION",
    "SUPPORTED_VERSIONS",
    "ValidationError",
    "build_preflight",
    "fallback_preflight",
    "validate_preflight",
    "build_postflight",
    "fallback_postflight",
    "validate_postflight",
    "validate_request",
    "unread_request_fields",
    "to_adapter_context",
]
