#!/usr/bin/env python3
"""
Phase 8.2.1 — Experience Extractor

Extracts ExperienceRecords from multi-agent TeamResult data.

Takes a TeamResult YAML (loaded as dict) and produces structured ExperienceRecords
that capture: technical patterns, problem patterns, solutions, failures, architecture
decisions, and engineering constraints.

Each ExperienceRecord is later converted to a MemoryCandidate by the TeamResultCollector.

Rules:
  - Do NOT save raw agent output directly
  - Extract structured lessons from agent outputs
  - Preserve provenance (source agent, team_id, loop_id)
  - Assign confidence based on output quality and agent role
"""

import re
import os
import hashlib
from typing import Optional


def _extract_title_from_output(output_text: str, role: str) -> str:
    """Extract or generate a title from agent output."""
    # Try to find a heading
    heading_match = re.search(r'#{1,3}\s+(.+?)(?:\n|$)', output_text)
    if heading_match:
        title = heading_match.group(1).strip()
        # Clean up markdown formatting
        title = re.sub(r'\*\*', '', title)
        title = re.sub(r'`', '', title)
        if len(title) > 80:
            title = title[:77] + "..."
        return title

    # Try to find a "诊断" / "分析" / "report" keyword
    for keyword in ["诊断", "分析", "报告", "report", "analysis", "diagnosis"]:
        idx = output_text.lower().find(keyword)
        if idx >= 0:
            snippet = output_text[max(0, idx - 10):idx + 60].strip()
            snippet = re.sub(r'[#*`\n]', '', snippet)
            return snippet[:80]

    return f"Agent analysis from {role}"


def _extract_context_from_task(task_cards: list, role: str) -> str:
    """Extract task context from the task card description."""
    for tc in task_cards:
        if isinstance(tc, dict) and tc.get("role") == role:
            return tc.get("output_summary", "")[:200]
    return ""


def _extract_technical_patterns(output_text: str) -> list[str]:
    """Extract technical patterns: tech stack, architectural decisions, patterns."""
    patterns = []

    # Look for specific tech patterns
    tech_patterns = [
        (r'(?:Redis|缓存).*?(?:过期|TTL|expir)', 'Cache expiration pattern'),
        (r'(?:JWT|token|Token).*?(?:刷新|revoke|refresh)', 'Token management pattern'),
        (r'(?:DB|数据库|MySQL|PostgreSQL).*?(?:回退|fallback|failover)', 'Database fallback pattern'),
        (r'(?:锁|lock|Lock|分布式).*?(?:竞争|超时|timeout)', 'Distributed lock pattern'),
        (r'(?:幂等|idempotent|去重|dedup)', 'Idempotency pattern'),
        (r'(?:状态机|state machine|status.*transition)', 'State machine pattern'),
        (r'(?:索引|index|查询优化|query.*optim)', 'Index/query optimization pattern'),
        (r'(?:虚拟线程|virtual thread|并发|concurren)', 'Concurrency pattern'),
        (r'(?:SSE|Server-Sent|轮询|polling)', 'Streaming pattern'),
        (r'(?:安全|security|认证|auth|授权|authoriz)', 'Security pattern'),
    ]

    for pattern, name in tech_patterns:
        if re.search(pattern, output_text, re.IGNORECASE):
            patterns.append(name)

    return patterns[:5]  # Max 5 patterns


def _extract_problem_patterns(output_text: str) -> list[str]:
    """Extract problem patterns: bugs, risks, anti-patterns."""
    problems = []

    problem_patterns = [
        (r'(?:不一致|inconsist|漂移|drift|stale)', 'Data inconsistency'),
        (r'(?:重复|duplicate|double.*submit)', 'Duplicate submission'),
        (r'(?:竞争|race.*condition|竞态)', 'Race condition'),
        (r'(?:超时|timeout|瓶颈|bottleneck)', 'Timeout/bottleneck'),
        (r'(?:内存泄漏|memory leak|OOM)', 'Memory leak'),
        (r'(?:NULL|空指针|NPE|NullPointer)', 'Null pointer'),
        (r'(?:丢失|数据丢失|data loss|miss)', 'Data loss'),
        (r'(?:死锁|deadlock)', 'Deadlock'),
        (r'(?:注入|injection|XSS|CSRF)', 'Injection vulnerability'),
        (r'(?:配置|config.*错误|misconfig)', 'Misconfiguration'),
    ]

    for pattern, name in problem_patterns:
        if re.search(pattern, output_text, re.IGNORECASE):
            problems.append(name)

    return problems[:5]


