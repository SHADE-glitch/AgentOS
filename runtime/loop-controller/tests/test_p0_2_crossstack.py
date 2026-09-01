#!/usr/bin/env python3
"""
Regression Tests — P0-2: Cross-Stack Protection

Tests:
  1. Java project → Python output → contamination detected
  2. Java project → Java output → no contamination
  3. Python project → Java output → contamination detected
  4. Tech stack detection from pom.xml
  5. Tech stack detection from package.json
  6. Stack context prompt building

These tests verify that the Agent OS correctly detects and prevents
cross-stack contamination.
"""

import sys
import os
import tempfile
import unittest

# Add loop-controller to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cross_stack_guard import (
    detect_tech_stack,
    validate_output_stack,
    build_stack_context,
    TechStack,
    CrossStackResult,
    PYTHON_MARKERS,
    JAVA_MARKERS,
    NODE_MARKERS,
    GO_MARKERS,
)


class TestTechStackDetection(unittest.TestCase):
    """Test project tech stack detection from build files."""

    def test_java_maven_detection(self):
        """Detect Java/Maven/Spring Boot from pom.xml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pom_path = os.path.join(tmpdir, "pom.xml")
            with open(pom_path, "w") as f:
                f.write("""<?xml version="1.0" encoding="UTF-8"?>
<project>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
    </parent>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>com.baomidou</groupId>
            <artifactId>mybatis-plus-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-amqp</artifactId>
        </dependency>
        <dependency>
            <groupId>org.redisson</groupId>
            <artifactId>redisson-spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
</project>""")
            stack = detect_tech_stack(tmpdir)
            self.assertEqual(stack.primary_language, "java")
            self.assertEqual(stack.language_version, "21")
            self.assertEqual(stack.build_system, "maven")
            self.assertIn("spring-boot", stack.framework)
            self.assertIn("mybatis-plus", stack.framework)
            self.assertIn("rabbitmq", stack.framework)
            self.assertIn("redis", stack.framework)
            self.assertEqual(stack.framework_version, "3.3.5")

    def test_unknown_project(self):
        """Empty directory → unknown stack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stack = detect_tech_stack(tmpdir)
            self.assertEqual(stack.primary_language, "unknown")

    def test_backend_subdirectory(self):
        """Detect from backend/ subdirectory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend_dir = os.path.join(tmpdir, "backend")
            os.makedirs(backend_dir)
            pom_path = os.path.join(backend_dir, "pom.xml")
            with open(pom_path, "w") as f:
                f.write("""<?xml version="1.0" encoding="UTF-8"?>
<project>
    <properties>
        <java.version>17</java.version>
    </properties>
</project>""")
            stack = detect_tech_stack(tmpdir)
            self.assertEqual(stack.primary_language, "java")
            self.assertEqual(stack.language_version, "17")


class TestCrossStackValidation(unittest.TestCase):
    """Test cross-stack output validation."""

    def test_java_project_python_output_contamination(self):
        """Java project + Python output → contamination detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake Java project
            pom_path = os.path.join(tmpdir, "pom.xml")
            with open(pom_path, "w") as f:
                f.write("""<?xml version="1.0" encoding="UTF-8"?>
<project>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
</project>""")

            # Python-looking output
            python_output = """
Here is the implementation:

```python
import langchain
from sentence_transformers import SentenceTransformer
import numpy as np

def process_query(query):
    model = SentenceTransformer('all-MiniLM-L6-v2')
    embedding = model.encode(query)
    return embedding

pip install langchain sentence-transformers
```
            """

            result = validate_output_stack(tmpdir, python_output)
            self.assertTrue(result.contamination_detected)
            self.assertEqual(result.contaminated_language, "python")
            self.assertFalse(result.is_valid)
            self.assertGreater(len(result.warnings), 0)
            self.assertIn("CROSS-STACK CONTAMINATION", result.warnings[0])

    def test_java_project_java_output_clean(self):
        """Java project + Java output → no contamination."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pom_path = os.path.join(tmpdir, "pom.xml")
            with open(pom_path, "w") as f:
                f.write("""<?xml version="1.0" encoding="UTF-8"?>
<project>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
</project>""")

            # Java-looking output
            java_output = """
Here is the implementation:

