#!/usr/bin/env python3
"""
Project Preflight — Phase 6.2
Detects project build system, runtime, required services, and validation commands.

This module provides PROJECT_PREFLIGHT capability for Agent OS:
  - detect build system (Maven, Gradle, Node, Python, Go)
  - detect runtime version (JDK, Node, Python, Go)
  - detect required services (MySQL, Redis, RabbitMQ)
  - detect validation command (compile, test, build)
  - detect environment blockers

Output: ProjectPreflightResult with status READY / PARTIALLY_READY / BLOCKED
"""

import os
import subprocess
import yaml
import re
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


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
    build_system: str  # maven / gradle / npm / pip / go / unknown
    build_file: str
    runtime: str  # java / node / python / go / unknown
    runtime_version_required: str
    runtime_version_actual: str
    runtime_version_match: bool
    compile_command: str
    test_command: str
    build_command: str
    services: List[ServiceDependency]
    environment_blockers: List[str]
    detected_at: str
    notes: List[str] = field(default_factory=list)


def detect_build_system(project_root: str) -> tuple[str, str]:
    """Detect build system and build file path."""
    checks = [
        ("maven", "pom.xml"),
        ("gradle", "build.gradle"),
        ("gradle_kts", "build.gradle.kts"),
        ("npm", "package.json"),
        ("pip", "requirements.txt"),
        ("pip", "setup.py"),
        ("pip", "pyproject.toml"),
        ("go", "go.mod"),
    ]

    for system, filename in checks:
        path = os.path.join(project_root, filename)
        if os.path.exists(path):
            normalized = system.replace("_kts", "gradle")
            return normalized, path

    # Check subdirectories (e.g., backend/pom.xml)
    for subdir in ["backend", "server", "api", "src"]:
        for system, filename in checks:
            path = os.path.join(project_root, subdir, filename)
            if os.path.exists(path):
                normalized = system.replace("_kts", "gradle")
                return normalized, path

    return "unknown", ""


