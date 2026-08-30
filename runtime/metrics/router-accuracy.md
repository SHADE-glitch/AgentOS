# Router Accuracy

This file stores the benchmark baseline and route quality progression.

## Purpose

The router is not considered reliable unless it is measured.

This file answers the question:

- How often is the router selecting the correct lead skill?
- What are the most common classes of route mistakes?
- Are supporting skills being omitted or overused?

## Template

```text
Benchmark:
Total Cases:
Correct Routing:
Wrong Routing:
Accuracy:
Main Errors:
Improvement:
```

## Current baseline

```text
Benchmark: Router Benchmark v1
Total Cases: 100+
Correct Routing: baseline pending
Wrong Routing: baseline pending
Accuracy: baseline pending
Main Errors: pending classification
Improvement: classify route failures and tune router priority rules
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

This file should be updated after every benchmark cycle.