def _extract_solutions(output_text: str) -> list[str]:
    """Extract solution patterns proposed by agents."""
    solutions = []

    solution_patterns = [
        (r'(?:幂等.*?键|idempotency.*?key|request.*?id)', 'Idempotency key'),
        (r'(?:消息.*?重建|rebuild.*?message|以.*?记录.*?为准)', 'Rebuild from source of truth'),
        (r'(?:去重.*?约束|UNIQUE.*?constraint|唯一.*?约束)', 'Unique constraint'),
        (r'(?:校验|validat.*?check|一致性.*?校验)', 'Validation check'),
        (r'(?:异步|async|队列|queue|MQ)', 'Async/queue processing'),
        (r'(?:T?TL.*?刷新|refresh.*?TTL|续期)', 'TTL refresh'),
        (r'(?:回滚|rollback|补偿|compensat)', 'Rollback/compensation'),
        (r'(?:熔断|circuit.*?breaker|降级|degrad)', 'Circuit breaker'),
        (r'(?:限流|rate.*?limit|throttl)', 'Rate limiting'),
        (r'(?:加密|encrypt|hash|哈希)', 'Encryption/hashing'),
    ]

    for pattern, name in solution_patterns:
        if re.search(pattern, output_text, re.IGNORECASE):
            solutions.append(name)

    return solutions[:5]


# Phase 8.2.1.1: Domain-specific pattern extraction
# Extracts file-level, class-level, and method-level patterns from agent output
# instead of only generic engineering patterns.

def _extract_domain_patterns(output_text: str) -> list[dict]:
    """
    Extract domain-specific patterns with file/line provenance.

    Looks for:
      - File paths with optional line numbers: InterviewService.java:372
      - Class.method references: RagService.retrieveChunks()
      - Specific code patterns in context

    Returns:
        list of dicts with: pattern_name, file, line, context, severity
    """
    patterns = []

    # Pattern 1: File:line references with a problem description
    # e.g., "InterviewService.java:372 TOCTOU race condition"
    file_line_context = re.findall(
        r'([\w/.-]+\.(?:java|py|ts|js|go|rs|rb|php|cs|kt|swift))\s*[:：]\s*(\d+)\s*(?:[：:\-–—]|\s+)(.+?)(?:\n|$)',
        output_text
    )
    for file_path, line_num, context in file_line_context[:10]:
        file_name = os.path.basename(file_path)
        # Classify the context
        severity = "medium"
        if re.search(r'(?:CRITICAL|critical|严重|critical)', context, re.IGNORECASE):
            severity = "critical"
        elif re.search(r'(?:HIGH|high|高)', context, re.IGNORECASE):
            severity = "high"

        pattern_name = f"{file_name}:{line_num} {context.strip()[:60]}"
        patterns.append({
            "pattern_name": pattern_name,
            "file": file_path,
            "line": int(line_num),
            "context": context.strip()[:200],
            "severity": severity,
            "pattern_type": "file_line_context",
        })

    # Pattern 2: Class.method or function references with issues
    # e.g., "RagService.retrieveChunks() performs full table scan"
    class_method = re.findall(
        r'([\w]+)\.([\w]+)\s*\(\)\s*(?:[：:\-–—]\s*)?(.+?)(?:\n|$)',
        output_text
    )
    for class_name, method_name, context in class_method[:10]:
        pattern_name = f"{class_name}.{method_name}() {context.strip()[:60]}"
        patterns.append({
            "pattern_name": pattern_name,
            "file": f"{class_name}.java",
            "line": 0,
            "context": context.strip()[:200],
            "severity": "medium",
            "pattern_type": "class_method",
        })

    # Pattern 3: Markdown code blocks with language annotation
    # Look for problems described near code blocks
    code_blocks = list(re.finditer(r'```(\w+)?\n(.*?)\n```', output_text, re.DOTALL))
    for i, match in enumerate(code_blocks):
        lang = match.group(1) or "code"
        code = match.group(2)
        # Look for the text before this code block for context
        pre_start = max(0, match.start() - 200)
        pre_text = output_text[pre_start:match.start()]
        # Extract a summary from the preceding text
        summary = pre_text.strip().split('\n')[-1] if pre_text.strip() else "Code pattern"
        if len(summary) > 80:
            summary = summary[:77] + "..."

        pattern_name = f"{lang}: {summary}"
        # Extract key identifiers from the code
        identifiers = re.findall(r'(?:class|def|function|method|public|private)\s+(\w+)', code)
        if identifiers:
            pattern_name = f"{lang}: {identifiers[0]} {summary[:50]}"

        patterns.append({
            "pattern_name": pattern_name,
            "file": "",
            "line": 0,
            "context": code[:200],
            "severity": "medium",
            "pattern_type": "code_block",
        })

    # Deduplicate by pattern_name
    seen = set()
    unique = []
    for p in patterns:
        if p["pattern_name"] not in seen:
            seen.add(p["pattern_name"])
            unique.append(p)

    return unique[:10]


def _extract_technical_patterns_enriched(output_text: str) -> list[str]:
    """
    Extract technical patterns combining generic patterns with domain-specific ones.
    Phase 8.2.1.1: Enriched with file/class/method level patterns.
    """
    # Get generic patterns
    generic = _extract_technical_patterns(output_text)

    # Get domain-specific patterns
    domain = _extract_domain_patterns(output_text)

    # Combine: domain patterns first (more specific), then generic (fallback)
    combined = [d["pattern_name"] for d in domain[:5]]
    for g in generic:
        if len(combined) >= 8:
            break
        if g not in combined:
            combined.append(g)

    return combined[:8]


