"""
Root Cause Ranker for Enterprise AI Reasoning Subsystem.

Ranks competing failure hypotheses using weighted multi-factor scoring and generates
structured, explainable summaries for network operations engineers.
"""

import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.reasoning.reasoning_models import (
    ConfidenceResult,
    Contradiction,
    Hypothesis,
    RankedRootCause,
    ReasoningEvidence,
    ReasoningExplanation,
    RootCause,
)

logger = get_agent_logger("RootCauseRanker")


class RootCauseRanker:
    """
    Thread-safe engine for ranking root cause hypotheses and formulating explainable rationales.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def rank_root_causes(
        self,
        hypotheses: List[Hypothesis],
        evidence_list: List[ReasoningEvidence],
        contradictions: List[Contradiction],
        confidence_result: ConfidenceResult,
    ) -> List[RankedRootCause]:
        """
        Evaluate and rank competing hypotheses.

        Returns:
            List of RankedRootCause models sorted by score descending.
        """
        with self._lock:
            ranked: List[RankedRootCause] = []

            for h in hypotheses:
                # Calculate weighted score for hypothesis
                sup_count = len(h.supporting_evidence_ids)
                per_conf = confidence_result.per_hypothesis_confidence.get(h.hypothesis_id, 0.5)

                # Count contradictions affecting this hypothesis evidence
                h_contradictions = [
                    c for c in contradictions
                    if any(eid in h.supporting_evidence_ids for eid in c.conflicting_evidence_ids)
                ]
                penalty = sum(c.penalty_factor for c in h_contradictions)

                raw_score = (h.initial_likelihood * 0.4) + (h.coverage_score * 0.4) + (min(1.0, sup_count / 3.0) * 0.2)
                final_score = max(0.05, min(1.0, (raw_score * per_conf) - penalty))

                # Actions based on category
                actions = self._get_recommended_actions(h.category.value if hasattr(h.category, "value") else str(h.category))

                rc = RootCause(
                    cause_id=f"rc-{uuid.uuid4().hex[:8]}",
                    title=h.title,
                    probability=round(final_score, 2),
                    description=h.description,
                    affected_components=[h.title.split()[0]],
                    recommended_actions=actions,
                )

                rationale_str = (
                    f"Selected as potential root cause with {final_score * 100:.1f}% probability based on "
                    f"{sup_count} supporting evidence signal(s) and {len(h_contradictions)} conflicting signal(s)."
                )

                ranked.append(
                    RankedRootCause(
                        rank=1,  # Temporary, re-assigned after sorting
                        root_cause=rc,
                        final_score=round(final_score, 2),
                        rationale=rationale_str,
                        supporting_evidence_ids=h.supporting_evidence_ids,
                        contradiction_count=len(h_contradictions),
                    )
                )

            # Sort descending by final score
            ranked.sort(key=lambda x: x.final_score, reverse=True)

            # Assign 1-based ranks
            for idx, item in enumerate(ranked, start=1):
                item.rank = idx

            logger.info(
                f"RootCauseRanker ranked {len(ranked)} hypotheses. "
                f"Top root cause: '{ranked[0].root_cause.title if ranked else 'None'}' (score={ranked[0].final_score:.2f})"
            )
            return ranked

    def generate_explanation(
        self,
        ranked_causes: List[RankedRootCause],
        contradictions: List[Contradiction],
        confidence_result: ConfidenceResult,
        query: str = "",
    ) -> ReasoningExplanation:
        """
        Synthesize explainable summary without exposing internal chain-of-thought.
        """
        with self._lock:
            top_cause = ranked_causes[0] if ranked_causes else None
            top_title = top_cause.root_cause.title if top_cause else "Unknown Network Anomaly"

            why_chosen = (
                f"Hypothesis '{top_title}' achieved the highest composite evidence score ({top_cause.final_score * 100:.1f}%) "
                f"supported by {len(top_cause.supporting_evidence_ids if top_cause else [])} verified evidence signals."
            )

            rejected = []
            for r in ranked_causes[1:]:
                rejected.append({
                    "title": r.root_cause.title,
                    "score": r.final_score,
                    "reason_rejected": f"Lower evidence coverage ({r.final_score * 100:.1f}%) and insufficient signal weight.",
                })

            contradictions_summary = (
                f"Detected {len(contradictions)} signal conflict(s). "
                f"Applied composite confidence penalty of {confidence_result.factors.contradiction_penalty:.2f}."
            ) if contradictions else "No contradictory signals detected across telemetry, predictions, or topology."

            evidence_quality_summary = (
                f"Evidence completeness: {confidence_result.factors.evidence_completeness * 100:.0f}%, "
                f"Cross-source agreement: {confidence_result.factors.cross_source_agreement * 100:.0f}%, "
                f"Freshness: {confidence_result.factors.freshness * 100:.0f}%."
            )

            missing_summary = "Additional NetFlow session analysis and interface queue depth metrics recommended for 100% certainty."

            next_steps = top_cause.root_cause.recommended_actions if top_cause else ["Verify physical interface status", "Check routing table stability"]

            return ReasoningExplanation(
                selected_root_cause_title=top_title,
                why_chosen=why_chosen,
                supporting_evidence_summary=f"Primary evidence supported by {len(top_cause.supporting_evidence_ids if top_cause else [])} signals.",
                rejected_hypotheses=rejected,
                contradictions_summary=contradictions_summary,
                evidence_quality_summary=evidence_quality_summary,
                missing_evidence_summary=missing_summary,
                recommended_next_steps=next_steps,
            )

    def _get_recommended_actions(self, category: str) -> List[str]:
        """Map category to actionable remediation steps."""
        cat_upper = category.upper()
        if "WAN" in cat_upper or "CONGESTION" in cat_upper:
            return [
                "Apply rate-limiting / shaping on high-bandwidth non-critical flows",
                "Reroute non-essential traffic to secondary uplink",
                "Verify QoS egress queue drop counters",
            ]
        elif "ROUTE" in cat_upper or "ROUTING" in cat_upper:
            return [
                "Check BGP neighbor uptime and flap counters",
                "Inspect OSPF hello/dead timer consistency across links",
                "Verify route filter maps for unexpected prefix dampening",
            ]
        elif "HARDWARE" in cat_upper or "INTERFACE" in cat_upper:
            return [
                "Run physical loopback testing on interface transceiver",
                "Check SFP DOM optical power levels (Rx/Tx dBm)",
                "Replace patch cable or clean optical fiber connector",
            ]
        else:
            return [
                "Inspect interface error counters",
                "Review syslog for unexpected daemon restarts",
                "Verify device CPU and RAM utilization metrics",
            ]
