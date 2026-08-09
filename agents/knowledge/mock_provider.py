"""
Mock LLM Provider Implementation.

Provides a lightweight, deterministic implementation of the LLMProvider interface
for offline testing, local validation, and pipeline verification prior to Ollama integration.
"""

from typing import Any, Dict, Optional

from agents.core.logger import get_agent_logger
from agents.knowledge.llm_provider import LLMProvider

logger = get_agent_logger("MockProvider")


class MockProvider(LLMProvider):
    """
    Production-quality Mock LLM Provider producing structured deterministic responses.
    """

    def __init__(self, model_name: str = "mock-llm-v1", custom_response: Optional[str] = None) -> None:
        """
        Initialize MockProvider.

        Args:
            model_name: Model identifier string.
            custom_response: Optional custom text response override.
        """
        self._model_name = model_name
        self._custom_response = custom_response
        self._is_initialized = False

    def initialize(self) -> None:
        """Initialize mock provider resources."""
        self._is_initialized = True
        logger.info(f"Initialized MockProvider (model: {self._model_name})")

    def shutdown(self) -> None:
        """Shutdown mock provider resources."""
        self._is_initialized = False
        logger.info("Shutdown MockProvider")

    def generate(self, prompt: str, parameters: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate deterministic mock completion text.

        Args:
            prompt: Text prompt string.
            parameters: Execution parameters.

        Returns:
            Structured text or JSON string response.
        """
        if not self._is_initialized:
            self.initialize()

        if self._custom_response:
            return self._custom_response

        # Build deterministic structured response based on keywords in prompt
        prompt_lower = prompt.lower()

        if "congestion" in prompt_lower or "bandwidth" in prompt_lower:
            return (
                "ROOT CAUSE ANALYSIS:\n"
                "The interface is experiencing peak bandwidth saturation caused by concurrent data flows exceeding capacity limits.\n\n"
                "RECOMMENDED ACTIONS:\n"
                "1. Apply QoS shaping policy to limit bulk egress traffic.\n"
                "2. Re-route non-critical workloads to secondary WAN link.\n"
                "3. Monitor interface queue counters for packet drop recovery.\n\n"
                "CONFIDENCE: 0.92"
            )
        elif "latency" in prompt_lower:
            return (
                "ROOT CAUSE ANALYSIS:\n"
                "Transient queue bufferbloat is inducing round-trip time latency spikes on the egress transmit buffer.\n\n"
                "RECOMMENDED ACTIONS:\n"
                "1. Enable Fair-Queueing on transmit interface.\n"
                "2. Clear buffer congestion queues.\n\n"
                "CONFIDENCE: 0.88"
            )

        return (
            "ROOT CAUSE ANALYSIS:\n"
            "Predictive telemetry drift indicates impending resource saturation on the target interface.\n\n"
            "RECOMMENDED ACTIONS:\n"
            "1. Inspect interface status and error counters.\n"
            "2. Verify BGP neighbor peering timers.\n\n"
            "CONFIDENCE: 0.85"
        )

    def health(self) -> Dict[str, Any]:
        """Return health status."""
        return {
            "status": "ok",
            "provider_name": "MockProvider",
            "model_name": self._model_name,
            "is_initialized": self._is_initialized,
        }

    def metadata(self) -> Dict[str, Any]:
        """Return model metadata."""
        return {
            "provider_name": "MockProvider",
            "model_name": self._model_name,
            "max_tokens": 2048,
            "supports_streaming": False,
            "is_mock": True,
        }
