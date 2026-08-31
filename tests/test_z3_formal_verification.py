"""
Unit & Integration Test Suite for Sprint 22 / v1.5 Z3 Formal Verification Subsystem.

Covers:
1. Formal verification of valid candidate plans yielding SAT
2. Rejection of invalid/unregistered providers yielding UNSAT
3. Rejection of invalid next-hop IPs
4. Cooldown period enforcement
5. Anti-flap hourly rate enforcement
6. Blast radius upper bound enforcement
7. Simulated-provider physical execution prohibition
8. PRODUCTION_AUTHORIZED == False hard gate enforcement
9. Deterministic fallback solver verification
10. Counterexample formulation for UNSAT results
"""

import unittest

from agents.z3_verifier.z3_models import (
    Z3VerificationRequest,
    Z3VerificationResult,
    Z3VerificationStatus,
)
from agents.z3_verifier.z3_verifier import Z3FormalVerifier


class TestZ3FormalVerification(unittest.TestCase):
    """Test suite for Z3FormalVerifier and formal invariant satisfaction."""

    def setUp(self) -> None:
        self.verifier = Z3FormalVerifier()
        self.fallback_verifier = Z3FormalVerifier(force_fallback=True)

    def test_01_valid_plan_yields_sat(self) -> None:
        """Verify standard safe failover candidate plan is formally verified SAT."""
        req = Z3VerificationRequest(
            source_provider="ISP-A",
            target_provider="ISP-B",
            target_device="branch3-uplink",
            wan_interface="Branch3-Uplink",
            next_hop="10.10.2.1",
            execution_mode="DRY_RUN",
            predicted_blast_radius_pct=15.0,
            time_since_last_transition_sec=120.0,
            transitions_last_hour=1,
            routes=[{"prefix": "0.0.0.0/0", "distance": 20}],
        )
        res = self.verifier.verify_plan(req)
        self.assertEqual(res.status, Z3VerificationStatus.SAT)
        self.assertTrue(res.is_safe)
        self.assertEqual(len(res.violated_invariants), 0)
        self.assertGreaterEqual(len(res.passed_invariants), 10)
        self.assertIn("SAT", res.proof_summary)

    def test_02_unregistered_provider_yields_unsat(self) -> None:
        """Verify unregistered provider violates INV-01 and yields UNSAT."""
        req = Z3VerificationRequest(
            source_provider="ISP-A",
            target_provider="ISP-ROGUE-99",
            target_device="branch3-uplink",
            wan_interface="Branch3-Uplink",
            next_hop="192.168.99.1",
            execution_mode="DRY_RUN",
        )
        res = self.verifier.verify_plan(req)
        self.assertEqual(res.status, Z3VerificationStatus.UNSAT)
        self.assertFalse(res.is_safe)
        self.assertIn("PROVIDER_EXISTS", res.violated_invariants)
        self.assertIsNotNone(res.counterexample)

    def test_03_invalid_next_hop_yields_unsat(self) -> None:
        """Verify loopback or malformed next-hop IP violates INV-04 and yields UNSAT."""
        req = Z3VerificationRequest(
            source_provider="ISP-A",
            target_provider="ISP-B",
            target_device="branch3-uplink",
            wan_interface="Branch3-Uplink",
            next_hop="127.0.0.1",  # Invalid loopback next-hop
            execution_mode="DRY_RUN",
        )
        res = self.verifier.verify_plan(req)
        self.assertEqual(res.status, Z3VerificationStatus.UNSAT)
        self.assertIn("NEXT_HOP_VALID", res.violated_invariants)

    def test_04_cooldown_violation_yields_unsat(self) -> None:
        """Verify insufficient cooldown violates INV-08 and yields UNSAT."""
        req = Z3VerificationRequest(
            source_provider="ISP-A",
            target_provider="ISP-B",
            target_device="branch3-uplink",
            wan_interface="Branch3-Uplink",
            next_hop="10.10.2.1",
            time_since_last_transition_sec=15.0,  # < 60s
            execution_mode="DRY_RUN",
        )
        res = self.verifier.verify_plan(req)
        self.assertEqual(res.status, Z3VerificationStatus.UNSAT)
        self.assertIn("COOLDOWN_SATISFIED", res.violated_invariants)

    def test_05_anti_flap_violation_yields_unsat(self) -> None:
        """Verify excessive hourly transitions violates INV-09 and yields UNSAT."""
        req = Z3VerificationRequest(
            source_provider="ISP-A",
            target_provider="ISP-B",
            target_device="branch3-uplink",
            wan_interface="Branch3-Uplink",
            next_hop="10.10.2.1",
            transitions_last_hour=8,  # > 4
            execution_mode="DRY_RUN",
        )
        res = self.verifier.verify_plan(req)
        self.assertEqual(res.status, Z3VerificationStatus.UNSAT)
        self.assertIn("ANTI_FLAP_STABILITY", res.violated_invariants)

    def test_06_blast_radius_overflow_yields_unsat(self) -> None:
        """Verify excessive blast radius violates INV-10 and yields UNSAT."""
        req = Z3VerificationRequest(
            source_provider="ISP-A",
            target_provider="ISP-B",
            target_device="branch3-uplink",
            wan_interface="Branch3-Uplink",
            next_hop="10.10.2.1",
            predicted_blast_radius_pct=75.0,  # > 40.0%
            execution_mode="DRY_RUN",
        )
        res = self.verifier.verify_plan(req)
        self.assertEqual(res.status, Z3VerificationStatus.UNSAT)
        self.assertIn("BLAST_RADIUS_BOUNDED", res.violated_invariants)

    def test_07_simulated_provider_in_physical_mode_yields_unsat(self) -> None:
        """Verify attempting physical mutation on simulated provider violates INV-12."""
        req = Z3VerificationRequest(
            source_provider="ISP-A",
            target_provider="ISP-C",  # Simulated
            target_device="branch3-uplink",
            wan_interface="Branch3-Cellular",
            next_hop="10.10.3.1",
            is_simulated=True,
            execution_mode="APPROVED_EXECUTION",  # Physical execution attempt
        )
        res = self.verifier.verify_plan(req)
        self.assertEqual(res.status, Z3VerificationStatus.UNSAT)
        self.assertIn("SIMULATED_PROVIDER_BOUNDARY", res.violated_invariants)

    def test_08_production_mode_hard_gate(self) -> None:
        """Verify unapproved production mode attempt violates INV-11."""
        req = Z3VerificationRequest(
            source_provider="ISP-A",
            target_provider="ISP-B",
            target_device="branch3-uplink",
            wan_interface="Branch3-Uplink",
            next_hop="10.10.2.1",
            execution_mode="PRODUCTION_AUTHORIZED",  # Prohibited
        )
        res = self.verifier.verify_plan(req)
        self.assertEqual(res.status, Z3VerificationStatus.UNSAT)
        self.assertIn("PRODUCTION_HARD_GATE", res.violated_invariants)

    def test_09_deterministic_fallback_solver(self) -> None:
        """Verify deterministic fallback solver produces equivalent valid proof."""
        req = Z3VerificationRequest(
            source_provider="ISP-A",
            target_provider="ISP-D",
            target_device="branch3-uplink",
            wan_interface="Branch3-Satellite",
            next_hop="10.10.4.1",
            is_simulated=True,
            execution_mode="DRY_RUN",
            predicted_blast_radius_pct=10.0,
            time_since_last_transition_sec=300.0,
            transitions_last_hour=0,
        )
        res = self.fallback_verifier.verify_plan(req)
        self.assertEqual(res.status, Z3VerificationStatus.SAT)
        self.assertEqual(res.solver_type, "deterministic_fallback")


if __name__ == "__main__":
    unittest.main()
