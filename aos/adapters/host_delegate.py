"""Host-delegation provider.

When a host (e.g. the OpenCode plugin) already owns execution, the engine
must not run anything itself. It returns a ``delegated`` result so the loop
stops after preflight; the host calls postflight when it is done, and the
learning loop closes there.
"""

from __future__ import annotations

from aos.adapters.base import STATUS_DELEGATED, ProviderResult


class HostDelegateProvider:
    name = "host_delegate"

    def invoke(
        self, *, prompt: str, model: str = "", cwd: str = "", timeout_seconds: int = 300
    ) -> ProviderResult:
        return ProviderResult(
            status=STATUS_DELEGATED,
            provider=self.name,
            model=model,
            delegated=True,
            raw={"note": "execution delegated to the host; postflight closes the loop"},
        )
