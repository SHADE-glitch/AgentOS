#!/usr/bin/env python3
"""
Cross-Stack Protection Guard — Phase 5.1 P0-2

Prevents Agent OS from generating code in the wrong technology stack.
Evidence: AIView project (Java 21, Spring Boot 3.3) → Agent produced Python
implementation using langchain/sentence_transformers.

This module:
  1. Detects project tech stack from build files
  2. Validates agent output against detected stack
  3. Provides stack context to prompt building
  4. Flags cross-stack contamination in output
"""

import os
import re
import yaml
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone


# ── Tech Stack Definition ───────────────────────────────────────

@dataclass
class TechStack:
    """Detected project technology stack."""
    primary_language: str = "unknown"  # java, python, javascript, typescript, go, rust
    language_version: str = "unknown"  # 21, 3.12, 20, etc.
    build_system: str = "unknown"      # maven, gradle, npm, pip, go, cargo
    framework: str = "unknown"         # spring-boot, flask, react, vue, gin, etc.
    framework_version: str = "unknown"
    runtime: str = "unknown"           # jvm, node, python, go
    build_file: str = ""               # path to build file
    detected_at: str = ""


# ── Language-specific markers in output ─────────────────────────

# Patterns that indicate Python output
PYTHON_MARKERS = [
    r'import\s+langchain',
    r'import\s+sentence_transformers',
    r'from\s+sentence_transformers\s+import',
    r'from\s+transformers\s+import',
    r'import\s+torch\b',
    r'import\s+tensorflow\b',
    r'import\s+numpy\b',
    r'from\s+numpy\s+import',
    r'import\s+pandas\b',
    r'def\s+\w+\(.*\):\s*$',
    r'pip\s+install',
    r'requirements\.txt',
    r'@app\.route',
    r'Flask\(',
    r'Django\(',
    r'FastAPI\(',
    r'uvicorn\b',
    r'\.py\b',
    r'__init__\.py',
    r'virtualenv\b',
    r'venv\b',
    r'poetry\b',
]

# Patterns that indicate Java/Spring Boot output
JAVA_MARKERS = [
    r'import\s+org\.springframework',
    r'import\s+com\.\w+',
    r'@Service\b',
    r'@Component\b',
    r'@RestController\b',
    r'@Autowired\b',
    r'@Bean\b',
    r'@Configuration\b',
    r'@Transactional\b',
    r'public\s+class\s+\w+',
    r'\.java\b',
    r'pom\.xml',
    r'build\.gradle',
    r'Maven\b',
    r'Gradle\b',
    r'application\.yml',
    r'application\.properties',
    r'pom\.xml',
    r'SpringApplication\.run',
    r'@SpringBootApplication',
]

# Patterns that indicate Node.js/JavaScript output
NODE_MARKERS = [
    r'import\s+.*\s+from\s+[\'"]react',
    r'import\s+.*\s+from\s+[\'"]vue',
    r'import\s+.*\s+from\s+[\'"]next',
    r'const\s+express\s*=\s*require',
    r'package\.json',
    r'npm\s+install',
    r'yarn\s+add',
    r'pnpm\b',
    r'\.jsx?\b',
    r'\.tsx?\b',
    r'useState\b',
    r'useEffect\b',
    r'useRef\b',
    r'export\s+default\s+function',
    r'export\s+const\s+\w+\s*=',
    r'\.js\b',
    r'\.ts\b',
    r'node_modules',
    r'webpack\.config',
    r'vite\.config',
    r'next\.config',
    r'npm\s+run\s+dev',
    r'npm\s+run\s+build',
]

# Patterns that indicate Go output
GO_MARKERS = [
    r'package\s+main\b',
    r'import\s+\(',
    r'func\s+\w+\(.*\)\s+\{',
    r'go\.mod',
    r'go\s+mod\s+init',
    r'go\s+build',
    r'go\s+run',
    r'\.go\b',
    r'net/http',
    r'gorilla/mux',
    r'gin-gonic/gin',
    r'github\.com/',
    r'golang\.org/',
]


