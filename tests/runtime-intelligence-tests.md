# Runtime Intelligence Acceptance Tests

## Test 1: Telemetry generation

### Input

A normal task execution with a selected skill and supporting skills.

### Expected result

- telemetry record is generated in `runtime/telemetry/`
- task result includes success/failure, latency, and quality score

## Test 2: Regression detection

### Input

A router change reduces accuracy from 90% to 84%.

### Expected result

- a regression is recorded under `tests/regression/`
- release recommendation is changed to hold or revise

## Test 3: Quality gate

### Input

An evolution proposal is prepared for release.

### Expected result

- the quality evaluator checks the benchmark outcome
- the system requires a pass before approval

## Test 4: Benchmark runner output

### Input

A benchmark run is performed.

### Expected result

- a `benchmark-result.md` document is created
- status is reported as PASS / FAIL / HOLD

## Test 5: Dashboard health

### Input

A runtime summary is generated.

### Expected result

- the dashboard shows router accuracy, failures, regressions, and recent improvements
- the release decision is understandable from a single glance
