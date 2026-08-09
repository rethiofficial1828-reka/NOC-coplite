"""
LLM Provider Abstract Interface.

Defines the contract for LLM inference engines (MockProvider, OllamaProvider, AtomicAgentProvider).
KnowledgeAgent depends strictly on this interface — never on specific LLM SDKs or external services.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class LLMProvider(ABC):
    """
    Abstract Interface for LLM Inference Providers.
    """

    @abstractmethod
    def initialize(self) -> None:
        """Initialize provider connections, model weights, or API clients."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Release provider resources cleanly."""
        pass

    @abstractmethod
    def generate(self, prompt: str, parameters: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate text completion or structured response for a given prompt.

        Args:
            prompt: Formatted text prompt.
            parameters: Optional execution parameters (temperature, max_tokens, etc.).

        Returns:
            Generated text string response.
        """
        pass

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """
        Check health and connectivity status of the provider.

        Returns:
            Dict containing status ('ok', 'degraded', 'error'), provider_name, and message.
        """
        pass

    @abstractmethod
    def metadata(self) -> Dict[str, Any]:
        """
        Return provider capabilities, model details, and version information.

        Returns:
            Dict containing model metadata attributes.
        """
        pass
