"""
Test Runner Script for Sprint 18 Failover Agent Tests.
"""

import sys
import unittest

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(start_dir="tests", pattern="test_failover_agent.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    with open("test_results_sprint18.txt", "w") as f:
        f.write(f"Tests run: {result.testsRun}\n")
        f.write(f"Errors: {len(result.errors)}\n")
        f.write(f"Failures: {len(result.failures)}\n")
        f.write(f"Was successful: {result.wasSuccessful()}\n")
        for err in result.errors:
            f.write(f"ERROR: {err[0]}\n{err[1]}\n")
        for fail in result.failures:
            f.write(f"FAILURE: {fail[0]}\n{fail[1]}\n")
    if not result.wasSuccessful():
        sys.exit(1)
