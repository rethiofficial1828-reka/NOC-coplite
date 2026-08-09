"""
Cross-Platform Operating System and Virtualization Environment Detector.

Detects OS (Windows, Linux, macOS), architecture, Python version, CPU count, RAM,
and Virtualization Environment (Native, VirtualBox, VMware, WSL, Docker) using reliable
runtime indicators without platform-specific hardcoding.
"""

import os
import platform
import sys
from typing import Dict, Tuple

from agents.runtime.runtime_models import (
    OSInfo,
    OperatingSystem,
    VirtualizationEnvironment,
)


class OSDetector:
    """
    Detector for host operating system and virtualization runtime.
    """

    def detect(self) -> OSInfo:
        """
        Detect OS details, hardware specs, and virtualization context.
        """
        system_name = platform.system().upper()
        if "WINDOWS" in system_name:
            os_enum = OperatingSystem.WINDOWS
        elif "LINUX" in system_name:
            os_enum = OperatingSystem.LINUX
        elif "DARWIN" in system_name or "MAC" in system_name:
            os_enum = OperatingSystem.MACOS
        else:
            os_enum = OperatingSystem.UNKNOWN

        arch = platform.machine() or "x86_64"
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        cpu_cnt = os.cpu_count() or 1

        total_gb, avail_gb = self._detect_memory()
        virt_env, is_virt = self._detect_virtualization()

        return OSInfo(
            operating_system=os_enum,
            platform_name=platform.platform(),
            architecture=arch,
            python_version=py_ver,
            cpu_count=cpu_cnt,
            total_memory_gb=round(total_gb, 2),
            available_memory_gb=round(avail_gb, 2),
            virtualization_environment=virt_env,
            is_virtualized=is_virt,
        )

    def _detect_memory(self) -> Tuple[float, float]:
        """Detect system memory in GB safely."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            return mem.total / (1024 ** 3), mem.available / (1024 ** 3)
        except ImportError:
            # Fallback estimation if psutil is not available
            return 8.0, 4.0

    def _detect_virtualization(self) -> Tuple[VirtualizationEnvironment, bool]:
        """
        Detect if running inside VirtualBox, VMware, WSL, Docker, or Native environment.
        """
        # Docker container check
        if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
            return VirtualizationEnvironment.DOCKER, True

        # WSL check
        if "microsoft" in platform.release().lower() or "wsl" in platform.release().lower():
            return VirtualizationEnvironment.WSL, True

        # Linux DMI vendor / systemd-detect-virt check
        if platform.system() == "Linux":
            dmi_files = [
                "/sys/class/dmi/id/sys_vendor",
                "/sys/class/dmi/id/product_name",
                "/sys/class/dmi/id/board_name",
            ]
            dmi_content = ""
            for df in dmi_files:
                if os.path.exists(df):
                    try:
                        with open(df, "r") as f:
                            dmi_content += f.read().lower() + " "
                    except Exception:
                        pass

            if "innotek" in dmi_content or "virtualbox" in dmi_content or "vbox" in dmi_content:
                return VirtualizationEnvironment.VIRTUALBOX, True
            elif "vmware" in dmi_content:
                return VirtualizationEnvironment.VMWARE, True
            elif "kvm" in dmi_content or "qemu" in dmi_content:
                return VirtualizationEnvironment.VIRTUALBOX, True  # VM container

            # Proc cpuinfo vendor check
            if os.path.exists("/proc/cpuinfo"):
                try:
                    with open("/proc/cpuinfo", "r") as f:
                        cpuinfo = f.read().lower()
                    if "hypervisor" in cpuinfo:
                        if "virtualbox" in cpuinfo or "vbox" in cpuinfo:
                            return VirtualizationEnvironment.VIRTUALBOX, True
                        return VirtualizationEnvironment.VIRTUALBOX, True
                except Exception:
                    pass

        # Windows WMI / System info check
        if platform.system() == "Windows":
            try:
                import subprocess
                out = subprocess.check_output("wmic baseboard get manufacturer,product", shell=True).decode().lower()
                if "virtualbox" in out or "innotek" in out:
                    return VirtualizationEnvironment.VIRTUALBOX, True
                elif "vmware" in out:
                    return VirtualizationEnvironment.VMWARE, True
            except Exception:
                pass

        return VirtualizationEnvironment.NATIVE, False
