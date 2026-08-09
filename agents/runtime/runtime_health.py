"""
Runtime Health and Degradation Rationale Evaluator.

Assesses overall runtime health (READY, DEGRADED, UNAVAILABLE) and formats structured
diagnostic summaries for NOC Copilot operations.
"""

from agents.runtime.runtime_models import (
    CapabilityStatus,
    InferenceBackend,
    OllamaLocation,
    RuntimeCapabilities,
    RuntimeHealth,
    RuntimeHealthStatus,
    VirtualizationEnvironment,
)


class RuntimeHealthEvaluator:
    """
    Evaluator determining runtime operational readiness.
    """

    def evaluate(self, caps: RuntimeCapabilities) -> RuntimeHealthStatus:
        """
        Evaluate capabilities into RuntimeHealthStatus.
        """
        details = {
            "operating_system": caps.operating_system.value,
            "architecture": caps.architecture,
            "virtualization_environment": caps.virtualization_environment.value,
            "gpu_vendor": caps.gpu_vendor.value,
            "gpu_name": caps.gpu_name,
            "gpu_status": caps.gpu_status.value,
            "is_guest_gpu_exposed": caps.is_guest_gpu_exposed,
            "ollama_available": caps.ollama_available,
            "ollama_location": caps.ollama_location.value,
            "ollama_endpoint": caps.ollama_endpoint,
            "qwen_available": caps.qwen_available,
            "selected_backend": caps.selected_backend.value,
        }

        recs = []

        # 1. Native / Full GPU Acceleration -> READY
        if caps.selected_backend in (InferenceBackend.OLLAMA_GPU_LOCAL, InferenceBackend.OLLAMA_GPU_REMOTE):
            health = RuntimeHealth.READY
            if caps.ollama_location == OllamaLocation.LOCAL_OLLAMA:
                summary = f"System Ready. Local GPU Acceleration Active ({caps.gpu_name})."
            else:
                summary = f"System Ready. Remote Host GPU Inference Active via {caps.ollama_endpoint}."
            return RuntimeHealthStatus(health=health, selected_backend=caps.selected_backend, summary=summary, details=details, recommendations=recs)

        # 2. CPU Fallback / Virtualized VM without GPU exposure -> DEGRADED
        if caps.selected_backend in (InferenceBackend.OLLAMA_CPU_LOCAL, InferenceBackend.OLLAMA_CPU_REMOTE, InferenceBackend.LOCAL_CPU):
            health = RuntimeHealth.DEGRADED
            reason_parts = []

            if caps.virtualization_environment == VirtualizationEnvironment.VIRTUALBOX and not caps.is_guest_gpu_exposed:
                reason_parts.append("Physical NVIDIA GPU is not exposed to VirtualBox guest VM.")
                recs.append("If host GPU inference is desired, point OLLAMA_BASE_URL to Windows host endpoint.")

            if not caps.ollama_available:
                reason_parts.append("Ollama LLM service endpoint is unreachable.")
                recs.append("Start Ollama service via 'ollama serve' or check network endpoint.")
            elif not caps.qwen_available:
                reason_parts.append("Required primary model 'qwen3:1.7b' is missing on Ollama.")
                recs.append("Run 'ollama pull qwen3:1.7b' to download required primary model.")
            else:
                reason_parts.append("Running on CPU fallback mode.")

            summary = f"System Operating in DEGRADED Mode: {' '.join(reason_parts)}"
            caps.degradation_reason = summary
            return RuntimeHealthStatus(health=health, selected_backend=caps.selected_backend, summary=summary, details=details, recommendations=recs)

        # 3. Completely Unavailable -> UNAVAILABLE
        health = RuntimeHealth.UNAVAILABLE
        summary = "System UNAVAILABLE: No inference engine or model available."
        recs.append("Install and start Ollama service with qwen3:1.7b model.")
        caps.degradation_reason = summary
        return RuntimeHealthStatus(health=health, selected_backend=caps.selected_backend, summary=summary, details=details, recommendations=recs)
