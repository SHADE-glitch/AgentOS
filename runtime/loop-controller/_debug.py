import sys
sys.path.insert(0, ".")
from test_provider import TestProvider, register_test_provider
from runtime_adapter import execute_with_reliability
from execution_reliability import ReliabilityConfig

provider = TestProvider()
register_test_provider(provider)
provider.set_scenario("timeout")

config = ReliabilityConfig(
    base_timeout_seconds=5, max_retries=2, max_timeout_seconds=10,
    backoff_multiplier=1.2, max_consecutive_failures=3,
    enable_fallback=False, enable_early_termination=True,
    max_total_timeout_seconds=60,
)

result = execute_with_reliability(
    task_id="DEBUG-001", task_text="Test", decision_context={},
    provider="test_provider", model="test-model", reliability_config=config,
)

print("Status:", result["status"])
print("Calls:", provider.call_count)
rel = result.get("reliability", {})
summary = rel.get("summary", {})
print("Attempts:", summary.get("total_attempts"))
print("Retries:", summary.get("retries_performed"))
print("Final:", summary.get("final_status"))
print("Terminated:", summary.get("terminated_early"))
print("Reason:", summary.get("termination_reason"))