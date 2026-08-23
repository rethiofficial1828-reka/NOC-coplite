"""
Failover Recommendation Engine Module for Enterprise Intelligent Network Path & Provider Decision Engine.

Formulates evidence-grounded path recommendation decisions (KEEP_CURRENT_PATH, MONITOR,
RECOMMEND_ALTERNATIVE, HUMAN_APPROVAL_REQUIRED, BLOCKED, INSUFFICIENT_EVIDENCE).
Calculates expected performance improvements and enforces safety execution policy (NOT PERFORMED).
"""

from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.path_decision.path_models import (
    DecisionStatus,
    FailoverRecommendation,
    PathCandidate,
    PathEvaluation,
    PathScore,
    SLAStatus,
)

logger = get_agent_logger("FailoverRecommendationEngine")


class FailoverRecommendationEngine:
    """
    Evaluates candidate path evaluations and scores to produce an actionable failover recommendation.
    """

    def generate_recommendation(
        self,
        current_path: Optional[PathCandidate],
        candidates: List[PathCandidate],
        evaluations: List[PathEvaluation],
        scores: List[PathScore],
        trust_policy_status: str = "HUMAN_APPROVAL_REQUIRED",
        evidence_lineage: Optional[List[Dict[str, Any]]] = None,
    ) -> FailoverRecommendation:
        """
        Formulate failover recommendation.

        Args:
            current_path: Primary active path candidate.
            candidates: All candidate paths.
            evaluations: List of PathEvaluation objects.
            scores: Sorted list of PathScore objects (rank 1 = top path).
            trust_policy_status: Policy gate result from TrustAgent.
            evidence_lineage: Traceability metadata list.

        Returns:
            FailoverRecommendation domain model.
        """
        rec_id = str(uuid.uuid4())
        lineage = evidence_lineage or []

        if not current_path or not evaluations or not scores:
            return FailoverRecommendation(
                recommendation_id=rec_id,
                current_provider=current_path.provider_name if current_path else "UNKNOWN",
                current_path_id=current_path.path_id if current_path else "UNKNOWN",
                current_status="UNKNOWN",
                current_failure_risk=0.0,
                decision_status=DecisionStatus.INSUFFICIENT_EVIDENCE,
                confidence=0.5,
                trust_policy_status=trust_policy_status,
                execution_status="NOT PERFORMED",
                rationale=["Topology or telemetry evidence was insufficient to formulate a decision."],
                evidence_lineage=lineage,
            )

        eval_map = {e.path_id: e for e in evaluations}
        cand_map = {c.path_id: c for c in candidates}

        curr_eval = eval_map.get(current_path.path_id)
        top_score = scores[0]
        top_cand = cand_map.get(top_score.path_id)
        top_eval = eval_map.get(top_score.path_id)

        curr_health = curr_eval.health if curr_eval else 100.0
        curr_risk = curr_eval.failure_risk if curr_eval else 0.0
        curr_status = "DEGRADING" if (curr_health < 70.0 or curr_risk > 0.4) else "HEALTHY"

        rationale: List[str] = []
        improvements: Dict[str, str] = {}

        # 1. Trust policy BLOCKED gate
        if trust_policy_status.upper() == "BLOCKED":
            return FailoverRecommendation(
                recommendation_id=rec_id,
                current_provider=current_path.provider_name,
                current_path_id=current_path.path_id,
                current_status=curr_status,
                current_failure_risk=curr_risk,
                decision_status=DecisionStatus.BLOCKED,
                confidence=0.9,
                trust_policy_status="BLOCKED",
                execution_status="NOT PERFORMED",
                rationale=["Path change blocked by operational trust policy or safety threshold."],
                evidence_lineage=lineage,
            )

        # 2. Check if current path is optimal
        if current_path.path_id == top_score.path_id or (curr_health >= 80.0 and curr_risk < 0.25):
            decision = DecisionStatus.KEEP_CURRENT_PATH
            rationale.append(f"Current provider '{current_path.provider_name}' is healthy ({curr_health:.1f}/100 health, {curr_risk*100:.0f}% risk).")
            rec_provider = current_path.provider_name
            rec_path_id = current_path.path_id

        # 3. Recommend alternative path
        elif top_cand and top_eval and top_score.total_score > 60.0:
            decision = DecisionStatus.RECOMMEND_ALTERNATIVE
            rec_provider = top_cand.provider_name
            rec_path_id = top_cand.path_id

            improvements["latency"] = f"{curr_eval.latency_ms:.1f}ms → ~{top_eval.latency_ms:.1f}ms"
            improvements["packet_loss"] = f"{curr_eval.packet_loss_percent:.1f}% → ~{top_eval.packet_loss_percent:.1f}%"
            improvements["failure_risk"] = f"{curr_risk*100:.0f}% → ~{top_eval.failure_risk*100:.0f}%"

            rationale.append(
                f"Current provider '{current_path.provider_name}' is degrading ({curr_health:.1f}/100 health, {curr_risk*100:.0f}% predicted failure risk)."
            )
            rationale.append(
                f"Recommended provider '{top_cand.provider_name}' ranks highest ({top_score.total_score:.1f}/100 score) with superior health and latency."
            )

        # 4. Moderate degradation or no healthy alternative available
        elif curr_health >= 50.0:
            decision = DecisionStatus.MONITOR
            rec_provider = current_path.provider_name
            rec_path_id = current_path.path_id
            rationale.append(f"Current provider '{current_path.provider_name}' shows minor degradation; continued monitoring recommended.")

        else:
            decision = DecisionStatus.INVESTIGATE
            rec_provider = None
            rec_path_id = None
            rationale.append(f"Current provider '{current_path.provider_name}' is severely degraded, but no healthy alternative path meets minimum criteria.")

        confidence = max(0.5, min(0.98, top_eval.collector_confidence if top_eval else 0.85))

        logger.info(
            f"FailoverRecommendationEngine decision: {decision.value} "
            f"(Current='{current_path.provider_name}', Recommended='{rec_provider}')"
        )

        return FailoverRecommendation(
            recommendation_id=rec_id,
            current_provider=current_path.provider_name,
            current_path_id=current_path.path_id,
            current_status=curr_status,
            current_failure_risk=curr_risk,
            recommended_provider=rec_provider,
            recommended_path_id=rec_path_id,
            decision_status=decision,
            expected_improvements=improvements,
            confidence=round(confidence, 2),
            trust_policy_status=trust_policy_status,
            execution_status="NOT PERFORMED",
            rationale=rationale,
            evidence_lineage=lineage,
        )
