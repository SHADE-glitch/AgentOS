"""Provider registry for the Agent OS loop."""

from __future__ import annotations

from aos.adapters.base import (
    Provider,
    ProviderResult,
    available,
    get,
    register,
    reset,
)

__all__ = ["Provider", "ProviderResult", "available", "get", "register", "reset"]
