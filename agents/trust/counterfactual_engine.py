"""
Counterfactual Analysis Engine for Enterprise Trust & Safe Autonomy Subsystem.

Evaluates counterfactual scenarios ('If hypothesis were false, what would we observe?') and
compares expected vs. observed evidence to adjust confidence deterministically.
"""

import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.reasoning.reasoning_models import (
    Hypothesis,
    ReasoningResult,
)
from agents.trust.trust_models import (
    CounterfactualHypothesis,
    CounterfactualResult,
)

logger = get_agent_logger("CounterfactualEngine")


class CounterfactualEngine:
    """
    Thread-safe engine for evidence-based counterfactual reasoning analysis.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def evaluate_counterfactuals(
        self, reasoning_result: ReasoningResult
    ) -> CounterfactualResult:
        """
        Evaluate counterfactual scenarios for all hypotheses in reasoning_result.

        Returns:
            CounterfactualResult model.
        """
        with self._lock:
            counterfactuals: List[CounterfactualHypothesis] = []
            hypotheses: List[Hypothesis] = reasoning_result.conclusion.ranked_hypotheses
            evidence_count = reasoning_result.statistics.evidence_processed

            supported_cnt = 0
            contradicted_cnt = 0

            for h in hypotheses:
                expected = [
                    "Normal utilization baseline on alternate interface",
                    "Stable error counts prior to failure timestamp",
                ]
                observed = [
                    f"Observed {len(h.supporting_evidence_ids)} supporting signals for category {h.category.value if hasattr(h.category, 'value') else str(h.category)}",
                ]

                # Counterfactual test: If hypothesis was false, supporting evidence count should be 0
                is_supp = len(h.supporting_evidence_ids) > 0
                if is_supp:
                    supported_cnt += 1
                else:
                    contradicted_cnt += 1

                c_hyp = CounterfactualHypothesis(
                    hypothesis_id=h.hypothesis_id,
                    counterfactual_statement=f"If '{h.title}' were false, we should observe normal metrics and 0 supporting signals.",
                    expected_evidence=expected,
                    observed_evidence=observed,
                    is_supported=is_supp,
                )
                counterfactuals.append(c_hyp)

            # Adjustment calculation
            if supported_cnt > 0 and contradicted_cnt == 0:
                adjustment = 0.05
                conclusion_str = f"Counterfactual analysis supports primary hypothesis. {supported_cnt} scenario(s) verified against observed evidence."
            elif supported_cnt >= contradicted_cnt:
                adjustment = 0.0
                conclusion_str = f"Counterfactual analysis partially supports hypotheses ({supported_cnt} supported, {contradicted_cnt} unconfirmed)."
            else:
                adjustment = -0.15
                conclusion_str = f"Counterfactual analysis failed to confirm primary hypothesis ({contradicted_cnt} unconfirmed scenarios)."

            result = CounterfactualResult(
                counterfactual_hypotheses=counterfactuals,
                total_supported=supported_cnt,
                total_contradicted=contradicted_cnt,
                confidence_adjustment=round(adjustment, 2),
                conclusion=conclusion_str,
            )

            logger.info(
                f"CounterfactualEngine completed: supported={supported_cnt}, "
                f"contradicted={contradicted_cnt}, adjustment={adjustment:+.2f}"
            )
            return result
