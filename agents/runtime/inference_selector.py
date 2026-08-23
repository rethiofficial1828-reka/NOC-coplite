"""
Deterministic Inference Execution Backend Selector.

Determines the optimal inference backend (OLLAMA_GPU_LOCAL, OLLAMA_GPU_REMOTE,
OLLAMA_CPU_LOCAL, OLLAMA_CPU_REMOTE, LOCAL_CPU, UNAVAILABLE) strictly grounded in
actual hardware exposure and endpoint capability.
"""

from typing import Union

from agents.runtime.runtime_models import (
    CapabilityStatus,
    GPUCapability,
    GPUInfo,
    GPUVendor,
    InferenceBackend,
    OSInfo,
    OllamaInfo,
    OllamaLocation,
)


class InferenceSelector:
    """
    Selector enforcing deterministic backend selection rules.
    """

    def select_backend(
        self,
        os_or_gpu_info: Union[OSInfo, GPUInfo, GPUCapability, None] = None,
        gpu_or_ollama_info: Union[GPUInfo, GPUCapability, OllamaInfo, None] = None,
        ollama_info: Union[OllamaInfo, None] = None,
    ) -> InferenceBackend:
        """
        Select best available backend according to strict priority matrix.

        Supports two calling signatures:
          - Legacy 2-arg: select_backend(gpu_info, ollama_info)
          - Extended 3-arg: select_backend(os_info, gpu_capability, ollama_info)

        Args:
            os_or_gpu_info: OSInfo (3-arg form) or GPUInfo/GPUCapability (2-arg form).
            gpu_or_ollama_info: GPUInfo/GPUCapability (3-arg form) or OllamaInfo (2-arg form).
            ollama_info: OllamaInfo (3-arg form only; None in 2-arg form).
        """
        # Normalize arguments to (gpu_info, resolved_ollama_info)
        if ollama_info is not None:
            # 3-arg form: (os_info, gpu_capability, ollama_info)
            gpu_info = gpu_or_ollama_info
            resolved_ollama = ollama_info
        elif isinstance(gpu_or_ollama_info, OllamaInfo):
            # 2-arg form: (gpu_info, ollama_info)
            gpu_info = os_or_gpu_info
            resolved_ollama = gpu_or_ollama_info
        else:
            # Fallback
            gpu_info = os_or_gpu_info
            resolved_ollama = OllamaInfo()

        # Normalize gpu_info: GPUCapability has has_gpu; GPUInfo has vendor/status
        if isinstance(gpu_info, GPUCapability):
            gpu_has_nvidia = gpu_info.has_gpu and (
                gpu_info.vendor == GPUVendor.NVIDIA or gpu_info.cuda_available
            )
            gpu_is_exposed = gpu_info.has_gpu
        elif isinstance(gpu_info, GPUInfo):
            gpu_has_nvidia = gpu_info.vendor == GPUVendor.NVIDIA
            gpu_is_exposed = gpu_info.is_guest_exposed
        else:
            gpu_has_nvidia = False
            gpu_is_exposed = False

        # 1. Ollama is available
        if resolved_ollama.available and resolved_ollama.qwen_available:
            # Case A: Local Ollama with physical GPU exposed locally
            if (
                resolved_ollama.location == OllamaLocation.LOCAL_OLLAMA
                and gpu_has_nvidia
                and gpu_is_exposed
            ):
                return InferenceBackend.OLLAMA_GPU_LOCAL

            # Case B: Remote Ollama (e.g. Windows Host from Kali VM) with GPU acceleration
            if (
                resolved_ollama.location == OllamaLocation.REMOTE_OLLAMA
                and resolved_ollama.remote_gpu_accelerated
            ):
                return InferenceBackend.OLLAMA_GPU_REMOTE

            # Case C: Local Ollama CPU only
            if resolved_ollama.location == OllamaLocation.LOCAL_OLLAMA:
                return InferenceBackend.OLLAMA_CPU_LOCAL

            # Case D: Remote Ollama CPU only
            if resolved_ollama.location == OllamaLocation.REMOTE_OLLAMA:
                return InferenceBackend.OLLAMA_CPU_REMOTE

        # 2. Ollama is available without qwen verification (degraded execution)
        if resolved_ollama.available:
            if (
                resolved_ollama.location == OllamaLocation.LOCAL_OLLAMA
                and gpu_has_nvidia
                and gpu_is_exposed
            ):
                return InferenceBackend.OLLAMA_GPU_LOCAL
            elif resolved_ollama.location == OllamaLocation.REMOTE_OLLAMA:
                return InferenceBackend.OLLAMA_CPU_REMOTE
            else:
                return InferenceBackend.OLLAMA_CPU_LOCAL

        # 3. Ollama unavailable -> Local CPU fallback
        return InferenceBackend.LOCAL_CPU
