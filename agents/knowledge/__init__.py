"""
Agents Knowledge Subpackage Initialization.

Provides production KnowledgeAgent, KnowledgeService, KnowledgeRepository, KnowledgeValidator,
KnowledgePromptBuilder, KnowledgeCache, LLMProvider interface, MockProvider, OllamaProvider,
ProviderFactory, and domain models.
"""

from agents.knowledge.knowledge_agent import KnowledgeAgent, register_knowledge_agent
from agents.knowledge.knowledge_cache import KnowledgeCache
from agents.knowledge.knowledge_models import (
    KnowledgeCacheEntry,
    KnowledgeQuery,
    KnowledgeResult,
    KnowledgeStatistics,
)
from agents.knowledge.knowledge_prompt_builder import KnowledgePromptBuilder
from agents.knowledge.knowledge_repository import KnowledgeRepository
from agents.knowledge.knowledge_service import KnowledgeService
from agents.knowledge.knowledge_validator import KnowledgeValidator
from agents.knowledge.llm_provider import LLMProvider
from agents.knowledge.mock_provider import MockProvider
from agents.knowledge.ollama_provider import OllamaProvider
from agents.knowledge.provider_factory import ProviderFactory

__all__ = [
    "KnowledgeAgent",
    "register_knowledge_agent",
    "KnowledgeService",
    "KnowledgeRepository",
    "KnowledgeValidator",
    "KnowledgePromptBuilder",
    "KnowledgeCache",
    "LLMProvider",
    "MockProvider",
    "OllamaProvider",
    "ProviderFactory",
    "KnowledgeQuery",
    "KnowledgeResult",
    "KnowledgeCacheEntry",
    "KnowledgeStatistics",
]
