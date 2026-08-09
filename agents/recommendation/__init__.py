"""
Agents Recommendation Subpackage Initialization.

Provides production RecommendationAgent, RecommendationService, RecommendationRepository,
RecommendationValidator, RecommendationRules, RecommendationTemplateRegistry, and domain models.
"""

from agents.recommendation.recommendation_agent import RecommendationAgent, register_recommendation_agent
from agents.recommendation.recommendation_models import (
    ExecutionPlan,
    ImpactAssessment,
    RecommendationAction,
    RecommendationCommand,
    RecommendationPriority,
    RecommendationRecord,
    RecommendationStatistics,
    RiskLevel,
    RollbackPlan,
)
from agents.recommendation.recommendation_repository import RecommendationRepository
from agents.recommendation.recommendation_rules import RecommendationRules
from agents.recommendation.recommendation_service import RecommendationService
from agents.recommendation.recommendation_templates import RecommendationTemplateRegistry
from agents.recommendation.recommendation_validator import RecommendationValidator

__all__ = [
    "RecommendationAgent",
    "register_recommendation_agent",
    "RecommendationService",
    "RecommendationRepository",
    "RecommendationValidator",
    "RecommendationRules",
    "RecommendationTemplateRegistry",
    "RecommendationRecord",
    "RecommendationPriority",
    "RiskLevel",
    "RecommendationCommand",
    "RecommendationAction",
    "RollbackPlan",
    "ImpactAssessment",
    "ExecutionPlan",
    "RecommendationStatistics",
]
