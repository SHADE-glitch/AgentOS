# Failure Log

This file records outcomes that were below expected quality.

## Record format

```text
Date:
Context:
Failure Type:
Root Cause:
Impact:
Evidence:
Fix Direction:
```

## Example

```text
Date: 2026-08-30
Context: 遇到高并发订单场景
Failure Type: missing consistency analysis
Root Cause: routing selected backend-architect without sufficient distributed-system support
Impact: design missed stock reservation and ordering consistency concerns
Evidence: user requested architecture-level design but output lacked distributed trade-offs
Fix Direction: update route priority and include distributed-system support for concurrency-heavy tasks
```

## Important rule

Failures are not blame records. They are improvement fuel.
