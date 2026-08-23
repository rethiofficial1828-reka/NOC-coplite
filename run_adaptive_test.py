#!/usr/bin/env python3
import sys, os, unittest, io

os.chdir('/home/kali/Downloads/NOC-coplite')
sys.path.insert(0, '/home/kali/Downloads/NOC-coplite')

buf = io.StringIO()

import tests.test_adaptive_failover
loader = unittest.TestLoader()
suite = loader.loadTestsFromModule(tests.test_adaptive_failover)
runner = unittest.TextTestRunner(stream=buf, verbosity=2)
result = runner.run(suite)

output = buf.getvalue()

with open('/home/kali/Downloads/NOC-coplite/adaptive_test_result.txt', 'w') as f:
    f.write(output)
    f.write(f'\n\nRAN: {result.testsRun}  FAILURES: {len(result.failures)}  ERRORS: {len(result.errors)}\n')
    if result.failures:
        f.write('\n=== FAILURES ===\n')
        for test, tb in result.failures:
            f.write(f'FAIL: {test}\n{tb}\n')
    if result.errors:
        f.write('\n=== ERRORS ===\n')
        for test, tb in result.errors:
            f.write(f'ERROR: {test}\n{tb}\n')
