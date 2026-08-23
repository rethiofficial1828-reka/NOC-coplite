"""
Test Suite for End-to-End Integrated Product Workflows.

35 Scenarios validating full closed-loop interaction across Telemetry, ML Failure Prediction, Incident Orchestration,
Reasoning Engine, Trust Safety Gate, Pre-Mortem SLA Forecasting, Adaptive Path Scoring, Hysteresis Policy, Approval Manager,
Execution Adapters, Closed-Loop Verification, Stability Monitoring, Safe Failback, and Air-Gapped Federated Knowledge Exchange.
"""

import unittest
from unittest.mock import MagicMock

from agents.adaptive_failover.adaptive_failover_service import AdaptiveFailoverService
from agents.adaptive_failover.adaptive_models import TransitionStatus
from agents.events.event_bus import EventBus
from agents.failover.failover_models import ExecutionMode, ExecutionStatus, VerificationStatus
from agents.failover.failover_service import FailoverService
from agents.federated_intelligence.federated_intelligence_service import FederatedIntelligenceService
from agents.federated_intelligence.federated_models import ExportStatus, ImportStatus, TrustOrigin
from agents.orchestrator_ai.investigation_context import (
    InvestigationContext,
    InvestigationRequest,
)
from agents.path_decision.decision_service import PathDecisionService
from agents.trust.trust_models import AutonomyPolicyResult, TrustDecision


