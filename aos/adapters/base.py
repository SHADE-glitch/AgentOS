"""Provider protocol and registry.

A *provider* is whatever actually runs the task: the OpenCode CLI, the host
itself (delegation), or a deterministic test double. The loop only knows this
interface, so adding a provider never touches the lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# Result statuses. ``delegated`` means the host will do the work and the
# postflight stages will run later, out of band.
STATUS_SUCCESS = "success"
STATUS_TIMEOUT = "timeout"
STATUS_ERROR = "error"
STATUS_DELEGATED = "delegated"

_STATUSES = frozenset({STATUS_SUCCESS, STATUS_TIMEOUT, STATUS_ERROR, STATUS_DELEGATED})


@dataclass
class ProviderResult:
    """The normalised outcome of one provider invocation."""

    status: str
    provider: str
    model: str = ""
    session_id: str = ""
    response_text: str = ""
    tokens: dict[str, int] = field(default_factory=dict)
    cost: float = 0.0
    latency_ms: int = 0
    error: str = ""
    delegated: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in _STATUSES:
            raise ValueError(f"unknown provider status: {self.status!r}")
        self.delegated = self.delegated or self.status == STATUS_DELEGATED

    @property
    def ok(self) -> bool:
        return self.status == STATUS_SUCCESS

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider": self.provider,
            "model": self.model,
            "session_id": self.session_id,
            "response_text": self.response_text,
            "tokens": dict(self.tokens),
            "cost": self.cost,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "delegated": self.delegated,
        }


@runtime_checkable
class Provider(Protocol):
    """Anything the loop can hand a prompt to."""

    name: str

    def invoke(
        self, *, prompt: str, model: str = "", cwd: str = "", timeout_seconds: int = 300
    ) -> ProviderResult: ...


_REGISTRY: dict[str, Provider] = {}


def register(provider: Provider) -> None:
    """Register (or replace) a provider under its ``name``."""
    _REGISTRY[provider.name] = provider


def _ensure_builtins() -> None:
    if _REGISTRY:
        return
    from aos.adapters import host_delegate, opencode, test_provider

    register(test_provider.get_provider())
    register(opencode.OpenCodeProvider())
    register(host_delegate.HostDelegateProvider())


def get(name: str) -> Provider:
    """Look up a provider by name, loading the built-ins on first use."""
    _ensure_builtins()
    if name not in _REGISTRY:
        raise KeyError(f"unknown provider {name!r}; available: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def available() -> list[str]:
    _ensure_builtins()
    return sorted(_REGISTRY)


def reset() -> None:
    """Drop registered providers (used by tests)."""
    _REGISTRY.clear()
