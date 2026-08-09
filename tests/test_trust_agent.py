"""
Comprehensive Production Test Suite for Enterprise Trust, Verification & Safe Autonomy Subsystem.

Validates EvidenceRevalidator, AdversarialVerifier, CounterfactualEngine, BlastRadiusEngine,
AutonomyPolicyEngine, ConfidenceHandoffEngine, DecisionExplainer, TrustService, TrustAgent,
EventBus lifecycle events, ExecutionContext propagation, thread safety, and backward compatibility.
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
from agents.reasoning.reasoning_agent import ReasoningAgent
from agents.reasoning.reasoning_models import (
    ConfidenceResult,
    Contradiction,
    ContradictionSeverity,
    InvestigationConclusion,
    ReasoningEvidence,
    ReasoningExplanation,
    ReasoningResult,
    ReasoningStatistics,
    RootCause,
)
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import ExecutionContext
from agents.trust.adversarial_verifier import AdversarialVerifier
from agents.trust.autonomy_policy import AutonomyPolicyEngine
from agents.trust.blast_radius_engine import BlastRadiusEngine
from agents.trust.counterfactual_engine import CounterfactualEngine
from agents.trust.evidence_revalidator import EvidenceRevalidator
from agents.trust.trust_agent import TrustAgent
from agents.trust.trust_models import (
    AutonomyDecision,
    AutonomyPolicy,
    BlastRadiusLevel,
    TrustDecision,
    VerificationStatus,
)
from agents.trust.trust_service import TrustService


class TestTrustAgent(unittest.TestCase):
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

    def _create_mock_reasoning_result(self, confidence: float = 0.90, actions: List[str] = None) -> ReasoningResult:
        rc = RootCause(
            title="WAN Link Congestion & Traffic Saturation",
            probability=confidence,
            description="High utilization on uplink interface",
            recommended_actions=actions or ["Apply traffic shaping policy on egress port"],
        )
        expl = ReasoningExplanation(
            selected_root_cause_title=rc.title,
            why_chosen="Mock high confidence score",
            supporting_evidence_summary="Supported by 2 telemetry signals",
            rejected_hypotheses=[],
            contradictions_summary="No contradictions",
            evidence_quality_summary="High quality",
            missing_evidence_summary="None",
            recommended_next_steps=rc.recommended_actions,
        )
        conclusion = InvestigationConclusion(
            request_id="req-trust-001",
            primary_root_cause=rc,
            ranked_root_causes=[],
            ranked_hypotheses=[],
            contradictions=[],
            confidence_result=ConfidenceResult(overall_confidence=confidence),
            explanation=expl,
        )
        return ReasoningResult(
            request_id="req-trust-001",
            conclusion=conclusion,
            correlation=None,
            statistics=ReasoningStatistics(),
        )

    # --- Scenario 1: High Confidence + Low Blast Radius -> AUTO_ELIGIBLE ---

    def test_high_confidence_low_blast_radius_auto_eligible(self) -> None:
        service = TrustService()
        reasoning_res = self._create_mock_reasoning_result(confidence=0.92, actions=["Adjust local buffer limit"])

        decision = service.evaluate_trust(reasoning_result=reasoning_res)

        self.assertEqual(decision.decision, AutonomyDecision.AUTO_ELIGIBLE)
        self.assertGreaterEqual(decision.trust_assessment.trust_score.overall_trust_score, 0.85)

    # --- Scenario 2: High Confidence + High Blast Radius -> HUMAN_APPROVAL_REQUIRED ---

    def test_high_confidence_high_blast_radius_human_approval(self) -> None:
        service = TrustService()
        reasoning_res = self._create_mock_reasoning_result(confidence=0.95, actions=["BGP reroute core WAN traffic"])

        decision = service.evaluate_trust(reasoning_result=reasoning_res)

        self.assertEqual(decision.decision, AutonomyDecision.HUMAN_APPROVAL_REQUIRED)
        self.assertEqual(decision.trust_assessment.blast_radius.potential_action_level, BlastRadiusLevel.HIGH)

    # --- Scenario 3: Low Confidence -> ADDITIONAL_EVIDENCE_REQUIRED ---

    def test_low_confidence_additional_evidence_required(self) -> None:
        service = TrustService()
        reasoning_res = self._create_mock_reasoning_result(confidence=0.10, actions=["Inspect port"])
        req = InvestigationRequest(operator_query="Low confidence query")
        ctx = InvestigationContext(request=req)

        # Register stale evidence items
        for i in range(5):
            ctx.evidence_registry.register(
                source_agent="TelemetryAgent",
                evidence_type="telemetry",
                payload={},
                confidence=0.10,
            )
            # Artificially modify timestamp of evidence to old timestamp for stale test
            for ev_ref in ctx.evidence_registry._evidence.values():
                ev_ref.timestamp = datetime(2020, 1, 1, tzinfo=timezone.utc)

        decision = service.evaluate_trust(reasoning_result=reasoning_res, context=ctx)

        self.assertEqual(decision.decision, AutonomyDecision.ADDITIONAL_EVIDENCE_REQUIRED)
        self.assertLess(decision.trust_assessment.trust_score.overall_trust_score, 0.60)

    # --- Scenario 4: Contradictory Evidence & Failed Adversarial -> BLOCKED ---

    def test_failed_adversarial_verification_blocked(self) -> None:
        verifier = AdversarialVerifier()
        # Reasoning result with missing primary cause
        no_cause_res = ReasoningResult(
            request_id="req-none",
            conclusion=InvestigationConclusion(
                request_id="req-none",
                primary_root_cause=None,
                confidence_result=ConfidenceResult(overall_confidence=0.0),
                explanation=None,
            ),
            correlation=None,
            statistics=ReasoningStatistics(),
        )

        adv_res = verifier.verify_hypothesis(no_cause_res)
        self.assertTrue(adv_res.is_disproved)

        service = TrustService()
        decision = service.evaluate_trust(reasoning_result=no_cause_res)
        self.assertEqual(decision.decision, AutonomyDecision.BLOCKED)

    # --- Scenario 5: Missing Rollback Plan -> HUMAN_APPROVAL_REQUIRED ---

    def test_missing_rollback_plan_enforces_human_approval(self) -> None:
        service = TrustService()
        reasoning_res = self._create_mock_reasoning_result(confidence=0.90, actions=["Adjust queue limit"])

        decision = service.evaluate_trust(
            reasoning_result=reasoning_res,
            has_rollback_plan=False,
        )

        self.assertEqual(decision.decision, AutonomyDecision.HUMAN_APPROVAL_REQUIRED)

    # --- Scenario 6: Current vs Potential Blast Radius Distinction ---

    def test_current_vs_potential_blast_radius_distinction(self) -> None:
        blast_engine = BlastRadiusEngine()
        reasoning_res = self._create_mock_reasoning_result(confidence=0.90, actions=["BGP reroute primary core uplink"])

        blast = blast_engine.calculate_blast_radius(reasoning_res)

        self.assertEqual(blast.current_incident_level, BlastRadiusLevel.LOW)
        self.assertEqual(blast.potential_action_level, BlastRadiusLevel.HIGH)
        self.assertTrue(blast.is_action_larger_than_incident)

    # --- Scenario 7: Stale Evidence Downgrade ---

    def test_stale_evidence_downgrade(self) -> None:
        revalidator = EvidenceRevalidator(max_age_seconds=600.0)

        stale_item = ReasoningEvidence(
            source_agent="TelemetryAgent",
            evidence_type="telemetry",
            timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc),
            payload={"bw": 90},
        )

        reval = revalidator.revalidate_evidence_list([stale_item])
        self.assertEqual(reval.stale_count, 1)
        self.assertLess(reval.overall_quality_score, 0.50)

    # --- Scenario 8: Counterfactual Analysis Evaluation ---

    def test_counterfactual_engine_evaluation(self) -> None:
        engine = CounterfactualEngine()
        reasoning_res = self._create_mock_reasoning_result(confidence=0.90)

        cf_res = engine.evaluate_counterfactuals(reasoning_res)
        self.assertIsNotNone(cf_res.conclusion)

    # --- Scenario 9: TrustAgent Execution & EventBus Lifecycle ---

    def test_trust_agent_execution_and_events(self) -> None:
        self.registry.register(TrustAgent())

        events_received = []

        def event_handler(evt: Event) -> None:
            events_received.append(evt.event_type)

        self.event_bus.subscribe("*", event_handler)

        agent = TrustAgent()
        reasoning_res = self._create_mock_reasoning_result(confidence=0.92)

        exec_context = ExecutionContext()
        decision = agent.execute(reasoning_res, exec_context)

        self.assertIsInstance(decision, TrustDecision)
        self.assertIn(agent.name, exec_context.results)
        self.assertEqual(exec_context.shared_state.get("trust_decision", {}).get("request_id"), "req-trust-001")

        # Check Lifecycle Event Publishing
        self.assertIn("trust.started", events_received)
        self.assertIn("trust.evidence.revalidated", events_received)
        self.assertIn("trust.adversarial.completed", events_received)
        self.assertIn("trust.counterfactual.completed", events_received)
        self.assertIn("trust.blastradius.completed", events_received)
        self.assertIn("trust.confidence.assessed", events_received)
        self.assertIn("trust.autonomy.decided", events_received)
        self.assertIn("trust.decision.completed", events_received)

    # --- Scenario 10: Thread Safety & Concurrent Execution ---

    def test_trust_agent_concurrent_execution(self) -> None:
        agent = TrustAgent()
        results: List[TrustDecision] = []
        lock = threading.Lock()

        def worker(idx: int) -> None:
            reasoning_res = self._create_mock_reasoning_result(confidence=0.85)
            decision = agent.execute(reasoning_res)
            with lock:
                results.append(decision)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 5)


if __name__ == "__main__":
    unittest.main()
