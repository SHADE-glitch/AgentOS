# Improvement Candidate IC-002

## Problem
Distributed-system tasks are occasionally classified as generic backend-architect work, causing consistency and transaction reasoning to be under-prioritized.

## Evidence
- Failure records: F-002 and related benchmark review
- Runtime tasks: high-concurrency order and transaction scenarios
- Observed pattern: distributed consistency, idempotency, and partition handling were absent in the final design

## Root Cause
The router weights service architecture terminology more than distributed-state and failure-handling language.

## Proposed Change
- Increase distributed-system priority when keywords like transaction boundary, idempotency, partition tolerance, Consistency, inventory reservation, or eventual consistency appear
- Require system-architect and database-engineer support on these tasks
- Reduce generic backend-architect lead routing when the main risk is failure consistency

## Risk
Low to medium; could change some backend architecture tasks that are not actually distributed high-risk work.

## Validation
- Run 5 distributed-system benchmark cases
- Require benchmark evidence showing 4/5 or better lead-skill accuracy
- Human review required before implementation

## Status
Approved
