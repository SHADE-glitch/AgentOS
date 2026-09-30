"""OpenCode CLI provider.

Runs ``opencode run <prompt>`` as a subprocess in the target directory. This
is the only provider that shells out; everything it returns is normalised
into a :class:`ProviderResult` so the loop never parses CLI output itself.
"""

from __future__ import annotations

import shutil
import subprocess
import time

from aos.adapters.base import (
    STATUS_ERROR,
    STATUS_SUCCESS,
    STATUS_TIMEOUT,
    ProviderResult,
)

DEFAULT_BINARY = "opencode"


class OpenCodeProvider:
    name = "opencode"

    def __init__(self, binary: str = DEFAULT_BINARY):
        self.binary = binary

    def invoke(
        self, *, prompt: str, model: str = "", cwd: str = "", timeout_seconds: int = 300
    ) -> ProviderResult:
        binary = shutil.which(self.binary)
        if binary is None:
            return ProviderResult(
                status=STATUS_ERROR,
                provider=self.name,
                model=model,
                error=f"{self.binary!r} not found on PATH",
            )

        command = [binary, "run", prompt]
        if model:
            command += ["--model", model]

        started = time.time()
        try:
            completed = subprocess.run(
                command,
                cwd=cwd or None,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ProviderResult(
                status=STATUS_TIMEOUT,
                provider=self.name,
                model=model,
                latency_ms=int((time.time() - started) * 1000),
                error=f"opencode timed out after {timeout_seconds}s",
            )
        except OSError as exc:
            return ProviderResult(
                status=STATUS_ERROR,
                provider=self.name,
                model=model,
                latency_ms=int((time.time() - started) * 1000),
                error=str(exc),
            )

        latency_ms = int((time.time() - started) * 1000)
        if completed.returncode != 0:
            return ProviderResult(
                status=STATUS_ERROR,
                provider=self.name,
                model=model,
                latency_ms=latency_ms,
                error=(completed.stderr or "").strip()[:2000]
                or f"opencode exited with code {completed.returncode}",
            )

        return ProviderResult(
            status=STATUS_SUCCESS,
            provider=self.name,
            model=model,
            response_text=completed.stdout or "",
            latency_ms=latency_ms,
            raw={"returncode": completed.returncode},
        )
