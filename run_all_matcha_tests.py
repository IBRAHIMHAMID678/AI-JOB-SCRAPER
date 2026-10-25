"""
Master Test Runner for Matcha Parity Upgrade.
Executes all validation suites to verify:
1. Strict 24h freshness temporal gate
2. ATS Harvester concurrency & canonical URL extraction
3. Structured metadata & salary extraction
4. Company intelligence enrichment
5. Database non-destructive integrity
6. Server endpoints & direct apply redirects
"""
import unittest
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from test_freshness import TestMatchaFreshness
from test_structurer import TestMatchaStructurer
from test_database import TestDatabaseParity
from test_server_endpoints import TestServerEndpoints

def run_suite():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestMatchaFreshness))
    suite.addTests(loader.loadTestsFromTestCase(TestMatchaStructurer))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseParity))
    suite.addTests(loader.loadTestsFromTestCase(TestServerEndpoints))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    print("MATCH PARITY VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"Total Tests Run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Status: {'ALL TESTS PASSED - PARITY VERIFIED' if result.wasSuccessful() else 'FAILED'}")
    print("=" * 60)

    if not result.wasSuccessful():
        sys.exit(1)

if __name__ == "__main__":
    run_suite()
