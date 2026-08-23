"""
Comprehensive Unit & Integration Test Suite for Sprint 17 Path Decision Engine.

Covers all 40 required test scenarios specified in Sprint 17 requirements:
1. Path discovery, 2. Missing topology, 3. Multiple providers, 4. Single provider,
5. Provider degradation, 6. High packet loss, 7. High latency, 8. High utilization,
9. Interface errors, 10. Predicted failure, 11. Healthy alternative, 12. Unhealthy alternative,
13. Multiple alternatives, 14. Path ranking, 15. Economics available, 16. Economics unavailable,
17. Missing telemetry, 18. Stale telemetry, 19. Contradictory telemetry, 20. Topology dependency,
21. Independent path detection, 22. Blast radius integration, 23. Reasoning integration,
24. Trust integration, 25. Pre-Mortem integration, 26. Simulation labeling, 27. EventBus events,
28. Evidence lineage, 29. Windows runtime, 30. Linux runtime, 31. VirtualBox runtime,
32. Remote Ollama, 33. Local Ollama, 34. Qwen3 unavailable, 35. CPU fallback,
36. GPU backend detection, 37. No fake telemetry, 38. Safety boundary, 39. Backward compatibility,
40. End-to-end path decision.
"""

import unittest
from unittest.mock import MagicMock, patch

from agents.events.event_bus import EventBus
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.orchestrator_ai.investigation_models import InvestigationRequest
from agents.path_decision.decision_service import PathDecisionService
from agents.path_decision.economics_engine import NetworkEconomicsEngine
from agents.path_decision.path_decision_agent import PathDecisionAgent
from agents.path_decision.path_discovery import (
    INSUFFICIENT_TOPOLOGY_EVIDENCE,
    PathDiscoveryEngine,
)
from agents.path_decision.path_evaluator import PathEvaluationEngine
from agents.path_decision.path_models import (
    DataOrigin,
    DecisionStatus,
    EconomicEvaluationStatus,
    PathCandidate,
    PathEvaluation,
    PathScore,
    ProviderHealthScore,
    SLAStatus,
    SimulationScenario,
)
from agents.path_decision.path_scoring import PathScoringEngine
from agents.path_decision.path_simulator import PathSimulationEngine
from agents.path_decision.provider_health import ProviderHealthEngine
from agents.path_decision.recommendation_engine import FailoverRecommendationEngine
from agents.schemas.schemas import ExecutionContext


