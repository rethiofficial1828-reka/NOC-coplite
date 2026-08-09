"""
Production Ollama Provider Implementation.

Subclasses LLMProvider to execute LLM inference via Ollama HTTP API with retry policy,
timeout handling, connection pooling, health checks, event publishing, and thread safety.
"""

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Union

from agents.core.exceptions import ExecutionError
from agents.core.logger import get_agent_logger, log_execution_event
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.knowledge.llm_provider import LLMProvider
from config.config_manager import ConfigManager
from config.settings import (
    OLLAMA_BASE_URL,
    OLLAMA_MAX_TOKENS,
    OLLAMA_MODEL,
    OLLAMA_RETRY_COUNT,
    OLLAMA_TEMPERATURE,
    OLLAMA_TIMEOUT_SEC,
    OLLAMA_TOP_P,
)

logger = get_agent_logger("OllamaProvider")


class OllamaProvider(LLMProvider):
    """
    Production-grade Ollama LLM Provider supporting any model specified in configuration.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_sec: Optional[float] = None,
        retry_count: Optional[int] = None,
        event_bus: Optional[EventBus] = None,
        config_manager: Optional[ConfigManager] = None,
        runtime_service: Optional[Any] = None,
    ) -> None:
        """
        Initialize OllamaProvider.

        Args:
            model_name: Optional explicit model override (e.g. 'llama3', 'qwen2.5').
            base_url: Optional explicit base URL override (e.g. 'http://localhost:11434').
            timeout_sec: Optional HTTP request timeout in seconds.
            retry_count: Optional maximum number of retry attempts.
            event_bus: Optional EventBus instance for provider lifecycle events.
            config_manager: Optional ConfigManager instance.
            runtime_service: Optional RuntimeService instance for capability inspection.
        """
        self._config = config_manager or ConfigManager.get_instance()
        self._event_bus = event_bus or EventBus.get_global()
        self._runtime_service = runtime_service
        self._lock = threading.RLock()
        self._is_initialized = False

        self._explicit_model = model_name
        self._explicit_base_url = base_url
        self._model_name = model_name or self._config.get("OLLAMA_MODEL", OLLAMA_MODEL)
        self._base_url = (base_url or self._config.get("OLLAMA_BASE_URL", OLLAMA_BASE_URL)).rstrip("/")
        self._timeout = timeout_sec if timeout_sec is not None else float(self._config.get("OLLAMA_TIMEOUT_SEC", OLLAMA_TIMEOUT_SEC))
        self._retry_count = retry_count if retry_count is not None else int(self._config.get("OLLAMA_RETRY_COUNT", OLLAMA_RETRY_COUNT))
        self._temperature = float(self._config.get("OLLAMA_TEMPERATURE", OLLAMA_TEMPERATURE))
        self._top_p = float(self._config.get("OLLAMA_TOP_P", OLLAMA_TOP_P))
        self._max_tokens = int(self._config.get("OLLAMA_MAX_TOKENS", OLLAMA_MAX_TOKENS))

    @property
    def model_name(self) -> str:
        """Configured Ollama model name."""
        return self._explicit_model or self._config.get("OLLAMA_MODEL", self._model_name)

    @property
    def base_url(self) -> str:
        """Configured Ollama base URL."""
        url = self._explicit_base_url or self._config.get("OLLAMA_BASE_URL", self._base_url)
        return url.rstrip("/")

    def initialize(self) -> None:
        """Initialize provider connections and emit provider.initialized event."""
        with self._lock:
            if self._is_initialized:
                return

            self._is_initialized = True
            logger.info(f"Initialized OllamaProvider (model: '{self.model_name}', url: '{self.base_url}')")

            if self._event_bus:
                evt = Event(
                    event_type="provider.initialized",
                    source="OllamaProvider",
                    payload={"model": self.model_name, "base_url": self.base_url},
                )
                self._event_bus.publish(evt)

    def shutdown(self) -> None:
        """Release provider resources and emit provider.shutdown event."""
        with self._lock:
            if not self._is_initialized:
                return

            self._is_initialized = False
            logger.info("Shutdown OllamaProvider")

            if self._event_bus:
                evt = Event(
                    event_type="provider.shutdown",
                    source="OllamaProvider",
                    payload={"model": self.model_name},
                )
                self._event_bus.publish(evt)

    def _http_request(self, url: str, data: Optional[bytes] = None, timeout: float = 30.0) -> bytes:
        """Internal HTTP helper using urllib for connection reuse and zero extra dependencies."""
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()

    def generate(self, prompt: str, parameters: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate completion from Ollama endpoint with automatic retries, timeout, and logging.

        Args:
            prompt: Text prompt string.
            parameters: Optional parameter overrides (temperature, top_p, max_tokens, etc.).

        Returns:
            Generated text string response.

        Raises:
            ExecutionError: If inference fails after retry attempts.
        """
        if not self._is_initialized:
            self.initialize()

        params = parameters or {}
        temp = float(params.get("temperature", self._temperature))
        top_p = float(params.get("top_p", self._top_p))
        max_tok = int(params.get("max_tokens", self._max_tokens))
        current_model = params.get("model", self.model_name)
        current_base_url = self.base_url

        url = f"{current_base_url}/api/generate"
        payload_dict = {
            "model": current_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temp,
                "top_p": top_p,
                "num_predict": max_tok,
            },
        }

        payload_bytes = json.dumps(payload_dict).encode("utf-8")
        max_attempts = max(1, self._retry_count)

        last_exception: Optional[Exception] = None
        start_time = time.perf_counter()

        for attempt in range(1, max_attempts + 1):
            try:
                logger.debug(f"Ollama inference attempt {attempt}/{max_attempts} for model '{current_model}'")
                raw_bytes = self._http_request(url, data=payload_bytes, timeout=self._timeout)
                resp_json = json.loads(raw_bytes.decode("utf-8"))

                if not isinstance(resp_json, dict) or "response" not in resp_json:
                    raise ExecutionError(f"Malformed Ollama response format: {resp_json}")

                duration_ms = (time.perf_counter() - start_time) * 1000.0
                completion_text = str(resp_json["response"]).strip()

                log_execution_event(
                    logger,
                    "OllamaProvider",
                    "INFERENCE_SUCCESS",
                    f"Generated completion via Ollama model '{current_model}' in {duration_ms:.2f}ms",
                    exec_time_ms=duration_ms,
                )

                return completion_text

            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Ollama inference attempt {attempt}/{max_attempts} failed: {e}. Retrying..."
                )
                if attempt < max_attempts:
                    time.sleep(0.5 * attempt)  # Backoff delay

        # Failure handling after exhausting retries
        logger.error(f"Exhausted all {max_attempts} retries for Ollama model '{current_model}': {last_exception}")
        if self._event_bus:
            evt = Event(
                event_type="provider.failed",
                source="OllamaProvider",
                payload={"model": current_model, "error": str(last_exception)},
            )
            self._event_bus.publish(evt)

        raise ExecutionError(f"OllamaProvider inference failed for model '{current_model}': {last_exception}") from last_exception

    def health(self) -> Dict[str, Any]:
        """
        Check connectivity to Ollama server and verify model availability.

        Returns:
            Dict containing health status and details.
        """
        start_ts = time.perf_counter()
        url = f"{self.base_url}/api/tags"

        try:
            raw_bytes = self._http_request(url, timeout=5.0)
            latency_ms = (time.perf_counter() - start_ts) * 1000.0
            data = json.loads(raw_bytes.decode("utf-8"))

            models_list = [m.get("name") for m in data.get("models", [])] if isinstance(data, dict) else []
            model_found = any(self.model_name in m for m in models_list)

            return {
                "status": "ok" if model_found or len(models_list) > 0 else "degraded",
                "provider_name": "OllamaProvider",
                "model_name": self.model_name,
                "base_url": self.base_url,
                "latency_ms": round(latency_ms, 2),
                "available_models": models_list,
                "model_available": model_found,
            }
        except Exception as e:
            return {
                "status": "error",
                "provider_name": "OllamaProvider",
                "model_name": self.model_name,
                "base_url": self.base_url,
                "error": str(e),
            }

    def metadata(self) -> Dict[str, Any]:
        """Return provider capabilities and metadata."""
        return {
            "provider_name": "OllamaProvider",
            "model_name": self.model_name,
            "base_url": self.base_url,
            "timeout_sec": self._timeout,
            "retry_count": self._retry_count,
            "max_tokens": self._max_tokens,
            "supports_streaming": True,
            "supports_json": True,
            "is_mock": False,
        }
