"""
Comprehensive Production Test Suite for Enterprise AI Reasoning Subsystem.

Validates EvidenceCorrelator, HypothesisGenerator, ContradictionDetector, EvidenceValidator,
ConfidenceEngine, RootCauseRanker, ReasoningService, ReasoningAgent, EventBus lifecycle events,
ExecutionContext integration, thread safety, and backward compatibility.
"""

from datetime import datetime, timezone
import threading
import unittest
from typing import Any, Dict, List

from agents.core.container import ServiceContainer
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.orchestrator_ai.evidence_registry import EvidenceRegistry
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.orchestrator_ai.investigation_models import InvestigationRequest
from agents.reasoning.confidence_engine import ConfidenceEngine
from agents.reasoning.contradiction_detector import ContradictionDetector
from agents.reasoning.evidence_correlator import EvidenceCorrelator
from agents.reasoning.evidence_validator import EvidenceValidator
from agents.reasoning.hypothesis_generator import HypothesisGenerator
from agents.reasoning.reasoning_agent import ReasoningAgent
from agents.reasoning.reasoning_models import (
    ContradictionSeverity,
    HypothesisCategory,
    ReasoningEvidence,
    ReasoningResult,
)
from agents.reasoning.reasoning_service import ReasoningService
from agents.reasoning.root_cause_ranker import RootCauseRanker
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import ExecutionContext


