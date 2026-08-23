"""
Runtime Service Domain Component.

High-level domain service providing programmatic runtime inspection, capability discovery,
and health diagnostics.
"""

from typing import Optional

from agents.runtime.capability_manager import CapabilityManager
from agents.runtime.runtime_models import RuntimeCapabilities, RuntimeHealthStatus


class RuntimeService:
    """
    Domain service orchestrating hardware and runtime capability discovery.
    """

    def __init__(self, capability_manager: Optional[CapabilityManager] = None) -> None:
        self._capability_manager = capability_manager or CapabilityManager()

    def get_capabilities(self, force_refresh: bool = False) -> RuntimeCapabilities:
        """
        Get composite runtime capability matrix.
        """
        return self._capability_manager.get_capabilities(force_refresh=force_refresh)

    def get_health_status(self, force_refresh: bool = False) -> RuntimeHealthStatus:
        """
        Get diagnostic health evaluation.
        """
        return self._capability_manager.get_health_status(force_refresh=force_refresh)

    def check_runtime_health(self, force_refresh: bool = False) -> RuntimeHealthStatus:
        """
        Compatibility alias delegating to get_health_status.
        """
        return self.get_health_status(force_refresh=force_refresh)

    def refresh(self) -> RuntimeCapabilities:
        """
        Force immediate hardware and service capability detection.
        """
        return self._capability_manager.get_capabilities(force_refresh=True)
