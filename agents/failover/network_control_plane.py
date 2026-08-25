"""
Typed Network Control-Plane Abstraction Module for Enterprise Controlled Failover Engine.

Defines the abstract interface INetworkControlPlane, strongly-typed domain request/response models,
and the safe NotConfiguredControlPlane default implementation.
Guarantees zero arbitrary shell/SSH/CLI execution, zero in-memory masquerading, and explicit
readiness probing.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field

from agents.core.logger import get_agent_logger
from agents.failover.execution_adapter import INetworkProviderDelegate

logger = get_agent_logger("NetworkControlPlane")


# ---------------------------------------------------------------------------
# Control Plane Enums
# ---------------------------------------------------------------------------


class ControlPlaneDriverType(str, Enum):
    """Supported control-plane driver backend types."""

    NONE = "none"
    GNMI = "gnmi"
    NETCONF = "netconf"
    FRR_ZAPI = "frr_zapi"
    CUSTOM = "custom"


class ControlPlaneStatus(str, Enum):
    """Operational status of the network control plane."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"
    READY = "READY"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# Strongly-Typed Domain Request & Response Models
# ---------------------------------------------------------------------------


class FailoverProviderRequest(BaseModel):
    """Typed request payload for provider failover."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_device: str = Field(..., description="Target router or gateway device ID/name")
    wan_interface: str = Field(..., description="Target WAN interface name")
    source_provider: str = Field(..., description="Currently active degraded provider")
    target_provider: str = Field(..., description="Candidate backup provider to activate")
    next_hop: Optional[str] = Field(default=None, description="Optional target next-hop IP")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Validated metadata")


class FailbackProviderRequest(BaseModel):
    """Typed request payload for provider failback."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_device: str = Field(..., description="Target router or gateway device ID/name")
    wan_interface: str = Field(..., description="Target WAN interface name")
    source_provider: str = Field(..., description="Currently active backup provider")
    target_provider: str = Field(..., description="Primary provider to restore")
    next_hop: Optional[str] = Field(default=None, description="Optional primary next-hop IP")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Validated metadata")


class SwitchInterfaceRequest(BaseModel):
    """Typed request payload for direct interface switching."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_device: str = Field(..., description="Target router or gateway device ID/name")
    from_interface: str = Field(..., description="Interface to deactivate")
    to_interface: str = Field(..., description="Interface to activate")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Validated metadata")


class PathStateRequest(BaseModel):
    """Typed request payload for enabling/disabling path states."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_device: str = Field(..., description="Target router or gateway device ID/name")
    wan_interface: str = Field(..., description="Target WAN interface name")
    path_id: Optional[str] = Field(default=None, description="Path identifier")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Validated metadata")


class RouteVerificationRequest(BaseModel):
    """Typed request payload for verifying active route/path state."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_device: str = Field(..., description="Target router or gateway device ID/name")
    expected_provider: str = Field(..., description="Expected active provider")
    expected_next_hop: Optional[str] = Field(default=None, description="Expected next-hop IP")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Validated metadata")


class ControlPlaneResponse(BaseModel):
    """Standardized response from control plane operations."""

    success: bool = Field(default=False, description="Whether the operation succeeded")
    status: ControlPlaneStatus = Field(default=ControlPlaneStatus.NOT_CONFIGURED)
    driver_type: ControlPlaneDriverType = Field(default=ControlPlaneDriverType.NONE)
    action_type: str = Field(default="", description="Executed action type")
    target: str = Field(default="", description="Target device or interface")
    message: str = Field(default="", description="Human-readable status/error description")
    details: Dict[str, Any] = Field(default_factory=dict, description="Sanitized result details")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Abstract Control Plane Interface
# ---------------------------------------------------------------------------


class INetworkControlPlane(ABC):
    """
    Abstract Interface for strongly-typed Network Control Plane drivers.

    Concrete implementations (e.g. gNMI, NETCONF, FRR ZAPI) must implement all methods
    using structured protocol messages rather than command strings.
    """

    @property
    @abstractmethod
    def driver_type(self) -> ControlPlaneDriverType:
        """Return the driver backend type."""
        pass

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Return True only if a supported live driver is fully configured and connected."""
        pass

    @abstractmethod
    def check_readiness(self) -> ControlPlaneResponse:
        """
        Non-mutating readiness probe.
        Returns ControlPlaneResponse with success=True only when control plane is operational.
        """
        pass

    @abstractmethod
    def failover_provider(self, request: FailoverProviderRequest) -> ControlPlaneResponse:
        """Execute typed provider failover."""
        pass

    @abstractmethod
    def failback_provider(self, request: FailbackProviderRequest) -> ControlPlaneResponse:
        """Execute typed provider failback."""
        pass

    @abstractmethod
    def switch_interface(self, request: SwitchInterfaceRequest) -> ControlPlaneResponse:
        """Execute typed interface switch."""
        pass

    @abstractmethod
    def enable_backup_path(self, request: PathStateRequest) -> ControlPlaneResponse:
        """Execute typed backup path enablement."""
        pass

    @abstractmethod
    def disable_degraded_path(self, request: PathStateRequest) -> ControlPlaneResponse:
        """Execute typed degraded path disablement."""
        pass

    @abstractmethod
    def verify_route_path(self, request: RouteVerificationRequest) -> ControlPlaneResponse:
        """Non-mutating verification of active route/path."""
        pass


