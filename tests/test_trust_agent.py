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
    ConfidenceFactors,
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
from agents.trust.decision_explainer import DecisionExplainer
from agents.trust.evidence_revalidator import EvidenceRevalidator
from agents.trust.trust_agent import TrustAgent
from agents.trust.trust_models import (
    AutonomyDecision,
    AutonomyPolicy,
    BlastRadiusLevel,
    ConfidenceLevel,
    DecisionExplanationReport,
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


# ===========================================================================
# Phase 3: Comprehensive Confidence & Decision Explainability Tests
# ===========================================================================


class TestComprehensiveDecisionExplainability(unittest.TestCase):
    """
    Tests for DecisionExplainer.generate_comprehensive_explanation and DecisionExplanationReport.
    """

    def setUp(self) -> None:
        self.explainer = DecisionExplainer()
        self.trust_service = TrustService()

    def _create_mock_reasoning_result(self, confidence: float = 0.52) -> ReasoningResult:
        factors = ConfidenceResult(
            overall_confidence=confidence,
            factors=ConfidenceFactors(
                evidence_completeness=0.65,
                prediction_certainty=0.75,
                contradiction_penalty=0.15,
            ),
        )
        cause = RootCause(
            cause_id="RC-01",
            title="WAN Link Congestion & Traffic Saturation",
            probability=confidence,
            description="Elevated traffic on Branch3-Uplink caused severe queueing.",
            affected_components=["Branch3-Uplink"],
            recommended_actions=["Switch to backup link ISP-B"],
        )
        contradiction = Contradiction(
            source_a="TelemetryAgent",
            source_b="CoreRouterProbe",
            description="Core router CPU utilization normal despite edge interface congestion.",
            severity=ContradictionSeverity.MEDIUM,
        )
        conclusion = InvestigationConclusion(
            conclusion_id="CONC-01",
            request_id="REQ-TEST-EXP-01",
            primary_root_cause=cause,
            ranked_root_causes=[],
            confidence_result=factors,
            contradictions=[contradiction],
            explanation=ReasoningExplanation(
                selected_root_cause_title=cause.title,
                why_chosen="Elevated traffic on Branch3-Uplink caused severe queueing.",
                supporting_evidence_summary="High egress bandwidth, Packet loss > 3%",
                rejected_hypotheses=[],
                contradictions_summary="Core router CPU utilization normal",
                evidence_quality_summary="Medium quality due to sampling",
                missing_evidence_summary="Full flow-table dump not captured.",
                recommended_next_steps=cause.recommended_actions,
            ),
        )
        return ReasoningResult(
            request_id="REQ-TEST-EXP-01",
            conclusion=conclusion,
            statistics=ReasoningStatistics(),
        )

    def test_01_complete_decision_explanation_report(self) -> None:
        """Report contains all 10 required fields populated with valid types."""
        reasoning_res = self._create_mock_reasoning_result(confidence=0.52)
        trust_dec = self.trust_service.evaluate_trust(reasoning_res)

        report = self.explainer.generate_comprehensive_explanation(
            target_entity="Branch3-Uplink",
            trust_decision=trust_dec,
            reasoning_result=reasoning_res,
        )

        self.assertIsInstance(report, DecisionExplanationReport)
        self.assertEqual(report.target_entity, "Branch3-Uplink")
        self.assertIn("HUMAN_APPROVAL_REQUIRED", report.final_decision)
        self.assertIsInstance(report.confidence_score, float)
        self.assertEqual(report.confidence_level, "HIGH")
        self.assertIsInstance(report.top_supporting_factors, list)
        self.assertIsInstance(report.top_contradicting_factors, list)
        self.assertIsInstance(report.key_uncertainties, list)
        self.assertIsInstance(report.safety_constraints, list)
        self.assertIsInstance(report.why_recommended_path_won, str)
        self.assertIsInstance(report.why_human_approval_required, str)
        self.assertIsInstance(report.what_would_change_decision, list)

    def test_02_deterministic_confidence_mapping(self) -> None:
        """Confidence scores map to the exact deterministic categorical levels."""
        cases = [
            (0.95, "VERY_HIGH"),
            (0.90, "VERY_HIGH"),
            (0.85, "HIGH"),
            (0.75, "HIGH"),
            (0.60, "MEDIUM"),
            (0.50, "MEDIUM"),
            (0.35, "LOW"),
            (0.25, "LOW"),
            (0.15, "VERY_LOW"),
            (0.00, "VERY_LOW"),
        ]
        for score, expected_level in cases:
            reasoning_res = self._create_mock_reasoning_result(confidence=score)
            trust_dec = self.trust_service.evaluate_trust(reasoning_res)
            # Override trust score to test exact score threshold mapping
            trust_dec.trust_assessment.trust_score.overall_trust_score = score

            report = self.explainer.generate_comprehensive_explanation(
                target_entity="Branch3-Uplink",
                trust_decision=trust_dec,
            )
            self.assertEqual(report.confidence_level, expected_level, f"Failed for score {score}")

    def test_03_supporting_contradicting_partition(self) -> None:
        """Supporting factors and contradicting factors are strictly partitioned."""
        reasoning_res = self._create_mock_reasoning_result(confidence=0.60)
        trust_dec = self.trust_service.evaluate_trust(reasoning_res)

        report = self.explainer.generate_comprehensive_explanation(
            target_entity="Branch3-Uplink",
            trust_decision=trust_dec,
            reasoning_result=reasoning_res,
        )

        self.assertGreater(len(report.top_supporting_factors), 0)
        self.assertGreater(len(report.top_contradicting_factors), 0)
        # Verify contradicting factors contain the expected contradiction
        self.assertTrue(any("Core router CPU" in cf["description"] for cf in report.top_contradicting_factors))

    def test_04_uncertainty_categorization(self) -> None:
        """Uncertainty items are categorized under explicit supported domains."""
        reasoning_res = self._create_mock_reasoning_result(confidence=0.52)
        report = self.explainer.generate_comprehensive_explanation(
            target_entity="Branch3-Uplink",
            reasoning_result=reasoning_res,
        )
        categories = [u["category"] for u in report.key_uncertainties]
        self.assertIn("insufficient_evidence", categories)
        self.assertIn("contradictory_evidence", categories)
        self.assertIn("unresolved_telemetry", categories)

    def test_05_topology_evidence_integration(self) -> None:
        """Topology impact result seamlessly integrates into supporting factors and uncertainties."""
        class MockTopoImpact:
            blast_radius_level = "CRITICAL"
            impact_percentage = 83.33
            single_points_of_failure = ["branch3-uplink", "fw-01", "rtr-01"]

        report = self.explainer.generate_comprehensive_explanation(
            target_entity="Branch3-Uplink",
            topology_impact=MockTopoImpact(),
        )
        self.assertTrue(any(sf["factor"] == "Topology Blast Radius" for sf in report.top_supporting_factors))
        self.assertTrue(any(u["category"] == "topology_uncertainty" for u in report.key_uncertainties))

    def test_06_provider_recommendation_rationale(self) -> None:
        """Winner rationale is derived from comparative path scores and metric evaluations."""
        from agents.path_decision.path_models import FailoverRecommendation, PathDecisionResult, PathEvaluation, PathScore

        scores = [
            PathScore(path_id="p2", provider_name="ISP-B", total_score=94.1, rank=1),
            PathScore(path_id="p1", provider_name="ISP-A", total_score=42.5, rank=2),
        ]
        evals = [
            PathEvaluation(path_id="p2", provider_name="ISP-B", health=94.0, packet_loss_percent=0.0, latency_ms=12.0),
            PathEvaluation(path_id="p1", provider_name="ISP-A", health=40.0, packet_loss_percent=3.0, latency_ms=45.0),
        ]
        rec = FailoverRecommendation(
            current_provider="ISP-A",
            recommended_provider="ISP-B",
            current_failure_risk=0.88,
        )
        path_res = PathDecisionResult(
            request_id="REQ-PATH-01",
            scores=scores,
            evaluations=evals,
            recommendation=rec,
        )

        report = self.explainer.generate_comprehensive_explanation(
            target_entity="Branch3-Uplink",
            path_decision_result=path_res,
        )

        self.assertIn("ISP-B", report.why_recommended_path_won)
        self.assertIn("94.1", report.why_recommended_path_won)
        self.assertIn("ISP-A", report.why_recommended_path_won)

    def test_07_human_approval_rationale(self) -> None:
        """Human approval explanation reflects the actual autonomy policy constraint triggered."""
        reasoning_res = self._create_mock_reasoning_result(confidence=0.52)
        trust_dec = self.trust_service.evaluate_trust(reasoning_res)

        report = self.explainer.generate_comprehensive_explanation(
            target_entity="Branch3-Uplink",
            trust_decision=trust_dec,
        )

        self.assertIn("trust score", report.why_human_approval_required.lower())
        self.assertIn("0.85", report.why_human_approval_required)

        # Also test with high blast radius
        trust_dec_high_blast = self.trust_service.evaluate_trust(
            self._create_mock_reasoning_result(confidence=0.95),
        )
        trust_dec_high_blast.trust_assessment.blast_radius.potential_action_level = BlastRadiusLevel.HIGH
        report_high_blast = self.explainer.generate_comprehensive_explanation(
            target_entity="Branch3-Uplink",
            trust_decision=trust_dec_high_blast,
        )
        self.assertIn("blast radius", report_high_blast.why_human_approval_required.lower())

    def test_08_threshold_policy_grounded_change_conditions(self) -> None:
        """What would change decision references valid policy rules and conditions."""
        reasoning_res = self._create_mock_reasoning_result(confidence=0.52)
        trust_dec = self.trust_service.evaluate_trust(reasoning_res)

        report = self.explainer.generate_comprehensive_explanation(
            target_entity="Branch3-Uplink",
            trust_decision=trust_dec,
        )

        target_decisions = [c["target_decision"] for c in report.what_would_change_decision]
        self.assertIn("AUTO_ELIGIBLE", target_decisions)
        self.assertIn("KEEP_CURRENT_PATH", target_decisions)
        self.assertIn("BLOCKED", target_decisions)

    def test_09_deterministic_output(self) -> None:
        """Repeated invocations with identical inputs produce identical explanation outputs."""
        reasoning_res = self._create_mock_reasoning_result(confidence=0.52)
        trust_dec = self.trust_service.evaluate_trust(reasoning_res)

        report1 = self.explainer.generate_comprehensive_explanation("Branch3-Uplink", trust_decision=trust_dec)
        report2 = self.explainer.generate_comprehensive_explanation("Branch3-Uplink", trust_decision=trust_dec)

        self.assertEqual(report1.final_decision, report2.final_decision)
        self.assertEqual(report1.confidence_score, report2.confidence_score)
        self.assertEqual(report1.confidence_level, report2.confidence_level)
        self.assertEqual(report1.why_human_approval_required, report2.why_human_approval_required)
        self.assertEqual(len(report1.what_would_change_decision), len(report2.what_would_change_decision))

    def test_10_no_hidden_chain_of_thought_exposure(self) -> None:
        """Report fields contains strictly factors, calculations, and factual rationale without CoT scratchpads."""
        reasoning_res = self._create_mock_reasoning_result(confidence=0.52)
        trust_dec = self.trust_service.evaluate_trust(reasoning_res)

        report = self.explainer.generate_comprehensive_explanation(
            target_entity="Branch3-Uplink",
            trust_decision=trust_dec,
            reasoning_result=reasoning_res,
        )

        prohibited_terms = ["<thought>", "</thought>", "chain_of_thought", "internal_scratchpad", "system_prompt"]
        report_dict_str = str(report.model_dump())
        for term in prohibited_terms:
            self.assertNotIn(term, report_dict_str)


if __name__ == "__main__":
    unittest.main()

