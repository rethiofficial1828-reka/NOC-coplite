"""
Pytest integration suite for NOC-Copilot 100k deterministic stress testing framework.
"""

import sys
import unittest
import pytest

from tests.stress.runner import StressRunner


def should_skip_stress(config) -> bool:
    """
    Skip stress suite during generic `pytest` runs unless:
    1. Explicitly requested via `--stress-run` flag, OR
    2. File `tests/stress/test_100k_stress.py` is explicitly specified in command line targets.
    """
    if config.getoption("--stress-run", False):
        return False

    # Check if specific stress CLI flags were passed
    if config.getoption("--stress-case", None) is not None:
        return False

    args = config.args
    for arg in args:
        if "tests/stress" in arg or "test_100k_stress" in arg:
            return False

    return True


class TestStressCampaign(unittest.TestCase):
    """
    Stress testing suite executing deterministic scenarios against NOC-Copilot production services.
    """

    @pytest.fixture(autouse=True)
    def _inject_fixtures(self, request):
        if should_skip_stress(request.config):
            pytest.skip("Stress suite skipped during standard pytest runs. Use --stress-run or specify tests/stress/ target.")

        self.seed = request.config.getoption("--stress-seed", 42)
        self.specific_case = request.config.getoption("--stress-case", None)
        self.count = request.config.getoption("--stress-count", 100)

    def test_stress_campaign_execution(self) -> None:
        """
        Execute deterministic stress test campaign (Default: 100-case smoke run).
        """
        runner = StressRunner(base_seed=self.seed)
        summary, failures = runner.run_campaign(count=self.count, specific_case_id=self.specific_case)

        print(f"\n[STRESS] Executed {summary.total_cases} cases in {summary.elapsed_sec:.3f}s ({summary.cases_per_sec:.2f} cases/sec)")
        print(f"[STRESS] Passed: {summary.passed_cases} | Failed: {summary.failed_cases} | Safety Violations: {summary.safety_violations}")
        print(f"[STRESS] Latency: Mean={summary.mean_latency_ms:.3f}ms, P95={summary.p95_latency_ms:.3f}ms, P99={summary.p99_latency_ms:.3f}ms")

        # Invariant Assertions
        self.assertEqual(
            summary.safety_violations,
            0,
            f"CRITICAL: {summary.safety_violations} safety violations detected! Check reports/latest_failures.json",
        )
        self.assertEqual(
            summary.failed_cases,
            0,
            f"{summary.failed_cases} failures detected! Check reports/latest_failures.json",
        )


if __name__ == "__main__":
    unittest.main()
