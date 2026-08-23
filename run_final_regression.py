#!/usr/bin/env python3
"""
NOC Copilot Final Regression Repair — Self-Contained Test Runner.
Runs all required test suites and writes results to data/final_regression_results.txt
"""
import io
import os
import sys
import time
import unittest

ROOT = '/home/kali/Downloads/NOC-coplite'
os.chdir(ROOT)
sys.path.insert(0, ROOT)

OUTPUT_FILE = os.path.join(ROOT, 'data', 'final_regression_results.txt')
os.makedirs(os.path.join(ROOT, 'data'), exist_ok=True)

results = []

SUITES = [
    'tests.test_matrix_10000',
    'tests.test_adaptive_failover',
    'tests.test_failover_agent',
    'tests.test_path_decision',
    'tests.test_federated_intelligence',
]

with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
    out.write('=' * 80 + '\n')
    out.write('NOC COPILOT — FINAL REGRESSION REPAIR RESULTS\n')
    out.write(f'Timestamp: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
    out.write('=' * 80 + '\n\n')

    total_tests = 0
    total_pass = 0
    total_fail = 0
    total_err = 0

    for suite_name in SUITES:
        out.write(f'\n{"=" * 60}\n')
        out.write(f'SUITE: {suite_name}\n')
        out.write(f'{"=" * 60}\n')

        buf = io.StringIO()
        t0 = time.perf_counter()
        try:
            loader = unittest.TestLoader()
            suite = loader.loadTestsFromName(suite_name)
            runner = unittest.TextTestRunner(stream=buf, verbosity=2)
            result = runner.run(suite)
            elapsed = time.perf_counter() - t0

            n_tests = result.testsRun
            n_fail = len(result.failures)
            n_err = len(result.errors)
            n_pass = n_tests - n_fail - n_err

            total_tests += n_tests
            total_pass += n_pass
            total_fail += n_fail
            total_err += n_err

            status = 'PASS' if result.wasSuccessful() else 'FAIL'
            out.write(buf.getvalue())
            out.write(f'\nSUMMARY: Ran={n_tests}, Pass={n_pass}, Fail={n_fail}, Err={n_err}, Status={status}, Time={elapsed:.2f}s\n')

            if result.failures:
                out.write('\n--- FAILURES ---\n')
                for test, tb in result.failures:
                    out.write(f'FAIL: {test}\n{tb}\n')
            if result.errors:
                out.write('\n--- ERRORS ---\n')
                for test, tb in result.errors[:5]:  # cap at 5 to avoid huge file
                    out.write(f'ERROR: {test}\n{tb}\n')
                if len(result.errors) > 5:
                    out.write(f'... and {len(result.errors) - 5} more errors\n')

        except Exception as ex:
            elapsed = time.perf_counter() - t0
            out.write(f'LOAD ERROR: {ex}\n')
            total_err += 1

    out.write('\n' + '=' * 80 + '\n')
    out.write('AGGREGATE SUMMARY\n')
    out.write(f'Total Tests:  {total_tests}\n')
    out.write(f'Total Passed: {total_pass}\n')
    out.write(f'Total Failed: {total_fail}\n')
    out.write(f'Total Errors: {total_err}\n')
    pct = (total_pass / total_tests * 100) if total_tests > 0 else 0.0
    out.write(f'Pass Rate:    {pct:.2f}%\n')
    out.write('=' * 80 + '\n')

print(f'Results written to {OUTPUT_FILE}')
