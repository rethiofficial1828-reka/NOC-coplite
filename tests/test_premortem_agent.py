"""
Comprehensive Production Test Suite for Enterprise Incident Fingerprinting & Pre-Mortem Intelligence Engine.

Validates IncidentFingerprintEngine, HistoricalIncidentMatcher, IncidentPatternClusterer,
FutureScenarioEngine, TimeToImpactEstimator, PreMortemConfidenceEngine, EarlyWarningEngine,
PreMortemService, PreMortemAgent, EventBus lifecycle events, ExecutionContext propagation,
RAG integration, thread safety, and zero network execution safety boundaries.
"""

from datetime import datetime, timezone
import threading
import unittest
from typing import Any, Dict, List

from agents.core.container import ServiceContainer
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.orchestrator_ai.investigation_models import InvestigationRequest
from agents.reasoning.reasoning_models import (
    ConfidenceResult,
    InvestigationConclusion,
    ReasoningExplanation,
    ReasoningResult,
    ReasoningStatistics,
    RootCause,
)
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import ExecutionContext
from agents.trust.trust_models import (
    AutonomyDecision,
    AutonomyPolicy,
    BlastRadius,
    BlastRadiusLevel,
    ConfidenceHandoff,
    DecisionExplanation,
    TrustAssessment,
    TrustDecision,
    TrustScore,
    VerificationStatus,
)
from agents.premortem.early_warning import EarlyWarningEngine
from agents.premortem.incident_fingerprint import IncidentFingerprintEngine
from agents.premortem.incident_matcher import HistoricalIncidentMatcher
from agents.premortem.pattern_cluster import IncidentPatternClusterer
from agents.premortem.premortem_agent import PreMortemAgent
from agents.premortem.premortem_confidence import PreMortemConfidenceEngine
from agents.premortem.premortem_engine import PreMortemEngine
from agents.premortem.premortem_models import (
    HistoricalComparisonItem,
    HistoricalEvidenceClassification,
    HistoricalIncidentLearningResult,
    ObservationType,
    PreMortemConfidence,
    PreMortemResult,
    PreMortemSeverity,
    ScenarioType,
)
from agents.premortem.premortem_service import PreMortemService
from agents.premortem.scenario_engine import FutureScenarioEngine
from agents.premortem.time_to_impact import TimeToImpactEstimator