# ---------------------------------------------------------------------------
# Safe NotConfigured Implementation (Default for v1.2)
# ---------------------------------------------------------------------------


class NotConfiguredControlPlane(INetworkControlPlane):
    """
    Default safe control plane implementation.
    Explicitly reports NOT_CONFIGURED and rejects all mutation attempts safely without shell/SSH.
    """

    def __init__(self, driver_name: str = "none") -> None:
        self._driver_name = driver_name

    @property
    def driver_type(self) -> ControlPlaneDriverType:
        return ControlPlaneDriverType.NONE

    @property
    def is_configured(self) -> bool:
        return False

    def check_readiness(self) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="CHECK_READINESS",
            message="No network control plane driver is configured on this host.",
            details={"driver_name": self._driver_name, "is_configured": False},
        )

    def failover_provider(self, request: FailoverProviderRequest) -> ControlPlaneResponse:
        logger.warning("failover_provider invoked on NotConfiguredControlPlane — rejecting execution.")
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="FAILOVER_PROVIDER",
            target=request.target_device,
            message="Cannot execute failover_provider: No network control plane driver is configured.",
            details={"target_provider": request.target_provider},
        )

    def failback_provider(self, request: FailbackProviderRequest) -> ControlPlaneResponse:
        logger.warning("failback_provider invoked on NotConfiguredControlPlane — rejecting execution.")
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="FAILBACK_PROVIDER",
            target=request.target_device,
            message="Cannot execute failback_provider: No network control plane driver is configured.",
            details={"target_provider": request.target_provider},
        )

    def switch_interface(self, request: SwitchInterfaceRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="SWITCH_INTERFACE",
            target=request.target_device,
            message="Cannot execute switch_interface: No network control plane driver is configured.",
        )

    def enable_backup_path(self, request: PathStateRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="ENABLE_BACKUP_PATH",
            target=request.target_device,
            message="Cannot execute enable_backup_path: No network control plane driver is configured.",
        )

    def disable_degraded_path(self, request: PathStateRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="DISABLE_DEGRADED_PATH",
            target=request.target_device,
            message="Cannot execute disable_degraded_path: No network control plane driver is configured.",
        )

    def verify_route_path(self, request: RouteVerificationRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="VERIFY_ROUTE_PATH",
            target=request.target_device,
            message="Cannot verify route path: No network control plane driver is configured.",
        )


# ---------------------------------------------------------------------------
# Delegate Bridge: TypedControlPlaneDelegate
# ---------------------------------------------------------------------------


