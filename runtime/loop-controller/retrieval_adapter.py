#!/usr/bin/env python3
"""
Retrieval Adapter — Phase 5.8.2.2
Bridges between task input and retrieval_optimizer.

Task → classify → retrieval_optimizer.retrieve() → DecisionContext

This is NOT an Agent. It does NOT decide team formation.
It only classifies the task and queries existing Memory.
"""

import sys
import os
import re
from datetime import datetime, timezone

# Allow importing retrieval_optimizer from sibling package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "memory-feedback", "retrieval"))
from retrieval_optimizer import retrieve as retrieval_retrieve, save_retrieval_history

BASE = "/home/shade/.agents"


# ---------------------------------------------------------------------------
# Task Classification
# ---------------------------------------------------------------------------

CATEGORY_RULES = [
    ("optimization", re.compile(r"优化|慢查询|slow.query|性能|performance|调优|索引|index", re.I)),
    ("backend",     re.compile(r"API|后端|backend|Spring|Java|认证|鉴权|REST|接口", re.I)),
    ("frontend",    re.compile(r"前端|frontend|Vite|React|Vue|TypeScript|CSS|UI|页面", re.I)),
    ("architecture", re.compile(r"架构|architect|分布式|distributed|微服务|microservice|系统设计|高并发|seckill|秒杀|多租户|multi.tenant", re.I)),
    ("ai",          re.compile(r"RAG|LLM|向量|vector|embedding|检索|rerank|Agent|tool.calling|prompt", re.I)),
    ("database",    re.compile(r"MySQL|数据库|database|SQL|schema|DDL|DML|存储|连接池", re.I)),
    ("devops",      re.compile(r"Docker|部署|deploy|CI/CD|容器|container|k8s|Kubernetes", re.I)),
]

DOMAIN_RULES = [
    ("database",    re.compile(r"MySQL|SQL|数据库|database|慢查询|索引|index|schema|DDL|连接池", re.I)),
    ("backend",     re.compile(r"API|后端|backend|Spring|Java|REST|接口|认证|鉴权|OAuth|JWT", re.I)),
    ("frontend",    re.compile(r"前端|frontend|Vite|React|Vue|TypeScript|CSS|UI|页面|组件", re.I)),
    ("security",    re.compile(r"安全|security|PCI|DSS|TLS|AES|加密|encrypt|RBAC|认证|鉴权|OAuth", re.I)),
    ("distributed", re.compile(r"分布式|distributed|高并发|concurrency|seckill|秒杀|微服务|microservice|Saga|多租户|multi.tenant", re.I)),
    ("rag",         re.compile(r"RAG|向量|vector|embedding|检索|retrieval|rerank|chunk", re.I)),
    ("agent",       re.compile(r"Agent|tool.calling|LLM|prompt|agent|多智能体", re.I)),
    ("devops",      re.compile(r"Docker|部署|deploy|CI/CD|容器|container|k8s|Kubernetes|镜像", re.I)),
    ("architecture", re.compile(r"架构|architect|系统设计|设计模式|pattern|领域驱动|DDD", re.I)),
    ("optimization", re.compile(r"优化|性能|performance|调优|benchmark|profiling", re.I)),
]

ROLE_RULES = [
    ("database-engineer",   re.compile(r"MySQL|SQL|数据库|database|慢查询|索引|index", re.I)),
    ("backend-architect",   re.compile(r"API|后端|backend|Spring|Java|REST|接口", re.I)),
    ("frontend-architect",  re.compile(r"前端|frontend|Vite|React|Vue|TypeScript|UI|页面", re.I)),
    ("security-engineer",   re.compile(r"安全|security|PCI|DSS|TLS|加密|encrypt|RBAC|OAuth", re.I)),
    ("system-architect",    re.compile(r"架构|architect|分布式|distributed|系统设计|高并发|seckill|秒杀|微服务", re.I)),
    ("rag-engineer",        re.compile(r"RAG|向量|vector|embedding|检索|retrieval|rerank", re.I)),
    ("llm-engineer",        re.compile(r"LLM|Agent|tool.calling|prompt|agent", re.I)),
    ("devops-engineer",     re.compile(r"Docker|部署|deploy|CI/CD|容器|container|k8s|Kubernetes", re.I)),
]