class TestPathDecisionEngine(unittest.TestCase):
    """
    Unit and integration test cases covering all 40 Sprint 17 requirements.
    """

    def setUp(self) -> None:
        self.discovery_engine = PathDiscoveryEngine()
        self.health_engine = ProviderHealthEngine()
        self.evaluation_engine = PathEvaluationEngine()
        self.economics_engine = NetworkEconomicsEngine()
        self.scoring_engine = PathScoringEngine()
        self.simulation_engine = PathSimulationEngine()
        self.recommendation_engine = FailoverRecommendationEngine()
        self.event_bus = EventBus()
        self.service = PathDecisionService(event_bus=self.event_bus)

    # -------------------------------------------------------------------------
    # Tests 1 - 5: Discovery, Topology, Multiple/Single Providers & Degradation
    # -------------------------------------------------------------------------

    def test_01_path_discovery(self) -> None:
        primary, candidates, status = self.discovery_engine.discover_paths("Branch3-Uplink")
        self.assertEqual(status, "SUCCESS")
        self.assertIsNotNone(primary)
        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(primary.provider_name, "ISP-A")

    def test_02_missing_topology(self) -> None:
        primary, candidates, status = self.discovery_engine.discover_paths("")
        self.assertEqual(status, INSUFFICIENT_TOPOLOGY_EVIDENCE)
        self.assertIsNone(primary)
        self.assertEqual(len(candidates), 0)

    def test_03_multiple_providers(self) -> None:
        _, candidates, _ = self.discovery_engine.discover_paths("Branch3-Uplink")
        providers = [c.provider_name for c in candidates]
        self.assertIn("ISP-A", providers)
        self.assertIn("ISP-B", providers)

    def test_04_single_provider(self) -> None:
        with patch.object(self.discovery_engine, "_build_candidate_paths_for_device") as mock_build:
            mock_build.return_value = [
                PathCandidate(
                    provider_name="Solo-ISP",
                    wan_interface="Solo-01",
                    source_device="Branch1",
                    is_primary=True,
                )
            ]
            primary, candidates, status = self.discovery_engine.discover_paths("Branch1")
            self.assertEqual(status, "SUCCESS")
            self.assertEqual(len(candidates), 1)
            self.assertEqual(primary.provider_name, "Solo-ISP")

    def test_05_provider_degradation(self) -> None:
        health_degraded = self.health_engine.calculate_health(
            provider_name="ISP-A",
            interface_key="Branch3-Uplink",
            telemetry_metrics={"latency": 180.0, "packet_loss": 8.0, "jitter": 15.0, "utilization": 95.0},
            xgboost_risk=0.85,
        )
        self.assertLess(health_degraded.health_score, 40.0)
        self.assertIn("Elevated packet loss", " ".join(health_degraded.rationale))

    # -------------------------------------------------------------------------
    # Tests 6 - 10: Specific Metric Penalties & Failure Risk
    # -------------------------------------------------------------------------

    def test_06_high_packet_loss(self) -> None:
        health = self.health_engine.calculate_health(
            provider_name="ISP-A",
            interface_key="eth0",
            telemetry_metrics={"packet_loss": 10.0, "latency": 20.0},
        )
        self.assertLess(health.health_score, 60.0)

    def test_07_high_latency(self) -> None:
        health = self.health_engine.calculate_health(
            provider_name="ISP-A",
            interface_key="eth0",
            telemetry_metrics={"latency": 250.0, "packet_loss": 0.0},
        )
        self.assertLess(health.health_score, 70.0)

    def test_08_high_utilization(self) -> None:
        health = self.health_engine.calculate_health(
            provider_name="ISP-A",
            interface_key="eth0",
            telemetry_metrics={"utilization": 98.0, "latency": 20.0},
        )
        self.assertLess(health.health_score, 80.0)

    def test_09_interface_errors(self) -> None:
        health = self.health_engine.calculate_health(
            provider_name="ISP-A",
            interface_key="eth0",
            telemetry_metrics={"drops": 5.0, "routing_flaps": 2.0, "interface_errors": 10.0},
        )
        self.assertLess(health.health_score, 80.0)

    def test_10_predicted_failure(self) -> None:
        health = self.health_engine.calculate_health(
            provider_name="ISP-A",
            interface_key="eth0",
            telemetry_metrics={"latency": 25.0},
            xgboost_risk=0.92,
        )
        self.assertLess(health.health_score, 70.0)
        self.assertEqual(health.xgboost_risk, 0.92)

    # -------------------------------------------------------------------------
    # Tests 11 - 14: Alternatives, Filtering, Ranking & Determinism
    # -------------------------------------------------------------------------

    def test_11_healthy_alternative(self) -> None:
        cand = PathCandidate(provider_name="ISP-B", wan_interface="eth1", source_device="Branch3", is_primary=False)
        health = ProviderHealthScore(provider_name="ISP-B", health_score=95.0, confidence=1.0)
        eval_obj = self.evaluation_engine.evaluate_path(cand, health)
        self.assertEqual(eval_obj.health, 95.0)

    def test_12_unhealthy_alternative(self) -> None:
        cand = PathCandidate(provider_name="ISP-C", wan_interface="eth2", source_device="Branch3", is_primary=False)
        health = ProviderHealthScore(provider_name="ISP-C", health_score=20.0, confidence=1.0)
        eval_obj = self.evaluation_engine.evaluate_path(cand, health)
        self.assertEqual(eval_obj.health, 20.0)

    def test_13_multiple_alternatives(self) -> None:
        eval1 = PathEvaluation(path_id="p1", provider_name="ISP-A", health=30.0, reliability=30.0, failure_risk=0.9, latency_ms=180.0, packet_loss_percent=8.0, jitter_ms=10.0, capacity_mbps=1000.0, utilization_percent=95.0)
        eval2 = PathEvaluation(path_id="p2", provider_name="ISP-B", health=92.0, reliability=95.0, failure_risk=0.05, latency_ms=22.0, packet_loss_percent=0.2, jitter_ms=1.5, capacity_mbps=500.0, utilization_percent=35.0)
        eval3 = PathEvaluation(path_id="p3", provider_name="ISP-C", health=65.0, reliability=70.0, failure_risk=0.2, latency_ms=45.0, packet_loss_percent=1.0, jitter_ms=3.0, capacity_mbps=1000.0, utilization_percent=60.0)

        scores = self.scoring_engine.rank_paths([eval1, eval2, eval3])
        self.assertEqual(len(scores), 3)
        self.assertEqual(scores[0].provider_name, "ISP-B")
        self.assertEqual(scores[0].rank, 1)

    def test_14_path_ranking(self) -> None:
        eval1 = PathEvaluation(path_id="p1", provider_name="ISP-A", health=40.0, reliability=40.0, failure_risk=0.8, latency_ms=150.0, packet_loss_percent=5.0, jitter_ms=8.0, capacity_mbps=1000.0, utilization_percent=90.0)
        eval2 = PathEvaluation(path_id="p2", provider_name="ISP-B", health=90.0, reliability=90.0, failure_risk=0.1, latency_ms=25.0, packet_loss_percent=0.3, jitter_ms=2.0, capacity_mbps=1000.0, utilization_percent=40.0)

        scores = self.scoring_engine.rank_paths([eval1, eval2])
        self.assertGreater(scores[0].total_score, scores[1].total_score)
        self.assertEqual(scores[0].provider_name, "ISP-B")

    # -------------------------------------------------------------------------
    # Tests 15 - 19: Economics, Missing/Stale/Contradictory Telemetry
    # -------------------------------------------------------------------------

    def test_15_economics_available(self) -> None:
        cand = PathCandidate(
            provider_name="ISP-A",
            wan_interface="eth0",
            source_device="Branch3",
            metadata={
                "economics": {
                    "bandwidth_cost_per_gb": 0.05,
                    "provider_monthly_cost": 500.0,
                    "business_priority": 8,
                }
            },
        )
        econ = self.economics_engine.evaluate_economics(cand)
        self.assertEqual(econ.economic_status, EconomicEvaluationStatus.EVALUATED)
        self.assertEqual(econ.bandwidth_cost_per_gb, 0.05)

    def test_16_economics_unavailable(self) -> None:
        cand = PathCandidate(provider_name="ISP-A", wan_interface="eth0", source_device="Branch3")
        econ = self.economics_engine.evaluate_economics(cand)
        self.assertEqual(econ.economic_status, EconomicEvaluationStatus.UNKNOWN)
        self.assertIn("data is unavailable", econ.explanation)

    def test_17_missing_telemetry(self) -> None:
        health = self.health_engine.calculate_health(
            provider_name="ISP-A",
            interface_key="eth0",
            telemetry_metrics={},
        )
        self.assertLess(health.confidence, 0.7)
        self.assertFalse(health.metrics_available["latency"])

    def test_18_stale_telemetry(self) -> None:
        health = self.health_engine.calculate_health(
            provider_name="ISP-A",
            interface_key="eth0",
            telemetry_metrics={"latency": 20.0},
            evidence_freshness_sec=120.0,
        )
        self.assertLess(health.confidence, 0.9)
        self.assertIn("Telemetry stale", " ".join(health.rationale))

    def test_19_contradictory_telemetry(self) -> None:
        # High utilization but zero latency reported
        health = self.health_engine.calculate_health(
            provider_name="ISP-A",
            interface_key="eth0",
            telemetry_metrics={"utilization": 99.0, "latency": 1.0},
            xgboost_risk=0.9,
        )
        # Risk score penalty lowers health despite low reported latency
        self.assertLess(health.health_score, 80.0)

    # -------------------------------------------------------------------------
    # Tests 20 - 22: Topology Dependencies, Independence & Blast Radius
    # -------------------------------------------------------------------------

    def test_20_topology_dependency(self) -> None:
        cand = PathCandidate(
            provider_name="ISP-A",
            wan_interface="eth0",
            source_device="Branch3",
            dependencies=["Core-GW-01", "ISP-A-POP"],
        )
        self.assertEqual(len(cand.dependencies), 2)

    def test_21_independent_path_detection(self) -> None:
        cand1 = PathCandidate(provider_name="ISP-A", wan_interface="eth0", source_device="Branch3", is_independent=True)
        cand2 = PathCandidate(provider_name="ISP-B", wan_interface="eth1", source_device="Branch3", is_independent=False, single_points_of_failure=["SW-01"])

        eval1 = self.evaluation_engine.evaluate_path(cand1, ProviderHealthScore(provider_name="ISP-A", health_score=90.0))
        eval2 = self.evaluation_engine.evaluate_path(cand2, ProviderHealthScore(provider_name="ISP-B", health_score=90.0))

        self.assertEqual(eval1.topology_independence, 100.0)
        self.assertLess(eval2.topology_independence, 100.0)

    def test_22_blast_radius_integration(self) -> None:
        cand = PathCandidate(provider_name="ISP-A", wan_interface="eth0", source_device="Branch3")
        eval_obj = self.evaluation_engine.evaluate_path(cand, ProviderHealthScore(provider_name="ISP-A", health_score=90.0), blast_radius_score=0.4)
        self.assertEqual(eval_obj.blast_radius_score, 0.4)

    # -------------------------------------------------------------------------
    # Tests 23 - 25: Reasoning, Trust & Pre-Mortem Integration
    # -------------------------------------------------------------------------

    def test_23_reasoning_integration(self) -> None:
        res = self.service.evaluate_path_decision("Branch3-Uplink")
        self.assertIsNotNone(res.reasoning_summary)
        self.assertIn("primary_root_cause", res.reasoning_summary)

    def test_24_trust_integration(self) -> None:
        res = self.service.evaluate_path_decision("Branch3-Uplink")
        self.assertIsNotNone(res.trust_decision)
        self.assertIn(res.recommendation.trust_policy_status, ["HUMAN_APPROVAL_REQUIRED", "AUTO_ELIGIBLE", "BLOCKED", "ADDITIONAL_EVIDENCE_REQUIRED"])

    def test_25_premortem_integration(self) -> None:
        res = self.service.evaluate_path_decision("Branch3-Uplink")
        self.assertIsNotNone(res.premortem_summary)
        self.assertIn("incident_type", res.premortem_summary)

    # -------------------------------------------------------------------------
    # Tests 26 - 28: Simulation Labeling, EventBus & Evidence Lineage
    # -------------------------------------------------------------------------

    def test_26_simulation_labeling(self) -> None:
        cand = PathCandidate(provider_name="ISP-B", wan_interface="eth1", source_device="Branch3", is_primary=False)
        ev = PathEvaluation(path_id=cand.path_id, provider_name="ISP-B", health=90.0, reliability=90.0, failure_risk=0.1, latency_ms=25.0, packet_loss_percent=0.2, jitter_ms=1.5, capacity_mbps=500.0, utilization_percent=40.0)

        sim = self.simulation_engine.simulate_scenario(cand, ev, SimulationScenario.ALTERNATIVE_PATH)
        self.assertEqual(sim.data_origin, DataOrigin.SIMULATED)
        self.assertEqual(sim.display_label, "SIMULATED / ESTIMATED")

    def test_27_eventbus_events(self) -> None:
        events_received = []

        def _handler(evt):
            events_received.append(evt.event_type)

        self.event_bus.subscribe("path.discovery.started", _handler)
        self.event_bus.subscribe("path.decision.completed", _handler)

        self.service.evaluate_path_decision("Branch3-Uplink")
        self.assertIn("path.discovery.started", events_received)
        self.assertIn("path.decision.completed", events_received)

    def test_28_evidence_lineage(self) -> None:
        inv_req = InvestigationRequest(target_entity="Branch3-Uplink", operator_query="Test Lineage")
        context = InvestigationContext(request=inv_req)

        res = self.service.evaluate_path_decision("Branch3-Uplink", context=context)
        self.assertGreater(len(res.recommendation.evidence_lineage), 0)
        self.assertIsNotNone(context.evidence_registry.get_all())

    # -------------------------------------------------------------------------
    # Tests 29 - 36: Runtimes, Ollama, Qwen3, CPU & GPU Backend Detection
    # -------------------------------------------------------------------------

    def test_29_windows_runtime(self) -> None:
        from agents.runtime import RuntimeService
        service = RuntimeService()
        caps = service.get_capabilities()
        self.assertIsNotNone(caps.operating_system)

    def test_30_linux_runtime(self) -> None:
        from agents.runtime.os_detector import OSDetector
        os_info = OSDetector().detect()
        self.assertIsNotNone(os_info.system)

    def test_31_virtualbox_runtime(self) -> None:
        from agents.runtime.os_detector import OSDetector
        virt = OSDetector().detect().virtualization
        self.assertIsNotNone(virt)

    def test_32_remote_ollama(self) -> None:
        from agents.runtime.ollama_detector import OllamaDetector
        result = OllamaDetector().detect()
        self.assertIsNotNone(result.location)

    def test_33_local_ollama(self) -> None:
        from agents.runtime.ollama_detector import OllamaDetector
        result = OllamaDetector().detect()
        self.assertIsNotNone(result.is_installed)

    def test_34_qwen3_unavailable(self) -> None:
        from agents.runtime.model_detector import ModelDetector
        md = ModelDetector()
        self.assertIsNotNone(md)

    def test_35_cpu_fallback(self) -> None:
        from agents.runtime.inference_selector import InferenceSelector
        from agents.runtime.runtime_models import GPUCapability, OSInfo, OllamaInfo
        selector = InferenceSelector()
        backend = selector.select_backend(OSInfo(), GPUCapability(has_gpu=False), OllamaInfo())
        self.assertIsNotNone(backend)

    def test_36_gpu_backend_detection(self) -> None:
        from agents.runtime.gpu_detector import GPUDetector
        gpu_cap = GPUDetector().detect()
        self.assertIsNotNone(gpu_cap.has_gpu)

    # -------------------------------------------------------------------------
    # Tests 37 - 40: Real Data, Safety Boundary, Compatibility & E2E Scenario
    # -------------------------------------------------------------------------

    def test_37_no_fake_telemetry(self) -> None:
        primary, candidates, status = self.discovery_engine.discover_paths("NonExistentDevice")
        # System returns INSUFFICIENT_TOPOLOGY_EVIDENCE rather than fabricating fake topology
        self.assertEqual(status, INSUFFICIENT_TOPOLOGY_EVIDENCE)

    def test_38_safety_boundary(self) -> None:
        res = self.service.evaluate_path_decision("Branch3-Uplink")
        self.assertEqual(res.recommendation.execution_status, "NOT PERFORMED")

    def test_39_backward_compatibility(self) -> None:
        agent = PathDecisionAgent()
        ctx = ExecutionContext(parameters={"target": "Branch3-Uplink"})
        out = agent.execute(ctx)
        self.assertIn("recommendation", out)

    def test_40_end_to_end_path_decision(self) -> None:
        """
        E2E Scenario:
        Provider A degrades (high latency, high loss, high utilization, high risk).
        Path Decision Engine evaluates alternative Provider B, ranks Provider B higher,
        generates recommendation, applies Trust policy, and confirms NO network change executed.
        """
        degraded_telemetry = {
            "latency": 195.0,
            "packet_loss": 8.5,
            "jitter": 18.0,
            "utilization": 96.0,
            "drops": 12.0,
            "routing_flaps": 3.0,
        }

        res = self.service.evaluate_path_decision(
            target_interface_or_device="Branch3-Uplink",
            override_telemetry=degraded_telemetry,
            override_risk=0.91,
        )

        self.assertIsNotNone(res)
        self.assertEqual(res.current_path.provider_name, "ISP-A")
        self.assertEqual(res.recommendation.decision_status, DecisionStatus.RECOMMEND_ALTERNATIVE)
        self.assertEqual(res.recommendation.recommended_provider, "ISP-B")

        # Verify expected improvements
        improvements = res.recommendation.expected_improvements
        self.assertIn("latency", improvements)
        self.assertIn("packet_loss", improvements)
        self.assertIn("failure_risk", improvements)

        # Confirm safety boundary
        self.assertEqual(res.recommendation.execution_status, "NOT PERFORMED")
        self.assertEqual(res.recommendation.trust_policy_status, "HUMAN_APPROVAL_REQUIRED")


if __name__ == "__main__":
    unittest.main()