class TestPreMortemAgent(unittest.TestCase):
    def setUp(self) -> None:
        self.container = ServiceContainer.get_global()
        self.container.reset()
        self.registry = AgentRegistry.get_global()
        self.registry.clear()
        self.event_bus = EventBus.get_global()
        self.event_bus.clear()

    def tearDown(self) -> None:
        self.registry.clear()
        self.event_bus.clear()
        self.container.reset()

    def _create_mock_reasoning_result(self, confidence: float = 0.90) -> ReasoningResult:
        rc = RootCause(
            title="WAN Link Congestion & Interface Oversubscription",
            probability=confidence,
            description="Interface utilization > 95%",
            recommended_actions=["Apply traffic shaping"],
        )
        expl = ReasoningExplanation(
            selected_root_cause_title=rc.title,
            why_chosen="High utilization",
            supporting_evidence_summary="2 signals",
            rejected_hypotheses=[],
            contradictions_summary="None",
            evidence_quality_summary="High",
            missing_evidence_summary="None",
            recommended_next_steps=rc.recommended_actions,
        )
        conclusion = InvestigationConclusion(
            request_id="req-pm-001",
            primary_root_cause=rc,
            ranked_root_causes=[],
            ranked_hypotheses=[],
            contradictions=[],
            confidence_result=ConfidenceResult(overall_confidence=confidence),
            explanation=expl,
        )
        return ReasoningResult(
            request_id="req-pm-001",
            conclusion=conclusion,
            correlation=None,
            statistics=ReasoningStatistics(),
        )

    # --- Test 1: Fingerprint Generation ---
    def test_fingerprint_generation(self) -> None:
        engine = IncidentFingerprintEngine()
        fp = engine.generate_fingerprint(telemetry_payload={"bandwidth_utilization": 96.0, "packet_loss": 9.0})
        self.assertIsNotNone(fp.fingerprint_id)
        self.assertEqual(fp.incident_type, "WAN_CONGESTION")
        self.assertEqual(fp.interface_pattern, "HIGH_UTILIZATION_WITH_PACKET_LOSS")

    # --- Test 2: Deterministic Fingerprinting ---
    def test_deterministic_fingerprinting(self) -> None:
        engine = IncidentFingerprintEngine()
        payload = {"bandwidth_utilization": 96.0, "packet_loss": 9.0}
        fp1 = engine.generate_fingerprint(telemetry_payload=payload)
        fp2 = engine.generate_fingerprint(telemetry_payload=payload)
        self.assertEqual(fp1.incident_type, fp2.incident_type)
        self.assertEqual(fp1.interface_pattern, fp2.interface_pattern)

    # --- Test 3: Historical Incident Matching ---
    def test_historical_incident_matching(self) -> None:
        fp_engine = IncidentFingerprintEngine()
        fp = fp_engine.generate_fingerprint()
        matcher = HistoricalIncidentMatcher()
        matches = matcher.match_fingerprint(fp)
        self.assertGreater(len(matches), 0)
        self.assertGreaterEqual(matches[0].similarity_score, 0.40)

    # --- Test 4: Incident Pattern Clustering ---
    def test_pattern_clustering(self) -> None:
        fp_engine = IncidentFingerprintEngine()
        fp = fp_engine.generate_fingerprint()
        clusterer = IncidentPatternClusterer()
        clusters = clusterer.cluster_patterns(fp, [])
        self.assertGreater(len(clusters), 0)
        self.assertIn("WAN", clusters[0].category)

    # --- Test 5: Future Scenario Generation ---
    def test_future_scenario_generation(self) -> None:
        engine = FutureScenarioEngine()
        scenarios = engine.generate_scenarios(current_utilization=96.0)
        self.assertEqual(len(scenarios), 3)
        self.assertEqual(scenarios[0].scenario_type, ScenarioType.BASELINE_PERSISTENCE)
        self.assertEqual(scenarios[0].severity, PreMortemSeverity.HIGH)

    # --- Test 6: Time-to-Impact Estimation ---
    def test_time_to_impact_estimation(self) -> None:
        estimator = TimeToImpactEstimator()
        t = estimator.estimate_time_to_impact(current_utilization=96.0, prediction_risk=0.92)
        self.assertLessEqual(t.min_time_minutes, t.expected_time_minutes)
        self.assertLessEqual(t.expected_time_minutes, t.max_time_minutes)
        self.assertGreaterEqual(t.confidence, 0.70)

    # --- Test 7: Early Warning Detection ---
    def test_early_warning_detection(self) -> None:
        fp_engine = IncidentFingerprintEngine()
        fp = fp_engine.generate_fingerprint(telemetry_payload={"bandwidth_utilization": 96.0, "packet_loss": 9.0})
        engine = EarlyWarningEngine()
        warnings = engine.detect_early_warnings(fp, [])
        self.assertGreater(len(warnings), 0)
        self.assertIn("WAN Congestion", warnings[0].title)

    # --- Test 8: Pre-Mortem Confidence Calculation ---
    def test_premortem_confidence_calculation(self) -> None:
        engine = PreMortemConfidenceEngine()
        conf = engine.calculate_confidence(matches=[], scenarios=[], evidence_quality=0.90, trust_score=0.85)
        self.assertGreaterEqual(conf.score, 0.50)
        self.assertIsNotNone(conf.confidence_level)

    # --- Test 9: ObservationType Classification Integrity ---
    def test_observation_type_classification(self) -> None:
        engine = FutureScenarioEngine()
        scenarios = engine.generate_scenarios()
        for s in scenarios:
            for ev in s.evidence:
                self.assertIn(ev.observation_type, list(ObservationType))

    # --- Test 10: Missing Evidence Handling ---
    def test_missing_evidence_handling(self) -> None:
        engine = PreMortemConfidenceEngine()
        conf = engine.calculate_confidence(matches=[], scenarios=[])
        self.assertGreater(len(conf.missing_evidence), 0)

    # --- Test 11: Topology Integration in Scenarios ---
    def test_topology_integration_in_scenarios(self) -> None:
        engine = FutureScenarioEngine()
        scenarios = engine.generate_scenarios(target_device="Core-Router-99")
        self.assertIn("Core-Router-99", scenarios[0].affected_devices)

    # --- Test 12: RAG History Integration ---
    def test_rag_history_integration(self) -> None:
        matcher = HistoricalIncidentMatcher()
        fp = IncidentFingerprintEngine().generate_fingerprint()
        matches = matcher.match_fingerprint(fp, top_k=2)
        self.assertIsNotNone(matches[0].historical_root_cause)

    # --- Test 13: EventBus Lifecycle Broadcasting ---
    def test_event_bus_lifecycle_events(self) -> None:
        self.registry.register(PreMortemAgent())
        events_received = []

        def event_handler(evt: Event) -> None:
            events_received.append(evt.event_type)

        self.event_bus.subscribe("*", event_handler)
        agent = PreMortemAgent()
        reasoning_res = self._create_mock_reasoning_result()
        exec_ctx = ExecutionContext()

        result = agent.execute(reasoning_res, exec_ctx)

        self.assertIsInstance(result, PreMortemResult)
        self.assertIn("premortem.started", events_received)
        self.assertIn("premortem.fingerprint.generated", events_received)
        self.assertIn("premortem.history.matched", events_received)
        self.assertIn("premortem.scenarios.generated", events_received)
        self.assertIn("premortem.time_to_impact.calculated", events_received)
        self.assertIn("premortem.confidence.calculated", events_received)
        self.assertIn("premortem.completed", events_received)

    # --- Test 14: ExecutionContext & InvestigationContext Propagation ---
    def test_context_propagation(self) -> None:
        agent = PreMortemAgent()
        reasoning_res = self._create_mock_reasoning_result()
        req = InvestigationRequest(operator_query="Pre-Mortem Investigation")
        inv_ctx = InvestigationContext(request=req)
        exec_ctx = ExecutionContext()

        result = agent.execute(inv_ctx, exec_ctx)

        self.assertIsNotNone(inv_ctx.get_agent_output("PreMortemAgent"))
        self.assertIn(agent.name, exec_ctx.results)

    # --- Test 15: Parallel-Safe Thread Execution ---
    def test_parallel_thread_execution(self) -> None:
        agent = PreMortemAgent()
        results: List[PreMortemResult] = []
        lock = threading.Lock()

        def worker() -> None:
            res = agent.execute(self._create_mock_reasoning_result())
            with lock:
                results.append(res)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 5)

    # --- Test 16: Empty Historical Dataset Graceful Handling ---
    def test_empty_historical_dataset_graceful_handling(self) -> None:
        service = PreMortemService()
        res = service.run_premortem_analysis(telemetry_payload={"bandwidth_utilization": 50.0})
        self.assertIsNotNone(res.summary)
        self.assertGreater(len(res.scenarios), 0)

    # --- Test 17: Stale & Conflicting Telemetry Handling ---
    def test_stale_and_conflicting_telemetry(self) -> None:
        service = PreMortemService()
        res = service.run_premortem_analysis(telemetry_payload={"bandwidth_utilization": 99.0, "packet_loss": 0.0})
        self.assertIsNotNone(res.confidence)

    # --- Test 18: High-Risk Future Scenario Severity ---
    def test_high_risk_future_scenario_severity(self) -> None:
        service = PreMortemService()
        res = service.run_premortem_analysis(telemetry_payload={"bandwidth_utilization": 98.0, "packet_loss": 12.0})
        high_sev = [s for s in res.scenarios if s.severity in (PreMortemSeverity.HIGH, PreMortemSeverity.CRITICAL)]
        self.assertGreater(len(high_sev), 0)

    # --- Test 19: Strict Non-Execution Safety Boundary ---
    def test_strict_non_execution_safety_boundary(self) -> None:
        agent = PreMortemAgent()
        result = agent.execute(self._create_mock_reasoning_result())
        # Ensure output is purely analytical and does not contain execution commands or handles
        self.assertIsInstance(result, PreMortemResult)
        self.assertFalse(hasattr(result, "executed_commands"))

    # --- Test 20: PreMortemService Statistics Tracking ---
    def test_premortem_service_statistics(self) -> None:
        service = PreMortemService()
        service.run_premortem_analysis()
        stats = service.get_statistics()
        self.assertGreaterEqual(stats.total_evaluations, 1)

    # --- Test 21: Full Backward Compatibility ---
    def test_backward_compatibility(self) -> None:
        agent = PreMortemAgent()
        self.assertEqual(agent.name, "PreMortemAgent")
        self.assertTrue(agent.metadata.capabilities.supports_parallel_execution)


