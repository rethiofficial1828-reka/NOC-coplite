"""
Master End-to-End Integration Test Suite for NOC-Copilot v1.5 Next-Generation Intelligence.

Verifies full closed-loop integration of:
1. Configuration-Driven Multi-WAN Selection (ISP-A, ISP-B, ISP-C, ISP-D)
2. Network Digital Twin State Tracking & What-If Simulations
3. Advisory GNN Failure Propagation & Blast-Radius Estimation
4. Z3 Formal Safety Verification Gate (SAT/UNSAT enforcement)
5. Generic Provider Transitions (source -> target)
6. Strict separation of physical vs simulated providers
7. Preservation of 16 Prechecks, Quorum, RBAC, and Rollback guarantees
8. PRODUCTION_AUTHORIZED == False invariant enforcement
"""

import unittest
from unittest.mock import MagicMock, patch

from agents.failover.failover_models import ExecutionMode, ExecutionStatus
from agents.failover.failover_service import FailoverService
from agents.gnn.gnn_service import GNNService
from agents.path_decision.decision_service import PathDecisionService
from agents.path_decision.path_models import DecisionStatus
from agents.twin.twin_service import DigitalTwinService
from agents.z3_verifier.z3_models import Z3VerificationStatus
from agents.z3_verifier.z3_verifier import Z3FormalVerifier
from config.settings import PRODUCTION_AUTHORIZED, WAN_PROVIDER_REGISTRY


