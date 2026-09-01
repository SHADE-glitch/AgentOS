#!/usr/bin/env python3
"""Populate routing-feedback.yaml from real trace data."""
import yaml
import os
import re
from datetime import datetime, timezone

TRACES_DIR = "/home/shade/.agents/runtime/traces"
ROUTING_FEEDBACK = "/home/shade/.agents/runtime/memory-feedback/retrieval/routing-feedback.yaml"


def compute_quality(response):
    comp = acc = struct = act = nov = 0
    if re.search(r'#{1,3}\s', response): comp += 1
    if re.search(r'[-*]\s', response): comp += 1
    if re.search(r'```', response): comp += 1
    if len(re.findall(r'#{1,3}\s', response)) >= 3: comp += 1
    if len(response) > 100: comp += 1
    tech_terms = ['API', 'TLS', 'AES', 'JWT', 'RBAC', 'SQL', 'RAG', 'LLM',
                  'cache', 'token', 'encrypt', 'vector', 'retrieval', 'index',
                  '数据库', '向量', '检索', '加密', '认证', '授权', '缓存']
    if any(t.lower() in response.lower() for t in tech_terms): acc += 1
    if re.search(r'(?:使用|采用|选择|推荐|基于|通过)', response): acc += 1
    if re.search(r'(?:实现|配置|部署|设置|构建|处理)', response): acc += 1
    if re.search(r'(?:因为|原因|由于|为了|确保|避免)', response): acc += 1
    if re.search(r'(?:具体|详细|明确)', response): acc += 1
    if re.search(r'^\d+[\.、）)]\s', response, re.MULTILINE): struct += 1
    if re.search(r'^#{1,3}\s', response, re.MULTILINE): struct += 1
    if len(response.split('\n')) > 8: struct += 1
    if response.count('\n') > 5: struct += 1
    if len(response) > 100 and '\n\n' in response: struct += 1
    if re.search(r'(?:步骤|流程|Step|方法|方式)', response): act += 1
    if re.search(r'(?:建议|推荐|方案|策略|设计)', response): act += 1
    if re.search(r'(?:例如|示例|比如|如)', response): act += 1
    if re.search(r'(?:配置|参数|设置|兼容|注意)', response): act += 1
    if len(response) > 100: act += 1
    if re.search(r'(?:数据库|向量|检索|索引|缓存|存储|查询)', response): nov += 1
    if re.search(r'(?:权衡|取舍|trade|利弊|对比|相比)', response, re.IGNORECASE): nov += 1
    if re.search(r'(?:边界|极端|边缘|corner|特殊|异常)', response, re.IGNORECASE): nov += 1
    if re.search(r'(?:优化|改进|提升|增强|加速)', response): nov += 1
    if len(response) > 200: nov += 1
    return round(comp * 0.25 + acc * 0.30 + struct * 0.15 + act * 0.20 + nov * 0.10, 2)


def main():
    targets = [
        "EXEC-1788090990", "EXEC-1788091359", "EXEC-1788091469",
        "EXEC-1788091972", "EXEC-1788092974"
    ]

    entries = []
    for exec_id in targets:
        fname = f"{exec_id}.yaml"
        path = os.path.join(TRACES_DIR, fname)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            trace = yaml.unsafe_load(f)

        mem_retrieval = trace.get("memory_retrieval", {})
        mem_used = mem_retrieval.get("memories_used", [])
        mem_influence = mem_retrieval.get("memory_influence", mem_retrieval.get("influence", "none"))
        ai = trace.get("agent_invocation", {})
        tokens = ai.get("tokens", {})
        quality = compute_quality(trace.get("agent_response", ""))

        # Determine weight adjustments
        for mid in mem_used:
            if quality >= 3.0:
                direction, magnitude, reason = "up", 0.1, "High-quality outcome"
            elif quality >= 2.0:
                direction, magnitude, reason = "up", 0.05, "Acceptable outcome"
            elif quality < 1.0:
                direction, magnitude, reason = "down", 0.1, "Low-quality outcome (fallback model?)"
            else:
                direction, magnitude, reason = "hold", 0.0, "Neutral outcome"

            entries.append({
                "feedback_id": f"RF-{exec_id}-{mid}",
                "execution_id": exec_id,
                "task": {
                    "task_id": trace.get("task_id", ""),
                    "task_text": trace.get("task_text", "")[:100],
                    "category": trace.get("domain", ""),
                    "domains": [trace.get("domain", "")],
                    "difficulty": trace.get("difficulty", ""),
                },
                "selected_memories": [
                    {
                        "memory_id": mid,
                        "relevance_score": 0.0,
                        "final_score": 0.0,
                        "influence_type": mem_influence,
                        "was_applied": True,
                    }
                ],
                "selected_agent": {
                    "lead_agent": ai.get("agent_role", "unknown"),
                    "support_agents": [],
                    "team_size": 1,
                    "memory_influenced": mem_influence != "none",
                },
                "execution_quality": {
                    "status": trace.get("status", "unknown"),
                    "quality_score": quality,
                    "tokens_total": tokens.get("total", 0),
                    "latency_ms": ai.get("latency_ms", 0),
                    "model_used": ai.get("model", "unknown"),
                    "fallback_used": "fallback" in trace.get("agent_response", "").lower() or ai.get("model", "").lower() == "fallback",
                },
                "future_weight_change": {
                    "memory_id": mid,
                    "direction": direction,
                    "magnitude": magnitude,
                    "reason": reason,
                    "confidence": "low",
                },
            })

    # Load existing routing feedback
    with open(ROUTING_FEEDBACK) as f:
        fb = yaml.unsafe_load(f)

    fb["routing_feedback"]["entries"] = entries
    fb["routing_feedback"]["generated_at"] = datetime.now(timezone.utc).isoformat()

    with open(ROUTING_FEEDBACK, "w") as f:
        yaml.dump(fb, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"Populated {len(entries)} routing feedback entries from {len(targets)} traces")
    for e in entries:
        print(f"  {e['feedback_id']}: {e['selected_memories'][0]['memory_id']} → "
              f"quality={e['execution_quality']['quality_score']} → "
              f"{e['future_weight_change']['direction']} {e['future_weight_change']['magnitude']}")


if __name__ == "__main__":
    main()