def detect_tech_stack(project_root: str) -> TechStack:
    """
    Detect project tech stack from build files.

    Priority order:
      1. pom.xml → Java/Maven — check for spring-boot-starter
      2. build.gradle(.kts) → Java/Gradle — check for spring-boot
      3. package.json → JavaScript/Node.js
      4. requirements.txt / pyproject.toml → Python
      5. go.mod → Go

    Returns:
        TechStack with detected values
    """
    stack = TechStack(detected_at=datetime.now(timezone.utc).isoformat())

    # Check for pom.xml (Maven/Java)
    pom_path = _find_file(project_root, "pom.xml")
    if pom_path:
        stack.build_file = pom_path
        stack.build_system = "maven"
        stack.primary_language = "java"
        stack.runtime = "jvm"

        try:
            with open(pom_path) as f:
                content = f.read()

            # Detect Java version
            m = re.search(r'<java\.version>(\d+)</java\.version>', content)
            if m:
                stack.language_version = m.group(1)
            else:
                m = re.search(r'<maven\.compiler\.release>(\d+)</maven\.compiler\.release>', content)
                if m:
                    stack.language_version = m.group(1)

            # Detect Spring Boot
            if 'spring-boot-starter' in content:
                stack.framework = "spring-boot"
                m = re.search(r'<version>(\d+\.\d+\.\d+)</version>', content)
                if m:
                    stack.framework_version = m.group(1)
                # Also check parent POM
                m = re.search(r'<parent>.*?<version>(\d+\.\d+\.\d+)</version>.*?</parent>',
                              content, re.DOTALL)
                if m:
                    stack.framework_version = m.group(1)

            # Detect MyBatis-Plus
            if 'mybatis-plus' in content:
                stack.framework += "+mybatis-plus"

            # Detect RabbitMQ
            if 'spring-boot-starter-amqp' in content or 'spring-rabbit' in content:
                stack.framework += "+rabbitmq"

            # Detect Redis
            if 'spring-boot-starter-data-redis' in content or 'redisson' in content:
                stack.framework += "+redis"

            return stack
        except Exception:
            pass

    # Check for build.gradle(.kts) (Gradle/Java)
    for gradle_file in ["build.gradle", "build.gradle.kts"]:
        gradle_path = _find_file(project_root, gradle_file)
        if gradle_path:
            stack.build_file = gradle_path
            stack.build_system = "gradle"
            stack.primary_language = "java"
            stack.runtime = "jvm"

            try:
                with open(gradle_path) as f:
                    content = f.read()

                m = re.search(r'JavaVersion\.VERSION_(\d+)', content)
                if m:
                    stack.language_version = m.group(1)
                m = re.search(r'sourceCompatibility\s*=\s*[\'"](\d+)[\'"]', content)
                if m:
                    stack.language_version = m.group(1)

                if 'spring-boot' in content.lower():
                    stack.framework = "spring-boot"

                return stack
            except Exception:
                pass

    # Check for package.json (Node.js)
    pkg_path = _find_file(project_root, "package.json")
    if pkg_path:
        stack.build_file = pkg_path
        stack.build_system = "npm"
        stack.primary_language = "javascript"
        stack.runtime = "node"

        try:
            import json
            with open(pkg_path) as f:
                pkg = json.load(f)

            deps = {}
            deps.update(pkg.get("dependencies", {}))
            deps.update(pkg.get("devDependencies", {}))

            if "react" in deps:
                stack.framework = "react"
            elif "vue" in deps:
                stack.framework = "vue"
            elif "next" in deps:
                stack.framework = "nextjs"
            elif "typescript" in deps:
                stack.primary_language = "typescript"

            if "typescript" in deps or "typescript" in pkg.get("devDependencies", {}):
                stack.primary_language = "typescript"

            return stack
        except Exception:
            pass

    # Check for requirements.txt / pyproject.toml (Python)
    for py_file in ["requirements.txt", "setup.py", "pyproject.toml"]:
        py_path = _find_file(project_root, py_file)
        if py_path:
            stack.build_file = py_path
            stack.build_system = "pip"
            stack.primary_language = "python"
            stack.runtime = "python"
            return stack

    # Check for go.mod (Go)
    go_path = _find_file(project_root, "go.mod")
    if go_path:
        stack.build_file = go_path
        stack.build_system = "go"
        stack.primary_language = "go"
        stack.runtime = "go"
        return stack

    return stack


def _find_file(project_root: str, filename: str) -> Optional[str]:
    """Find a file in project root or common subdirectories."""
    candidates = [
        project_root,
        os.path.join(project_root, "backend"),
        os.path.join(project_root, "server"),
        os.path.join(project_root, "api"),
        os.path.join(project_root, "src"),
        os.path.join(project_root, "frontend"),
        os.path.join(project_root, "web"),
    ]
    for c in candidates:
        path = os.path.join(c, filename)
        if os.path.exists(path):
            return path
    return None


# ── Cross-Stack Output Validation ───────────────────────────────

@dataclass
class CrossStackResult:
    """Result of cross-stack validation."""
    project_stack: TechStack = field(default_factory=TechStack)
    output_indicators: Dict[str, int] = field(default_factory=dict)
    """Count of markers per detected language."""

    contamination_detected: bool = False
    contaminated_language: str = ""
    contamination_details: List[str] = field(default_factory=list)

    is_valid: bool = True
    """True if output matches or is compatible with project stack."""

    warnings: List[str] = field(default_factory=list)