KEYWORD_RULES = [
    # database
    ("mysql",       re.compile(r"MySQL|mysql", re.I)),
    ("slow-query",  re.compile(r"慢查询|slow.query", re.I)),
    ("indexing",    re.compile(r"索引|index", re.I)),
    ("optimization", re.compile(r"优化|性能|调优|performance", re.I)),
    # backend
    ("api",         re.compile(r"API|接口", re.I)),
    ("spring",      re.compile(r"Spring|spring", re.I)),
    ("java",        re.compile(r"Java|java", re.I)),
    ("auth",        re.compile(r"认证|鉴权|OAuth|JWT|RBAC", re.I)),
    # frontend
    ("vite",        re.compile(r"Vite|vite", re.I)),
    ("react",       re.compile(r"React|react", re.I)),
    ("typescript",  re.compile(r"TypeScript|typescript", re.I)),
    # architecture
    ("distributed", re.compile(r"分布式|distributed", re.I)),
    ("high-concurrency", re.compile(r"高并发|concurrency|seckill|秒杀", re.I)),
    ("multi-tenant", re.compile(r"多租户|multi.tenant", re.I)),
    # ai
    ("rag",         re.compile(r"RAG|rag", re.I)),
    ("vector",      re.compile(r"向量|vector|embedding", re.I)),
    ("llm",         re.compile(r"LLM|llm", re.I)),
    ("agent",       re.compile(r"Agent|agent|tool.calling", re.I)),
    # security
    ("pci-dss",     re.compile(r"PCI.DSS|PCI|DSS", re.I)),
    ("encryption",  re.compile(r"加密|encrypt|TLS|AES", re.I)),
    # devops
    ("docker",      re.compile(r"Docker|docker|容器|container", re.I)),
    ("deploy",      re.compile(r"部署|deploy|CI/CD", re.I)),
]

DIFFICULTY_RULES = [
    ("easy",    re.compile(r"简单|simple|easy|基础|basic|单个|single|简单查询|慢查询", re.I)),
    ("hard",    re.compile(r"复杂|complex|高并发|分布式|distributed|跨领域|cross.domain|多租户|multi.tenant|秒杀|seckill|系统设计|架构", re.I)),
]


def classify_task(task_text):
    """
    Classify a task into category, domains, roles, keywords, difficulty.
    Uses simple keyword matching — no ML, no external deps.
    """
    category = "backend"  # default
    for cat, pattern in CATEGORY_RULES:
        if pattern.search(task_text):
            category = cat
            break

    domains = []
    for dom, pattern in DOMAIN_RULES:
        if pattern.search(task_text):
            domains.append(dom)

    roles = []
    for role, pattern in ROLE_RULES:
        if pattern.search(task_text):
            roles.append(role)

    keywords = []
    for kw, pattern in KEYWORD_RULES:
        if pattern.search(task_text):
            keywords.append(kw)

    difficulty = "medium"  # default
    for diff, pattern in DIFFICULTY_RULES:
        if pattern.search(task_text):
            difficulty = diff
            break

    return {
        "task_text": task_text,
        "category": category,
        "domains": domains,
        "roles": roles,
        "keywords": keywords,
        "difficulty": difficulty,
    }


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

def adapt(task_id, task_text, memory_mode):
    """
    Bridge: task → retrieval_optimizer.retrieve() → DecisionContext

    Args:
        task_id: str like "RT-003"
        task_text: str, the task description
        memory_mode: "enabled" | "fallback" | "disabled"

    Returns:
        DecisionContext dict with retrieval results, or empty context if disabled.
    """
    if memory_mode in ("disabled", "off"):
        return {
            "task_id": task_id,
            "task_text": task_text,
            "memory_mode": memory_mode,
            "retrieved": False,
            "memories": [],
            "hypotheses": [],
            "total_retrieved": 0,
            "ranking": [],
            "retrieval_raw": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # Classify task
    query = classify_task(task_text)
    query["exclude_hypothesis"] = False

    # Phase 5.8.2.2: Always retrieve — but label hypotheses separately
    raw_result = retrieval_retrieve(query)

    # Separate hypotheses from established memories
    memories = []
    hypotheses = []
    for r in raw_result.get("results", []):
        if r.get("is_hypothesis") or r.get("type") == "hypothesis":
            hypotheses.append(r)
        else:
            memories.append(r)

    # Save retrieval history for decay tracking
    try:
        save_retrieval_history(query, raw_result)
    except Exception:
        pass  # Non-critical

    return {
        "task_id": task_id,
        "task_text": task_text,
        "memory_mode": memory_mode,
        "retrieved": True,
        "memories": memories,
        "hypotheses": hypotheses,
        "total_retrieved": raw_result.get("top_k", 0),
        "total_considered": raw_result.get("total_considered", 0),
        "after_filter": raw_result.get("after_filter", 0),
        "ranking": [m["memory_id"] for m in memories],
        "retrieval_raw": raw_result,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import yaml

    if len(sys.argv) < 3:
        print("Usage: python3 retrieval_adapter.py <task_id> <task_text> [memory_mode]")
        print("Example: python3 retrieval_adapter.py RT-003 '分析 MySQL 慢查询问题' enabled")
        sys.exit(1)

    task_id = sys.argv[1]
    task_text = sys.argv[2]
    memory_mode = sys.argv[3] if len(sys.argv) > 3 else "enabled"

    result = adapt(task_id, task_text, memory_mode)
    print(yaml.dump(result, default_flow_style=False, allow_unicode=True, sort_keys=False))