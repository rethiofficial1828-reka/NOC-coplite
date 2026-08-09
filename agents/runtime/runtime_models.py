"""
Strongly Typed Pydantic V2 Domain Models for Enterprise Runtime & Hardware Acceleration Layer.

Provides schemas and enums for OS detection, virtualization context, GPU hardware detection,
Ollama endpoint classification, inference backend selection, and runtime health tracking.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field, ConfigDict


class OperatingSystem(str, Enum):
    """Supported operating systems."""

    WINDOWS = "WINDOWS"
    LINUX = "LINUX"
    MACOS = "MACOS"
    UNKNOWN = "UNKNOWN"


class VirtualizationEnvironment(str, Enum):
    """Virtualization / container environment classification."""

    NATIVE = "NATIVE"
    VIRTUALBOX = "VIRTUALBOX"
    VMWARE = "VMWARE"
    WSL = "WSL"
    DOCKER = "DOCKER"
    UNKNOWN = "UNKNOWN"


class GPUVendor(str, Enum):
    """GPU hardware vendor classification."""

    NVIDIA = "NVIDIA"
    AMD = "AMD"
    INTEL = "INTEL"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class CapabilityStatus(str, Enum):
    """Hardware or service capability status."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_EXPOSED_TO_GUEST = "NOT_EXPOSED_TO_GUEST"
    UNKNOWN = "UNKNOWN"


class OllamaLocation(str, Enum):
    """Network location of the targeted Ollama LLM service."""

    LOCAL_OLLAMA = "LOCAL_OLLAMA"
    REMOTE_OLLAMA = "REMOTE_OLLAMA"
    UNAVAILABLE = "UNAVAILABLE"


class InferenceBackend(str, Enum):
    """Selected LLM inference execution backend."""

    OLLAMA_GPU_LOCAL = "OLLAMA_GPU_LOCAL"
    OLLAMA_GPU_REMOTE = "OLLAMA_GPU_REMOTE"
    OLLAMA_CPU_LOCAL = "OLLAMA_CPU_LOCAL"
    OLLAMA_CPU_REMOTE = "OLLAMA_CPU_REMOTE"
    LOCAL_CPU = "LOCAL_CPU"
    UNAVAILABLE = "UNAVAILABLE"


class RuntimeHealth(str, Enum):
    """Overall operational health of the AI runtime environment."""

    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class OSInfo(BaseModel):
    """Operating system and host hardware platform details."""

    model_config = ConfigDict(frozen=False)

    operating_system: OperatingSystem = Field(default=OperatingSystem.UNKNOWN)
    platform_name: str = Field(default="Unknown")
    architecture: str = Field(default="x86_64")
    python_version: str = Field(default="3.13.0")
    cpu_count: int = Field(default=1, ge=1)
    total_memory_gb: float = Field(default=0.0, ge=0.0)
    available_memory_gb: float = Field(default=0.0, ge=0.0)
    virtualization_environment: VirtualizationEnvironment = Field(default=VirtualizationEnvironment.UNKNOWN)
    is_virtualized: bool = Field(default=False)


class GPUInfo(BaseModel):
    """Physical GPU hardware detection status."""

    model_config = ConfigDict(frozen=False)

    vendor: GPUVendor = Field(default=GPUVendor.NONE)
    name: str = Field(default="None")
    vram_mb: float = Field(default=0.0, ge=0.0)
    driver_version: str = Field(default="None")
    cuda_available: bool = Field(default=False)
    status: CapabilityStatus = Field(default=CapabilityStatus.UNAVAILABLE)
    is_guest_exposed: bool = Field(default=False)
    detection_method: str = Field(default="NONE")
    error_message: Optional[str] = Field(default=None)


class OllamaInfo(BaseModel):
    """Ollama LLM service discovery status."""

    model_config = ConfigDict(frozen=False)

    available: bool = Field(default=False)
    location: OllamaLocation = Field(default=OllamaLocation.UNAVAILABLE)
    endpoint_url: str = Field(default="http://127.0.0.1:11434")
    version: str = Field(default="Unknown")
    qwen_available: bool = Field(default=False)
    qwen_model_tag: str = Field(default="qwen3:1.7b")
    remote_gpu_accelerated: bool = Field(default=False)
    error_message: Optional[str] = Field(default=None)


class RuntimeCapabilities(BaseModel):
    """Complete composite hardware & software capability matrix for NOC Copilot."""

    model_config = ConfigDict(frozen=False)

    capability_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    operating_system: OperatingSystem = Field(default=OperatingSystem.UNKNOWN)
    architecture: str = Field(default="x86_64")
    virtualization_environment: VirtualizationEnvironment = Field(default=VirtualizationEnvironment.UNKNOWN)
    python_version: str = Field(default="3.13.0")
    cpu_count: int = Field(default=1, ge=1)
    total_memory_gb: float = Field(default=0.0, ge=0.0)
    available_memory_gb: float = Field(default=0.0, ge=0.0)

    # GPU fields
    gpu_vendor: GPUVendor = Field(default=GPUVendor.NONE)
    gpu_name: str = Field(default="None")
    gpu_memory_mb: float = Field(default=0.0, ge=0.0)
    gpu_driver_version: str = Field(default="None")
    cuda_available: bool = Field(default=False)
    gpu_status: CapabilityStatus = Field(default=CapabilityStatus.UNAVAILABLE)
    is_guest_gpu_exposed: bool = Field(default=False)

    # Ollama fields
    ollama_available: bool = Field(default=False)
    ollama_location: OllamaLocation = Field(default=OllamaLocation.UNAVAILABLE)
    ollama_endpoint: str = Field(default="http://127.0.0.1:11434")
    ollama_version: str = Field(default="Unknown")
    qwen_available: bool = Field(default=False)
    qwen_model: str = Field(default="qwen3:1.7b")

    # Selection & Health
    selected_backend: InferenceBackend = Field(default=InferenceBackend.UNAVAILABLE)
    runtime_health: RuntimeHealth = Field(default=RuntimeHealth.UNAVAILABLE)
    degradation_reason: Optional[str] = Field(default=None)
    detection_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RuntimeHealthStatus(BaseModel):
    """Diagnostic health assessment output payload."""

    model_config = ConfigDict(frozen=False)

    health: RuntimeHealth = Field(default=RuntimeHealth.UNAVAILABLE)
    selected_backend: InferenceBackend = Field(default=InferenceBackend.UNAVAILABLE)
    summary: str = Field(...)
    details: Dict[str, Any] = Field(default_factory=dict)
    recommendations: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