def validate_output_stack(project_root: str, output_text: str,
                          project_stack: Optional[TechStack] = None) -> CrossStackResult:
    """
    Validate that agent output matches the project's tech stack.

    Checks for markers of foreign languages in the output and flags
    contamination when the agent produces code in the wrong stack.

    Args:
        project_root: path to project root
        output_text: agent output text to validate
        project_stack: pre-detected tech stack (if None, detect from project_root)

    Returns:
        CrossStackResult with validation details
    """
    if project_stack is None:
        project_stack = detect_tech_stack(project_root)

    result = CrossStackResult(project_stack=project_stack)

    # Count markers per language
    python_count = sum(1 for p in PYTHON_MARKERS if re.search(p, output_text, re.MULTILINE))
    java_count = sum(1 for p in JAVA_MARKERS if re.search(p, output_text, re.MULTILINE))
    node_count = sum(1 for p in NODE_MARKERS if re.search(p, output_text, re.MULTILINE))
    go_count = sum(1 for p in GO_MARKERS if re.search(p, output_text, re.MULTILINE))

    result.output_indicators = {
        "python": python_count,
        "java": java_count,
        "javascript": node_count,
        "go": go_count,
    }

    primary = project_stack.primary_language

    # Check for contamination based on project language
    if primary == "java":
        if python_count > 0 and java_count == 0:
            result.contamination_detected = True
            result.contaminated_language = "python"
            result.is_valid = False
            result.contamination_details = _extract_contamination_lines(output_text, PYTHON_MARKERS)
            result.warnings.append(
                f"CROSS-STACK CONTAMINATION: Project is Java ({project_stack.framework}), "
                f"but output contains Python-specific code ({python_count} markers detected). "
                f"The agent generated code for the wrong technology stack."
            )
        elif python_count > 0 and java_count > 0:
            # Mixed output — both Java and Python present
            result.warnings.append(
                f"MIXED-STACK WARNING: Output contains both Java ({java_count}) and Python "
                f"({python_count}) markers. Verify the Python parts are intentional (e.g., scripts)."
            )
        elif python_count > java_count:
            result.warnings.append(
                f"STACK-DOMINANCE WARNING: Python markers ({python_count}) outnumber Java "
                f"markers ({java_count}). Output may be Python-dominant."
            )

    elif primary == "python":
        if java_count > 0 and python_count == 0:
            result.contamination_detected = True
            result.contaminated_language = "java"
            result.is_valid = False
            result.contamination_details = _extract_contamination_lines(output_text, JAVA_MARKERS)
            result.warnings.append(
                f"CROSS-STACK CONTAMINATION: Project is Python, but output contains Java-specific code."
            )

    elif primary == "javascript":
        if java_count > 0 and node_count == 0:
            result.contamination_detected = True
            result.contaminated_language = "java"
            result.is_valid = False
            result.contamination_details = _extract_contamination_lines(output_text, JAVA_MARKERS)

    elif primary == "go":
        if python_count > 0 and go_count == 0:
            result.contamination_detected = True
            result.contaminated_language = "python"
            result.is_valid = False
            result.contamination_details = _extract_contamination_lines(output_text, PYTHON_MARKERS)

    return result


def _extract_contamination_lines(text: str, markers: List[str]) -> List[str]:
    """Extract lines that match contamination markers."""
    lines = text.split("\n")
    contaminated = []
    for line in lines:
        for pattern in markers:
            if re.search(pattern, line):
                contaminated.append(line.strip()[:200])
                break
    return contaminated[:10]  # Max 10 lines


# ── Stack-Aware Prompt Enhancement ───────────────────────────────

def build_stack_context(project_root: str, stack: Optional[TechStack] = None) -> str:
    """
    Build a tech stack context string for inclusion in the agent prompt.

    This ensures the agent knows what technology stack to target.
    """
    if stack is None:
        stack = detect_tech_stack(project_root)

    if stack.primary_language == "unknown":
        return ""

    parts = []
    parts.append("\n## Project Technology Stack")
    parts.append(f"**Primary Language**: {stack.primary_language}")

    if stack.language_version != "unknown":
        parts.append(f"**Language Version**: {stack.language_version}")

    if stack.framework != "unknown":
        parts.append(f"**Framework**: {stack.framework}")

    if stack.build_system != "unknown":
        parts.append(f"**Build System**: {stack.build_system}")

    if stack.runtime != "unknown":
        parts.append(f"**Runtime**: {stack.runtime}")

    parts.append("")
    parts.append(f"**CRITICAL**: You MUST generate {stack.primary_language} code using {stack.framework} patterns.")
    parts.append(f"Do NOT produce code in any other language unless explicitly requested by the task.")
    parts.append(f"All code examples, imports, and configuration must be valid for {stack.primary_language} / {stack.framework}.")

    return "\n".join(parts)