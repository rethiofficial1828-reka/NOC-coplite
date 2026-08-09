"""
LLM Provider Factory Module.

Instantiates appropriate LLMProvider instances (MockProvider, OllamaProvider, or future providers)
based on central ConfigManager configuration or explicit dependency injection.
"""

import threading
from typing import Any, Dict, Optional, Type

from agents.core.container import ServiceContainer
from agents.core.exceptions import ConfigurationError
from agents.core.logger import get_agent_logger
from agents.knowledge.llm_provider import LLMProvider
from agents.knowledge.mock_provider import MockProvider
from agents.knowledge.ollama_provider import OllamaProvider
from config.config_manager import ConfigManager
from config.settings import LLM_PROVIDER_TYPE

logger = get_agent_logger("ProviderFactory")


class ProviderFactory:
    """
    Factory for instantiating LLMProvider instances dynamically.
    """

    _registry: Dict[str, Type[LLMProvider]] = {
        "mock": MockProvider,
        "ollama": OllamaProvider,
    }
    _lock = threading.RLock()

    @classmethod
    def register_provider_class(cls, type_name: str, provider_cls: Type[LLMProvider]) -> None:
        """
        Register a new LLMProvider class dynamically for future extensibility (OpenAI, Anthropic, etc.).

        Args:
            type_name: Provider key string (e.g. 'openai', 'anthropic', 'vllm').
            provider_cls: Subclass of LLMProvider.
        """
        with cls._lock:
            key = type_name.lower().strip()
            cls._registry[key] = provider_cls
            logger.info(f"Registered LLM provider class '{provider_cls.__name__}' for type key '{key}'.")

    @classmethod
    def create_provider(
        cls,
        provider_type: Optional[str] = None,
        container: Optional[ServiceContainer] = None,
        config_manager: Optional[ConfigManager] = None,
        **kwargs: Any,
    ) -> LLMProvider:
        """
        Create and return an LLMProvider instance based on configuration or explicit type.

        Args:
            provider_type: Optional explicit provider type key ('mock', 'ollama', etc.).
            container: Optional ServiceContainer instance.
            config_manager: Optional ConfigManager instance.
            **kwargs: Additional keyword arguments passed to provider constructor.

        Returns:
            Instantiated LLMProvider object.

        Raises:
            ConfigurationError: If requested provider type is unknown.
        """
        cfg = config_manager or ConfigManager.get_instance()
        target_type = (provider_type or cfg.get("LLM_PROVIDER_TYPE", LLM_PROVIDER_TYPE)).lower().strip()

        # Check ServiceContainer first if registered
        if container and container.has(LLMProvider):
            instance = container.get(LLMProvider)
            if isinstance(instance, LLMProvider):
                return instance

        with cls._lock:
            if target_type not in cls._registry:
                raise ConfigurationError(
                    f"Unknown LLM provider type '{target_type}'. Registered types: {list(cls._registry.keys())}"
                )

            provider_cls = cls._registry[target_type]
            provider_instance = provider_cls(**kwargs)
            logger.info(f"Created LLM provider '{provider_cls.__name__}' for type '{target_type}'.")

            # Register in ServiceContainer if container provided
            if container and not container.has(LLMProvider):
                container.register_instance(LLMProvider, provider_instance)

            return provider_instance