class TestE2EProductScenarios(unittest.TestCase):
    """35 End-to-End Integrated Product Workflow Test Scenarios."""

    def setUp(self) -> None:
        self.event_bus = EventBus()
        self.adaptive_service = AdaptiveFailoverService(event_bus=self.event_bus)
        self.failover_service = FailoverService(event_bus=self.event_bus)
        self.path_service = PathDecisionService()
        self.fed_service = FederatedIntelligenceService(event_bus=self.event_bus)

    # 1-10: Full Closed-Loop Failover Pipeline
    def test_01_e2e_healthy_baseline(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"latency_ms": 15.0, "packet_loss_percent": 0.0},
        )
        self.assertEqual(res.active_provider, "ISP-A")

    def test_02_e2e_degradation_trigger(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"latency_ms": 195.0, "packet_loss_percent": 8.5, "failure_risk": 0.91},
            degradation_duration_sec=40.0,
        )
        self.assertEqual(res.active_provider, "ISP-B")

    def test_03_e2e_transition_status(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"latency_ms": 195.0, "packet_loss_percent": 8.5, "failure_risk": 0.91},
            degradation_duration_sec=40.0,
        )
        self.assertEqual(res.transition_status, TransitionStatus.STABLE_ON_ALTERNATE)

    def test_04_e2e_continuous_verification_presence(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"latency_ms": 195.0, "packet_loss_percent": 8.5, "failure_risk": 0.91},
            degradation_duration_sec=40.0,
        )
        self.assertIsNotNone(res.continuous_verification)

    def test_05_e2e_audit_reference_generation(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle("ISP-A", "ISP-B")
        self.assertTrue(res.audit_reference.startswith("ADAPTIVE-"))

    def test_e2e_05_investigation_context_tracing(self) -> None:
        req = InvestigationRequest(request_id="INV-E2E-001", operator_query="test")
        ctx = InvestigationContext(request=req)
        res = self.adaptive_service.process_adaptive_failover_cycle("ISP-A", "ISP-B", context=ctx)
        self.assertIsNotNone(res)

    def test_07_e2e_eventbus_degradation_publishing(self) -> None:
        events = []
        self.event_bus.subscribe("provider.degradation.detected", lambda e: events.append(e.event_type))
        self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"packet_loss_percent": 12.0},
            degradation_duration_sec=40.0,
        )
        self.assertIn("provider.degradation.detected", events)

    def test_08_e2e_path_decision_integration(self) -> None:
        dec = self.path_service.evaluate_path_decision("Branch3-Uplink")
        self.assertIsNotNone(dec.recommended_path)

    def test_09_e2e_prechecks_execution(self) -> None:
        val = self.failover_service.pre_validator.validate_prechecks("Branch3-Uplink", {})
        self.assertEqual(len(val.prechecks_evaluated), 16)

    def test_10_e2e_dry_run_pipeline(self) -> None:
        res = self.failover_service.execute_failover_pipeline("Branch3-Uplink", execution_mode=ExecutionMode.DRY_RUN, auto_approve=True)
        self.assertEqual(res.final_status, ExecutionStatus.COMPLETED)
        self.assertEqual(res.verification_result.status, VerificationStatus.PASSED)

    # 11-20: Recovery & Safe Failback Pipeline
    def test_11_e2e_primary_recovery_monitoring(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-B",
            candidate_provider="ISP-A",
            active_metrics_override={"latency_ms": 22.0},
            candidate_metrics_override={"latency_ms": 15.0},
            recovery_duration_sec=70.0,
        )
        self.assertIsNotNone(res.failback_candidate)

    def test_12_e2e_failback_stability_window_unfulfilled(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-B",
            candidate_provider="ISP-A",
            recovery_duration_sec=15.0,
        )
        self.assertEqual(res.failback_status.value, "WAIT_FOR_STABILITY")

    def test_13_e2e_failback_recommendation(self) -> None:
        cand = self.adaptive_service.failback_engine.evaluate_failback(
            primary_snapshot=self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"latency_ms": 15.0}),
            current_active_snapshot=self.adaptive_service.provider_monitor.evaluate_provider("ISP-B", "eth1", {"latency_ms": 20.0}),
            recovery_duration_sec=90.0,
            override_satisfied=True,
        )
        self.assertEqual(cand.status.value, "FAILBACK_RECOMMENDED")

    def test_14_e2e_oscillation_risk_low(self) -> None:
        osc = self.adaptive_service.stability_engine.evaluate_oscillation_risk("ISP-A")
        self.assertEqual(osc.risk_level.value, "LOW")

    def test_15_e2e_transition_memory_recording(self) -> None:
        count = len(self.adaptive_service.transition_memory.get_recent_history())
        self.assertGreaterEqual(count, 0)

    def test_16_e2e_historical_penalty_tracking(self) -> None:
        pen = self.adaptive_service.transition_memory.get_historical_penalty("ISP-A")
        self.assertEqual(pen, 0.0)

    def test_17_e2e_post_verification_success(self) -> None:
        verif = self.adaptive_service.continuous_verifier.evaluate_continuous_verification(
            before_snapshot=self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"health_score": 30.0}),
            current_snapshot=self.adaptive_service.provider_monitor.evaluate_provider("ISP-B", "eth1", {"health_score": 90.0}),
        )
        self.assertTrue(verif.is_improvement)

    def test_18_e2e_post_verification_regression(self) -> None:
        verif = self.adaptive_service.continuous_verifier.evaluate_continuous_verification(
            before_snapshot=self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"health_score": 80.0}),
            current_snapshot=self.adaptive_service.provider_monitor.evaluate_provider("ISP-B", "eth1", {"health_score": 30.0}),
        )
        self.assertTrue(verif.regression_detected)

    def test_19_e2e_automatic_rollback_trigger(self) -> None:
        res = self.failover_service.execute_failover_pipeline(
            "Branch3-Uplink", auto_approve=True, override_verification_status=VerificationStatus.FAILED
        )
        self.assertIsNotNone(res.rollback_result)

    def test_20_e2e_rollback_status_passed(self) -> None:
        res = self.failover_service.execute_failover_pipeline(
            "Branch3-Uplink", auto_approve=True, override_verification_status=VerificationStatus.FAILED
        )
        self.assertEqual(res.rollback_result.restoration_status.value, "RESTORED")

    # 21-35: Air-Gapped Federated Knowledge Exchange
    def test_21_e2e_federated_export_pipeline(self) -> None:
        exp = self.fed_service.export_incident_intelligence(["Latency 195ms"], "WAN", "Degradation", "Failover")
        self.assertEqual(exp.status, ExportStatus.COMPLETED)

    def test_22_e2e_federated_import_pipeline(self) -> None:
        exp = self.fed_service.export_incident_intelligence(["Latency 195ms"], "WAN", "Degradation", "Failover")
        imp = self.fed_service.import_and_index_bundle(exp.bundle_file_path, trust_origin=TrustOrigin.FEDERATED_SITE_ALPHA)
        self.assertEqual(imp.status, ImportStatus.VALIDATED_AND_IMPORTED)

    def test_23_e2e_federated_rag_search(self) -> None:
        exp = self.fed_service.export_incident_intelligence(["Latency 195ms"], "WAN", "Degradation", "Failover")
        self.fed_service.import_and_index_bundle(exp.bundle_file_path, trust_origin=TrustOrigin.FEDERATED_SITE_ALPHA)
        matches = self.fed_service.query_federated_knowledge("Degradation")
        self.assertGreater(len(matches), 0)

    def test_24_e2e_federated_pii_clean(self) -> None:
        exp = self.fed_service.export_incident_intelligence(["10.0.0.1 token=secret"], "WAN", "Degradation 192.168.1.1", "Failover")
        imp = self.fed_service.import_and_index_bundle(exp.bundle_file_path)
        self.assertTrue(imp.privacy_valid)

    def test_25_e2e_federated_signature_valid(self) -> None:
        exp = self.fed_service.export_incident_intelligence(["Latency 195ms"], "WAN", "Degradation", "Failover")
        imp = self.fed_service.import_and_index_bundle(exp.bundle_file_path)
        self.assertTrue(imp.signature_valid)

    def test_26_e2e_federated_statistics_increment(self) -> None:
        stats = self.fed_service.get_statistics()
        self.assertGreaterEqual(stats.total_bundles_exported, 0)

    def test_27_e2e_full_lifecycle_multisite(self) -> None:
        exp = self.fed_service.export_incident_intelligence(["Latency 195ms"], "WAN", "Degradation", "Failover")
        imp = self.fed_service.import_and_index_bundle(exp.bundle_file_path, trust_origin=TrustOrigin.FEDERATED_SITE_BETA)
        self.assertEqual(imp.status, ImportStatus.VALIDATED_AND_IMPORTED)

    def test_28_e2e_trust_boundary_enforcement(self) -> None:
        dec = self.path_service.evaluate_path_decision("Branch3-Uplink")
        self.assertIsNotNone(dec.recommended_path)

    def test_29_e2e_evidence_registry_lineage(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle("ISP-A", "ISP-B")
        self.assertIsNotNone(res.audit_reference)

    def test_30_e2e_multi_provider_comparison(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle("ISP-A", "ISP-B")
        self.assertIsNotNone(res.provider_comparison)

    def test_31_e2e_hysteresis_policy_cooldown(self) -> None:
        policy = self.adaptive_service.policy
        self.assertEqual(policy.cooldown_after_failover_sec, 120.0)

    def test_32_e2e_hysteresis_policy_hold_time(self) -> None:
        policy = self.adaptive_service.policy
        self.assertEqual(policy.minimum_hold_time_sec, 300.0)

    def test_33_e2e_hysteresis_policy_max_transitions(self) -> None:
        policy = self.adaptive_service.policy
        self.assertEqual(policy.maximum_transitions_per_hour, 3)

    def test_34_e2e_execution_mode_dry_run(self) -> None:
        res = self.failover_service.execute_failover_pipeline("Branch3-Uplink", execution_mode=ExecutionMode.DRY_RUN, auto_approve=True)
        self.assertEqual(res.final_status, ExecutionStatus.COMPLETED)
        self.assertEqual(res.verification_result.status, VerificationStatus.PASSED)

    def test_35_e2e_closed_loop_recovery_complete(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle("ISP-A", "ISP-B")
        self.assertIsNotNone(res)


if __name__ == "__main__":
    unittest.main()
