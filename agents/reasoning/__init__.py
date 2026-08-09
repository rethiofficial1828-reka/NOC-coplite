"""
Enterprise Reasoning & Evidence Correlation Package.

Provides evidence correlation, competing hypothesis generation, contradiction detection,
evidence validation, dynamic confidence computation, root cause ranking, and explainable
reasoning conclusions for NOC Copilot.
"""

from agents.reasoning.confidence_engine import ConfidenceEngine
from agents.reasoning.contradiction_detector import ContradictionDetector
from agents.reasoning.evidence_correlator import EvidenceCorrelator
from agents.reasoning.evidence_validator import EvidenceValidator
from agents.reasoning.hypothesis_generator import HypothesisGenerator
from agents.reasoning.reasoning_agent import ReasoningAgent
from agents.reasoning.reasoning_models import (
    ConfidenceFactors,
    ConfidenceResult,
    Contradiction,
    ContradictionSeverity,
    EvidenceCorrelation,
    EvidenceGroup,
    Hypothesis,
    HypothesisCategory,
    HypothesisScore,
    InvestigationConclusion,
    RankedRootCause,
    ReasoningEvidence,
    ReasoningExplanation,
    ReasoningResult,
    ReasoningStatistics,
    RootCause,
    ValidationResult,
)
from agents.reasoning.reasoning_service import ReasoningService
from agents.reasoning.root_cause_ranker import RootCauseRanker

__all__ = [
    "HypothesisCategory",
    "ContradictionSeverity",
    "ReasoningEvidence",
    "EvidenceGroup",
    "EvidenceCorrelation",
    "Hypothesis",
    "HypothesisScore",
    "Contradiction",
    "ValidationResult",
    "ConfidenceFactors",
    "ConfidenceResult",
    "RootCause",
    "RankedRootCause",
    "ReasoningExplanation",
    "InvestigationConclusion",
    "ReasoningStatistics",
    "ReasoningResult",
    "EvidenceCorrelator",
    "HypothesisGenerator",
    "ContradictionDetector",
    "EvidenceValidator",
    "ConfidenceEngine",
    "RootCauseRanker",
    "ReasoningService",
    "ReasoningAgent",
]
