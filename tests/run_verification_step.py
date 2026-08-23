import unittest
import sys
import os

# Add workspace to path
sys.path.insert(0, '/home/kali/Downloads/NOC-coplite')

log_file = '/home/kali/Downloads/NOC-coplite/tests/verification_output.txt'

with open(log_file, 'w', encoding='utf-8') as out_f:
    out_f.write("Starting test execution...\n")
    
    import tests.test_path_decision
    import tests.test_failover_agent
    import tests.test_adaptive_failover
    import tests.test_federated_intelligence

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromModule(tests.test_path_decision))
    suite.addTests(loader.loadTestsFromModule(tests.test_failover_agent))
    suite.addTests(loader.loadTestsFromModule(tests.test_adaptive_failover))
    suite.addTests(loader.loadTestsFromModule(tests.test_federated_intelligence))

    runner = unittest.TextTestRunner(stream=out_f, verbosity=2)
    result = runner.run(suite)

    out_f.write(f"\nRESULTS: Total={result.testsRun}, Failures={len(result.failures)}, Errors={len(result.errors)}, WasSuccessful={result.wasSuccessful()}\n")
