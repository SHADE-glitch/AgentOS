# Router Accuracy

This file stores the benchmark baseline and route quality progression.

## Purpose

The router is not considered reliable unless it is measured.

This file answers the question:

- How often is the router selecting the correct lead skill?
- What are the most common classes of route mistakes?
- Are supporting skills being omitted or overused?

## Current baseline

```text
Benchmark: Router Benchmark v1.1
Total Cases: 58
Correct Routing: 53
Wrong Routing: 5
Accuracy: 91.4%
Main Errors: Wrong lead skill in RAG and distributed-system tasks; missing support skill in SQL and API tasks
Improvement: tightened router priority rules for retrieval/vector terms, distributed consistency wording, and cache/index terminology
```

## Evaluation rule

The first goal is not to be perfect.
The first goal is to be honest and measurable.

Each benchmark pass must classify:

- correct routing
- wrong lead skill
- missing support skill
- skill boundary conflict
- fallback failure

This file is updated only after benchmark evidence is recorded, not simply after a calendar interval.
