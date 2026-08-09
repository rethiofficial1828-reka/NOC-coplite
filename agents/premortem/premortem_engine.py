"""
Pre-Mortem Engine for Enterprise Pre-Mortem Subsystem.

Synthesizes incident fingerprinting, historical matching, pattern clustering,
what-if scenario generation, time-to-impact estimation, and early warnings.
"""

import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.reasoning.reasoning_models import ReasoningResult
from agents.trust.trust_models import TrustDecision
from agents.premortem.early_warning import EarlyWarningEngine
from agents.premortem.incident_fingerprint import IncidentFingerprintEngine
from agents.premortem.incident_matcher import HistoricalIncidentMatcher
from agents.premortem.pattern_cluster import IncidentPatternClusterer
from agents.premortem.premortem_confidence import PreMortemConfidenceEngine
from agents.premortem.premortem_models import PreMortemResult
from agents.premortem.scenario_engine import FutureScenarioEngine
from agents.premortem.time_to_impact import TimeToImpactEstimator

logger = get_agent_logger("PreMortemEngine")


class PreMortemEngine:
    """
    Thread-safe core engine for generating pre-mortem future-state predictions.
    """

    def __init__(
        self,
        fingerprint_engine: Optional[IncidentFingerprintEngine] = None,
        matcher: Optional[HistoricalIncidentMatcher] = None,
        clusterer: Optional[IncidentPatternClusterer] = None,
        scenario_engine: Optional[FutureScenarioEngine] = None,
        time_estimator: Optional[TimeToImpactEstimator] = None,
        confidence_engine: Optional[PreMortemConfidenceEngine] = None,
        early_warning_engine: Optional[EarlyWarningEngine] = None,
    ) -> None:
        self._fingerprint_engine = fingerprint_engine or IncidentFingerprintEngine()
        self._matcher = matcher or HistoricalIncidentMatcher()
        self._clusterer = clusterer or IncidentPatternClusterer()
        self._scenario_engine = scenario_engine or FutureScenarioEngine()
        self._time_estimator = time_estimator or TimeToImpactEstimator()
        self._confidence_engine = confidence_engine or PreMortemConfidenceEngine()
        self._early_warning_engine = early_warning_engine or EarlyWarningEngine()
        self._lock = threading.RLock()

    def generate_premortem(
        self,
        reasoning_result: Optional[ReasoningResult] = None,
        trust_decision: Optional[TrustDecision] = None,
        context: Optional[InvestigationContext] = None,
        telemetry_payload: Optional[Dict[str, Any]] = None,
    ) -> PreMortemResult:
        """
        Execute pre-mortem future-state prediction pipeline.

        Returns:
            PreMortemResult model.
        """
        with self._lock:
            req_id = reasoning_result.request_id if reasoning_result else (context.request.request_id if context and context.request else str(uuid.uuid4()))
            inv_id = context.context_id if context else str(uuid.uuid4())

            # 1. Generate Deterministic Incident Fingerprint
            fingerprint = self._fingerprint_engine.generate_fingerprint(
                reasoning_result=reasoning_result,
                context=context,
                telemetry_payload=telemetry_payload,
            )

            # 2. Match Historical Incidents via RAG VectorStore
            matches = self._matcher.match_fingerprint(fingerprint=fingerprint)

            # 3. Cluster Incident Patterns
            clusters = self._clusterer.cluster_patterns(fingerprint=fingerprint, matches=matches)

            # 4. Generate Future Scenarios
            scenarios = self._scenario_engine.generate_scenarios()

            # 5. Estimate Time-to-Impact
            time_to_impact = self._time_estimator.estimate_time_to_impact()

            # 6. Detect Early Warnings
            early_warnings = self._early_warning_engine.detect_early_warnings(
                fingerprint=fingerprint, matches=matches
            )

            # 7. Calculate Composite Pre-Mortem Confidence
            quality_score = 0.90
            trust_val = trust_decision.trust_assessment.trust_score.overall_trust_score if trust_decision else 0.85

            confidence = self._confidence_engine.calculate_confidence(
                matches=matches,
                scenarios=scenarios,
                evidence_quality=quality_score,
                trust_score=trust_val,
            )

            # 8. Synthesize Pre-Mortem Summary Rationale
            summary = (
                f"PRE-MORTEM ANALYSIS: If current condition persists on '{fingerprint.incident_type}', "
                f"SLA breach is expected in {time_to_impact.min_time_minutes:.0f}–{time_to_impact.max_time_minutes:.0f} minutes. "
                f"Matched {len(matches)} historical incident(s) with {matches[0].similarity_score*100:.0f}% similarity. "
                f"Generated {len(scenarios)} future scenarios and {len(early_warnings)} early warning indicator(s)."
            )

            result = PreMortemResult(
                premortem_id=str(uuid.uuid4()),
                investigation_id=inv_id,
                request_id=req_id,
                fingerprint=fingerprint,
                historical_matches=matches,
                pattern_clusters=clusters,
                scenarios=scenarios,
                time_to_impact=time_to_impact,
                early_warnings=early_warnings,
                confidence=confidence,
                summary=summary,
            )

            logger.info(f"PreMortemEngine completed evaluation for request '{req_id}'")
            return result
