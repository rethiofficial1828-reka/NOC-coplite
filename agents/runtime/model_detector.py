"""
Primary LLM Model Presence Detector.

Specifically verifies availability of the required primary model (qwen3:1.7b).
Enforces zero silent substitution rules.
"""

from typing import Optional, Tuple

from agents.runtime.ollama_detector import OllamaDetector
from config.settings import OLLAMA_MODEL


class ModelDetector:
    """
    Detector verifying required primary LLM model registration.
    """

    def __init__(self, ollama_detector: Optional[OllamaDetector] = None) -> None:
        self._ollama_detector = ollama_detector or OllamaDetector()

    def verify_primary_model(self, endpoint_url: str) -> Tuple[bool, str]:
        """
        Verify presence of primary model qwen3:1.7b on target Ollama endpoint.

        Returns:
            Tuple of (is_available, status_message)
        """
        info = self._ollama_detector.detect(endpoint_url)
        if not info.available:
            return False, f"Ollama endpoint at {endpoint_url} is unavailable."

        if info.qwen_available:
            return True, f"Primary model '{OLLAMA_MODEL}' registered and ready."

        return False, f"MODEL_UNAVAILABLE: Primary model '{OLLAMA_MODEL}' is missing on Ollama endpoint {endpoint_url}."
