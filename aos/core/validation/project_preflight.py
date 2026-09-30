"""Project build detection.

Ported from ``runtime/loop-controller/project_preflight.py``. Detects the
build system, runtime, declared service dependencies and the compile/test
commands a project expects. Zero dependencies: no YAML, so ``docker-compose``
is read with a small line scanner instead of a parser.

The Maven/Gradle/Java specialisation is kept because the original targeted it,
but nothing here requires Java — an unknown project simply reports
``build_system = "unknown"`` and no commands.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# Build file probes, in priority order.
_BUILD_FILES: tuple[tuple[str, str], ...] = (
    ("maven", "pom.xml"),
    ("gradle", "build.gradle"),
    ("gradle", "build.gradle.kts"),
    ("npm", "package.json"),
    ("pip", "requirements.txt"),
    ("pip", "setup.py"),
    ("pip", "pyproject.toml"),
    ("go", "go.mod"),
)
_SUBDIRS = ("backend", "server", "api", "src")

# Declared-service signals: (service, marker substring).
_SERVICE_MARKERS: tuple[tuple[str, str], ...] = (
    ("MySQL", "mysql"),
    ("PostgreSQL", "postgres"),
    ("Redis", "redis"),
    ("RabbitMQ", "rabbit"),
    ("RabbitMQ", "amqp"),
    ("MongoDB", "mongo"),
    ("Kafka", "kafka"),
)

# Ports used when a caller opts into probing declared services.
_SERVICE_PORTS = {
    "MySQL": 3306,
    "PostgreSQL": 5432,
    "Redis": 6379,
    "RabbitMQ": 5672,
    "MongoDB": 27017,
    "Kafka": 9092,
}


@dataclass
class ServiceDependency:
    name: str
    required: bool
    detected: bool
    status: str  # AVAILABLE / MISSING / UNKNOWN


@dataclass
class ProjectPreflightResult:
    project_root: str
    status: str  # READY / PARTIALLY_READY / BLOCKED
    build_system: str
    build_file: str
    runtime: str
    runtime_version_required: str
    runtime_version_actual: str
    runtime_version_match: bool
    compile_command: str
    test_command: str
    build_command: str
    services: list[ServiceDependency] = field(default_factory=list)
    environment_blockers: list[str] = field(default_factory=list)
    detected_at: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run(command: list[str], timeout: int = 10) -> tuple[int, str, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, "", str(exc)


def detect_build_system(project_root: str) -> tuple[str, str]:
    """Return ``(build_system, build_file)`` for the project."""
    for system, filename in _BUILD_FILES:
        path = os.path.join(project_root, filename)
        if os.path.isfile(path):
            return system, path
    for subdir in _SUBDIRS:
        for system, filename in _BUILD_FILES:
            path = os.path.join(project_root, subdir, filename)
            if os.path.isfile(path):
                return system, path
    return "unknown", ""


def detect_java_version(build_file: str) -> tuple[str, str, list[str]]:
    """Return ``(required, actual, notes)`` for a Java project."""
    notes: list[str] = []
    required = "unknown"

    if build_file and build_file.endswith("pom.xml"):
        try:
            content = open(build_file, encoding="utf-8").read()
        except OSError:
            content = ""
        match = re.search(r"<java\.version>(\d+)</java\.version>", content)
        if not match:
            match = re.search(r"<maven\.compiler\.release>(\d+)</maven\.compiler\.release>", content)
        if match:
            required = match.group(1)

    actual = "unknown"
    candidates = []
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        candidates.append(os.path.join(java_home, "bin", "java"))
    candidates.append("java")
    if required != "unknown":
        candidates += [
            f"/usr/lib/jvm/java-{required}-openjdk-amd64/bin/java",
            f"/usr/lib/jvm/java-{required}-openjdk/bin/java",
            f"/usr/lib/jvm/java-{required}/bin/java",
        ]

    for candidate in candidates:
        code, out, err = _run([candidate, "-version"])
        text = err or out
        match = re.search(r'"(\d+)', text)
        if match:
            actual = match.group(1)
            if candidate != "java":
                notes.append(f"using JDK {actual} at {candidate}")
            break

    return required, actual, notes


def detect_services(project_root: str, *, probe: bool = False, timeout: float = 0.5) -> list[ServiceDependency]:
    """Detect *declared* service dependencies.

    Only when ``probe`` is true are the well-known ports actually contacted,
    so the default path stays hermetic and offline.
    """
    declared: dict[str, bool] = {}

    compose = os.path.join(project_root, "docker-compose.yml")
    if os.path.isfile(compose):
        try:
            text = open(compose, encoding="utf-8").read().lower()
        except OSError:
            text = ""
        for service, marker in _SERVICE_MARKERS:
            if marker in text:
                declared[service] = True

    env_file = os.path.join(project_root, ".env")
    if os.path.isfile(env_file):
        try:
            lines = open(env_file, encoding="utf-8").read().splitlines()
        except OSError:
            lines = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            haystack = f"{key} {value}".lower()
            for service, marker in _SERVICE_MARKERS:
                if marker in haystack:
                    declared[service] = True

    services = []
    for name in sorted(declared):
        if probe:
            detected = _port_open(_SERVICE_PORTS.get(name, 0), timeout)
            status = "AVAILABLE" if detected else "MISSING"
        else:
            detected, status = False, "UNKNOWN"
        services.append(ServiceDependency(name=name, required=True, detected=detected, status=status))
    return services


def _port_open(port: int, timeout: float) -> bool:
    if not port:
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def detect_validation_commands(build_system: str, build_file: str) -> tuple[str, str, str]:
    """Return ``(compile, test, build)`` commands for a build system."""
    build_dir = os.path.dirname(build_file) if build_file else ""
    prefix = f"cd {build_dir} && " if build_dir else ""

    if build_system == "maven":
        return f"{prefix}mvn compile -q", f"{prefix}mvn test -q", f"{prefix}mvn package -q -DskipTests"
    if build_system == "gradle":
        return "./gradlew compileJava", "./gradlew test", "./gradlew build -x test"
    if build_system == "npm":
        return "npm run build", "npm test", "npm run build"
    if build_system == "pip":
        return "python3 -m compileall -q .", "pytest", "python3 -m build"
    if build_system == "go":
        return "go build ./...", "go test ./...", "go build ./..."
    return "", "", ""


def run_preflight(
    project_root: str, *, probe_services: bool = False, detect_runtime: bool = True
) -> ProjectPreflightResult:
    """Detect the build system, runtime, services and validation commands."""
    notes: list[str] = []
    blockers: list[str] = []

    project_root = os.path.abspath(project_root)
    build_system, build_file = detect_build_system(project_root)
    notes.append(f"build system: {build_system}")
    if build_file:
        notes.append(f"build file: {build_file}")

    runtime = "unknown"
    required = actual = "unknown"
    version_match = False

    if build_system in ("maven", "gradle"):
        runtime = "java"
        required, actual, java_notes = detect_java_version(build_file)
        notes += java_notes
        if required != "unknown" and actual != "unknown":
            version_match = required == actual
            if version_match:
                notes.append(f"JDK version match: {actual}")
            else:
                blockers.append(f"JDK version mismatch: required={required}, actual={actual}")
    elif build_system in ("npm", "pip", "go") and detect_runtime:
        runtime = {"npm": "node", "pip": "python", "go": "go"}[build_system]
        command = {"npm": ["node", "--version"], "pip": ["python3", "--version"], "go": ["go", "version"]}[build_system]
        code, out, err = _run(command, timeout=5)
        if code == 0:
            actual = (out or err).strip().split()[-1].lstrip("v")
            notes.append(f"{runtime} version: {actual}")
        else:
            blockers.append(f"{runtime} not found")

    services = detect_services(project_root, probe=probe_services)
    notes += [f"service dependency: {s.name} (required={s.required}, {s.status})" for s in services]

    compile_command, test_command, build_command = detect_validation_commands(build_system, build_file)
    if compile_command:
        notes.append(f"compile command: {compile_command}")
        notes.append(f"test command: {test_command}")

    if blockers:
        status = "BLOCKED"
    elif required != "unknown" and not version_match:
        status = "PARTIALLY_READY"
    else:
        status = "READY"

    return ProjectPreflightResult(
        project_root=project_root,
        status=status,
        build_system=build_system,
        build_file=build_file,
        runtime=runtime,
        runtime_version_required=required,
        runtime_version_actual=actual,
        runtime_version_match=version_match,
        compile_command=compile_command,
        test_command=test_command,
        build_command=build_command,
        services=services,
        environment_blockers=blockers,
        detected_at=datetime.now(timezone.utc).isoformat(),
        notes=notes,
    )
