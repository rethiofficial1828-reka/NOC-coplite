"""
Runtime Capability & Hardware Acceleration Subsystem.

Provides OS detection, virtualization classification, GPU/CUDA discovery,
Ollama service probe, model verification, deterministic inference backend selection,
runtime health tracking, and Atomic RuntimeAgent interface.
"""

from agents.runtime.capability_manager import CapabilityManager
from agents.runtime.gpu_detector import GPUDetector
from agents.runtime.inference_selector import InferenceSelector
from agents.runtime.model_detector import ModelDetector
from agents.runtime.ollama_detector import OllamaDetector
from agents.runtime.os_detector import OSDetector
from agents.runtime.runtime_agent import RuntimeAgent
from agents.runtime.runtime_health import RuntimeHealthEvaluator
from agents.runtime.runtime_models import (
    CapabilityStatus,
    GPUCapability,
    GPUInfo,
    GPUVendor,
    InferenceBackend,
    OllamaInfo,
    OllamaLocation,
    OSInfo,
    OperatingSystem,
    RuntimeCapabilities,
    RuntimeHealth,
    RuntimeHealthStatus,
    VirtualizationEnvironment,
)
from agents.runtime.runtime_service import RuntimeService
from agents.runtime.startup_health import HealthCheckItem, StartupHealthReport, StartupHealthService

__all__ = [
    "CapabilityManager",
    "GPUDetector",
    "InferenceSelector",
    "ModelDetector",
    "OllamaDetector",
    "OSDetector",
    "RuntimeAgent",
    "RuntimeHealthEvaluator",
    "RuntimeService",
    "HealthCheckItem",
    "StartupHealthReport",
    "StartupHealthService",
    "CapabilityStatus",
    "GPUCapability",
    "GPUInfo",
    "GPUVendor",
    "InferenceBackend",
    "OllamaInfo",
    "OllamaLocation",
    "OSInfo",
    "OperatingSystem",
    "RuntimeCapabilities",
    "RuntimeHealth",
    "RuntimeHealthStatus",
    "VirtualizationEnvironment",
]
