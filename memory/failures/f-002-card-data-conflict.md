```yaml
memory_id: F-002
type: failure
created_at: 2026-08-30
source:
  type: benchmark
  task_id: backend-02
  run_id: round0
  mode: multi
  file: runtime/datasets/multi-agent/comparison/backend-02.yaml
category: backend
confidence: low
evidence_level: benchmark_evaluated
tags: [collaboration, security, card-data, conflict, productive-conflict]
status: observed
```

# F-002: Card Data Storage Conflict

## Symptom

During the payment system design, a conflict arose between the security-engineer and backend-architect over how to store card payment data.

## Root Cause

The security-engineer insisted on PCI-DSS compliance with tokenized card references, while the backend-architect had designed a more conventional storage model. The conflict emerged because security was integrated after the initial data model was proposed, forcing a late redesign.

## Impact

- 1 additional human review cycle required
- cost_delta increased to 2, causing the winner rule to flip from multi to single
- Despite the +1.50 quality gain (largest in Round 0), the task was marked as single win
- The conflict was **productive** — it led to a PCI-DSS compliant design

## Correction

The resolution produced a secure design: token reference in the ledger, last4 digits in a separate secured table with separate encryption. The security-engineer's late entry forced a redesign of the data model.

## Prevention

**Security role should join before API contract finalization.** The team formation sequencing should place security-engineer in layer 0 (architecture phase) rather than layer 1 (review phase) for payment and compliance-sensitive tasks.

## Evidence Level

`benchmark_evaluated` — single observation in Round 0. The sequencing issue is a hypothesis, not yet validated.

## Note

This is the strongest evidence for the "security-first" team formation pattern. The quality gain (+1.50) was the largest in Round 0, but the coordination cost from late security integration penalized the result. The lesson is about **role ordering** in team formation.