class TestAdaptiveIncidentLearning(unittest.TestCase):
    """
    Comprehensive test suite for Phase 4: Adaptive Incident Learning & Historical Pattern Intelligence.
    """

    def setUp(self) -> None:
        self.service = PreMortemService()
        self.mock_reasoning = self._create_mock_reasoning()

    def _create_mock_reasoning(self, confidence: float = 0.88) -> ReasoningResult:
        rc = RootCause(
            title="WAN Link Congestion & Traffic Saturation",
            probability=confidence,
            description="Interface utilization > 90%",
            recommended_actions=["Switch to backup link ISP-B"],
        )
        expl = ReasoningExplanation(
            selected_root_cause_title=rc.title,
            why_chosen="High bandwidth utilization and packet drop rate",
            supporting_evidence_summary="Bandwidth 88.5%, loss 3.0%",
            rejected_hypotheses=[],
            contradictions_summary="None",
            evidence_quality_summary="High",
            missing_evidence_summary="None",
            recommended_next_steps=rc.recommended_actions,
        )
        conclusion = InvestigationConclusion(
            request_id="req-hist-001",
            primary_root_cause=rc,
            ranked_root_causes=[],
            ranked_hypotheses=[],
            contradictions=[],
            confidence_result=ConfidenceResult(overall_confidence=confidence),
            explanation=expl,
        )
        return ReasoningResult(
            request_id="req-hist-001",
            conclusion=conclusion,
            statistics=ReasoningStatistics(),
        )

    def test_01_fingerprint_extraction_and_reuse(self) -> None:
        """Fingerprint is deterministically generated and reusable."""
        res = self.service.analyze_historical_learning(
            target_entity="Branch3-Uplink",
            reasoning_result=self.mock_reasoning,
            telemetry_payload={"bandwidth_utilization": 92.0, "packet_loss": 6.0},
        )
        self.assertIsNotNone(res.fingerprint)
        self.assertIn("WAN", res.fingerprint.incident_type)
        self.assertEqual(res.fingerprint.interface_pattern, "HIGH_UTILIZATION_WITH_PACKET_LOSS")

    def test_02_historical_matching(self) -> None:
        """Historical incidents are retrieved and matched against fingerprint."""
        res = self.service.analyze_historical_learning(
            target_entity="Branch3-Uplink",
            reasoning_result=self.mock_reasoning,
        )
        self.assertGreater(len(res.matched_incidents), 0)
        top = res.matched_incidents[0]
        self.assertIsNotNone(top.incident_id)
        self.assertGreaterEqual(top.similarity_score, 0.40)
        self.assertIsNotNone(top.historical_root_cause)
        self.assertIsNotNone(top.historical_resolution)
        self.assertIsNotNone(top.historical_outcome)

    def test_03_similarity_ranking(self) -> None:
        """Historical incident matches are ordered by similarity score."""
        res = self.service.analyze_historical_learning(
            target_entity="Branch3-Uplink",
            reasoning_result=self.mock_reasoning,
        )
        scores = [m.similarity_score for m in res.matched_incidents]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_04_pattern_clustering(self) -> None:
        """Recurring incident pattern clusters are accurately identified."""
        res = self.service.analyze_historical_learning(
            target_entity="Branch3-Uplink",
            reasoning_result=self.mock_reasoning,
        )
        self.assertGreater(len(res.pattern_clusters), 0)
        cluster = res.pattern_clusters[0]
        self.assertEqual(cluster.category, "WAN_CONGESTION")
        self.assertGreater(cluster.frequency_count, 0)
        self.assertGreater(len(cluster.common_indicators), 0)

    def test_05_current_vs_historical_comparison(self) -> None:
        """Multi-dimensional comparison evaluates existing metrics between current and historical cases."""
        res = self.service.analyze_historical_learning(
            target_entity="Branch3-Uplink",
            reasoning_result=self.mock_reasoning,
            telemetry_payload={"bandwidth_utilization": 88.5, "packet_loss": 3.0},
        )
        self.assertGreater(len(res.comparisons), 0)
        dims = [c.dimension for c in res.comparisons]
        self.assertIn("Incident Type & Signature", dims)
        self.assertIn("Bandwidth Utilization", dims)
        self.assertIn("Packet Loss Rate", dims)
        self.assertIn("Root Cause Hypothesis", dims)

    def test_06_classification_supporting_contradicting_inconclusive(self) -> None:
        """Comparisons are strictly classified into SUPPORTING, CONTRADICTING, or INCONCLUSIVE."""
        res = self.service.analyze_historical_learning(
            target_entity="Branch3-Uplink",
            reasoning_result=self.mock_reasoning,
        )
        for comp in res.comparisons:
            self.assertIn(
                comp.relationship,
                (
                    HistoricalEvidenceClassification.SUPPORTING,
                    HistoricalEvidenceClassification.CONTRADICTING,
                    HistoricalEvidenceClassification.INCONCLUSIVE,
                ),
            )

    def test_07_missing_historical_datasets_graceful(self) -> None:
        """Gracefully handles missing or empty historical matches without throwing errors."""
        empty_service = PreMortemService()
        # Override matcher with empty return
        empty_service._engine._matcher.match_fingerprint = lambda *args, **kwargs: []

        res = empty_service.analyze_historical_learning(
            target_entity="Isolated-Switch-01",
            reasoning_result=None,
            telemetry_payload={"bandwidth_utilization": 20.0, "packet_loss": 0.0},
        )
        self.assertEqual(len(res.matched_incidents), 0)
        self.assertEqual(res.confidence_adjustment, 0.0)
        self.assertEqual(res.comparisons[0].relationship, HistoricalEvidenceClassification.INCONCLUSIVE)

    def test_08_deterministic_output(self) -> None:
        """Identical inputs produce identical, deterministic historical learning results."""
        res1 = self.service.analyze_historical_learning(
            target_entity="Branch3-Uplink",
            reasoning_result=self.mock_reasoning,
            telemetry_payload={"bandwidth_utilization": 88.5},
        )
        res2 = self.service.analyze_historical_learning(
            target_entity="Branch3-Uplink",
            reasoning_result=self.mock_reasoning,
            telemetry_payload={"bandwidth_utilization": 88.5},
        )
        self.assertEqual(res1.fingerprint.incident_type, res2.fingerprint.incident_type)
        self.assertEqual(res1.confidence_adjustment, res2.confidence_adjustment)
        self.assertEqual(len(res1.comparisons), len(res2.comparisons))

    def test_09_evidence_registry_integration_with_historical_provenance(self) -> None:
        """Historical evidence registered into EvidenceRegistry carries strictly provenance=HISTORICAL."""
        ctx = InvestigationContext(request=InvestigationRequest(target_devices=["Branch3-Uplink"], operator_query="Investigate Branch3-Uplink"))
        res = self.service.analyze_historical_learning(
            target_entity="Branch3-Uplink",
            reasoning_result=self.mock_reasoning,
            context=ctx,
        )
        hist_evidence = ctx.evidence_registry.get_by_provenance("HISTORICAL")
        self.assertGreater(len(hist_evidence), 0)
        for ev in hist_evidence:
            self.assertEqual(ev.provenance, "HISTORICAL")
            self.assertIn("Branch3-Uplink", ev.affected_entity)

    def test_10_confidence_adjustment_bounds(self) -> None:
        """Confidence adjustment is strictly bounded within [-0.50, +0.50]."""
        res = self.service.analyze_historical_learning(
            target_entity="Branch3-Uplink",
            reasoning_result=self.mock_reasoning,
        )
        self.assertGreaterEqual(res.confidence_adjustment, -0.50)
        self.assertLessEqual(res.confidence_adjustment, 0.50)

    def test_11_historical_records_immutability(self) -> None:
        """Historical matches are read-only and do not mutate the underlying knowledge base."""
        res1 = self.service.analyze_historical_learning(target_entity="Branch3-Uplink")
        hist_id_1 = res1.matched_incidents[0].incident_id
        res2 = self.service.analyze_historical_learning(target_entity="Branch3-Uplink")
        hist_id_2 = res2.matched_incidents[0].incident_id
        self.assertEqual(hist_id_1, hist_id_2)

    def test_12_no_duplicate_registration(self) -> None:
        """Repeated analysis on same context does not duplicate historical evidence registrations."""
        ctx = InvestigationContext(request=InvestigationRequest(target_devices=["Branch3-Uplink"], operator_query="Investigate Branch3-Uplink"))
        self.service.analyze_historical_learning(target_entity="Branch3-Uplink", context=ctx)
        count_first = len(ctx.evidence_registry.get_by_provenance("HISTORICAL"))

        self.service.analyze_historical_learning(target_entity="Branch3-Uplink", context=ctx)
        count_second = len(ctx.evidence_registry.get_by_provenance("HISTORICAL"))
        self.assertEqual(count_first, count_second)

    def test_13_cross_agent_explainability_integration(self) -> None:
        """InvestigationContext.build_evidence_lineage properly integrates registered historical evidence."""
        ctx = InvestigationContext(request=InvestigationRequest(target_devices=["Branch3-Uplink"], operator_query="Investigate Branch3-Uplink"))
        self.service.analyze_historical_learning(
            target_entity="Branch3-Uplink",
            reasoning_result=self.mock_reasoning,
            context=ctx,
        )
        lineage = ctx.build_evidence_lineage(target_entity="Branch3-Uplink")
        self.assertGreater(lineage.evidence_count, 0)
        hist_items = [e for e in lineage.timeline if e.provenance == "HISTORICAL"]
        self.assertGreater(len(hist_items), 0)


if __name__ == "__main__":
    unittest.main()