```java
@Service
public class UserService {
    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Transactional
    public User createUser(CreateUserRequest request) {
        User user = new User();
        user.setName(request.getName());
        return userRepository.save(user);
    }
}
```

Add this to pom.xml:
```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
```
            """

            result = validate_output_stack(tmpdir, java_output)
            self.assertFalse(result.contamination_detected)
            self.assertTrue(result.is_valid)

    def test_java_project_mixed_output(self):
        """Java project + mixed Java/Python output → warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pom_path = os.path.join(tmpdir, "pom.xml")
            with open(pom_path, "w") as f:
                f.write("""<?xml version="1.0" encoding="UTF-8"?>
<project>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
</project>""")

            mixed_output = """
```java
@Service
public class UserService {
    private final UserRepository userRepository;
}
```

For testing, you can also use:
```python
import numpy as np
```
            """

            result = validate_output_stack(tmpdir, mixed_output)
            self.assertFalse(result.contamination_detected)  # Has Java markers too
            self.assertTrue(result.is_valid)
            self.assertGreater(len(result.warnings), 0)  # Should have mixed warning

    def test_empty_output(self):
        """Empty output should not trigger false positives."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pom_path = os.path.join(tmpdir, "pom.xml")
            with open(pom_path, "w") as f:
                f.write("""<?xml version="1.0" encoding="UTF-8"?>
<project>
    <properties><java.version>21</java.version></properties>
</project>""")

            result = validate_output_stack(tmpdir, "")
            self.assertFalse(result.contamination_detected)

    def test_python_project_java_output_contamination(self):
        """Python project + Java output → contamination detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            req_path = os.path.join(tmpdir, "requirements.txt")
            with open(req_path, "w") as f:
                f.write("flask==3.0.0\n")

            java_output = """
```java
@Service
public class UserService {
    @Autowired
    private UserRepository userRepository;
}
```
            """

            result = validate_output_stack(tmpdir, java_output)
            self.assertTrue(result.contamination_detected)
            self.assertEqual(result.contaminated_language, "java")


class TestStackContextPrompt(unittest.TestCase):
    """Test stack context prompt building."""

    def test_stack_context_for_java_spring(self):
        """Should generate appropriate context for Java Spring Boot project."""
        stack = TechStack(
            primary_language="java",
            language_version="21",
            build_system="maven",
            framework="spring-boot+mybatis-plus+rabbitmq+redis",
            runtime="jvm",
        )
        context = build_stack_context("", stack)
        self.assertIn("java", context)
        self.assertIn("21", context)
        self.assertIn("spring-boot", context)
        self.assertIn("maven", context)
        self.assertIn("CRITICAL", context)
        self.assertIn("generate java", context.lower())

    def test_stack_context_for_unknown(self):
        """Unknown stack → empty context."""
        stack = TechStack()
        context = build_stack_context("", stack)
        self.assertEqual(context, "")


class TestMarkerEffectiveness(unittest.TestCase):
    """Test that markers correctly detect different languages."""

    def test_python_markers_on_python_code(self):
        """Python markers should match Python code snippets."""
        python_snippets = [
            "import langchain",
            "from sentence_transformers import SentenceTransformer",
            "import torch",
            "def process(data):\n    return data",
            "pip install requests",
            "requirements.txt",
            "from transformers import pipeline",
            "@app.route('/')",
            "Flask(__name__)",
            "import numpy as np",
        ]
        for snippet in python_snippets:
            import re
            matches = any(re.search(p, snippet, re.MULTILINE) for p in PYTHON_MARKERS)
            self.assertTrue(matches, f"Python marker should match: {snippet}")

    def test_python_markers_on_java_code(self):
        """Python markers should NOT match Java code snippets."""
        java_snippets = [
            "@Service\npublic class UserService {",
            "import org.springframework.stereotype.Service;",
            "import com.example.demo.model.User;",
            "<dependency>\n    <groupId>org.springframework.boot</groupId>",
            "application.yml",
            "private final UserRepository userRepository;",
        ]
        for snippet in java_snippets:
            import re
            matches = any(re.search(p, snippet, re.MULTILINE) for p in PYTHON_MARKERS)
            self.assertFalse(matches, f"Python marker should NOT match: {snippet}")


if __name__ == "__main__":
    unittest.main()