class TypedControlPlaneDelegate(INetworkProviderDelegate):
    """
    Bridge connecting AuthorizedNetworkAdapter to an INetworkControlPlane driver.
    Converts generic execution steps into strongly-typed domain request models.
    """

    def __init__(self, control_plane: Optional[INetworkControlPlane] = None) -> None:
        self._control_plane: INetworkControlPlane = control_plane or NotConfiguredControlPlane()

    @property
    def control_plane(self) -> INetworkControlPlane:
        return self._control_plane

    def is_ready(self) -> bool:
        """Delegate readiness probe to control plane."""
        if not self._control_plane.is_configured:
            return False
        res = self._control_plane.check_readiness()
        return res.success

    def health_check(self) -> bool:
        """Synonym for is_ready."""
        return self.is_ready()

    def verify_capability(self) -> bool:
        """Synonym for is_ready."""
        return self.is_ready()

    def failover_provider(
        self,
        source_provider: str,
        target_provider: str,
        wan_interface: str = "Branch3-Uplink",
        target_device: str = "branch3-uplink",
    ) -> bool:
        """Convenience method to execute typed failover."""
        res = self.execute_typed_action(
            action_type="FAILOVER_PROVIDER",
            target=target_device,
            parameters={
                "source_provider": source_provider,
                "target_provider": target_provider,
                "interface": wan_interface,
            },
        )
        return bool(res.get("success", False))

    def failback_provider(
        self,
        source_provider: str,
        target_provider: str,
        wan_interface: str = "Branch3-Uplink",
        target_device: str = "branch3-uplink",
    ) -> bool:
        """Convenience method to execute typed failback."""
        res = self.execute_typed_action(
            action_type="FAILBACK_PROVIDER",
            target=target_device,
            parameters={
                "source_provider": source_provider,
                "target_provider": target_provider,
                "interface": wan_interface,
            },
        )
        return bool(res.get("success", False))

    def execute_typed_action(
        self,
        action_type: str,
        target: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Convert action_type and parameters to strongly-typed request and dispatch to control plane.
        """
        if action_type == "FAILOVER_PROVIDER":
            req = FailoverProviderRequest(
                target_device=target,
                wan_interface=parameters.get("interface", target),
                source_provider=parameters.get("source_provider", "ISP-A"),
                target_provider=parameters.get("target_provider", "ISP-B"),
                next_hop=parameters.get("next_hop"),
                metadata=parameters,
            )
            resp = self._control_plane.failover_provider(req)
        elif action_type == "FAILBACK_PROVIDER":
            req_fb = FailbackProviderRequest(
                target_device=target,
                wan_interface=parameters.get("interface", target),
                source_provider=parameters.get("source_provider", "ISP-B"),
                target_provider=parameters.get("target_provider", "ISP-A"),
                next_hop=parameters.get("next_hop"),
                metadata=parameters,
            )
            resp = self._control_plane.failback_provider(req_fb)
        elif action_type == "SWITCH_INTERFACE":
            req_sw = SwitchInterfaceRequest(
                target_device=target,
                from_interface=parameters.get("from_interface", ""),
                to_interface=parameters.get("to_interface", ""),
                metadata=parameters,
            )
            resp = self._control_plane.switch_interface(req_sw)
        elif action_type == "ENABLE_BACKUP_PATH":
            req_en = PathStateRequest(
                target_device=target,
                wan_interface=parameters.get("interface", target),
                path_id=parameters.get("path_id"),
                metadata=parameters,
            )
            resp = self._control_plane.enable_backup_path(req_en)
        elif action_type == "DISABLE_DEGRADED_PATH":
            req_dis = PathStateRequest(
                target_device=target,
                wan_interface=parameters.get("interface", target),
                path_id=parameters.get("path_id"),
                metadata=parameters,
            )
            resp = self._control_plane.disable_degraded_path(req_dis)
        else:
            return {
                "success": False,
                "status": ControlPlaneStatus.ERROR.value,
                "error": f"Unsupported action type '{action_type}'",
            }

        return resp.model_dump()

    def rollback_typed_action(
        self,
        action_type: str,
        target: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute rollback by inverting action type or executing formulated failback step.
        """
        if action_type == "FAILBACK_PROVIDER":
            return self.execute_typed_action(action_type, target, parameters)
        elif action_type == "FAILOVER_PROVIDER":
            inverse_params = dict(parameters)
            src = parameters.get("source_provider", "ISP-A")
            tgt = parameters.get("target_provider", "ISP-B")
            inverse_params["source_provider"] = tgt
            inverse_params["target_provider"] = src
            return self.execute_typed_action("FAILBACK_PROVIDER", target, inverse_params)
        elif action_type == "ENABLE_BACKUP_PATH":
            return self.execute_typed_action("DISABLE_DEGRADED_PATH", target, parameters)
        elif action_type == "DISABLE_DEGRADED_PATH":
            return self.execute_typed_action("ENABLE_BACKUP_PATH", target, parameters)
        else:
            return {
                "success": False,
                "status": ControlPlaneStatus.ERROR.value,
                "error": f"Unsupported rollback action type '{action_type}'",
            }