def _assess_confidence(output_text: str, role: str, is_lead: bool,
                       token_count: int, latency_ms: int) -> float:
    """Heuristic confidence assessment based on output quality."""
    score = 0.5  # Base

    # Length and structure
    if len(output_text) > 500: score += 0.05
    if len(output_text) > 2000: score += 0.05
    if len(output_text) > 5000: score += 0.05
    if re.search(r'#{1,3}\s', output_text): score += 0.03  # Has headers
    if re.search(r'```', output_text): score += 0.03  # Has code blocks
    if re.search(r'\|\s.*\|\s.*\|', output_text): score += 0.03  # Has tables

    # Role authority
    if is_lead: score += 0.05
    if role in ["backend-architect", "security-engineer", "code-reviewer"]:
        score += 0.03

    # Execution quality
    if token_count > 20000: score += 0.03
    if token_count > 40000: score += 0.03
    if 60 < latency_ms / 1000 < 600: score += 0.02  # Reasonable latency

    return min(score, 0.95)


def extract_experiences(team_result_data: dict) -> list[dict]:
    """
    Extract ExperienceRecords from a TeamResult dict.

    Args:
        team_result_data: loaded team-result-*.yaml as dict

    Returns:
        list of ExperienceRecord dicts
    """
    experiences = []
    team_result = team_result_data.get("team_result", {})
    task_cards = team_result_data.get("task_cards", [])

    team_id = team_result_data.get("team_id", "")
    loop_id = team_result_data.get("loop_id", "")
    team_status = team_result.get("status", "unknown")

    # Extract from lead agent output
    lead_output = team_result.get("lead_output", {})
    if lead_output and lead_output.get("output"):
        lead_role = lead_output.get("agent", "lead")
        output_text = lead_output.get("output", "")
        tokens = lead_output.get("tokens", {})
        latency = lead_output.get("latency_ms", 0)

        exp = {
            "experience_id": f"EXP-{loop_id}-{_sanitize_id(lead_role)}",
            "source_id": loop_id,
            "source_type": "team_result",
            "type": "engineering_pattern",
            "title": _extract_title_from_output(output_text, lead_role),
            "context": _extract_context_from_task(task_cards, lead_role),
            "lesson": output_text[:500],  # First 500 chars as lesson summary
            "technical_patterns": _extract_technical_patterns_enriched(output_text),
            "domain_patterns": _extract_domain_patterns(output_text),
            "problem_patterns": _extract_problem_patterns(output_text),
            "solutions": _extract_solutions(output_text),
            "confidence": _assess_confidence(output_text, lead_role, True,
                                             tokens.get("total", 0), latency),
            "agent_role": lead_role,
            "is_lead": True,
            "team_id": team_id,
            "team_status": team_status,
            "evidence": {
                "output_hash": hashlib.sha256(output_text.encode()).hexdigest()[:16],
                "token_usage": tokens,
                "latency_ms": latency,
                "output_length": len(output_text),
                "is_real_execution": True,
            },
        }
        experiences.append(exp)

    # Extract from support agent contributions
    contributions = team_result.get("contributions", [])
    for contrib in contributions:
        role = contrib.get("role", "")
        is_lead = contrib.get("is_lead", False)
        if is_lead:
            continue  # Already handled above

        output_data = contrib.get("output", {})
        if not output_data:
            continue

        output_text = output_data.get("output", "")
        if not output_text:
            continue

        tokens = output_data.get("tokens", {})
        latency = output_data.get("latency_ms", 0)

        exp = {
            "experience_id": f"EXP-{loop_id}-{_sanitize_id(role)}",
            "source_id": loop_id,
            "source_type": "team_result",
            "type": "engineering_pattern",
            "title": _extract_title_from_output(output_text, role),
            "context": _extract_context_from_task(task_cards, role),
            "lesson": output_text[:500],
            "technical_patterns": _extract_technical_patterns_enriched(output_text),
            "domain_patterns": _extract_domain_patterns(output_text),
            "problem_patterns": _extract_problem_patterns(output_text),
            "solutions": _extract_solutions(output_text),
            "confidence": _assess_confidence(output_text, role, False,
                                             tokens.get("total", 0), latency),
            "agent_role": role,
            "is_lead": False,
            "team_id": team_id,
            "team_status": team_status,
            "evidence": {
                "output_hash": hashlib.sha256(output_text.encode()).hexdigest()[:16],
                "token_usage": tokens,
                "latency_ms": latency,
                "output_length": len(output_text),
                "is_real_execution": True,
            },
        }
        experiences.append(exp)

    return experiences


def _sanitize_id(name: str) -> str:
    """Sanitize a name for use in an ID."""
    return re.sub(r'[^a-zA-Z0-9_-]', '-', name)[:40]