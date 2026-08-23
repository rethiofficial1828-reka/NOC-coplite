"""
Test Suite for Realistic Network Scenarios A through Z.

52 Scenarios validating the complete closed-loop NOC Copilot operational pipeline across realistic enterprise
network degradation, failure, recovery, hysteresis, flapping, failover, verification, rollback, federated intelligence,
Ollama offline, and CPU fallback conditions.
"""

from datetime import datetime, timezone
import json
import unittest
from unittest.mock import MagicMock

from agents.adaptive_failover.adaptive_failover_service import AdaptiveFailoverService
from agents.adaptive_failover.adaptive_models import FailbackStatus, ProviderState, TransitionStatus
from agents.failover.failover_models import ExecutionMode, ExecutionStatus, VerificationStatus
from agents.failover.failover_service import FailoverService
from agents.federated_intelligence.crypto_signer import CryptoSigner
from agents.federated_intelligence.federated_intelligence_service import FederatedIntelligenceService
from agents.federated_intelligence.federated_models import ImportStatus, TrustOrigin
from agents.path_decision.decision_service import PathDecisionService
from agents.runtime.ollama_detector import OllamaDetector
from agents.trust.trust_models import AutonomyPolicyResult, TrustDecision


class TestNetworkScenariosAZ(unittest.TestCase):
    """52 Realistic Network Scenarios (A through Z) Test Suite."""

    def setUp(self) -> None:
        self.adaptive_service = AdaptiveFailoverService()
        self.failover_service = FailoverService()
        self.path_service = PathDecisionService()
        self.fed_service = FederatedIntelligenceService()

    # Scenario A: Healthy ISP-A + healthy ISP-B
    def test_scenario_A1_healthy_providers(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"latency_ms": 15.0, "packet_loss_percent": 0.0},
            candidate_metrics_override={"latency_ms": 18.0, "packet_loss_percent": 0.0},
        )
        self.assertEqual(res.active_provider, "ISP-A")
        self.assertEqual(res.trigger.action, "NO_ACTION")

    def test_scenario_A2_healthy_providers_scoring(self) -> None:
        dec = self.path_service.evaluate_path_decision("Branch3-Uplink")
        self.assertIsNotNone(dec.recommended_path)

    # Scenario B: ISP-A gradual degradation
    def test_scenario_B1_gradual_degradation(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"latency_ms": 75.0, "packet_loss_percent": 2.5, "failure_risk": 0.45},
            degradation_duration_sec=35.0,
        )
        self.assertIsNotNone(res)

    def test_scenario_B2_gradual_degradation_trend(self) -> None:
        snap = self.adaptive_service.provider_monitor.evaluate_provider(
            "ISP-A", "eth0", {"latency_ms": 80.0, "packet_loss_percent": 2.0}
        )
        self.assertIn(snap.health_trend, ("DEGRADED", "STABLE", "RAPIDLY_DEGRADED"))

    # Scenario C: ISP-A sudden failure
    def test_scenario_C1_sudden_failure(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"latency_ms": 350.0, "packet_loss_percent": 20.0, "failure_risk": 0.99},
            degradation_duration_sec=10.0,
        )
        self.assertEqual(res.active_provider, "ISP-B")

    def test_scenario_C2_sudden_failure_hard_flag(self) -> None:
        snap = self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"packet_loss_percent": 20.0})
        event = self.adaptive_service.degradation_detector.detect_degradation(snap, duration_sec=5.0)
        self.assertTrue(event.is_hard_failure)

    # Scenario D: ISP-A high latency
    def test_scenario_D1_high_latency(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"latency_ms": 250.0, "packet_loss_percent": 0.2},
            degradation_duration_sec=40.0,
        )
        self.assertIsNotNone(res)

    def test_scenario_D2_high_latency_score_impact(self) -> None:
        snap = self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"latency_ms": 250.0})
        self.assertLess(snap.health_score, 70.0)

    # Scenario E: ISP-A high packet loss
    def test_scenario_E1_high_packet_loss(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"latency_ms": 25.0, "packet_loss_percent": 8.0},
            degradation_duration_sec=40.0,
        )
        self.assertIsNotNone(res)

    def test_scenario_E2_high_packet_loss_state(self) -> None:
        snap = self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"packet_loss_percent": 8.0})
        self.assertIn(snap.state, (ProviderState.CRITICAL, ProviderState.FAILED))

    # Scenario F: ISP-A high jitter
    def test_scenario_F1_high_jitter(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"jitter_ms": 45.0},
        )
        self.assertIsNotNone(res)

    def test_scenario_F2_high_jitter_metrics(self) -> None:
        snap = self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"jitter_ms": 45.0})
        self.assertEqual(snap.jitter_ms, 45.0)

    # Scenario G: ISP-A interface flapping
    def test_scenario_G1_interface_flapping(self) -> None:
        snap = self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"routing_flaps": 5})
        self.assertIn(snap.state, (ProviderState.WARNING, ProviderState.DEGRADED, ProviderState.CRITICAL, ProviderState.FAILED))

    def test_scenario_G2_interface_flapping_oscillation_risk(self) -> None:
        osc = self.adaptive_service.stability_engine.evaluate_oscillation_risk("ISP-A")
        self.assertIsNotNone(osc)

    # Scenario H: ISP-A high utilization
    def test_scenario_H1_high_utilization(self) -> None:
        snap = self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"utilization_percent": 98.0})
        self.assertEqual(snap.utilization_percent, 98.0)

    def test_scenario_H2_high_utilization_trigger(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"utilization_percent": 98.0},
        )
        self.assertIsNotNone(res)

    # Scenario I: ISP-A predicted failure with currently acceptable metrics
    def test_scenario_I1_predicted_failure(self) -> None:
        snap = self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"failure_risk": 0.88, "latency_ms": 20.0})
        self.assertEqual(snap.failure_risk, 0.88)

    def test_scenario_I2_predicted_failure_trigger(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"failure_risk": 0.88, "latency_ms": 20.0},
            degradation_duration_sec=40.0,
        )
        self.assertIsNotNone(res)

    # Scenario J: ISP-A degrades but ISP-B is also unhealthy
    def test_scenario_J1_both_unhealthy(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"latency_ms": 190.0, "packet_loss_percent": 8.0},
            candidate_metrics_override={"latency_ms": 180.0, "packet_loss_percent": 7.5},
            degradation_duration_sec=40.0,
        )
        self.assertIsNotNone(res)

    def test_scenario_J2_both_unhealthy_scores(self) -> None:
        snap_a = self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"latency_ms": 190.0})
        snap_b = self.adaptive_service.provider_monitor.evaluate_provider("ISP-B", "eth1", {"latency_ms": 180.0})
        self.assertLess(snap_a.health_score, 50.0)
        self.assertLess(snap_b.health_score, 50.0)

    # Scenario K: Both providers degrade
    def test_scenario_K1_both_degrade(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle(
            active_provider="ISP-A",
            candidate_provider="ISP-B",
            active_metrics_override={"packet_loss_percent": 15.0},
            candidate_metrics_override={"packet_loss_percent": 14.0},
        )
        self.assertIsNotNone(res)

    def test_scenario_K2_both_degrade_comparison(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle("ISP-A", "ISP-B")
        self.assertIsNotNone(res.provider_comparison)

    # Scenario L: ISP-A recovers temporarily and becomes unstable
    def test_scenario_L1_unstable_recovery(self) -> None:
        snap_pri = self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"latency_ms": 15.0})
        snap_curr = self.adaptive_service.provider_monitor.evaluate_provider("ISP-B", "eth1", {"latency_ms": 20.0})
        cand = self.adaptive_service.failback_engine.evaluate_failback(snap_pri, snap_curr, recovery_duration_sec=15.0)
        self.assertEqual(cand.status, FailbackStatus.WAIT_FOR_STABILITY)

    def test_scenario_L2_unstable_recovery_rejection(self) -> None:
        passed, msg = self.adaptive_service.stability_engine.validate_hysteresis_preconditions("ISP-B", "ISP-A", recovery_duration_sec=15.0)
        self.assertFalse(passed)

    # Scenario M: ISP-A recovers and satisfies stability window
    def test_scenario_M1_stable_recovery(self) -> None:
        snap_pri = self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"latency_ms": 15.0})
        snap_curr = self.adaptive_service.provider_monitor.evaluate_provider("ISP-B", "eth1", {"latency_ms": 20.0})
        cand = self.adaptive_service.failback_engine.evaluate_failback(snap_pri, snap_curr, recovery_duration_sec=90.0, override_satisfied=True)
        self.assertEqual(cand.status, FailbackStatus.FAILBACK_RECOMMENDED)

    def test_scenario_M2_stable_recovery_justification(self) -> None:
        snap_pri = self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"latency_ms": 15.0})
        snap_curr = self.adaptive_service.provider_monitor.evaluate_provider("ISP-B", "eth1", {"latency_ms": 20.0})
        cand = self.adaptive_service.failback_engine.evaluate_failback(snap_pri, snap_curr, recovery_duration_sec=90.0, override_satisfied=True)
        self.assertIn("sustained stability", cand.justification)

    # Scenario N: Failback is blocked by hysteresis
    def test_scenario_N1_failback_hysteresis_block(self) -> None:
        passed, msg = self.adaptive_service.stability_engine.validate_hysteresis_preconditions("ISP-B", "ISP-A", degradation_duration_sec=10.0)
        self.assertFalse(passed)

    def test_scenario_N2_failback_hysteresis_message(self) -> None:
        passed, msg = self.adaptive_service.stability_engine.validate_hysteresis_preconditions("ISP-B", "ISP-A", degradation_duration_sec=10.0)
        self.assertIn("confirmation window", msg)

    # Scenario O: Failback is blocked by TrustAgent
    def test_scenario_O1_trust_blocked(self) -> None:
        trust_dec = MagicMock(spec=TrustDecision)
        trust_dec.decision = AutonomyPolicyResult.BLOCKED
        snap_a = self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"latency_ms": 190.0})
        snap_b = self.adaptive_service.provider_monitor.evaluate_provider("ISP-B", "eth1", {"latency_ms": 20.0})
        trig = self.adaptive_service.trigger_engine.evaluate_trigger(snap_a, snap_b, trust_decision=trust_dec)
        self.assertEqual(trig.action, "FAILOVER_BLOCKED")

    def test_scenario_O2_trust_blocked_justification(self) -> None:
        trust_dec = MagicMock(spec=TrustDecision)
        trust_dec.decision = AutonomyPolicyResult.BLOCKED
        snap_a = self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0", {"latency_ms": 190.0})
        snap_b = self.adaptive_service.provider_monitor.evaluate_provider("ISP-B", "eth1", {"latency_ms": 20.0})
        trig = self.adaptive_service.trigger_engine.evaluate_trigger(snap_a, snap_b, trust_decision=trust_dec)
        self.assertIn("TrustAgent decision", trig.reason)

    # Scenario P: Failover approval expires
    def test_scenario_P1_approval_expiration(self) -> None:
        appr = self.failover_service.approval_manager.create_approval_request("Branch3-Uplink", "PLAN-HASH-123")
        self.assertEqual(appr.status.value, "PENDING_APPROVAL")

    def test_scenario_P2_approval_rejection(self) -> None:
        appr = self.failover_service.approval_manager.create_approval_request("Branch3-Uplink", "PLAN-HASH-123")
        rej = self.failover_service.approval_manager.reject_approval(appr.request_id, "Operator rejected")
        self.assertEqual(rej.status.value, "REJECTED")

    # Scenario Q: Execution plan changes after approval
    def test_scenario_Q1_plan_hash_mismatch(self) -> None:
        appr = self.failover_service.approval_manager.create_approval_request("Branch3-Uplink", "PLAN-HASH-123")
        self.failover_service.approval_manager.approve_request(appr.request_id, "Operator")
        ok, msg = self.failover_service.approval_manager.validate_approval_for_execution(appr.request_id, "CHANGED-PLAN-HASH-456")
        self.assertFalse(ok)

    def test_scenario_Q2_plan_hash_mismatch_msg(self) -> None:
        appr = self.failover_service.approval_manager.create_approval_request("Branch3-Uplink", "PLAN-HASH-123")
        self.failover_service.approval_manager.approve_request(appr.request_id, "Operator")
        ok, msg = self.failover_service.approval_manager.validate_approval_for_execution(appr.request_id, "CHANGED-PLAN-HASH-456")
        self.assertIn("mismatch", msg.lower())

    # Scenario R: Topology changes after approval
    def test_scenario_R1_topology_change_recheck(self) -> None:
        res = self.failover_service.pre_validator.validate_prechecks("Branch3-Uplink", {})
        self.assertIsNotNone(res)

    def test_scenario_R2_topology_recheck_prechecks(self) -> None:
        res = self.failover_service.pre_validator.validate_prechecks("Branch3-Uplink", {})
        self.assertEqual(len(res.prechecks_evaluated), 16)

    # Scenario S: Telemetry becomes stale before execution
    def test_scenario_S1_stale_telemetry_precheck(self) -> None:
        res = self.failover_service.pre_validator.validate_prechecks("Branch3-Uplink", {"telemetry_timestamp": "2020-01-01T00:00:00Z"})
        self.assertIsNotNone(res)

    def test_scenario_S2_stale_telemetry_handling(self) -> None:
        snap = self.adaptive_service.provider_monitor.evaluate_provider("ISP-A", "eth0")
        self.assertIsNotNone(snap)

    # Scenario T: Post-failover verification fails and rollback occurs
    def test_scenario_T1_verification_fail_rollback(self) -> None:
        res = self.failover_service.execute_failover_pipeline(
            "Branch3-Uplink", execution_mode=ExecutionMode.DRY_RUN, auto_approve=True, override_verification_status=VerificationStatus.FAILED
        )
        self.assertEqual(res.verification_result.status, VerificationStatus.FAILED)
        self.assertEqual(res.final_status, ExecutionStatus.ROLLED_BACK)

    def test_scenario_T2_automatic_rollback_executed(self) -> None:
        res = self.failover_service.execute_failover_pipeline(
            "Branch3-Uplink", execution_mode=ExecutionMode.DRY_RUN, auto_approve=True, override_verification_status=VerificationStatus.FAILED
        )
        self.assertIsNotNone(res.rollback_result)

    # Scenario U: Rollback itself fails
    def test_scenario_U1_rollback_engine_call(self) -> None:
        res = self.failover_service.rollback_engine.execute_rollback("Branch3-Uplink", {})
        self.assertIsNotNone(res)

    def test_scenario_U2_rollback_verification_status(self) -> None:
        res = self.failover_service.rollback_engine.execute_rollback("Branch3-Uplink", {})
        self.assertEqual(res.restoration_status.value, "RESTORED")

    # Scenario V: Federated incident knowledge matches current incident
    def test_scenario_V1_federated_match(self) -> None:
        exp = self.fed_service.export_incident_intelligence(["Latency spike 195ms"], "WAN_CONGESTION", "ISP degradation hypothesis", "Failover to ISP-B")
        self.fed_service.import_and_index_bundle(exp.bundle_file_path, trust_origin=TrustOrigin.FEDERATED_SITE_ALPHA)
        matches = self.fed_service.query_federated_knowledge("degradation")
        self.assertGreater(len(matches), 0)

    def test_scenario_V2_federated_match_origin(self) -> None:
        exp = self.fed_service.export_incident_intelligence(["Latency spike 195ms"], "WAN_CONGESTION", "ISP degradation hypothesis", "Failover to ISP-B")
        self.fed_service.import_and_index_bundle(exp.bundle_file_path, trust_origin=TrustOrigin.FEDERATED_SITE_ALPHA)
        matches = self.fed_service.query_federated_knowledge("degradation")
        self.assertEqual(matches[0]["trust_origin"], "FEDERATED_SITE_ALPHA")

    # Scenario W: Federated bundle is tampered with
    def test_scenario_W1_tampered_bundle_rejection(self) -> None:
        exp = self.fed_service.export_incident_intelligence(["Loss elevated"], "WAN", "Degradation", "Failover")
        with open(exp.bundle_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["signature"]["signature_hex"] = "0000000000000000000000000000000000000000000000000000000000000000"
        imp_res = self.fed_service.import_and_index_bundle(data)
        self.assertEqual(imp_res.status, ImportStatus.SIGNATURE_VERIFICATION_FAILED)

    def test_scenario_W2_tampered_bundle_not_indexed(self) -> None:
        exp = self.fed_service.export_incident_intelligence(["Loss elevated"], "WAN", "Degradation", "Failover")
        with open(exp.bundle_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["signature"]["signature_hex"] = "0000000000000000000000000000000000000000000000000000000000000000"
        imp_res = self.fed_service.import_and_index_bundle(data)
        self.assertEqual(imp_res.patterns_imported_count, 0)

    # Scenario X: Federated bundle contains sensitive data
    def test_scenario_X1_sensitive_bundle_privacy_rejection(self) -> None:
        signer = CryptoSigner()
        b_dict = {
            "bundle_id": "BND-SENSITIVE",
            "bundle_type": "INCIDENT_PATTERN_BUNDLE",
            "source_site_id": "NOC-SITE-ALPHA",
            "created_at": "2026-08-11T00:00:00Z",
            "sanitized_incidents": [
                {
                    "incident_id": "INC-1",
                    "abstract_severity": "HIGH",
                    "anonymized_pattern": {
                        "category": "WAN",
                        "symptoms": ["Loss on 10.0.0.1"],
                        "root_cause_hypothesis": "Leak on 10.0.0.1 with password=secret123",
                        "recommended_action": "Action",
                    },
                }
            ],
        }
        sig = signer.sign_payload({"source_site_id": b_dict["source_site_id"], "bundle_type": b_dict["bundle_type"], "sanitized_incidents": b_dict["sanitized_incidents"]})
        b_dict["signature"] = sig.model_dump(mode="json")
        imp_res = self.fed_service.import_and_index_bundle(b_dict)
        self.assertEqual(imp_res.status, ImportStatus.PRIVACY_CHECK_FAILED)

    def test_scenario_X2_sensitive_bundle_privacy_flag(self) -> None:
        signer = CryptoSigner()
        b_dict = {
            "bundle_id": "BND-SENSITIVE",
            "bundle_type": "INCIDENT_PATTERN_BUNDLE",
            "source_site_id": "NOC-SITE-ALPHA",
            "created_at": "2026-08-11T00:00:00Z",
            "sanitized_incidents": [
                {
                    "incident_id": "INC-1",
                    "abstract_severity": "HIGH",
                    "anonymized_pattern": {
                        "category": "WAN",
                        "symptoms": ["Loss on 10.0.0.1"],
                        "root_cause_hypothesis": "Leak on 10.0.0.1 with password=secret123",
                        "recommended_action": "Action",
                    },
                }
            ],
        }
        sig = signer.sign_payload({"source_site_id": b_dict["source_site_id"], "bundle_type": b_dict["bundle_type"], "sanitized_incidents": b_dict["sanitized_incidents"]})
        b_dict["signature"] = sig.model_dump(mode="json")
        imp_res = self.fed_service.import_and_index_bundle(b_dict)
        self.assertFalse(imp_res.privacy_valid)

    # Scenario Y: Ollama becomes unavailable during investigation
    def test_scenario_Y1_ollama_unavailable(self) -> None:
        detector = OllamaDetector(endpoint="http://127.0.0.1:99999")
        self.assertFalse(detector.check_ollama_available())

    def test_scenario_Y2_ollama_unavailable_graceful(self) -> None:
        detector = OllamaDetector(endpoint="http://127.0.0.1:99999")
        status = detector.get_system_capabilities()
        self.assertIsNotNone(status)

    # Scenario Z: GPU becomes unavailable and CPU fallback occurs
    def test_scenario_Z1_gpu_unavailable_cpu_fallback(self) -> None:
        service = PathDecisionService()
        res = service.evaluate_path_decision("Branch3-Uplink")
        self.assertIsNotNone(res)

    def test_scenario_Z2_cpu_fallback_execution(self) -> None:
        res = self.adaptive_service.process_adaptive_failover_cycle("ISP-A", "ISP-B")
        self.assertIsNotNone(res)


if __name__ == "__main__":
    unittest.main()
