"""
Validation Test Suite Execution Script for NOC Copilot Product Validation 2.0 (Post Sprint 18).

Executes all test modules and logs exact test counts, pass/fail/skip totals, and execution durations.
"""

import os
import sys
import time
import unittest

def run_suite(module_name):
    start = time.perf_counter()
    try:
        suite = unittest.defaultTestLoader.loadTestsFromName(module_name)
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
    modules = [
        "test_agents_foundation",
        "tests.test_orchestrator_ai",
        "tests.test_reasoning_agent",
        "tests.test_trust_agent",
        "tests.test_premortem_agent",
        "tests.test_path_decision",
        "tests.test_failover_agent",
        "tests.test_runtime_capability",
    ]
    
    results = []
    total_tests = 0
    total_passed = 0
    total_failed = 0
    total_errors = 0
    total_skipped = 0
    total_duration = 0.0

    print("============================================================")
    print("NOC COPILOT POST-SPRINT 18 FULL VALIDATION TEST SUITE RUNNER")
    print("============================================================")

    for mod in modules:
        res = run_suite(mod)
        results.append(res)
        total_tests += res["tests"]
        total_passed += res["passed"]
        total_failed += res["failures"]
        total_errors += res["errors"]
        total_skipped += res["skipped"]
        total_duration += res["duration_sec"]
        print(f"Module: {res['module']} | Status: {res['status']} | Passed: {res['passed']}/{res['tests']} | Duration: {res['duration_sec']}s")

    summary_file = "data/validation_test_summary.txt"
    os.makedirs("data", exist_ok=True)
    with open(summary_file, "w") as f:
        f.write("=== NOC COPILOT TEST SUITE RUNNER ===\n")

    for mod in modules:
        res = run_suite(mod)
        results.append(res)
        total_tests += res["tests"]
        total_passed += res["passed"]
        total_failed += res["failures"]
        total_errors += res["errors"]
        total_skipped += res["skipped"]
        total_duration += res["duration_sec"]
        
        with open(summary_file, "a") as f:
            f.write(f"{res['module']}: {res['status']} ({res['passed']}/{res['tests']} passed, {res['duration_sec']}s)\n")
        print(f"Module: {res['module']} | Status: {res['status']} | Passed: {res['passed']}/{res['tests']} | Duration: {res['duration_sec']}s", flush=True)

    with open(summary_file, "a") as f:
        f.write(f"\nTOTAL: {total_passed}/{total_tests} PASSED ({total_failed} fail, {total_errors} err, {total_skipped} skip) in {total_duration:.3f}s\n")

    print("============================================================")
    print(f"SUMMARY: {total_passed}/{total_tests} PASSED in {total_duration:.3f}s")
    print("============================================================")
