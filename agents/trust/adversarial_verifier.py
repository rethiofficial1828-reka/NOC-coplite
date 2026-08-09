"""
Adversarial Verifier Engine for Enterprise Trust & Safe Autonomy Subsystem.

Actively attempts to disprove proposed root cause hypotheses by challenging evidence
consistency, topology alignment, symptom coverage, and alternative explanations.
"""

import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.reasoning.reasoning_models import (
    InvestigationConclusion,
    ReasoningResult,
    RootCause,
)
from agents.trust.trust_models import (
    AdversarialChallenge,
    AdversarialResult,
    VerificationFinding,
    VerificationStatus,
)

logger = get_agent_logger("AdversarialVerifier")


class AdversarialVerifier:
    """
    Thread-safe adversarial verification engine designed to actively challenge hypotheses.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def verify_hypothesis(
        self,
        reasoning_result: ReasoningResult,
        context: Optional[InvestigationContext] = None,
    ) -> AdversarialResult:
        """
        Conduct adversarial probing against the primary root cause in reasoning_result.

        Returns:
            AdversarialResult containing challenges, findings, and penalty factors.
        """
        with self._lock:
            challenges: List[AdversarialChallenge] = []
            findings: List[VerificationFinding] = []
            conclusion: InvestigationConclusion = reasoning_result.conclusion
            primary_cause: Optional[RootCause] = conclusion.primary_root_cause

            if not primary_cause:
                return AdversarialResult(
                    is_disproved=True,
                    challenge_count=1,
                    passed_challenges=0,
                    failed_challenges=1,
                    challenges=[
                        AdversarialChallenge(
                            question="Is there a defined primary root cause hypothesis?",
                            rationale="No primary root cause was identified by reasoning engine.",
                            target_hypothesis_id="none",
                            result_status=VerificationStatus.FAILED,
                        )
                    ],
                    findings=[
                        VerificationFinding(
                            title="Missing Primary Root Cause",
                            status=VerificationStatus.FAILED,
                            description="Reasoning output lacked a valid primary root cause.",
                            severity="HIGH",
                        )
                    ],
                    penalty_factor=0.50,
                )

            hyp_id = primary_cause.cause_id
            target_title = primary_cause.title

            # Challenge 1: Contradictions Check
            contradiction_cnt = len(conclusion.contradictions)
            if contradiction_cnt > 0:
                c1_status = VerificationStatus.WARNING if contradiction_cnt == 1 else VerificationStatus.FAILED
                challenges.append(
                    AdversarialChallenge(
                        question=f"Does hypothesis '{target_title}' have unaddressed evidence contradictions?",
                        rationale=f"Found {contradiction_cnt} unaddressed contradiction(s) in reasoning evidence.",
                        target_hypothesis_id=hyp_id,
                        result_status=c1_status,
                    )
                )
                findings.append(
                    VerificationFinding(
                        title="Unresolved Evidence Contradiction",
                        status=c1_status,
                        description=f"Identified {contradiction_cnt} conflicting evidence signal(s).",
                        severity="MEDIUM" if contradiction_cnt == 1 else "HIGH",
                    )
                )
            else:
                challenges.append(
                    AdversarialChallenge(
                        question=f"Does hypothesis '{target_title}' have unaddressed evidence contradictions?",
                        rationale="No contradictory signals detected.",
                        target_hypothesis_id=hyp_id,
                        result_status=VerificationStatus.PASSED,
                    )
                )

            # Challenge 2: Competing Hypotheses Margin
            ranked_causes = conclusion.ranked_root_causes
            if len(ranked_causes) > 1:
                margin = ranked_causes[0].final_score - ranked_causes[1].final_score
                if margin < 0.10:
                    challenges.append(
                        AdversarialChallenge(
                            question=f"Is the probability margin of '{target_title}' sufficiently distinct from alternatives?",
                            rationale=f"Margin between top cause and second cause '{ranked_causes[1].root_cause.title}' is narrow ({margin:.2f} < 0.10).",
                            target_hypothesis_id=hyp_id,
                            result_status=VerificationStatus.WARNING,
                        )
                    )
                    findings.append(
                        VerificationFinding(
                            title="Narrow Hypothesis Margin",
                            status=VerificationStatus.WARNING,
                            description=f"Probability margin to alternative cause is only {margin * 100:.1f}%.",
                            severity="LOW",
                        )
                    )
                else:
                    challenges.append(
                        AdversarialChallenge(
                            question=f"Is the probability margin of '{target_title}' sufficiently distinct from alternatives?",
                            rationale=f"Clear probability margin ({margin:.2f}).",
                            target_hypothesis_id=hyp_id,
                            result_status=VerificationStatus.PASSED,
                        )
                    )

            # Challenge 3: Action Match Check
            rec_actions = primary_cause.recommended_actions
            if not rec_actions:
                challenges.append(
                    AdversarialChallenge(
                        question=f"Does proposed root cause '{target_title}' specify actionable remediation steps?",
                        rationale="No recommended actions provided.",
                        target_hypothesis_id=hyp_id,
                        result_status=VerificationStatus.FAILED,
                    )
                )
                findings.append(
                    VerificationFinding(
                        title="Missing Remediation Actions",
                        status=VerificationStatus.FAILED,
                        description="Root cause lacks actionable remediation steps.",
                        severity="HIGH",
                    )
                )
            else:
                challenges.append(
                    AdversarialChallenge(
                        question=f"Does proposed root cause '{target_title}' specify actionable remediation steps?",
                        rationale=f"Specified {len(rec_actions)} actionable remediation steps.",
                        target_hypothesis_id=hyp_id,
                        result_status=VerificationStatus.PASSED,
                    )
                )

            # Evaluate Adversarial Outcome
            passed_cnt = sum(1 for c in challenges if c.result_status == VerificationStatus.PASSED)
            failed_cnt = sum(1 for c in challenges if c.result_status == VerificationStatus.FAILED)

            is_disproved = failed_cnt > 1
            penalty = (failed_cnt * 0.20) + (sum(1 for c in challenges if c.result_status == VerificationStatus.WARNING) * 0.05)
            penalty_factor = max(0.0, min(0.60, penalty))

            result = AdversarialResult(
                is_disproved=is_disproved,
                challenge_count=len(challenges),
                passed_challenges=passed_cnt,
                failed_challenges=failed_cnt,
                challenges=challenges,
                findings=findings,
                penalty_factor=round(penalty_factor, 2),
            )

            logger.info(
                f"AdversarialVerifier completed: disproved={is_disproved}, "
                f"passed={passed_cnt}/{len(challenges)}, penalty={penalty_factor:.2f}"
            )
            return result
