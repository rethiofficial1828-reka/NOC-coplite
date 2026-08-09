"""
Deterministic Inference Execution Backend Selector.

Determines the optimal inference backend (OLLAMA_GPU_LOCAL, OLLAMA_GPU_REMOTE,
OLLAMA_CPU_LOCAL, OLLAMA_CPU_REMOTE, LOCAL_CPU, UNAVAILABLE) strictly grounded in
actual hardware exposure and endpoint capability.
"""

from agents.runtime.runtime_models import (
    CapabilityStatus,
    GPUInfo,
    GPUVendor,
    InferenceBackend,
    OllamaInfo,
    OllamaLocation,
)


class InferenceSelector:
    """
    Selector enforcing deterministic backend selection rules.
    """

    def select_backend(self, gpu_info: GPUInfo, ollama_info: OllamaInfo) -> InferenceBackend:
        """
        Select best available backend according to strict priority matrix.

        Args:
            gpu_info: Local GPU hardware inspection result.
            ollama_info: Ollama service discovery result.
        """
        # 1. Ollama is available
        if ollama_info.available and ollama_info.qwen_available:
            # Case A: Local Ollama with physical GPU exposed locally
            if (
                ollama_info.location == OllamaLocation.LOCAL_OLLAMA
                and gpu_info.vendor == GPUVendor.NVIDIA
                and gpu_info.status == CapabilityStatus.AVAILABLE
                and gpu_info.is_guest_exposed
            ):
                return InferenceBackend.OLLAMA_GPU_LOCAL

            # Case B: Remote Ollama (e.g. Windows Host from Kali VM) with GPU acceleration
            if (
                ollama_info.location == OllamaLocation.REMOTE_OLLAMA
                and ollama_info.remote_gpu_accelerated
            ):
                return InferenceBackend.OLLAMA_GPU_REMOTE

            # Case C: Local Ollama CPU only
            if ollama_info.location == OllamaLocation.LOCAL_OLLAMA:
                return InferenceBackend.OLLAMA_CPU_LOCAL

            # Case D: Remote Ollama CPU only
            if ollama_info.location == OllamaLocation.REMOTE_OLLAMA:
                return InferenceBackend.OLLAMA_CPU_REMOTE

        # 2. Ollama is available without qwen verification (degraded execution)
        if ollama_info.available:
            if (
                ollama_info.location == OllamaLocation.LOCAL_OLLAMA
                and gpu_info.vendor == GPUVendor.NVIDIA
                and gpu_info.is_guest_exposed
            ):
                return InferenceBackend.OLLAMA_GPU_LOCAL
            elif ollama_info.location == OllamaLocation.REMOTE_OLLAMA:
                return InferenceBackend.OLLAMA_CPU_REMOTE
            else:
                return InferenceBackend.OLLAMA_CPU_LOCAL

        # 3. Ollama unavailable -> Local CPU fallback
        return InferenceBackend.LOCAL_CPU
