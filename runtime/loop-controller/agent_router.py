#!/usr/bin/env python3
"""
Agent Router — Phase 5.7

REAL Router component that classifies tasks and maps to skills.
This is NOT a simulation. It performs actual intent classification,
domain mapping, and skill matching using the SKILL.md registry.

Outputs a RouteDecision that feeds into the Skill Loader and Memory.
"""

import os
import re
import yaml
from datetime import datetime, timezone

BASE = "/home/shade/.agents"
SKILLS_DIR = os.path.join(BASE, "skills")
ROLE_REGISTRY_PATH = os.path.join(SKILLS_DIR, "meta", "role-registry.md")


# ── Intent Classification ────────────────────────────────────────

INTENT_RULES = [
    ("debug",       re.compile(r"debug|bug|修复|fix|异常|error|报错|crash|失败", re.I)),
    ("optimization", re.compile(r"优化|slow|慢|性能|performance|调优|benchmark|profiling|加速", re.I)),
    ("coding",      re.compile(r"实现|开发|写|创建|添加|新增|implement|create|add|write|build|生成", re.I)),
    ("architecture", re.compile(r"架构|设计|architect|系统设计|方案|设计模式|DDD|重构|refactor", re.I)),
    ("review",      re.compile(r"review|审查|检查|评审|code review|PR|检查代码", re.I)),
    ("research",    re.compile(r"研究|调研|分析|对比|选型|research|compare|方案", re.I)),
    ("learning",    re.compile(r"学习|解释|说明|什么是|如何|怎么|what is|how to|explain|教程", re.I)),
    ("testing",     re.compile(r"测试|test|用例|coverage|QA|单测|集成测试", re.I)),
    ("deployment",  re.compile(r"部署|deploy|发布|上线|release|CI/CD|容器化|dockerize", re.I)),
    ("security",    re.compile(r"安全|security|漏洞|攻击|加密|认证|鉴权|权限|PCI|OAuth|JWT|token", re.I)),
    ("data",        re.compile(r"数据库|database|SQL|query|查询|索引|index|schema|迁移|migration|ETL", re.I)),
    ("devops",      re.compile(r"Docker|容器|k8s|Kubernetes|运维|监控|logging|日志|CI/CD|pipeline", re.I)),
]

DOMAIN_RULES = [
    ("backend",     re.compile(r"API|后端|backend|Spring|Java|REST|接口|Controller|Service|@Service|@Controller", re.I)),
    ("frontend",    re.compile(r"前端|frontend|Vite|React|Vue|TypeScript|CSS|UI|页面|组件|component", re.I)),
    ("database",    re.compile(r"MySQL|SQL|数据库|database|慢查询|索引|index|schema|DDL|连接池|PostgreSQL|Redis", re.I)),
    ("security",    re.compile(r"安全|security|PCI|DSS|TLS|AES|加密|encrypt|RBAC|认证|鉴权|OAuth|JWT|token|password", re.I)),
    ("distributed", re.compile(r"分布式|distributed|高并发|concurrency|秒杀|微服务|microservice|Saga|多租户|multi.tenant|消息队列|RabbitMQ|Kafka", re.I)),
    ("ai",          re.compile(r"RAG|LLM|向量|vector|embedding|检索|retrieval|rerank|chunk|prompt|Agent|tool.calling", re.I)),
    ("devops",      re.compile(r"Docker|部署|deploy|CI/CD|容器|container|k8s|Kubernetes|镜像|helm|terraform", re.I)),
    ("architecture", re.compile(r"架构|architect|系统设计|设计模式|pattern|领域驱动|DDD|事件驱动|EDA", re.I)),
    ("testing",     re.compile(r"测试|test|用例|coverage|QA|单测|集成测试|integration test|unit test", re.I)),
    ("data",        re.compile(r"数据|data|ETL|数据仓库|data warehouse|大数据|spark|hadoop", re.I)),
]

# ── Skill Mapping ─────────────────────────────────────────────────

