"""
Embedding Provider Factory Module.

Provides dynamic registration and creation of IEmbeddingProvider instances based on environment or configuration settings.
"""

from typing import Dict, Optional, Type

from agents.core.logger import get_agent_logger
from agents.rag.embedding_provider import (
    BGEEmbeddingProvider,
    NomicEmbeddingProvider,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    SentenceTransformersEmbeddingProvider,
    TFIDFEmbeddingProvider,
)
from agents.rag.interfaces import IEmbeddingProvider

logger = get_agent_logger("EmbeddingProviderFactory")


class EmbeddingProviderFactory:
    """
    Factory registry for creating and resolving IEmbeddingProvider instances.
    """

    _registry: Dict[str, Type[IEmbeddingProvider]] = {
        "tfidf": TFIDFEmbeddingProvider,
        "ollama": OllamaEmbeddingProvider,
        "sentencetransformers": SentenceTransformersEmbeddingProvider,
        "openai": OpenAIEmbeddingProvider,
        "bge": BGEEmbeddingProvider,
        "nomic": NomicEmbeddingProvider,
    }

    @classmethod
    def register_provider(cls, name: str, provider_cls: Type[IEmbeddingProvider]) -> None:
        """Register a custom embedding provider class."""
        key = name.lower().strip()
        cls._registry[key] = provider_cls
        logger.info(f"Registered embedding provider '{key}'.")

    @classmethod
    def create_provider(
        self, provider_type: str = "tfidf", **kwargs
    ) -> IEmbeddingProvider:
        """
        Create an instance of IEmbeddingProvider.

        Args:
            provider_type: Key identifier ('tfidf', 'ollama', 'sentencetransformers', etc.)
            kwargs: Parameters passed to provider constructor.

        Returns:
            Configured IEmbeddingProvider instance.
        """
        key = provider_type.lower().strip()
        provider_cls = self._registry.get(key, TFIDFEmbeddingProvider)

        try:
            instance = provider_cls(**kwargs)
            logger.info(f"Created embedding provider '{instance.provider_name}' (dim={instance.dimension}).")
            return instance
        except Exception as e:
            logger.warning(
                f"Failed to instantiate embedding provider '{key}' ({e}). Falling back to TFIDFEmbeddingProvider."
            )
            return TFIDFEmbeddingProvider()
