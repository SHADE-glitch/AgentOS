# Improvement Candidate IC-003

## Problem
SQL optimization and API-security tasks often omit required support roles, which weakens operational quality even when the lead skill is correct.

## Evidence
- Failure records: F-003, F-004
- Benchmark review: database and security support-role omissions were recurrent
- Runtime logs: queries and payment interfaces missing explicit support validation

## Root Cause
The router checks lead skill selection but not support-role completeness against domain-specific checklists.

## Proposed Change
- When SQL, EXPLAIN, index, slow query, or database tuning keywords appear, require database-engineer support
- When payment, authorization, auditing, throttling, or security review keywords appear, require security-engineer support
- Add support-role completeness as a soft gate before approval

## Risk
Low; this is a validation improvement rather than a semantic change to primary routing.

## Validation
- Run 5 benchmark cases spanning SQL optimization and secure API review
- Expect support-role completeness >90%
- Human review required before implementation

## Status
Reviewed
