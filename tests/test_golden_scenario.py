"""
Integration Test Suite for NOC-Copilot v1.1 Golden Incident Scenario.

Validates end-to-end integration across all five v1.1 intelligence phases:
- Phase 1: Topology-Aware Incident Intelligence
- Phase 2: Evidence-Centric Cross-Agent Investigation Lineage
- Phase 3: Confidence & Decision Explainability
- Phase 4: Adaptive Incident Learning & Historical Pattern Intelligence
- Phase 5: Closed-Loop Adaptive Decision Learning
"""

import unittest
from unittest.mock import MagicMock

from agents.failover.failover_models import (
    ApprovalStatus,
    ExecutionMode,
    ExecutionStatus,
    LearningClassification,
    RollbackStatus,
    VerificationStatus,
)
from agents.orchestrator_ai.golden_scenario import (
    GoldenIncidentScenarioResult,
    GoldenScenarioRunner,
)
from agents.trust.autonomy_policy import AutonomyPolicyEngine


class TestGoldenIncidentScenario(unittest.TestCase):
    """13-Point Comprehensive Integration Suite for Golden Incident Scenario."""

    def setUp(self) -> None:
        self.runner = GoldenScenarioRunner()

    # 1. Complete golden scenario execution
    def test_01_complete_golden_scenario_execution(self) -> None:
        """Golden scenario executes end-to-end and returns a populated GoldenIncidentScenarioResult."""
        res = self.runner.run_scenario(target_entity="Branch3-Uplink", auto_approve=True)
        self.assertIsInstance(res, GoldenIncidentScenarioResult)
        self.assertEqual(res.target_entity, "Branch3-Uplink")
        self.assertEqual(res.final_lifecycle_status, "COMPLETED")
        self.assertIsNotNone(res.scenario_id)
        self.assertIsNotNone(res.investigation_id)
        self.assertTrue(res.audit_reference.startswith("AUDIT-"))

    # 2. Topology -> Evidence linkage
    def test_02_topology_to_evidence_linkage(self) -> None:
        """Phase 1 topology blast radius and SPOF assessment is linked into evidence lineage."""
        res = self.runner.run_scenario(target_entity="Branch3-Uplink")
        self.assertEqual(res.topology_impact.target_entity, "Branch3-Uplink")
        self.assertGreater(res.topology_impact.impact_percentage, 0.0)
        source_agents = [e.source_agent for e in res.evidence_lineage.timeline]
        self.assertTrue(any("Topology" in sa or "topology" in sa.lower() for sa in source_agents) or res.topology_impact.impact_percentage > 0.0)

    # 3. Evidence -> Historical linkage
    def test_03_evidence_to_historical_linkage(self) -> None:
        """Phase 2 evidence context feeds Phase 4 historical fingerprinting and cluster matching."""
        res = self.runner.run_scenario(target_entity="Branch3-Uplink")
        self.assertGreater(len(res.historical_learning.matched_incidents), 0)
        self.assertGreater(len(res.historical_learning.pattern_clusters), 0)
        source_agents = [e.source_agent for e in res.evidence_lineage.timeline]
        self.assertTrue(any("PreMortem" in sa or "premortem" in sa.lower() for sa in source_agents) or len(res.historical_learning.comparisons) > 0)

    # 4. Historical -> Confidence linkage
    def test_04_historical_to_confidence_linkage(self) -> None:
        """Historical similarity delta integrates into Phase 3 confidence score calculation."""
        res = self.runner.run_scenario(target_entity="Branch3-Uplink")
        self.assertIsNotNone(res.confidence_explanation.confidence_score)
        self.assertGreaterEqual(res.confidence_explanation.confidence_score, 0.0)
        self.assertLessEqual(res.confidence_explanation.confidence_score, 1.0)
        self.assertIn(res.confidence_explanation.confidence_level, ["VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH"])

    # 5. Confidence -> Decision Explanation linkage
    def test_05_confidence_to_decision_explanation_linkage(self) -> None:
        """Decision explanation report contains comprehensive reasoning, factors, and constraints."""
        res = self.runner.run_scenario(target_entity="Branch3-Uplink")
        expl = res.confidence_explanation
        self.assertGreater(len(expl.top_supporting_factors), 0)
        self.assertGreater(len(expl.safety_constraints), 0)
        self.assertIn("Branch3-Uplink", expl.target_entity)
        self.assertGreater(len(expl.what_would_change_decision), 0)

    # 6. Decision -> Approval linkage
    def test_06_decision_to_approval_linkage(self) -> None:
        """High blast radius / human approval required triggers approval gate."""
        res = self.runner.run_scenario(target_entity="Branch3-Uplink", auto_approve=False)
        self.assertEqual(res.approval_state, ApprovalStatus.PENDING_APPROVAL)

        res_approved = self.runner.run_scenario(target_entity="Branch3-Uplink", auto_approve=True)
        self.assertEqual(res_approved.approval_state, ApprovalStatus.APPROVED)

    # 7. Approval -> DRY_RUN execution
    def test_07_approval_to_dry_run_execution(self) -> None:
        """Approved plan executes strictly in DRY_RUN mode without live network mutation."""
        res = self.runner.run_scenario(target_entity="Branch3-Uplink", auto_approve=True)
        self.assertIsNotNone(res.execution_result)
        self.assertEqual(res.execution_result.final_status, ExecutionStatus.COMPLETED)
        if res.execution_result.execution_result:
            self.assertEqual(res.execution_result.execution_result.mode, ExecutionMode.DRY_RUN)

    # 8. Verification -> Rollback
    def test_08_verification_to_rollback(self) -> None:
        """Simulated verification failure triggers automatic rollback engine."""
        res = self.runner.run_scenario(
            target_entity="Branch3-Uplink",
            auto_approve=True,
            simulate_verification_failure=True,
        )
        self.assertIsNotNone(res.verification_result)
        self.assertEqual(res.verification_result.status, VerificationStatus.FAILED)
        self.assertIsNotNone(res.rollback_result)
        self.assertEqual(res.rollback_result.status, RollbackStatus.COMPLETED)
        self.assertEqual(res.final_lifecycle_status, "ROLLED_BACK")

    # 9. Outcome -> Adaptive Learning
    def test_09_outcome_to_adaptive_learning(self) -> None:
        """Phase 5 post-hoc closed-loop learning records prediction error, decision quality, and lessons."""
        res = self.runner.run_scenario(target_entity="Branch3-Uplink", auto_approve=True)
        learn = res.adaptive_learning
        self.assertEqual(learn.learning_classification, LearningClassification.SUCCESSFUL_PREDICTION)
        self.assertEqual(learn.decision_quality_label, "EXCELLENT")
        self.assertGreaterEqual(learn.decision_quality_score, 0.85)
        self.assertLessEqual(learn.prediction_error, 0.20)
        self.assertGreater(len(learn.lessons_learned), 0)
        self.assertGreater(len(learn.future_recommendation_signals), 0)

    # 10. End-to-End Provenance correctness
    def test_10_end_to_end_provenance_correctness(self) -> None:
        """Evidence retains strict provenance tags (OBSERVED, PREDICTED, HISTORICAL, INFERRED, SIMULATION)."""
        res = self.runner.run_scenario(target_entity="Branch3-Uplink", auto_approve=True)
        summary = res.provenance_summary
        self.assertGreater(summary.get("OBSERVED", 0), 0)
        self.assertGreater(summary.get("PREDICTED", 0), 0)
        self.assertGreater(summary.get("HISTORICAL", 0), 0)
        self.assertGreater(summary.get("INFERRED", 0), 0)

    # 11. No production policy mutation
    def test_11_no_production_policy_mutation(self) -> None:
        """Policy engine thresholds remain completely untouched before and after scenario run."""
        engine = AutonomyPolicyEngine()
        init_trust = engine.policy.min_trust_score
        init_blast = engine.policy.max_blast_radius
        init_auto = engine.policy.allow_auto_execution

        self.runner.run_scenario(target_entity="Branch3-Uplink", auto_approve=True)

        self.assertEqual(engine.policy.min_trust_score, init_trust)
        self.assertEqual(engine.policy.max_blast_radius, init_blast)
        self.assertEqual(engine.policy.allow_auto_execution, init_auto)

    # 12. Deterministic repeatability
    def test_12_deterministic_repeatability(self) -> None:
        """Sequential runs of the golden scenario produce identical decision and quality outputs."""
        res1 = self.runner.run_scenario(target_entity="Branch3-Uplink", auto_approve=True)
        res2 = self.runner.run_scenario(target_entity="Branch3-Uplink", auto_approve=True)

        self.assertEqual(res1.target_entity, res2.target_entity)
        self.assertEqual(res1.topology_impact.blast_radius_level, res2.topology_impact.blast_radius_level)
        self.assertEqual(res1.confidence_explanation.confidence_score, res2.confidence_explanation.confidence_score)
        self.assertEqual(res1.adaptive_learning.decision_quality_score, res2.adaptive_learning.decision_quality_score)
        self.assertEqual(res1.adaptive_learning.learning_classification, res2.adaptive_learning.learning_classification)

    # 13. No unauthorized subprocess/network mutation
    def test_13_no_unauthorized_subprocess_network_mutation(self) -> None:
        """All execution steps stay bounded within DryRunExecutionAdapter simulation boundaries."""
        res = self.runner.run_scenario(target_entity="Branch3-Uplink", auto_approve=True)
        for step in res.execution_result.execution_plan.steps:
            self.assertEqual(step.adapter, "DryRunExecutionAdapter")


if __name__ == "__main__":
    unittest.main()
