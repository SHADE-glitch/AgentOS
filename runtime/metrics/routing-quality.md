# Routing Quality

## Goal

Measure whether the router chooses the correct lead skill and supporting skills.

## Current baseline

```text
Benchmark: router benchmark v1.4
Total Cases: 58
Correct Routes: 53
Wrong Lead Routes: 3
Missing Support Routes: 2
Accuracy: 91.4%
Precision: 89.7%
Recall: 93.1%
Regression Status: no critical regression observed in the validated sample
```

## Interpretation

- The router is evidence-based and operationally stable above the 85% readiness threshold.
- Most errors remain in domain terminology mismatches rather than total system failure.
- The support-skill gap is contained and should be addressed through explicit skill mapping rules.
