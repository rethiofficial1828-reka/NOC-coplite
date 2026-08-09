"""
Runtime Capability Aggregator and Caching Manager.

Combines OSDetector, GPUDetector, OllamaDetector, ModelDetector, InferenceSelector,
and RuntimeHealthEvaluator into a unified capability manager with TTL caching to avoid
repeated expensive subprocess/HTTP queries.
"""

from datetime import datetime, timezone
import threading
from typing import Optional

from agents.runtime.capability_manager import *  # Forward reference safety
from agents.runtime.gpu_detector import GPUDetector
from agents.runtime.inference_selector import InferenceSelector
from agents.runtime.model_detector import ModelDetector
from agents.runtime.ollama_detector import OllamaDetector
from agents.runtime.os_detector import OSDetector
from agents.runtime.runtime_health import RuntimeHealthEvaluator
from agents.runtime.runtime_models import (
    CapabilityStatus,
    RuntimeCapabilities,
    RuntimeHealthStatus,
)


class CapabilityManager:
    """
    Thread-safe manager aggregating hardware/software detectors with TTL caching.
    """

    def __init__(
        self,
        ttl_seconds: float = 60.0,
        os_detector: Optional[OSDetector] = None,
        gpu_detector: Optional[GPUDetector] = None,
        ollama_detector: Optional[OllamaDetector] = None,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._os_detector = os_detector or OSDetector()
        self._gpu_detector = gpu_detector or GPUDetector()
        self._ollama_detector = ollama_detector or OllamaDetector()
        self._model_detector = ModelDetector(self._ollama_detector)
        self._selector = InferenceSelector()
        self._evaluator = RuntimeHealthEvaluator()

        self._lock = threading.RLock()
        self._cached_capabilities: Optional[RuntimeCapabilities] = None
        self._last_detection_time: float = 0.0

    def get_capabilities(self, force_refresh: bool = False) -> RuntimeCapabilities:
        """
        Get aggregated runtime capabilities, using TTL cache unless force_refresh=True.
        """
        with self._lock:
            now = datetime.now(timezone.utc).timestamp()
            if not force_refresh and self._cached_capabilities and (now - self._last_detection_time) < self._ttl_seconds:
                return self._cached_capabilities

            # Perform detection
            os_info = self._os_detector.detect()
            gpu_info = self._gpu_detector.detect(os_type=os_info.operating_system, is_virtualized=os_info.is_virtualized)
            ollama_info = self._ollama_detector.detect()

            selected_backend = self._selector.select_backend(gpu_info, ollama_info)

            caps = RuntimeCapabilities(
                operating_system=os_info.operating_system,
                architecture=os_info.architecture,
                virtualization_environment=os_info.virtualization_environment,
                python_version=os_info.python_version,
                cpu_count=os_info.cpu_count,
                total_memory_gb=os_info.total_memory_gb,
                available_memory_gb=os_info.available_memory_gb,
                gpu_vendor=gpu_info.vendor,
                gpu_name=gpu_info.name,
                gpu_memory_mb=gpu_info.vram_mb,
                gpu_driver_version=gpu_info.driver_version,
                cuda_available=gpu_info.cuda_available,
                gpu_status=gpu_info.status,
                is_guest_gpu_exposed=gpu_info.is_guest_exposed,
                ollama_available=ollama_info.available,
                ollama_location=ollama_info.location,
                ollama_endpoint=ollama_info.endpoint_url,
                ollama_version=ollama_info.version,
                qwen_available=ollama_info.qwen_available,
                qwen_model=ollama_info.qwen_model_tag,
                selected_backend=selected_backend,
                detection_timestamp=datetime.now(timezone.utc),
            )

            # Evaluate health and set degradation reason
            health_status = self._evaluator.evaluate(caps)
            caps.runtime_health = health_status.health

            self._cached_capabilities = caps
            self._last_detection_time = now
            return caps

    def get_health_status(self, force_refresh: bool = False) -> RuntimeHealthStatus:
        """
        Get structured diagnostic health evaluation.
        """
        caps = self.get_capabilities(force_refresh=force_refresh)
        return self._evaluator.evaluate(caps)

    def invalidate_cache(self) -> None:
        """Explicitly clear capability cache."""
        with self._lock:
            self._cached_capabilities = None
            self._last_detection_time = 0.0
