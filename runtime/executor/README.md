# Runtime Executor

Minimal Execution Harness for Agent OS Phase 5.6.2.

## Purpose

This directory contains the adapter layer that connects Agent OS declarative specifications (Router, Memory, Orchestrator) to an actual Runtime Backend (OpenCode CLI).

## Structure

```
runtime/executor/
├── README.md                  # This file
├── execution-contract.md      # Input/output contract
├── opencode-adapter.md        # OpenCode CLI adapter spec
└── executions/                # Execution records
    └── <execution_id>.yaml
```

## Backend

| Property | Value |
|----------|-------|
| Backend | OpenCode CLI |
| Version | 1.18.23 |
| Default Model | opencode/ling-3.0-flash-fin-free |
| Cost | Free |
| Status | OPERATIONAL |

## Quick Start

```bash
# Single task execution
opencode run --format json --auto --model opencode/ling-3.0-flash-fin-free '<task prompt>'
```

## Pipeline

```
Task → Router → Memory Retrieval → Decision Support → Orchestrator → OpenCode CLI → Trace
```

## Execution Records

All execution records are written to `executions/` and `runtime/traces/`.