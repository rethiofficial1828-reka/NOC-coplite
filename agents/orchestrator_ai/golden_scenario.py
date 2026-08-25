"""
Golden Incident Scenario Integration Subsystem for NOC-Copilot v1.1.

Coordinates end-to-end multi-agent execution across all five intelligence phases:
- Phase 1: Topology-Aware Incident Intelligence
- Phase 2: Evidence-Centric Cross-Agent Investigation Lineage
- Phase 3: Confidence & Decision Explainability
- Phase 4: Adaptive Incident Learning & Historical Pattern Intelligence
- Phase 5: Closed-Loop Adaptive Decision Learning

Maintains strict read-only safety, zero production policy mutation, and explicit provenance tracking.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from agents.core.logger import get_agent_logger
from agents.failover.failover_models import (
    AdaptiveDecisionLearningResult,
    ApprovalStatus,
    ExecutionMode,
    FailoverResult,
    RollbackResult,
    VerificationResult,
    VerificationStatus,
)
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.orchestrator_ai.investigation_models import (
    InvestigationEvidenceLineage,
    InvestigationRequest,
)
from agents.path_decision.path_models import PathDecisionResult
from agents.premortem.premortem_models import HistoricalIncidentLearningResult
from agents.topology.topology_models import TopologyIncidentImpact
from agents.trust.trust_models import DecisionExplanationReport, TrustDecision

logger = get_agent_logger("GoldenScenarioRunner")


class GoldenIncidentScenarioResult(BaseModel):
    """
    Strongly-typed integration result payload capturing the complete
    end-to-end golden incident lifecycle across all five v1.1 intelligence phases.
    """

    model_config = ConfigDict(frozen=False)

    scenario_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    investigation_id: str = Field(...)
    target_entity: str = Field(...)
    incident_state: Dict[str, Any] = Field(default_factory=dict)
    topology_impact: TopologyIncidentImpact = Field(...)
    evidence_lineage: InvestigationEvidenceLineage = Field(...)
    historical_learning: HistoricalIncidentLearningResult = Field(...)
    confidence_explanation: DecisionExplanationReport = Field(...)
    trust_decision: Optional[Any] = Field(default=None)
    path_decision: PathDecisionResult = Field(...)
    approval_state: ApprovalStatus = Field(...)
    execution_result: Optional[FailoverResult] = Field(default=None)
    verification_result: Optional[VerificationResult] = Field(default=None)
    rollback_result: Optional[RollbackResult] = Field(default=None)
    adaptive_learning: AdaptiveDecisionLearningResult = Field(...)
    final_lifecycle_status: str = Field(...)
    provenance_summary: Dict[str, int] = Field(default_factory=dict)
    audit_reference: str = Field(...)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GoldenScenarioRunner:
    """
    Deterministic end-to-end orchestrator for executing the Golden Incident Scenario
    without duplicating domain logic, bypassing trust/approval checkpoints, or mutating policy.
    """

    def __init__(
        self,
        topology_service: Optional[Any] = None,
        premortem_service: Optional[Any] = None,
        path_decision_service: Optional[Any] = None,
        trust_service: Optional[Any] = None,
        failover_service: Optional[Any] = None,
    ) -> None:
        if topology_service is None:
            from agents.topology.topology_service import TopologyService
            topology_service = TopologyService()
        if premortem_service is None:
            from agents.premortem.premortem_service import PreMortemService
            premortem_service = PreMortemService()
        if path_decision_service is None:
            from agents.path_decision.decision_service import PathDecisionService
            path_decision_service = PathDecisionService()
        if trust_service is None:
            from agents.trust.trust_service import TrustService
            trust_service = TrustService()
        if failover_service is None:
            from agents.failover.failover_service import FailoverService
            failover_service = FailoverService()

        self.topology_service = topology_service
        self.premortem_service = premortem_service
        self.path_decision_service = path_decision_service
        self.trust_service = trust_service
        self.failover_service = failover_service

    def run_scenario(
        self,
        target_entity: str = "Branch3-Uplink",
        auto_approve: bool = True,
        simulate_verification_failure: bool = False,
    ) -> GoldenIncidentScenarioResult:
        """
        Execute the 14-step Golden Incident Scenario.

        Workflow:
        1. Telemetry / prediction context initialization
        2. Incident creation / evidence seeding
        3. Topology impact assessment (Phase 1)
        4. Historical pattern analysis (Phase 4)
        5. Provider / path recommendation
        6. Confidence evaluation & decision explanation (Phase 3)
        7. Trust / blast-radius policy
        8. Human approval checkpoint
        9. Evidence lineage construction (Phase 2)
        10. DRY_RUN failover execution
        11. Closed-loop verification
        12. Rollback execution (if verification fails)
        13. Post-hoc adaptive decision learning (Phase 5)
        14. Integration result assembly
        """
        # Step 1: Initialize Investigation Context & Request
        request = InvestigationRequest(
            target_devices=[target_entity],
            operator_query=f"Golden Scenario: Investigate WAN degradation and failover on {target_entity}",
        )
        context = InvestigationContext(request=request)

        # Step 2: Seed Telemetry & Prediction Evidence
        reg = context.evidence_registry
        reg.register(
            source_agent="TelemetryAgent",
            evidence_type="wan_metrics",
            payload={"packet_loss_pct": 12.0, "latency_ms": 185.0, "jitter_ms": 28.0},
            confidence=0.95,
            provenance="OBSERVED",
            relationship="SUPPORTING",
            affected_entity=target_entity,
            linked_decision="WAN Interface Degradation Detection",
            summary=f"High latency (185ms) and packet loss (12.0%) observed on {target_entity}.",
            device_id=target_entity,
        )
        reg.register(
            source_agent="PredictionAgent",
            evidence_type="risk_forecast",
            payload={"failure_risk": 0.88, "predicted_time_to_outage_sec": 180},
            confidence=0.89,
            provenance="PREDICTED",
            relationship="SUPPORTING",
            affected_entity=target_entity,
            linked_decision="Proactive Failover Recommendation",
            summary=f"Failure risk forecasted at 88% with imminent link saturation on {target_entity}.",
            device_id=target_entity,
        )

        incident_state = {
            "incident_id": f"INC-GOLDEN-{target_entity.upper()}",
            "title": f"WAN Degradation & Congestion on {target_entity}",
            "severity": "HIGH",
            "predicted_risk": 0.88,
            "status": "ACTIVE",
            "primary_provider": "ISP-A",
            "backup_provider": "ISP-B",
        }

        # Step 3: Phase 1 — Topology Impact Assessment
        topo_impact = self.topology_service.get_incident_topology_impact(
            target_entity,
            path_decision_service=self.path_decision_service,
        )

        # Step 4: Phase 4 — Historical Pattern Intelligence & Pre-Mortem Learning
        hist_learning = self.premortem_service.analyze_historical_learning(target_entity, context=context)

        # Step 5: Path Decision Service Evaluation
        path_decision = self.path_decision_service.evaluate_path_decision(
            target_interface_or_device=target_entity,
            request_id=context.context_id,
            context=context,
        )

        # Step 6: Trust Evaluation
        trust_dec = path_decision.trust_decision

        # Step 7: Phase 2 — Evidence Lineage Construction
        lineage = context.build_evidence_lineage(target_entity=target_entity)

        # Step 8: Phase 3 — Decision Explanation & Confidence Transparency
        expl_report = self.trust_service.explain_decision(
            target_entity=target_entity,
            trust_decision=trust_dec,
            path_decision_result=path_decision,
            topology_impact=topo_impact,
            lineage=lineage,
        )

        # Step 9: Human Approval Checkpoint
        approval_status = ApprovalStatus.APPROVED if auto_approve else ApprovalStatus.PENDING_APPROVAL

        # Step 10 & 11 & 12: Controlled Failover Execution (DRY_RUN mode) & Closed-Loop Verification / Rollback
        override_v = VerificationStatus.FAILED if simulate_verification_failure else None
        failover_res = self.failover_service.execute_failover_pipeline(
            target_interface_or_device=target_entity,
            execution_mode=ExecutionMode.DRY_RUN,
            operator_id="OPERATOR-GOLDEN",
            auto_approve=auto_approve,
            override_verification_status=override_v,
        )

        v_result = failover_res.verification_result
        rb_result = failover_res.rollback_result

        # Step 13: Phase 5 — Closed-Loop Adaptive Decision Learning
        learning_result = self.failover_service.generate_decision_learning(
            target_entity=target_entity,
            failover_result=failover_res,
            context=context,
            predicted_provider=path_decision.recommendation.recommended_provider if path_decision.recommendation else "ISP-B",
            predicted_risk=0.88,
            expected_latency_ms=12.0,
            expected_loss=0.0,
            expected_impact="Latency restoration to <= 15ms with 0.0% loss",
        )

        # Step 14: Compute Provenance Summary & Assemble Integration Result
        prov_counts: Dict[str, int] = {}
        for ev in context.evidence_registry.get_all():
            prov_counts[ev.provenance] = prov_counts.get(ev.provenance, 0) + 1

        final_lifecycle = failover_res.final_status.value
        audit_ref = failover_res.audit_reference or f"AUDIT-GOLDEN-{uuid.uuid4().hex[:8].upper()}"

        return GoldenIncidentScenarioResult(
            scenario_id=str(uuid.uuid4()),
            investigation_id=context.context_id,
            target_entity=target_entity,
            incident_state=incident_state,
            topology_impact=topo_impact,
            evidence_lineage=lineage,
            historical_learning=hist_learning,
            confidence_explanation=expl_report,
            trust_decision=trust_dec,
            path_decision=path_decision,
            approval_state=approval_status,
            execution_result=failover_res,
            verification_result=v_result,
            rollback_result=rb_result,
            adaptive_learning=learning_result,
            final_lifecycle_status=final_lifecycle,
            provenance_summary=prov_counts,
            audit_reference=audit_ref,
            timestamp=datetime.now(timezone.utc),
        )