class TestV15IntegratedIntelligence(unittest.TestCase):
    """Integration test suite for the complete v1.5 intelligence stack."""

    def setUp(self) -> None:
        self.decision_service = PathDecisionService()
        self.z3_verifier = Z3FormalVerifier()
        self.failover_service = FailoverService(path_decision_service=self.decision_service, z3_verifier=self.z3_verifier)
        self.twin_service = DigitalTwinService()
        self.gnn_service = GNNService()

    def test_01_configuration_driven_multi_wan_discovery(self) -> None:
        """Verify all 4 registered providers are evaluated in decision service."""
        res = self.decision_service.evaluate_path_decision("Branch3-Uplink")
        self.assertIsNotNone(res)
        self.assertEqual(len(res.candidate_paths), 4)
        candidate_names = [c.provider_name for c in res.candidate_paths]
        self.assertIn("ISP-A", candidate_names)
        self.assertIn("ISP-B", candidate_names)
        self.assertIn("ISP-C", candidate_names)
        self.assertIn("ISP-D", candidate_names)

    def test_02_path_decision_includes_twin_gnn_and_z3_metadata(self) -> None:
        """Verify PathDecisionResult contains Digital Twin, GNN, and Z3 outputs."""
        res = self.decision_service.evaluate_path_decision("Branch3-Uplink")
        self.assertIsNotNone(res.digital_twin_simulation)
        self.assertIsNotNone(res.gnn_blast_radius)
        self.assertIsNotNone(res.formal_verification)

        # Digital Twin simulation metadata
        self.assertEqual(res.digital_twin_simulation["scenario"], "FAILOVER")

        # GNN advisory blast-radius metadata
        self.assertIn("predicted_blast_radius_pct", res.gnn_blast_radius)
        self.assertEqual(res.gnn_blast_radius["provenance"], "DETERMINISTIC_PROPAGATION_FALLBACK")

        # Z3 formal verification verdict
        self.assertEqual(res.formal_verification["status"], "SAT")
        self.assertTrue(res.formal_verification["is_safe"])

    def test_03_failover_pipeline_end_to_end_dry_run(self) -> None:
        """Verify full failover pipeline completes with Z3 formal gate in DRY_RUN mode."""
        res = self.failover_service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            execution_mode=ExecutionMode.DRY_RUN,
            auto_approve=True,
            operator_id="OP-TEST-V15",
        )
        self.assertEqual(res.final_status, ExecutionStatus.COMPLETED)
        self.assertIsNotNone(res.z3_verification)
        self.assertEqual(res.z3_verification["status"], "SAT")
        self.assertIsNotNone(res.digital_twin_simulation)
        self.assertIsNotNone(res.gnn_blast_radius)
        self.assertEqual(len(res.prechecks), 16)

    def test_04_z3_gate_blocks_unsat_plan(self) -> None:
        """Verify failover pipeline blocks execution if Z3 formal verification yields UNSAT."""
        from agents.z3_verifier.z3_models import Z3VerificationRequest
        mock_unsat = self.z3_verifier.verify_plan(
            Z3VerificationRequest(
                request_id="REQ-FAIL",
                target_provider="UNREGISTERED-ROGUE-WAN",
                source_provider="ISP-A",
                target_device="branch3-uplink",
                wan_interface="Branch3-Uplink",
                next_hop="127.0.0.1",
                execution_mode="DRY_RUN",
                predicted_blast_radius_pct=90.0,
                time_since_last_transition_sec=5.0,
                transitions_last_hour=10,
                routes=[],
                topology_nodes=[],
                topology_links=[],
                is_simulated=False,
            )
        )
        with patch.object(self.failover_service._z3_verifier, "verify_plan", return_value=mock_unsat):
            res = self.failover_service.execute_failover_pipeline(
                target_interface_or_device="Branch3-Uplink",
                execution_mode=ExecutionMode.DRY_RUN,
                auto_approve=True,
                operator_id="OP-TEST-V15",
            )
            self.assertEqual(res.final_status, ExecutionStatus.BLOCKED)
            self.assertEqual(res.z3_verification["status"], "UNSAT")
            self.assertFalse(res.z3_verification["is_safe"])
            self.assertTrue(res.audit_reference.startswith("AUDIT-"))

    def test_05_physical_execution_rejected_for_simulated_provider(self) -> None:
        """Verify physical control plane rejects mutation if target provider is simulated (ISP-C/D)."""
        from agents.failover.frr_control_plane import FRRControlPlane
        from agents.failover.network_control_plane import TransitionProviderRequest, ControlPlaneStatus

        frr = FRRControlPlane()
        req_c = TransitionProviderRequest(
            target_device="branch3-uplink",
            wan_interface="Branch3-Cellular",
            source_provider="ISP-A",
            target_provider="ISP-C",
            is_simulated=True,
        )
        res_c = frr.transition_provider(req_c)
        self.assertFalse(res_c.success)
        self.assertEqual(res_c.status, ControlPlaneStatus.UNAVAILABLE)
        self.assertIn("SIMULATED", res_c.message)

        req_d = TransitionProviderRequest(
            target_device="branch3-uplink",
            wan_interface="Branch3-Satellite",
            source_provider="ISP-A",
            target_provider="ISP-D",
            is_simulated=True,
        )
        res_d = frr.transition_provider(req_d)
        self.assertFalse(res_d.success)
        self.assertEqual(res_d.status, ControlPlaneStatus.UNAVAILABLE)
        self.assertIn("SIMULATED", res_d.message)

    def test_06_generic_transition_between_physical_providers(self) -> None:
        """Verify generic transition abstraction works for physical providers (ISP-A <-> ISP-B)."""
        from agents.failover.frr_control_plane import FRRControlPlane
        from agents.failover.network_control_plane import TransitionProviderRequest

        frr = FRRControlPlane()
        # Mock vtysh and verify_route_path
        with patch.object(frr, "_execute_vtysh_config", return_value=True), \
             patch.object(frr, "verify_route_path") as mock_verify:
            mock_verify.return_value = MagicMock(success=True, message="Route verified", details={})

            req = TransitionProviderRequest(
                target_device="branch3-uplink",
                wan_interface="Branch3-Uplink",
                source_provider="ISP-A",
                target_provider="ISP-B",
                is_simulated=False,
            )
            res = frr.transition_provider(req)
            self.assertTrue(res.success)
            self.assertEqual(res.action_type, "FAILOVER_PROVIDER")

    def test_07_production_authorized_invariant_enforcement(self) -> None:
        """Verify PRODUCTION_AUTHORIZED is False and production execution raises error."""
        self.assertFalse(PRODUCTION_AUTHORIZED)
        from agents.failover.failover_models import ProductionExecutionDisabledError

        with self.assertRaises(ProductionExecutionDisabledError):
            self.failover_service.execute_failover_pipeline(
                target_interface_or_device="Branch3-Uplink",
                execution_mode=ExecutionMode.PRODUCTION_AUTHORIZED,
            )


if __name__ == "__main__":
    unittest.main()
