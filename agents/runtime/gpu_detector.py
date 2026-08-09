"""
Safe NVIDIA GPU and CUDA Acceleration Detector.

Provides read-only inspection of physical GPU devices exposed to the local runtime environment.
Gracefully handles missing drivers, inaccessible hardware in virtualized guests (e.g. VirtualBox),
timeouts, and CPU-only hosts without privileged commands or system modification.
"""

import os
import shutil
import subprocess
from typing import Optional

from agents.runtime.runtime_models import (
    CapabilityStatus,
    GPUInfo,
    GPUVendor,
    OperatingSystem,
)


class GPUDetector:
    """
    Read-only hardware detector for NVIDIA GPU devices and CUDA capabilities.
    """

    def __init__(self, timeout_sec: float = 3.0) -> None:
        self._timeout_sec = timeout_sec

    def detect(self, os_type: OperatingSystem = OperatingSystem.UNKNOWN, is_virtualized: bool = False) -> GPUInfo:
        """
        Detect local physical GPU device and VRAM status safely.

        Args:
            os_type: Host OS classification.
            is_virtualized: Whether running inside a VM/container environment.
        """
        # 1. Try PyTorch CUDA inspection if available
        try:
            import torch
            if torch.cuda.is_available() and torch.cuda.device_count() > 0:
                name = torch.cuda.get_device_name(0)
                vram_mb = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
                return GPUInfo(
                    vendor=GPUVendor.NVIDIA,
                    name=name,
                    vram_mb=round(vram_mb, 2),
                    driver_version="CUDA Active",
                    cuda_available=True,
                    status=CapabilityStatus.AVAILABLE,
                    is_guest_exposed=True,
                    detection_method="PYTORCH_CUDA",
                )
        except Exception:
            pass

        # 2. Try nvidia-smi CLI execution
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi and os_type == OperatingSystem.WINDOWS:
            # Check common Windows nvidia-smi installation path
            win_smi = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "DriverStore", "FileRepository")
            # If nvidia-smi command not directly on PATH, fallback to default lookup
            nvidia_smi = shutil.which("nvidia-smi")

        if not nvidia_smi:
            if is_virtualized:
                return GPUInfo(
                    vendor=GPUVendor.NONE,
                    name="Not Exposed",
                    vram_mb=0.0,
                    driver_version="None",
                    cuda_available=False,
                    status=CapabilityStatus.NOT_EXPOSED_TO_GUEST,
                    is_guest_exposed=False,
                    detection_method="NONE",
                    error_message="Physical GPU is not exposed to virtualized guest VM (nvidia-smi unavailable).",
                )
            return GPUInfo(
                vendor=GPUVendor.NONE,
                name="None",
                vram_mb=0.0,
                driver_version="None",
                cuda_available=False,
                status=CapabilityStatus.UNAVAILABLE,
                is_guest_exposed=False,
                detection_method="NONE",
                error_message="nvidia-smi binary not found on system PATH.",
            )

        # Execute nvidia-smi query
        try:
            cmd = [
                nvidia_smi,
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout_sec,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                lines = proc.stdout.strip().split("\n")
                if lines:
                    parts = [p.strip() for p in lines[0].split(",")]
                    if len(parts) >= 3:
                        name = parts[0]
                        vram_mb = float(parts[1]) if parts[1].replace(".", "", 1).isdigit() else 0.0
                        driver_ver = parts[2]
                        return GPUInfo(
                            vendor=GPUVendor.NVIDIA,
                            name=name,
                            vram_mb=vram_mb,
                            driver_version=driver_ver,
                            cuda_available=True,
                            status=CapabilityStatus.AVAILABLE,
                            is_guest_exposed=True,
                            detection_method="NVIDIA_SMI",
                        )
        except subprocess.TimeoutExpired:
            return GPUInfo(
                vendor=GPUVendor.UNKNOWN,
                name="Timeout",
                status=CapabilityStatus.UNAVAILABLE,
                is_guest_exposed=False,
                detection_method="NVIDIA_SMI_TIMEOUT",
                error_message="nvidia-smi command execution timed out.",
            )
        except Exception as e:
            return GPUInfo(
                vendor=GPUVendor.UNKNOWN,
                name="Error",
                status=CapabilityStatus.UNAVAILABLE,
                is_guest_exposed=False,
                detection_method="NVIDIA_SMI_ERROR",
                error_message=str(e),
            )

        # Fallback when nvidia-smi returns no lines
        if is_virtualized:
            return GPUInfo(
                vendor=GPUVendor.NONE,
                name="Not Exposed",
                status=CapabilityStatus.NOT_EXPOSED_TO_GUEST,
                is_guest_exposed=False,
                detection_method="NVIDIA_SMI_EMPTY",
                error_message="No physical GPU reported by nvidia-smi in virtualized guest.",
            )

        return GPUInfo(
            vendor=GPUVendor.NONE,
            name="None",
            status=CapabilityStatus.UNAVAILABLE,
            is_guest_exposed=False,
            detection_method="NONE",
            error_message="No active NVIDIA GPU detected.",
        )
