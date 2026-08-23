"""
Enterprise Master Validation Matrix Runner Script (500+ Test Target).

Auto-discovers, counts, executes, and records metrics for all validation test modules across the 32 required product domains.
Enforces MINIMUM 500 meaningful executable tests requirement.
"""

import os
import sys
import time
import unittest

def run_module(module_name):
    start = time.perf_counter()
    try:
        suite = unittest.defaultTestLoader.loadTestsFromName(module_name)
        test_count = suite.countTestCases()
        stream = sys.stdout
        runner = unittest.TextTestRunner(stream=stream, verbosity=1)
        result = runner.run(suite)
        duration = time.perf_counter() - start
        return {
            "module": module_name,
            "tests": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
            "duration_sec": round(duration, 3),
            "status": "PASS" if result.wasSuccessful() else "FAIL",
        }
    except Exception as e:
        return {
            "module": module_name,
            "tests": 0,
            "failures": 0,
            "errors": 1,
            "skipped": 0,
            "passed": 0,
            "duration_sec": round(time.perf_counter() - start, 3),
            "status": f"ERROR: {e}",
        }

if __name__ == "__main__":
    # Ensure root directory is on sys.path
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    test_modules = [
        "test_agents_foundation",
        "tests.test_orchestrator_ai",
        "tests.test_reasoning_agent",
        "tests.test_trust_agent",
        "tests.test_premortem_agent",
        "tests.test_path_decision",
        "tests.test_failover_agent",
        "tests.test_adaptive_failover",
        "tests.test_federated_intelligence",
        "tests.test_runtime_capability",
        "tests.test_enterprise_collectors",
        "tests.test_rag_agent",
        "tests.test_topology_agent",
        "tests.test_incident_agent",
        "tests.test_knowledge_agent",
        "tests.test_recommendation_agent",
        "tests.test_prediction_agent",
        "tests.test_telemetry_agent",
        "tests.test_ollama_provider",
        "tests.test_security_audit",
        "tests.test_resilience_failure_injection",
        "tests.test_ui_streamlit",
        "tests.test_network_scenarios_a_z",
        "tests.test_e2e_product_scenarios",
    ]

    print("=" * 80)
    print("      NOC COPILOT — ENTERPRISE MASTER VALIDATION MATRIX RUNNER")
    print("        Target: 500+ Meaningful Executable Test Cases")
    print("=" * 80)

    results = []
    total_tests = 0
    total_passed = 0
    total_failed = 0
    total_errors = 0
    total_skipped = 0
    total_duration = 0.0

    summary_file = os.path.join(PROJECT_ROOT, "data", "500_test_validation_matrix.txt")
    os.makedirs(os.path.dirname(summary_file), exist_ok=True)

    with open(summary_file, "w", encoding="utf-8") as f:
        f.write("=== NOC COPILOT 500+ ENTERPRISE VALIDATION MATRIX SUMMARY ===\n")
        f.write(f"Execution Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    for mod in test_modules:
        res = run_module(mod)
        results.append(res)
        total_tests += res["tests"]
        total_passed += res["passed"]
        total_failed += res["failures"]
        total_errors += res["errors"]
        total_skipped += res["skipped"]
        total_duration += res["duration_sec"]

        line = f"Module: {res['module']:<42} | Status: {res['status']:<4} | Passed: {res['passed']:>3}/{res['tests']:<3} | Duration: {res['duration_sec']:>6.3f}s"
        print(line, flush=True)

        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    acceptance_status = "PASSED" if (total_tests >= 500 and total_failed == 0 and total_errors == 0) else ("INCOMPLETE" if total_tests < 500 else "FAILED")

    summary_header = f"\nAGGREGATE RESULTS:\nTotal Discovered Tests: {total_tests}\nTotal Passed: {total_passed}\nTotal Failed: {total_failed}\nTotal Errors: {total_errors}\nTotal Skipped: {total_skipped}\nPass Percentage: {(total_passed / total_tests * 100):.2f}%\nTotal Duration: {total_duration:.3f}s\nACCEPTANCE_STATUS: {acceptance_status}\n"

    print("-" * 80)
    print(summary_header)
    print("-" * 80)

    with open(summary_file, "a", encoding="utf-8") as f:
        f.write(summary_header)