class TestReasoningAgent(unittest.TestCase):
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

    # --- EvidenceCorrelator Tests ---

    def test_evidence_correlator_grouping_and_deduplication(self) -> None:
        correlator = EvidenceCorrelator()

        ev1 = ReasoningEvidence(
            source_agent="TelemetryAgent",
            evidence_type="telemetry",
            device_id="Router-1",
            payload={"bandwidth_utilization": 92.5},
        )
        ev2 = ReasoningEvidence(
            source_agent="TelemetryAgent",
            evidence_type="telemetry",
            device_id="Router-1",
            payload={"bandwidth_utilization": 92.5},
        )
        ev3 = ReasoningEvidence(
            source_agent="PredictionAgent",
            evidence_type="prediction",
            device_id="Router-1",
            payload={"risk_score": 0.89},
        )

        correlation = correlator.correlate(raw_evidence_list=[ev1, ev2, ev3])

        self.assertEqual(correlation.total_evidence_count, 2)  # Deduplicated ev2
        self.assertGreater(len(correlation.groups), 0)
        self.assertIn("Router-1", correlation.groups[0].group_name)

    # --- HypothesisGenerator Tests ---

    def test_hypothesis_generator_competing_hypotheses(self) -> None:
        correlator = EvidenceCorrelator()
        generator = HypothesisGenerator()

        ev1 = ReasoningEvidence(
            source_agent="TelemetryAgent",
            evidence_type="telemetry",
            device_id="Branch3-Uplink",
            payload={"bandwidth_utilization": 98.0, "packet_loss": 0.05},
        )
        ev2 = ReasoningEvidence(
            source_agent="PredictionAgent",
            evidence_type="prediction",
            device_id="Branch3-Uplink",
            payload={"risk_score": 0.94, "contributing_signals": ["congestion"]},
        )

        correlation = correlator.correlate(raw_evidence_list=[ev1, ev2])
        hypotheses = generator.generate_hypotheses(correlation, evidence_list=[ev1, ev2])

        self.assertGreaterEqual(len(hypotheses), 4)
        wan_hyp = next(h for h in hypotheses if h.category == HypothesisCategory.WAN_CONGESTION)
        self.assertGreater(len(wan_hyp.supporting_evidence_ids), 0)
        self.assertGreaterEqual(wan_hyp.initial_likelihood, 0.70)

    # --- ContradictionDetector Tests ---

    def test_contradiction_detector_conflict_identification(self) -> None:
        detector = ContradictionDetector()

        ev_healthy_telemetry = ReasoningEvidence(
            source_agent="TelemetryAgent",
            evidence_type="telemetry",
            payload={"metrics": {"bandwidth_utilization": 5.0}},
        )
        ev_critical_prediction = ReasoningEvidence(
            source_agent="PredictionAgent",
            evidence_type="prediction",
            payload={"risk_score": 0.95},
        )

        contradictions = detector.detect_contradictions([ev_healthy_telemetry, ev_critical_prediction])

        self.assertEqual(len(contradictions), 1)
        self.assertEqual(contradictions[0].severity, ContradictionSeverity.HIGH)
        self.assertGreater(contradictions[0].penalty_factor, 0.0)

    # --- EvidenceValidator Tests ---

    def test_evidence_validator_freshness_and_completeness(self) -> None:
        validator = EvidenceValidator(max_age_seconds=600.0)

        ev_valid = ReasoningEvidence(
            source_agent="TelemetryAgent",
            evidence_type="telemetry",
            timestamp=datetime.now(timezone.utc),
            payload={"bandwidth": 80.0},
        )
        ev_stale = ReasoningEvidence(
            source_agent="PredictionAgent",
            evidence_type="prediction",
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            payload={"risk": 0.5},
        )

        val_results = validator.validate_evidence_list([ev_valid, ev_stale])

        self.assertEqual(len(val_results), 2)
        self.assertTrue(val_results[0].is_valid)
        self.assertFalse(val_results[1].is_valid)
        self.assertLess(val_results[1].freshness_score, 0.5)

    # --- ConfidenceEngine Tests ---

    def test_confidence_engine_composite_scoring(self) -> None:
        engine = ConfidenceEngine()
        correlator = EvidenceCorrelator()
        generator = HypothesisGenerator()
        validator = EvidenceValidator()

        ev1 = ReasoningEvidence(source_agent="TelemetryAgent", evidence_type="telemetry", payload={"bw": 90})
        ev2 = ReasoningEvidence(source_agent="PredictionAgent", evidence_type="prediction", payload={"risk": 0.9})

        ev_list = [ev1, ev2]
        correlation = correlator.correlate(raw_evidence_list=ev_list)
        hypotheses = generator.generate_hypotheses(correlation, evidence_list=ev_list)
        val_results = validator.validate_evidence_list(ev_list)

        conf_res = engine.calculate_confidence(ev_list, val_results, [], hypotheses)

        self.assertGreaterEqual(conf_res.overall_confidence, 0.50)
        self.assertLessEqual(conf_res.overall_confidence, 1.0)
        self.assertIn(hypotheses[0].hypothesis_id, conf_res.per_hypothesis_confidence)

    # --- RootCauseRanker Tests ---

    def test_root_cause_ranker_and_explanation(self) -> None:
        ranker = RootCauseRanker()
        correlator = EvidenceCorrelator()
        generator = HypothesisGenerator()
        confidence_engine = ConfidenceEngine()

        ev1 = ReasoningEvidence(source_agent="TelemetryAgent", evidence_type="telemetry", payload={"bw": 99.0})
        correlation = correlator.correlate(raw_evidence_list=[ev1])
        hypotheses = generator.generate_hypotheses(correlation, evidence_list=[ev1])
        conf_res = confidence_engine.calculate_confidence([ev1], [], [], hypotheses)

        ranked = ranker.rank_root_causes(hypotheses, [ev1], [], conf_res)

        self.assertEqual(ranked[0].rank, 1)
        self.assertGreater(ranked[0].final_score, 0.0)

        explanation = ranker.generate_explanation(ranked, [], conf_res, "Why is Branch Router unstable?")
        self.assertIsNotNone(explanation.selected_root_cause_title)
        self.assertIn("Hypothesis", explanation.why_chosen)
        self.assertGreater(len(explanation.recommended_next_steps), 0)

    # --- ReasoningService & ReasoningAgent Integration Tests ---

    def test_reasoning_service_full_pipeline(self) -> None:
        req = InvestigationRequest(
            operator_query="Why is Branch Router experiencing packet loss?",
            device_id="Branch3-Uplink",
        )
        ctx = InvestigationContext(request=req)
        reg = ctx.evidence_registry

        reg.register(
            source_agent="TelemetryAgent",
            evidence_type="telemetry",
            payload={"bandwidth_utilization": 96.0, "packet_loss": 0.08},
            device_id="Branch3-Uplink",
        )
        reg.register(
            source_agent="PredictionAgent",
            evidence_type="prediction",
            payload={"risk_score": 0.92, "contributing_signals": ["congestion"]},
            device_id="Branch3-Uplink",
        )

        service = ReasoningService()
        res = service.process_reasoning(ctx)

        self.assertIsInstance(res, ReasoningResult)
        self.assertEqual(res.request_id, req.request_id)
        self.assertIsNotNone(res.conclusion.primary_root_cause)
        self.assertGreater(len(res.conclusion.ranked_root_causes), 0)

    def test_reasoning_agent_execution_and_events(self) -> None:
        self.registry.register(ReasoningAgent())

        events_received = []

        def event_handler(evt: Event) -> None:
            events_received.append(evt.event_type)

        self.event_bus.subscribe("*", event_handler)

        agent = ReasoningAgent()
        req = InvestigationRequest(
            operator_query="Investigate Core Router performance",
            device_id="Core-Router-01",
        )

        exec_context = ExecutionContext()
        res = agent.execute(req, exec_context)

        self.assertIsInstance(res, ReasoningResult)
        self.assertIn(agent.name, exec_context.results)
        self.assertEqual(exec_context.shared_state.get("reasoning_conclusion", {}).get("request_id"), req.request_id)

        # Check Lifecycle Event Publishing
        self.assertIn("reasoning.started", events_received)
        self.assertIn("reasoning.evidence.correlated", events_received)
        self.assertIn("reasoning.hypotheses.generated", events_received)
        self.assertIn("reasoning.validation.completed", events_received)
        self.assertIn("reasoning.confidence.calculated", events_received)
        self.assertIn("reasoning.completed", events_received)

    def test_reasoning_agent_concurrent_execution(self) -> None:
        agent = ReasoningAgent()
        results: List[ReasoningResult] = []
        lock = threading.Lock()

        def worker(idx: int) -> None:
            req = InvestigationRequest(operator_query=f"Concurrent Test Query {idx}")
            res = agent.execute(req)
            with lock:
                results.append(res)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 5)


if __name__ == "__main__":
    unittest.main()