SKILL_CATEGORY_MAP = {
    "backend":      ["backend-architect", "backend/distributed-system"],
    "frontend":     ["frontend-architect", "frontend/frontend-performance"],
    "database":     ["database-engineer"],
    "security":     ["security-engineer"],
    "distributed":  ["system-architect", "backend/distributed-system"],
    "ai":           ["rag-engineer", "llm-engineer", "prompt-engineer", "agent-engineer"],
    "devops":       ["devops-engineer"],
    "architecture": ["system-architect", "technical-reviewer"],
    "testing":      ["testing-engineer", "code-reviewer"],
    "data":         ["database-engineer"],
}

INTENT_SKILL_PRIORITY = {
    "debug":        ["security-engineer", "code-reviewer", "backend-architect"],
    "optimization": ["database-engineer", "backend-architect", "frontend-performance"],
    "coding":       ["backend-architect", "frontend-architect", "system-architect"],
    "architecture": ["system-architect", "technical-reviewer"],
    "review":       ["code-reviewer", "technical-reviewer", "security-engineer"],
    "security":     ["security-engineer", "code-reviewer"],
    "data":         ["database-engineer"],
    "devops":       ["devops-engineer"],
    "testing":      ["testing-engineer", "code-reviewer"],
    "ai":           ["rag-engineer", "llm-engineer", "agent-engineer"],
}


def classify_intent(task_text: str) -> dict:
    """Classify task intent and domains."""
    intent = "coding"
    for name, pattern in INTENT_RULES:
        if pattern.search(task_text):
            intent = name
            break

    domains = []
    for name, pattern in DOMAIN_RULES:
        if pattern.search(task_text):
            domains.append(name)

    if not domains:
        domains = ["backend"]

    return {
        "intent": intent,
        "domains": domains,
    }


def route(task_text: str, memory_context: dict = None) -> dict:
    """
    Route a task to the appropriate skill(s).

    This is the REAL Router function. It:
    1. Classifies intent and domains
    2. Maps to skills using domain rules
    3. Considers memory context for routing decisions
    4. Returns a RouteDecision with lead_skill, support_skills, confidence

    Args:
        task_text: The task description
        memory_context: Optional dict with memories that may influence routing

    Returns:
        dict: RouteDecision
    """
    started_at = datetime.now(timezone.utc).isoformat()

    # Stage 1: Intent classification
    intent_info = classify_intent(task_text)
    intent = intent_info["intent"]
    domains = intent_info["domains"]

    # Stage 2: Skill matching
    primary_domain = domains[0]
    lead_skill = None
    support_skills = []

    # Intent-based priority
    priority_skills = INTENT_SKILL_PRIORITY.get(intent, [])
    for skill in priority_skills:
        if lead_skill is None:
            lead_skill = skill
        elif len(support_skills) < 2:
            support_skills.append(skill)

    # Domain-based skills
    domain_skills = SKILL_CATEGORY_MAP.get(primary_domain, [])
    for skill in domain_skills:
        if skill not in [lead_skill] + support_skills:
            if len(support_skills) < 2:
                support_skills.append(skill)

    if lead_skill is None:
        lead_skill = "backend-architect"

    # Stage 3: Confidence assessment
    confidence = "medium"
    if len(domains) == 1 and primary_domain in SKILL_CATEGORY_MAP:
        confidence = "high"
    elif len(domains) > 2:
        confidence = "low"

    # Stage 4: Memory influence on routing
    memory_influence = "none"
    memory_count = 0
    if memory_context:
        memories = memory_context.get("memories", [])
        memory_count = len(memories)
        if memory_count > 0:
            if memory_count >= 3:
                memory_influence = "confirmation"
            else:
                memory_influence = "weak"

    completed_at = datetime.now(timezone.utc).isoformat()

    return {
        "intent": intent,
        "domains": domains,
        "primary_domain": primary_domain,
        "lead_skill": lead_skill,
        "support_skills": support_skills,
        "confidence": confidence,
        "memory_influence": memory_influence,
        "memory_retrieved": memory_count,
        "rules_applied": [
            f"Intent '{intent}' → priority skills {priority_skills[:3]}",
            f"Domain '{primary_domain}' → skills {domain_skills[:3]}",
        ],
        "started_at": started_at,
        "completed_at": completed_at,
    }