def detect_java_version(project_root: str, build_file: str) -> tuple[str, str]:
    """Detect required and actual Java versions."""
    required = "unknown"
    actual = "unknown"

    # Detect required version from pom.xml
    if build_file and build_file.endswith("pom.xml"):
        try:
            with open(build_file) as f:
                content = f.read()
            # Look for java.version property
            m = re.search(r"<java\.version>(\d+)</java\.version>", content)
            if m:
                required = m.group(1)
            # Look for maven.compiler.release
            m = re.search(r"<maven\.compiler\.release>(\d+)</maven\.compiler\.release>", content)
            if m and required == "unknown":
                required = m.group(1)
        except Exception:
            pass

    # Detect actual version
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version_str = result.stderr if result.stderr else result.stdout
        m = re.search(r'"(\d+)', version_str)
        if m:
            actual = m.group(1)
    except Exception:
        pass

    # Check JAVA_HOME
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home and actual == "unknown":
        try:
            result = subprocess.run(
                [os.path.join(java_home, "bin", "java"), "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            version_str = result.stderr if result.stderr else result.stdout
            m = re.search(r'"(\d+)', version_str)
            if m:
                actual = m.group(1)
        except Exception:
            pass

    # Check standard JDK locations if version mismatch
    if required != "unknown" and actual != required:
        standard_locations = [
            f"/usr/lib/jvm/java-{required}-openjdk-amd64",
            f"/usr/lib/jvm/java-{required}-openjdk",
            f"/usr/lib/jvm/java-{required}",
        ]
        for loc in standard_locations:
            java_bin = os.path.join(loc, "bin", "java")
            if os.path.exists(java_bin):
                try:
                    result = subprocess.run(
                        [java_bin, "-version"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    version_str = result.stderr if result.stderr else result.stdout
                    m = re.search(r'"(\d+)', version_str)
                    if m and m.group(1) == required:
                        actual = m.group(1)
                        notes.append(f"Found JDK {required} at {loc}")
                        break
                except Exception:
                    pass

    return required, actual


def detect_services(project_root: str) -> List[ServiceDependency]:
    """Detect required services from project configuration."""
    services = []

    # Check docker-compose.yml
    compose_path = os.path.join(project_root, "docker-compose.yml")
    if os.path.exists(compose_path):
        try:
            with open(compose_path) as f:
                compose = yaml.safe_load(f)
            if compose and "services" in compose:
                for svc_name, svc_config in compose["services"].items():
                    image = svc_config.get("image", "")
                    if "mysql" in svc_name.lower() or "mysql" in image.lower():
                        services.append(ServiceDependency(
                            name="MySQL",
                            required=True,
                            detected=False,
                            status="UNKNOWN",
                        ))
                    elif "redis" in svc_name.lower() or "redis" in image.lower():
                        services.append(ServiceDependency(
                            name="Redis",
                            required=True,
                            detected=False,
                            status="UNKNOWN",
                        ))
                    elif "rabbit" in svc_name.lower() or "rabbitmq" in image.lower():
                        services.append(ServiceDependency(
                            name="RabbitMQ",
                            required=True,
                            detected=False,
                            status="UNKNOWN",
                        ))
        except Exception:
            pass

    # Check .env file for service URLs
    env_path = os.path.join(project_root, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip().lower()
                    if "mysql" in key or "database" in key:
                        services.append(ServiceDependency(
                            name="MySQL",
                            required=True,
                            detected=False,
                            status="UNKNOWN",
                        ))
                    elif "redis" in key:
                        services.append(ServiceDependency(
                            name="Redis",
                            required=True,
                            detected=False,
                            status="UNKNOWN",
                        ))
                    elif "rabbit" in key or "amqp" in key:
                        services.append(ServiceDependency(
                            name="RabbitMQ",
                            required=True,
                            detected=False,
                            status="UNKNOWN",
                        ))
        except Exception:
            pass

    # Deduplicate
    seen = set()
    unique_services = []
    for svc in services:
        if svc.name not in seen:
            seen.add(svc.name)
            unique_services.append(svc)

    return unique_services


def detect_validation_commands(build_system: str, build_file: str) -> tuple[str, str, str]:
    """Detect compile, test, and build commands based on build system."""
    if build_system == "maven":
        build_dir = os.path.dirname(build_file) if build_file else ""
        if build_dir:
            compile_cmd = f"cd {build_dir} && mvn compile -q"
            test_cmd = f"cd {build_dir} && mvn test -q"
            build_cmd = f"cd {build_dir} && mvn package -q -DskipTests"
        else:
            compile_cmd = "mvn compile -q"
            test_cmd = "mvn test -q"
            build_cmd = "mvn package -q -DskipTests"
    elif build_system == "gradle":
        compile_cmd = "./gradlew compileJava"
        test_cmd = "./gradlew test"
        build_cmd = "./gradlew build -x test"
    elif build_system == "npm":
        compile_cmd = "npm run build"
        test_cmd = "npm test"
        build_cmd = "npm run build"
    elif build_system == "pip":
        compile_cmd = "python -m py_compile"
        test_cmd = "pytest"
        build_cmd = "python -m build"
    elif build_system == "go":
        compile_cmd = "go build ./..."
        test_cmd = "go test ./..."
        build_cmd = "go build ./..."
    else:
        compile_cmd = "echo 'No build system detected'"
        test_cmd = "echo 'No test system detected'"
        build_cmd = "echo 'No build system detected'"

    return compile_cmd, test_cmd, build_cmd


def run_preflight(project_root: str) -> ProjectPreflightResult:
    """
    Run project preflight detection.

    Args:
        project_root: Path to the project root directory

    Returns:
        ProjectPreflightResult with detection results
    """
    notes = []
    blockers = []

    # Detect build system
    build_system, build_file = detect_build_system(project_root)
    notes.append(f"Build system: {build_system}")
    if build_file:
        notes.append(f"Build file: {build_file}")

    # Detect runtime
    runtime = "unknown"
    runtime_required = "unknown"
    runtime_actual = "unknown"
    runtime_match = False

    if build_system == "maven" or build_system == "gradle":
        runtime = "java"
        runtime_required, runtime_actual = detect_java_version(project_root, build_file)
        if runtime_required != "unknown" and runtime_actual != "unknown":
            runtime_match = runtime_required == runtime_actual
            if not runtime_match:
                blockers.append(f"JDK version mismatch: required={runtime_required}, actual={runtime_actual}")
                notes.append(f"JDK mismatch: project requires {runtime_required}, system has {runtime_actual}")
            else:
                notes.append(f"JDK version match: {runtime_actual}")
    elif build_system == "npm":
        runtime = "node"
        try:
            result = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
            runtime_actual = result.stdout.strip().lstrip("v")
            notes.append(f"Node.js version: {runtime_actual}")
        except Exception:
            blockers.append("Node.js not found")
    elif build_system == "pip":
        runtime = "python"
        try:
            result = subprocess.run(["python3", "--version"], capture_output=True, text=True, timeout=5)
            runtime_actual = result.stdout.strip().split()[-1]
            notes.append(f"Python version: {runtime_actual}")
        except Exception:
            blockers.append("Python not found")
    elif build_system == "go":
        runtime = "go"
        try:
            result = subprocess.run(["go", "version"], capture_output=True, text=True, timeout=5)
            runtime_actual = result.stdout.split()[-1]
            notes.append(f"Go version: {runtime_actual}")
        except Exception:
            blockers.append("Go not found")

    # Detect services
    services = detect_services(project_root)
    for svc in services:
        notes.append(f"Service dependency: {svc.name} (required={svc.required})")

    # Detect validation commands
    compile_cmd, test_cmd, build_cmd = detect_validation_commands(build_system, build_file)
    notes.append(f"Compile command: {compile_cmd}")
    notes.append(f"Test command: {test_cmd}")

    # Determine overall status
    if blockers:
        status = "BLOCKED"
    elif runtime_match or runtime_required == "unknown":
        status = "READY"
    else:
        status = "PARTIALLY_READY"

    return ProjectPreflightResult(
        project_root=project_root,
        status=status,
        build_system=build_system,
        build_file=build_file,
        runtime=runtime,
        runtime_version_required=runtime_required,
        runtime_version_actual=runtime_actual,
        runtime_version_match=runtime_match,
        compile_command=compile_cmd,
        test_command=test_cmd,
        build_command=build_cmd,
        services=services,
        environment_blockers=blockers,
        detected_at=datetime.now(timezone.utc).isoformat(),
        notes=notes,
    )


def to_yaml(result: ProjectPreflightResult) -> str:
    """Convert preflight result to YAML string."""
    return yaml.dump(
        asdict(result),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 project_preflight.py <project_root>")
        print()
        print("Example:")
        print("  python3 project_preflight.py /home/shade/Public/test")
        sys.exit(1)

    project_root = sys.argv[1]
    result = run_preflight(project_root)

    print("=" * 60)
    print("Project Preflight — Phase 6.2")
    print("=" * 60)
    print(to_yaml(result))
    print(f"Status: {result.status}")
