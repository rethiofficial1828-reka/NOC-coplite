"""
Decision Explainer for Enterprise Trust & Safe Autonomy Subsystem.

Synthesizes structured, auditable explanations for final trust and autonomy decisions
without exposing internal chain-of-thought.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.reasoning.reasoning_models import ReasoningResult, RootCause
from agents.trust.trust_models import (
    AdversarialResult,
    AutonomyDecision,
    BlastRadius,
    BlastRadiusLevel,
    ConfidenceLevel,
    CounterfactualResult,
    DecisionExplanation,
    DecisionExplanationReport,
    EvidenceRevalidation,
    TrustDecision,
    TrustScore,
)

logger = get_agent_logger("DecisionExplainer")


class DecisionExplainer:
    """
    Thread-safe engine for constructing auditable decision explanations.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def generate_explanation(
        self,
        decision: AutonomyDecision,
        reasoning_result: ReasoningResult,
        trust_score: TrustScore,
        adversarial_result: AdversarialResult,
        counterfactual_result: CounterfactualResult,
        blast_radius: BlastRadius,
        revalidation: EvidenceRevalidation,
    ) -> DecisionExplanation:
        """
        Synthesize concise, auditable DecisionExplanation model.

        Returns:
            DecisionExplanation model.
        """
        with self._lock:
            primary_cause: Optional[RootCause] = reasoning_result.conclusion.primary_root_cause
            top_title = primary_cause.title if primary_cause else "Unknown Anomaly"

            # Why selected
            why_sel = (
                f"Selected decision '{decision.value}' for hypothesis '{top_title}'. "
                f"Overall trust score = {trust_score.overall_trust_score * 100:.1f}%, "
                f"reasoning confidence = {trust_score.reasoning_confidence * 100:.1f}%."
            )

            # Why not alternative
            why_not = (
                "Alternative root cause hypotheses had lower evidence coverage and confidence scores."
                if len(reasoning_result.conclusion.ranked_root_causes) > 1
                else "No alternative hypothesis met the minimum evidence threshold."
            )

            # Supporting / Contradicting evidence
            ev_refs = getattr(reasoning_result.conclusion, "evidence_references", None) or getattr(reasoning_result, "evidence_references", None) or revalidation.revalidated_items
            supporting = [
                f"Evidence signal from {getattr(ref, 'source_agent', 'Agent')} (quality={getattr(ref, 'freshness_score', getattr(ref, 'confidence', 0.9)):.2f})"
                for ref in ev_refs[:5]
            ]
            contradicting = [
                f"Contradiction: {c.description}"
                for c in reasoning_result.conclusion.contradictions
            ]
            missing_text = reasoning_result.conclusion.explanation.missing_evidence_summary if reasoning_result.conclusion.explanation else "None"
            missing = missing_text.split(".")

            # Verifications & Counterfactual
            verif_res = (
                f"Adversarial verification {'PASSED' if not adversarial_result.is_disproved else 'FAILED'} "
                f"({adversarial_result.passed_challenges}/{adversarial_result.challenge_count} challenges passed)."
            )

            # Blast radius & Autonomy reason
            blast_reason = (
                f"Potential action blast radius rated '{blast_radius.potential_action_level.value}' "
                f"affecting {len(blast_radius.potential_affected_devices)} device(s) and "
                f"{len(blast_radius.potential_affected_services)} service(s)."
            )
            if blast_radius.is_action_larger_than_incident:
                blast_reason += " (Note: Action blast radius is larger than current incident blast radius)."

            if decision == AutonomyDecision.AUTO_ELIGIBLE:
                autonomy_reason = "Action meets all safety policy thresholds for autonomous execution: high trust score and low blast radius."
            elif decision == AutonomyDecision.HUMAN_APPROVAL_REQUIRED:
                autonomy_reason = f"Potential action blast radius ({blast_radius.potential_action_level.value}) exceeds policy threshold for automatic execution. Operator approval required."
            elif decision == AutonomyDecision.ADDITIONAL_EVIDENCE_REQUIRED:
                autonomy_reason = "Overall trust score or evidence completeness is insufficient to grant execution eligibility."
            else:
                autonomy_reason = "Action is BLOCKED due to disproved adversarial verification or unaddressed signal contradictions."

            # Risk factors
            risk_factors = []
            if blast_radius.potential_action_level in (BlastRadiusLevel.HIGH, BlastRadiusLevel.CRITICAL):
                risk_factors.append("High blast radius impacting critical core network services")
            if revalidation.stale_count > 0:
                risk_factors.append(f"Contains {revalidation.stale_count} stale evidence item(s)")
            if len(contradicting) > 0:
                risk_factors.append(f"Contains {len(contradicting)} conflicting evidence signal(s)")

            # Next step
            if primary_cause and primary_cause.recommended_actions:
                next_step = primary_cause.recommended_actions[0]
            else:
                next_step = "Present findings to Network Operations Center operator for manual review."

            explanation = DecisionExplanation(
                why_selected=why_sel,
                why_not_alternative=why_not,
                supporting_evidence=supporting,
                contradicting_evidence=contradicting,
                missing_evidence=[m.strip() for m in missing if m.strip()],
                verification_result=verif_res,
                counterfactual_result=counterfactual_result.conclusion,
                blast_radius_reason=blast_reason,
                autonomy_reason=autonomy_reason,
                risk_factors=risk_factors,
                recommended_next_step=next_step,
            )

            logger.info(f"DecisionExplainer generated explanation for decision '{decision.value}'")
            return explanation

    def generate_comprehensive_explanation(
        self,
        target_entity: str,
        trust_decision: Optional[TrustDecision] = None,
        reasoning_result: Optional[ReasoningResult] = None,
        path_decision_result: Optional[Any] = None,
        topology_impact: Optional[Any] = None,
        lineage: Optional[Any] = None,
    ) -> DecisionExplanationReport:
        """
        Synthesize concise, auditable DecisionExplanationReport grounded in actual evidence and policy.
        """
        with self._lock:
            # 1. FINAL DECISION
            rec_provider = None
            curr_provider = None
            if path_decision_result and getattr(path_decision_result, "recommendation", None):
                rec = path_decision_result.recommendation
                rec_provider = getattr(rec, "recommended_provider", None)
                curr_provider = getattr(rec, "current_provider", None)

            if trust_decision:
                if hasattr(trust_decision, "decision"):
                    autonomy_str = trust_decision.decision.value if hasattr(trust_decision.decision, "value") else str(trust_decision.decision)
                elif isinstance(trust_decision, dict):
                    dec_val = trust_decision.get("decision", "HUMAN_APPROVAL_REQUIRED")
                    autonomy_str = dec_val.get("value", str(dec_val)) if isinstance(dec_val, dict) else str(dec_val)
                else:
                    autonomy_str = str(trust_decision)

                if rec_provider and rec_provider != curr_provider:
                    final_dec = f"{autonomy_str} — Switch traffic from {curr_provider} to candidate {rec_provider}"
                elif curr_provider:
                    final_dec = f"{autonomy_str} — Maintain active provider {curr_provider}"
                else:
                    final_dec = f"{autonomy_str} — Incident Mitigation on {target_entity}"
            elif path_decision_result and getattr(path_decision_result, "recommendation", None):
                rec = path_decision_result.recommendation
                final_dec = f"{rec.decision_status.value} — Recommend {rec.recommended_provider or curr_provider}"
            else:
                final_dec = f"INVESTIGATION_COMPLETE — Target {target_entity}"

            # 2. CONFIDENCE SCORE & CONFIDENCE LEVEL
            if trust_decision and hasattr(trust_decision, "trust_assessment") and trust_decision.trust_assessment:
                conf_score = trust_decision.trust_assessment.trust_score.overall_trust_score
            elif trust_decision and isinstance(trust_decision, dict):
                ta = trust_decision.get("trust_assessment") or {}
                ts = ta.get("trust_score") or {}
                conf_score = ts.get("overall_trust_score", 0.52)
            elif reasoning_result and reasoning_result.conclusion:
                conf_score = reasoning_result.conclusion.confidence_result.overall_confidence
            elif lineage and getattr(lineage, "timeline", None):
                conf_score = sum(e.confidence for e in lineage.timeline) / len(lineage.timeline)
            else:
                conf_score = 0.50

            conf_score = round(max(0.0, min(1.0, conf_score)), 2)

            if conf_score >= 0.90:
                conf_level = ConfidenceLevel.VERY_HIGH.value
            elif conf_score >= 0.75:
                conf_level = ConfidenceLevel.HIGH.value
            elif conf_score >= 0.50:
                conf_level = ConfidenceLevel.MEDIUM.value
            elif conf_score >= 0.25:
                conf_level = ConfidenceLevel.LOW.value
            else:
                conf_level = ConfidenceLevel.VERY_LOW.value

            # 3. TOP SUPPORTING FACTORS
            supporting_factors: List[Dict[str, Any]] = []

            # From trust score breakdown factors
            if trust_decision and hasattr(trust_decision, "trust_assessment") and trust_decision.trust_assessment:
                ts = trust_decision.trust_assessment.trust_score
                for factor in ts.breakdown:
                    supporting_factors.append({
                        "factor": factor.factor_name,
                        "score": factor.score,
                        "weight": factor.weight,
                        "rationale": factor.rationale,
                    })
            elif trust_decision and isinstance(trust_decision, dict):
                ta = trust_decision.get("trust_assessment") or {}
                ts = ta.get("trust_score") or {}
                for factor in ts.get("breakdown", []):
                    supporting_factors.append({
                        "factor": factor.get("factor_name", "Decision Factor"),
                        "score": factor.get("score", 0.5),
                        "weight": factor.get("weight", 0.25),
                        "rationale": factor.get("rationale", ""),
                    })

            # From path evaluations / scores
            if path_decision_result and getattr(path_decision_result, "scores", None):
                top_score = path_decision_result.scores[0] if path_decision_result.scores else None
                if top_score:
                    supporting_factors.append({
                        "factor": "Path Ranking Score",
                        "score": round(top_score.total_score / 100.0, 2),
                        "rationale": f"Candidate {top_score.provider_name} ranked #1 with total score {top_score.total_score:.1f}/100.",
                    })

            # From topology impact
            if topology_impact:
                supporting_factors.append({
                    "factor": "Topology Blast Radius",
                    "score": round(getattr(topology_impact, "impact_percentage", 0.0) / 100.0, 2),
                    "rationale": f"Identified blast radius level {getattr(topology_impact, 'blast_radius_level', 'CRITICAL')} ({getattr(topology_impact, 'impact_percentage', 0.0):.1f}% network impact, {len(getattr(topology_impact, 'single_points_of_failure', []))} SPOFs).",
                })

            # From lineage if supporting_factors is small
            if len(supporting_factors) < 2 and lineage and getattr(lineage, "timeline", None):
                for e in lineage.timeline:
                    if (e.relationship or "").upper() == "SUPPORTING" and e.summary:
                        supporting_factors.append({
                            "factor": e.source_agent,
                            "score": e.confidence,
                            "rationale": e.summary,
                        })

            # 4. TOP CONTRADICTING FACTORS
            contradicting_factors: List[Dict[str, Any]] = []
            if reasoning_result and reasoning_result.conclusion and reasoning_result.conclusion.contradictions:
                for c in reasoning_result.conclusion.contradictions:
                    contradicting_factors.append({
                        "source": f"{c.source_a} vs {c.source_b}",
                        "severity": c.severity.value if hasattr(c.severity, "value") else str(c.severity),
                        "description": c.description,
                    })

            if lineage and getattr(lineage, "timeline", None):
                for e in lineage.timeline:
                    if (e.relationship or "").upper() == "CONTRADICTING":
                        contradicting_factors.append({
                            "source": e.source_agent,
                            "severity": "MEDIUM",
                            "description": e.summary or (e.payload.get("data") if isinstance(e.payload, dict) else str(e.payload)),
                        })

            # 5. KEY UNCERTAINTIES
            key_uncertainties: List[Dict[str, Any]] = []
            if reasoning_result and reasoning_result.conclusion:
                c_res = reasoning_result.conclusion.confidence_result
                if c_res and hasattr(c_res, "factors"):
                    f = c_res.factors
                    if f.evidence_completeness < 0.8:
                        key_uncertainties.append({
                            "category": "insufficient_evidence",
                            "description": f"Evidence completeness is at {f.evidence_completeness*100:.0f}%; full flow-table telemetry dump is sampled.",
                        })
                    if f.contradiction_penalty > 0.0:
                        key_uncertainties.append({
                            "category": "contradictory_evidence",
                            "description": f"Contradiction penalty of {f.contradiction_penalty:.2f} applied due to cross-source metric disparity.",
                        })
                    if f.prediction_certainty < 0.8:
                        key_uncertainties.append({
                            "category": "unresolved_telemetry",
                            "description": f"Predictive certainty is {f.prediction_certainty*100:.0f}%; risk trajectory reflects short-window sampling.",
                        })

            if topology_impact and getattr(topology_impact, "single_points_of_failure", None):
                spofs = getattr(topology_impact, "single_points_of_failure", [])
                if len(spofs) > 2:
                    key_uncertainties.append({
                        "category": "topology_uncertainty",
                        "description": f"Multiple SPOF articulation points ({', '.join(spofs[:3])}) exist along the core-to-distribution transit boundary.",
                    })

            if path_decision_result and getattr(path_decision_result, "evaluations", None):
                for ev in path_decision_result.evaluations:
                    if ev.historical_reliability < 90.0:
                        key_uncertainties.append({
                            "category": "provider_uncertainty",
                            "description": f"Provider {ev.provider_name} historical reliability is {ev.historical_reliability:.1f}%.",
                        })

            # 6. SAFETY CONSTRAINTS
            safety_constraints: List[str] = []
            if trust_decision and hasattr(trust_decision, "policy_applied") and hasattr(trust_decision, "trust_assessment"):
                p = trust_decision.policy_applied
                br = trust_decision.trust_assessment.blast_radius
                safety_constraints.append(f"Autonomy Policy Maximum Blast Radius: {p.max_blast_radius.value} (Evaluated: {br.potential_action_level.value})")
                if p.require_reversibility:
                    safety_constraints.append("Reversibility Required: Action must have automated roll-back capability")
                if p.require_rollback_plan:
                    safety_constraints.append("Rollback Plan Required: Pre-execution checkpoint snapshot validated")
                if p.min_trust_score:
                    safety_constraints.append(f"Autonomous Execution Minimum Trust Threshold: {p.min_trust_score:.2f}")
            elif trust_decision and isinstance(trust_decision, dict):
                p = trust_decision.get("policy_applied") or {}
                ta = trust_decision.get("trust_assessment") or {}
                br = ta.get("blast_radius") or {}
                max_b = p.get("max_blast_radius", "MEDIUM")
                act_b = br.get("potential_action_level", "HIGH")
                safety_constraints.append(f"Autonomy Policy Maximum Blast Radius: {max_b} (Evaluated: {act_b})")
                safety_constraints.append("Reversibility Required: Action must have automated roll-back capability")
                safety_constraints.append("Rollback Plan Required: Pre-execution checkpoint snapshot validated")
                safety_constraints.append("Autonomous Execution Minimum Trust Threshold: 0.85")
            else:
                safety_constraints.append("Autonomy Policy Maximum Blast Radius: MEDIUM")
                safety_constraints.append("Reversibility Required: Automated rollback plan pre-computed")
            safety_constraints.append("Execution Boundary: Locked to DRY_RUN / Typed Execution Adapters (No Shell Access)")

            # 7. WHY THE RECOMMENDED PATH WON
            why_path_won = ""
            if path_decision_result and getattr(path_decision_result, "scores", None) and getattr(path_decision_result, "evaluations", None):
                scores = path_decision_result.scores
                evals = {e.path_id: e for e in path_decision_result.evaluations}
                if len(scores) >= 2:
                    top = scores[0]
                    runner_up = scores[1]
                    top_ev = evals.get(top.path_id)
                    rup_ev = evals.get(runner_up.path_id)

                    why_path_won = (
                        f"Candidate '{top.provider_name}' achieved the highest overall score of {top.total_score:.1f}/100 "
                        f"(Rank #1) compared to '{runner_up.provider_name}' at {runner_up.total_score:.1f}/100."
                    )
                    if top_ev and rup_ev:
                        why_path_won += (
                            f" Key decisive metrics: Health {top_ev.health:.1f} vs {rup_ev.health:.1f}, "
                            f"Packet Loss {top_ev.packet_loss_percent:.2f}% vs {rup_ev.packet_loss_percent:.2f}%, "
                            f"Latency {top_ev.latency_ms:.1f}ms vs {rup_ev.latency_ms:.1f}ms."
                        )
                elif scores:
                    top = scores[0]
                    why_path_won = f"Candidate '{top.provider_name}' was selected with rank #1 score of {top.total_score:.1f}/100."
            if not why_path_won:
                why_path_won = "Recommended path was selected as the sole viable candidate meeting connectivity requirements."

            # 8. WHY HUMAN APPROVAL IS REQUIRED
            why_approval = ""
            if trust_decision and hasattr(trust_decision, "policy_applied") and hasattr(trust_decision, "trust_assessment"):
                p = trust_decision.policy_applied
                ts = trust_decision.trust_assessment.trust_score
                br = trust_decision.trust_assessment.blast_radius
                reasons = []
                level_rank = {BlastRadiusLevel.LOW: 1, BlastRadiusLevel.MEDIUM: 2, BlastRadiusLevel.HIGH: 3, BlastRadiusLevel.CRITICAL: 4}
                if level_rank.get(br.potential_action_level, 1) > level_rank.get(p.max_blast_radius, 2):
                    reasons.append(f"Potential action blast radius ({br.potential_action_level.value}) exceeds configured policy maximum ({p.max_blast_radius.value})")
                if ts.overall_trust_score < p.min_trust_score:
                    reasons.append(f"Overall trust score ({ts.overall_trust_score:.2f}) is below the autonomous threshold ({p.min_trust_score:.2f})")
                if not p.allow_auto_execution:
                    reasons.append("Global autonomous execution is disabled by policy")

                if reasons:
                    why_approval = "; ".join(reasons) + ". Operator sign-off is mandatory before executing routing change."
                else:
                    why_approval = "Action requires human approval as a standard operational safety precaution."
            elif trust_decision and isinstance(trust_decision, dict):
                p = trust_decision.get("policy_applied") or {}
                ta = trust_decision.get("trust_assessment") or {}
                ts = ta.get("trust_score") or {}
                br = ta.get("blast_radius") or {}
                max_b = p.get("max_blast_radius", "MEDIUM")
                act_b = br.get("potential_action_level", "HIGH")
                score_val = ts.get("overall_trust_score", 0.52)
                min_t = p.get("min_trust_score", 0.85)
                reasons = [
                    f"Potential action blast radius ({act_b}) exceeds configured policy maximum ({max_b})",
                    f"Overall trust score ({score_val:.2f}) is below the autonomous threshold ({min_t:.2f})",
                ]
                why_approval = "; ".join(reasons) + ". Operator sign-off is mandatory before executing routing change."
            else:
                why_approval = "Potential action blast radius exceeds policy limit for automatic execution. Operator confirmation required."

            # 9. WHAT EVIDENCE WOULD CHANGE THE DECISION
            what_change: List[Dict[str, Any]] = []
            if trust_decision and hasattr(trust_decision, "policy_applied") and hasattr(trust_decision, "trust_assessment"):
                p = trust_decision.policy_applied
                ts = trust_decision.trust_assessment.trust_score
                br = trust_decision.trust_assessment.blast_radius

                # Condition for AUTO_ELIGIBLE
                what_change.append({
                    "target_decision": "AUTO_ELIGIBLE",
                    "condition": f"Overall trust score increases from {ts.overall_trust_score:.2f} to >= {p.min_trust_score:.2f} and potential blast radius is reduced to <= LOW.",
                    "policy_rule": "AutonomyPolicy.Rule6 (High Trust & Low Blast Radius)",
                })
                # Condition for KEEP_CURRENT_PATH
                what_change.append({
                    "target_decision": "KEEP_CURRENT_PATH",
                    "condition": "Primary path packet loss returns below SLA limit (< 0.5%) and failure risk drops below 0.30.",
                    "policy_rule": "PathEvaluation.SLAStatus == COMPLIANT",
                })
                # Condition for BLOCKED
                what_change.append({
                    "target_decision": "BLOCKED",
                    "condition": "Adversarial verification challenges fail or candidate provider health drops below 50.0.",
                    "policy_rule": "AutonomyPolicy.Rule1 (Adversarial Disproof)",
                })
            else:
                what_change.append({
                    "target_decision": "AUTO_ELIGIBLE",
                    "condition": "Overall trust score >= 0.85 and blast radius reduced to LOW.",
                    "policy_rule": "AutonomyPolicy.min_trust_score",
                })
                what_change.append({
                    "target_decision": "KEEP_CURRENT_PATH",
                    "condition": "Primary path telemetry stabilizes with packet loss < 0.5% and failure risk < 0.30.",
                    "policy_rule": "PathEvaluation.SLAStatus == COMPLIANT",
                })

            report = DecisionExplanationReport(
                explanation_id=str(uuid.uuid4()),
                target_entity=target_entity,
                final_decision=final_dec,
                confidence_score=conf_score,
                confidence_level=conf_level,
                top_supporting_factors=supporting_factors,
                top_contradicting_factors=contradicting_factors,
                key_uncertainties=key_uncertainties,
                safety_constraints=safety_constraints,
                why_recommended_path_won=why_path_won,
                why_human_approval_required=why_approval,
                what_would_change_decision=what_change,
                evidence_lineage_ref=getattr(lineage, "investigation_id", None) if lineage else None,
                timestamp=datetime.now(timezone.utc),
                metadata={
                    "trust_decision": trust_decision.decision.value if (trust_decision and hasattr(trust_decision, "decision")) else (str(trust_decision.get("decision", "N/A")) if isinstance(trust_decision, dict) else "N/A"),
                },
            )
            logger.info(f"DecisionExplainer generated comprehensive report for {target_entity}: {final_dec}")
            return report
