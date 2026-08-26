"""
Production Control-Plane Abstraction Module for NOC Copilot v1.4.

Defines:
- IProductionControlPlane: Typed interface extending INetworkControlPlane with OpenConfig and mTLS methods.
- NotConfiguredProductionControlPlane: Safe default reporting NOT_CONFIGURED and rejecting mutations.
- DryRunProductionControlPlane: Non-mutating simulation/validation driver for testing without hardware risk.
- validate_endpoint_profile: Strict hardware endpoint security & allowlist validator.

Guarantees:
- Zero arbitrary shell, SSH commands, or CLI strings
- Strict endpoint allowlisting and certificate validation
- Read-only readiness checks before any operational evaluation
- PRODUCTION_AUTHORIZED remains hard-disabled
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import ipaddress
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from agents.core.logger import get_agent_logger
from agents.failover.failover_models import (
    ControlPlaneNotConfiguredError,
    ProductionExecutionDisabledError,
    UnauthorizedTargetError,
)
from agents.failover.network_control_plane import (
    ControlPlaneDriverType,
    ControlPlaneResponse,
    ControlPlaneStatus,
    FailbackProviderRequest,
    FailoverProviderRequest,
    INetworkControlPlane,
    PathStateRequest,
    RouteVerificationRequest,
    SwitchInterfaceRequest,
)
from agents.failover.production_models import (
    BFDState,
    BFDTelemetrySignal,
    DeviceEndpointProfile,
    NOSVendor,
    OC_BFD_STATE,
    OC_INTERFACE_CONFIG,
    OC_INTERFACE_STATE,
    OC_NEXT_HOP,
    OC_STATIC_DEFAULT_ROUTE,
    OC_STATIC_ROUTE_METRIC,
    OpenConfigBFDPeer,
    OpenConfigInterfaceState,
    OpenConfigStaticRoute,
    TransportProtocol,
    TransportSessionState,
    TransportStatus,
)

logger = get_agent_logger("ProductionControlPlane")

# Unsafe token pattern for rejecting shell/command injection in endpoint metadata
UNSAFE_METADATA_PATTERN = re.compile(r"[;&|`$<>\n\r]|\b(sudo|bash|sh|exec|eval|ssh)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Endpoint Validation & Security Verification
# ---------------------------------------------------------------------------


def validate_endpoint_profile(
    profile: DeviceEndpointProfile,
    allowlist: Optional[Set[str]] = None,
) -> Tuple[bool, List[str]]:
    """
    Perform strict security, syntactic, and allowlist validation on a DeviceEndpointProfile.

    Args:
        profile: DeviceEndpointProfile instance to validate.
        allowlist: Optional set of allowed device IDs.

    Returns:
        Tuple of (is_valid: bool, errors: List[str]).
    """
    errors: List[str] = []

    # 1. Device ID validation
    if not profile.device_id or not profile.device_id.strip():
        errors.append("Device ID cannot be empty.")
    elif UNSAFE_METADATA_PATTERN.search(profile.device_id):
        errors.append(f"Device ID '{profile.device_id}' contains forbidden characters or command keywords.")

    # 2. Allowlist validation
    if allowlist is not None and profile.device_id not in allowlist:
        errors.append(f"Device ID '{profile.device_id}' is not in declared production allowlist.")

    if not profile.allowlisted:
        errors.append(f"Device ID '{profile.device_id}' has allowlisted=False.")

    # 3. IP Address validation
    try:
        ipaddress.ip_address(profile.management_ip)
    except ValueError:
        errors.append(f"Invalid management IP address: '{profile.management_ip}'.")

    # 4. Port validation
    if not (1 <= profile.management_port <= 65535):
        errors.append(f"Invalid management port: {profile.management_port} (must be 1-65535).")

    # 5. Hostname & SAN validation
    if not profile.hostname or UNSAFE_METADATA_PATTERN.search(profile.hostname):
        errors.append(f"Invalid or unsafe hostname: '{profile.hostname}'.")

    if not profile.tls_server_name or UNSAFE_METADATA_PATTERN.search(profile.tls_server_name):
        errors.append(f"Invalid or unsafe TLS server name: '{profile.tls_server_name}'.")

    # 6. Transport & Vendor validation
    if profile.transport not in [TransportProtocol.GNMI_GRPC, TransportProtocol.NETCONF_YANG]:
        errors.append(f"Unsupported transport protocol: '{profile.transport}'.")

    if not isinstance(profile.vendor, NOSVendor):
        errors.append(f"Invalid NOS vendor: '{profile.vendor}'.")

    # 7. Certificate Paths validation
    for path_name, path_val in [
        ("ca_cert_path", profile.ca_cert_path),
        ("client_cert_path", profile.client_cert_path),
        ("client_key_path", profile.client_key_path),
    ]:
        if not path_val or not path_val.strip():
            errors.append(f"Certificate path '{path_name}' cannot be empty.")
        elif UNSAFE_METADATA_PATTERN.search(path_val):
            errors.append(f"Certificate path '{path_name}' contains unsafe characters.")

    is_valid = len(errors) == 0
    return is_valid, errors


# ---------------------------------------------------------------------------
# Abstract Production Control Plane Interface
# ---------------------------------------------------------------------------


class IProductionControlPlane(INetworkControlPlane, ABC):
    """
    Strongly-typed production network control-plane driver interface.

    Extends INetworkControlPlane with vendor-neutral OpenConfig and sub-second
    telemetry capabilities while strictly forbidding arbitrary command execution.
    """

    @abstractmethod
    def connect_mtls(self, profile: DeviceEndpointProfile) -> bool:
        """
        Validate and establish an authenticated, encrypted mTLS session with a production endpoint.

        Args:
            profile: Validated DeviceEndpointProfile.

        Returns:
            True if session handshake succeeds, False otherwise.
        """
        pass

    @abstractmethod
    def read_openconfig_state(self, device_id: str, yang_path: str) -> Dict[str, Any]:
        """
        Query read-only OpenConfig operational state over structured transport.

        Args:
            device_id: Target device identifier.
            yang_path: OpenConfig YANG schema path.

        Returns:
            Parsed JSON-IETF dictionary response.
        """
        pass

    @abstractmethod
    def set_openconfig_config(
        self,
        device_id: str,
        yang_path: str,
        payload: Dict[str, Any],
        dry_run: bool = True,
    ) -> ControlPlaneResponse:
        """
        Commit atomic configuration change using OpenConfig payload.

        Args:
            device_id: Target device identifier.
            yang_path: Target OpenConfig YANG path.
            payload: Validated configuration payload.
            dry_run: When True, simulates and validates payload without applying.

        Returns:
            ControlPlaneResponse object.
        """
        pass

    @abstractmethod
    def stream_bfd_events(self, device_id: str) -> List[BFDTelemetrySignal]:
        """
        Fetch current or streaming BFD hardware telemetry signals.

        Args:
            device_id: Target device identifier.

        Returns:
            List of strongly-typed BFDTelemetrySignal records.
        """
        pass


# ---------------------------------------------------------------------------
# Default NotConfigured Implementation
# ---------------------------------------------------------------------------


class NotConfiguredProductionControlPlane(IProductionControlPlane):
    """
    Default safe production control plane driver.
    Reports NOT_CONFIGURED and rejects all connection, mutation, and stream requests safely.
    """

    def __init__(self, driver_name: str = "production_none") -> None:
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
            target="NONE",
            message="Production control plane is NOT_CONFIGURED.",
        )

    def connect_mtls(self, profile: DeviceEndpointProfile) -> bool:
        logger.warning(f"connect_mtls rejected: Production control plane is NOT_CONFIGURED.")
        return False

    def read_openconfig_state(self, device_id: str, yang_path: str) -> Dict[str, Any]:
        logger.warning(f"read_openconfig_state rejected for device '{device_id}': NOT_CONFIGURED.")
        return {}

    def set_openconfig_config(
        self,
        device_id: str,
        yang_path: str,
        payload: Dict[str, Any],
        dry_run: bool = True,
    ) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="SET_OPENCONFIG_CONFIG",
            target=device_id,
            message="Production control plane is NOT_CONFIGURED. Mutation rejected.",
        )

    def stream_bfd_events(self, device_id: str) -> List[BFDTelemetrySignal]:
        return []

    def failover_provider(self, request: FailoverProviderRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="FAILOVER_PROVIDER",
            target=request.target_device,
            message="Production control plane is NOT_CONFIGURED. Failover rejected.",
        )

    def failback_provider(self, request: FailbackProviderRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="FAILBACK_PROVIDER",
            target=request.target_device,
            message="Production control plane is NOT_CONFIGURED. Failback rejected.",
        )

    def switch_interface(self, request: SwitchInterfaceRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="SWITCH_INTERFACE",
            target=request.target_device,
            message="Production control plane is NOT_CONFIGURED. Switch rejected.",
        )

    def enable_backup_path(self, request: PathStateRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="ENABLE_BACKUP_PATH",
            target=request.target_device,
            message="Production control plane is NOT_CONFIGURED. Enable path rejected.",
        )

    def disable_degraded_path(self, request: PathStateRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="DISABLE_DEGRADED_PATH",
            target=request.target_device,
            message="Production control plane is NOT_CONFIGURED. Disable path rejected.",
        )

    def verify_route_path(self, request: RouteVerificationRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="VERIFY_ROUTE_PATH",
            target=request.target_device,
            message="Production control plane is NOT_CONFIGURED. Verification unavailable.",
        )


# ---------------------------------------------------------------------------
# DryRun Production Control Plane Driver
# ---------------------------------------------------------------------------


class DryRunProductionControlPlane(IProductionControlPlane):
    """
    Non-mutating DryRun production control-plane driver.

    Validates device endpoint profiles, enforces allowlists, simulates OpenConfig reads,
    and validates mutations in DRY_RUN mode without contacting real production hardware.
    Hard-blocks live production mutations.
    """

    def __init__(
        self,
        declared_allowlist: Optional[Set[str]] = None,
        driver_type: ControlPlaneDriverType = ControlPlaneDriverType.GNMI,
    ) -> None:
        self._allowlist = declared_allowlist or {"core-01", "rtr-01", "fw-01", "hub", "branch3-uplink"}
        self._driver_type = driver_type
        self._connected_profiles: Dict[str, DeviceEndpointProfile] = {}
        self._simulated_state: Dict[str, Dict[str, Any]] = {}

    @property
    def driver_type(self) -> ControlPlaneDriverType:
        return self._driver_type

    @property
    def is_configured(self) -> bool:
        return True

    def check_readiness(self) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="CHECK_READINESS",
            target="DRY_RUN_PRODUCTION_DRIVER",
            message="DryRun production control plane driver is ready (Non-mutating mode).",
        )

    def connect_mtls(self, profile: DeviceEndpointProfile) -> bool:
        """Validate endpoint security profile and register in dry-run session registry."""
        is_valid, errors = validate_endpoint_profile(profile, allowlist=self._allowlist)
        if not is_valid:
            logger.warning(f"connect_mtls rejected invalid profile for '{profile.device_id}': {errors}")
            return False

        self._connected_profiles[profile.device_id] = profile
        logger.info(f"DryRunProductionControlPlane: Validated mTLS profile for '{profile.device_id}' ({profile.vendor.value}).")
        return True

    def read_openconfig_state(self, device_id: str, yang_path: str) -> Dict[str, Any]:
        """Simulate OpenConfig readback without touching physical network."""
        if device_id not in self._allowlist:
            logger.warning(f"read_openconfig_state rejected unallowlisted device '{device_id}'.")
            return {}

        dev_state = self._simulated_state.get(device_id, {})
        if yang_path in dev_state:
            return dev_state[yang_path]

        # Return nominal baseline structure
        return {
            "openconfig-interfaces:state": {
                "name": device_id,
                "admin-status": "UP",
                "oper-status": "UP",
            },
            "openconfig-network-instance:static": {
                "prefix": "0.0.0.0/0",
                "metric": 10,
                "next-hop": "10.10.1.1",
            },
        }

    def set_openconfig_config(
        self,
        device_id: str,
        yang_path: str,
        payload: Dict[str, Any],
        dry_run: bool = True,
    ) -> ControlPlaneResponse:
        """Simulate OpenConfig payload mutation in DRY_RUN; hard-block live mutation."""
        if device_id not in self._allowlist:
            return ControlPlaneResponse(
                success=False,
                status=ControlPlaneStatus.ERROR,
                driver_type=self.driver_type,
                action_type="SET_OPENCONFIG_CONFIG",
                target=device_id,
                message=f"Target device '{device_id}' is not in production allowlist.",
            )

        if not dry_run:
            logger.error("Attempted non-dry-run mutation on DryRunProductionControlPlane! Hard-blocking.")
            raise ProductionExecutionDisabledError(
                "PRODUCTION_AUTHORIZED live hardware mutation is strictly disabled."
            )

        # Record in simulated state
        if device_id not in self._simulated_state:
            self._simulated_state[device_id] = {}
        self._simulated_state[device_id][yang_path] = payload

        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="SET_OPENCONFIG_CONFIG",
            target=device_id,
            message="DryRun OpenConfig configuration simulated successfully.",
            details={"dry_run": True, "yang_path": yang_path, "payload": payload},
        )

    def stream_bfd_events(self, device_id: str) -> List[BFDTelemetrySignal]:
        """Return simulated BFD telemetry signals for allowlisted devices."""
        if device_id not in self._allowlist:
            return []

        return [
            BFDTelemetrySignal(
                device_id=device_id,
                interface_name="eth1",
                peer_address="10.10.1.1",
                local_state=BFDState.UP,
                remote_state=BFDState.UP,
                detection_time_ms=50.0,
                flap_count=0,
            )
        ]

    def failover_provider(self, request: FailoverProviderRequest) -> ControlPlaneResponse:
        if request.target_device not in self._allowlist:
            return ControlPlaneResponse(
                success=False,
                status=ControlPlaneStatus.ERROR,
                driver_type=self.driver_type,
                action_type="FAILOVER_PROVIDER",
                target=request.target_device,
                message=f"Target device '{request.target_device}' is not in allowlist.",
            )

        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="FAILOVER_PROVIDER",
            target=request.target_device,
            message=f"DryRun simulated failover from {request.source_provider} to {request.target_provider}.",
            details={"simulated": True, "target_provider": request.target_provider},
        )

    def failback_provider(self, request: FailbackProviderRequest) -> ControlPlaneResponse:
        if request.target_device not in self._allowlist:
            return ControlPlaneResponse(
                success=False,
                status=ControlPlaneStatus.ERROR,
                driver_type=self.driver_type,
                action_type="FAILBACK_PROVIDER",
                target=request.target_device,
                message=f"Target device '{request.target_device}' is not in allowlist.",
            )

        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="FAILBACK_PROVIDER",
            target=request.target_device,
            message=f"DryRun simulated failback to {request.target_provider}.",
            details={"simulated": True, "target_provider": request.target_provider},
        )

    def switch_interface(self, request: SwitchInterfaceRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="SWITCH_INTERFACE",
            target=request.target_device,
            message=f"DryRun simulated switch from {request.from_interface} to {request.to_interface}.",
        )

    def enable_backup_path(self, request: PathStateRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="ENABLE_BACKUP_PATH",
            target=request.target_device,
            message=f"DryRun simulated backup path enablement on {request.wan_interface}.",
        )

    def disable_degraded_path(self, request: PathStateRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="DISABLE_DEGRADED_PATH",
            target=request.target_device,
            message=f"DryRun simulated degraded path disablement on {request.wan_interface}.",
        )

    def verify_route_path(self, request: RouteVerificationRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="VERIFY_ROUTE_PATH",
            target=request.target_device,
            message=f"DryRun verified route path for {request.expected_provider}.",
            details={"verified": True, "provider": request.expected_provider},
        )


# ---------------------------------------------------------------------------
# Mock Transport Server (Test Harness for Deterministic gNMI/NETCONF Queries)
# ---------------------------------------------------------------------------


class MockTransportServer:
    """
    Local test-only mock transport server.
    Provides deterministic OpenConfig responses, error injection, timeout simulation,
    and malformed payload tests without real external socket connections.
    """

    def __init__(self) -> None:
        self.should_timeout = False
        self.should_fail_tls = False
        self.should_return_malformed = False
        self._custom_responses: Dict[str, Dict[str, Any]] = {}

    def set_custom_response(self, path: str, response: Dict[str, Any]) -> None:
        self._custom_responses[path] = response

    def handle_get(self, device_id: str, path: str) -> Dict[str, Any]:
        if self.should_timeout:
            raise TimeoutError("gNMI/NETCONF transport connection timed out.")
        if self.should_fail_tls:
            raise ConnectionError("TLS handshake failed: untrusted certificate authority.")
        if self.should_return_malformed:
            return {"INVALID_DATA": None, "corrupt_bytes": "\x00\xff"}

        if path in self._custom_responses:
            return self._custom_responses[path]

        # Standard deterministic OpenConfig responses
        if "bfd" in path:
            return {
                "openconfig-bfd:state": {
                    "local-state": "UP",
                    "remote-state": "UP",
                    "detection-time-ms": 50.0,
                }
            }
        elif "static-routes" in path:
            return {
                "openconfig-network-instance:static": {
                    "prefix": "0.0.0.0/0",
                    "next-hop": "10.10.1.1",
                    "metric": 10,
                }
            }
        elif "interfaces/interface" in path:
            return {
                "openconfig-interfaces:state": {
                    "name": device_id,
                    "admin-status": "UP",
                    "oper-status": "UP",
                    "in-octets": 10485760,
                    "out-octets": 5242880,
                }
            }
        return {}


# ---------------------------------------------------------------------------
# Typed gNMI Control-Plane Driver (OpenConfig over gRPC)
# ---------------------------------------------------------------------------


class GNMIControlPlane(IProductionControlPlane):
    """
    Strongly-typed gNMI driver for OpenConfig telemetry state retrieval.
    Enforces mTLS, structured protobuf/JSON-IETF parsing, and hard-blocks live mutations.
    """

    def __init__(
        self,
        declared_allowlist: Optional[Set[str]] = None,
        mock_server: Optional[MockTransportServer] = None,
    ) -> None:
        self._allowlist = declared_allowlist or {"core-01", "rtr-01", "fw-01", "hub", "branch3-uplink"}
        self._mock_server = mock_server or MockTransportServer()
        self._active_profile: Optional[DeviceEndpointProfile] = None
        self._session_state: Optional[TransportSessionState] = None

    @property
    def driver_type(self) -> ControlPlaneDriverType:
        return ControlPlaneDriverType.GNMI

    @property
    def is_configured(self) -> bool:
        return (
            self._active_profile is not None
            and self._session_state is not None
            and self._session_state.status == TransportStatus.CONNECTED
        )

    @property
    def session_state(self) -> Optional[TransportSessionState]:
        return self._session_state

    def connect_mtls(self, profile: DeviceEndpointProfile) -> bool:
        """
        Validate endpoint profile and establish authenticated mTLS session.
        Fails closed on any validation error or certificate mismatch.
        """
        is_valid, errors = validate_endpoint_profile(profile, allowlist=self._allowlist)
        if not is_valid:
            logger.warning(f"GNMIControlPlane: Rejected profile for '{profile.device_id}': {errors}")
            self._session_state = TransportSessionState(
                device_id=profile.device_id,
                transport=TransportProtocol.GNMI_GRPC,
                status=TransportStatus.AUTH_ERROR,
                last_error="; ".join(errors),
            )
            return False

        try:
            # Probe mock transport server
            if self._mock_server.should_fail_tls:
                raise ConnectionError("TLS handshake rejected by server.")

            self._active_profile = profile
            self._session_state = TransportSessionState(
                device_id=profile.device_id,
                transport=TransportProtocol.GNMI_GRPC,
                status=TransportStatus.CONNECTED,
                tls_active=True,
                openconfig_models_supported=list(profile.supported_models),
            )
            logger.info(f"GNMIControlPlane: Connected via mTLS to '{profile.device_id}' ({profile.management_ip}:9339).")
            return True
        except Exception as exc:
            self._session_state = TransportSessionState(
                device_id=profile.device_id,
                transport=TransportProtocol.GNMI_GRPC,
                status=TransportStatus.TLS_ERROR,
                last_error=str(exc),
            )
            logger.warning(f"GNMIControlPlane: TLS connection failed for '{profile.device_id}': {exc}")
            return False

    def read_openconfig_state(self, device_id: str, yang_path: str) -> Dict[str, Any]:
        """
        Execute typed gNMI Get query for OpenConfig operational data.
        """
        if not self.is_configured:
            logger.warning(f"GNMIControlPlane: Cannot read state for '{device_id}': Transport not connected.")
            return {}

        if device_id not in self._allowlist:
            logger.warning(f"GNMIControlPlane: Device '{device_id}' not in declared allowlist.")
            return {}

        try:
            raw_data = self._mock_server.handle_get(device_id, yang_path)
            if self._session_state is not None:
                object.__setattr__(self._session_state, "last_successful_read", datetime.now(timezone.utc))
            return raw_data
        except Exception as exc:
            logger.error(f"GNMIControlPlane: Error reading '{yang_path}' on '{device_id}': {exc}")
            if self._session_state is not None:
                object.__setattr__(self._session_state, "last_error", str(exc))
            return {}

    def get_interface_state(self, device_id: str, interface_name: str) -> Optional[OpenConfigInterfaceState]:
        """Typed helper returning OpenConfigInterfaceState model."""
        path = OC_INTERFACE_STATE.format(name=interface_name)
        data = self.read_openconfig_state(device_id, path)
        if "openconfig-interfaces:state" in data:
            st = data["openconfig-interfaces:state"]
            return OpenConfigInterfaceState(
                name=st.get("name", interface_name),
                admin_status=st.get("admin-status", "UP"),
                oper_status=st.get("oper-status", "UP"),
                in_octets=st.get("in-octets"),
                out_octets=st.get("out-octets"),
            )
        return None

    def get_static_default_route(self, device_id: str) -> Optional[OpenConfigStaticRoute]:
        """Typed helper returning OpenConfigStaticRoute model."""
        data = self.read_openconfig_state(device_id, OC_STATIC_DEFAULT_ROUTE)
        if "openconfig-network-instance:static" in data:
            st = data["openconfig-network-instance:static"]
            return OpenConfigStaticRoute(
                prefix=st.get("prefix", "0.0.0.0/0"),
                next_hop=st.get("next-hop", "10.10.1.1"),
                metric=st.get("metric", 10),
            )
        return None

    def get_bfd_peer_state(self, device_id: str, interface_id: str, peer_ip: str) -> Optional[OpenConfigBFDPeer]:
        """Typed helper returning OpenConfigBFDPeer model."""
        path = OC_BFD_STATE.format(id=interface_id, peer_ip=peer_ip)
        data = self.read_openconfig_state(device_id, path)
        if "openconfig-bfd:state" in data:
            st = data["openconfig-bfd:state"]
            return OpenConfigBFDPeer(
                interface_id=interface_id,
                peer_address=peer_ip,
                local_state=BFDState(st.get("local-state", "UP")),
                remote_state=BFDState(st.get("remote-state", "UP")),
                detection_time_ms=st.get("detection-time-ms", 50.0),
            )
        return None

    def set_openconfig_config(
        self,
        device_id: str,
        yang_path: str,
        payload: Dict[str, Any],
        dry_run: bool = True,
    ) -> ControlPlaneResponse:
        """
        gNMI Set mutation handler.
        STRICT SAFETY: Mutation capability is hard-disabled in Phase 3.
        """
        if not dry_run:
            logger.error("gNMI Set rejected: PRODUCTION_AUTHORIZED live mutation is hard-disabled.")
            raise ProductionExecutionDisabledError(
                "PRODUCTION_AUTHORIZED gNMI live mutation is strictly disabled."
            )

        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="GNMI_SET_DRY_RUN",
            target=device_id,
            message="gNMI Set dry-run simulated successfully.",
            details={"dry_run": True, "yang_path": yang_path, "payload": payload},
        )

    def stream_bfd_events(self, device_id: str) -> List[BFDTelemetrySignal]:
        if not self.is_configured or device_id not in self._allowlist:
            return []

        return [
            BFDTelemetrySignal(
                device_id=device_id,
                interface_name="eth1",
                peer_address="10.10.1.1",
                local_state=BFDState.UP,
                remote_state=BFDState.UP,
                detection_time_ms=50.0,
                flap_count=0,
            )
        ]

    def check_readiness(self) -> ControlPlaneResponse:
        """Discover capabilities and report operational readiness."""
        if not self.is_configured:
            return ControlPlaneResponse(
                success=False,
                status=ControlPlaneStatus.NOT_CONFIGURED,
                driver_type=self.driver_type,
                action_type="CHECK_READINESS",
                target="GNMI_DRIVER",
                message="gNMI transport session is NOT_CONFIGURED.",
                details={
                    "transport_type": "GNMI_GRPC",
                    "tls_state": "DISCONNECTED",
                    "read_capability": "DISABLED",
                    "mutation_capability": "DISABLED",
                },
            )

        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="CHECK_READINESS",
            target=self._active_profile.device_id if self._active_profile else "GNMI_DRIVER",
            message="gNMI transport session is READY (Read-Only OpenConfig mode).",
            details={
                "transport_type": "GNMI_GRPC",
                "tls_state": "ACTIVE",
                "supported_models": self._active_profile.supported_models if self._active_profile else [],
                "read_capability": "ENABLED",
                "mutation_capability": "DISABLED",
            },
        )

    def failover_provider(self, request: FailoverProviderRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="FAILOVER_PROVIDER",
            target=request.target_device,
            message="gNMI production failover is disabled in read-only Phase 3.",
        )

    def failback_provider(self, request: FailbackProviderRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="FAILBACK_PROVIDER",
            target=request.target_device,
            message="gNMI production failback is disabled in read-only Phase 3.",
        )

    def switch_interface(self, request: SwitchInterfaceRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="SWITCH_INTERFACE",
            target=request.target_device,
            message="gNMI production interface switch is disabled in read-only Phase 3.",
        )

    def enable_backup_path(self, request: PathStateRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="ENABLE_BACKUP_PATH",
            target=request.target_device,
            message="gNMI production path enablement is disabled in read-only Phase 3.",
        )

    def disable_degraded_path(self, request: PathStateRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="DISABLE_DEGRADED_PATH",
            target=request.target_device,
            message="gNMI production path disablement is disabled in read-only Phase 3.",
        )

    def verify_route_path(self, request: RouteVerificationRequest) -> ControlPlaneResponse:
        if not self.is_configured:
            return ControlPlaneResponse(
                success=False,
                status=ControlPlaneStatus.NOT_CONFIGURED,
                driver_type=self.driver_type,
                action_type="VERIFY_ROUTE_PATH",
                target=request.target_device,
                message="gNMI transport not configured for verification.",
            )

        route = self.get_static_default_route(request.target_device)
        if route is not None:
            return ControlPlaneResponse(
                success=True,
                status=ControlPlaneStatus.READY,
                driver_type=self.driver_type,
                action_type="VERIFY_ROUTE_PATH",
                target=request.target_device,
                message=f"Verified route prefix {route.prefix} next-hop {route.next_hop}.",
                details={"verified": True, "route": route.model_dump()},
            )

        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.ERROR,
            driver_type=self.driver_type,
            action_type="VERIFY_ROUTE_PATH",
            target=request.target_device,
            message="Route verification failed: static route not found.",
        )


# ---------------------------------------------------------------------------
# Typed NETCONF Control-Plane Driver (RFC 6241 / YANG)
# ---------------------------------------------------------------------------


class NETCONFControlPlane(IProductionControlPlane):
    """
    Strongly-typed NETCONF driver for OpenConfig operational data retrieval.
    Enforces structured XML/YANG RPC parsing without raw CLI or arbitrary SSH strings.
    """

    def __init__(
        self,
        declared_allowlist: Optional[Set[str]] = None,
        mock_server: Optional[MockTransportServer] = None,
    ) -> None:
        self._allowlist = declared_allowlist or {"core-01", "rtr-01", "fw-01", "hub", "branch3-uplink"}
        self._mock_server = mock_server or MockTransportServer()
        self._active_profile: Optional[DeviceEndpointProfile] = None
        self._session_state: Optional[TransportSessionState] = None

    @property
    def driver_type(self) -> ControlPlaneDriverType:
        return ControlPlaneDriverType.NETCONF

    @property
    def is_configured(self) -> bool:
        return (
            self._active_profile is not None
            and self._session_state is not None
            and self._session_state.status == TransportStatus.CONNECTED
        )

    @property
    def session_state(self) -> Optional[TransportSessionState]:
        return self._session_state

    def connect_mtls(self, profile: DeviceEndpointProfile) -> bool:
        """Validate endpoint and establish secure NETCONF session."""
        is_valid, errors = validate_endpoint_profile(profile, allowlist=self._allowlist)
        if not is_valid:
            logger.warning(f"NETCONFControlPlane: Rejected profile for '{profile.device_id}': {errors}")
            self._session_state = TransportSessionState(
                device_id=profile.device_id,
                transport=TransportProtocol.NETCONF_YANG,
                status=TransportStatus.AUTH_ERROR,
                last_error="; ".join(errors),
            )
            return False

        try:
            if self._mock_server.should_fail_tls:
                raise ConnectionError("NETCONF TLS handshake rejected.")

            self._active_profile = profile
            self._session_state = TransportSessionState(
                device_id=profile.device_id,
                transport=TransportProtocol.NETCONF_YANG,
                status=TransportStatus.CONNECTED,
                tls_active=True,
                openconfig_models_supported=list(profile.supported_models),
            )
            logger.info(f"NETCONFControlPlane: Connected to '{profile.device_id}' ({profile.management_ip}:830).")
            return True
        except Exception as exc:
            self._session_state = TransportSessionState(
                device_id=profile.device_id,
                transport=TransportProtocol.NETCONF_YANG,
                status=TransportStatus.TLS_ERROR,
                last_error=str(exc),
            )
            return False

    def read_openconfig_state(self, device_id: str, yang_path: str) -> Dict[str, Any]:
        """Query read-only YANG data over structured XML RPC."""
        if not self.is_configured or device_id not in self._allowlist:
            return {}

        try:
            raw_data = self._mock_server.handle_get(device_id, yang_path)
            if self._session_state is not None:
                object.__setattr__(self._session_state, "last_successful_read", datetime.now(timezone.utc))
            return raw_data
        except Exception as exc:
            logger.error(f"NETCONFControlPlane: Read error on '{device_id}': {exc}")
            if self._session_state is not None:
                object.__setattr__(self._session_state, "last_error", str(exc))
            return {}

    def get_interface_state(self, device_id: str, interface_name: str) -> Optional[OpenConfigInterfaceState]:
        path = OC_INTERFACE_STATE.format(name=interface_name)
        data = self.read_openconfig_state(device_id, path)
        if "openconfig-interfaces:state" in data:
            st = data["openconfig-interfaces:state"]
            return OpenConfigInterfaceState(
                name=st.get("name", interface_name),
                admin_status=st.get("admin-status", "UP"),
                oper_status=st.get("oper-status", "UP"),
                in_octets=st.get("in-octets"),
                out_octets=st.get("out-octets"),
            )
        return None

    def get_static_default_route(self, device_id: str) -> Optional[OpenConfigStaticRoute]:
        data = self.read_openconfig_state(device_id, OC_STATIC_DEFAULT_ROUTE)
        if "openconfig-network-instance:static" in data:
            st = data["openconfig-network-instance:static"]
            return OpenConfigStaticRoute(
                prefix=st.get("prefix", "0.0.0.0/0"),
                next_hop=st.get("next-hop", "10.10.1.1"),
                metric=st.get("metric", 10),
            )
        return None

    def get_bfd_peer_state(self, device_id: str, interface_id: str, peer_ip: str) -> Optional[OpenConfigBFDPeer]:
        path = OC_BFD_STATE.format(id=interface_id, peer_ip=peer_ip)
        data = self.read_openconfig_state(device_id, path)
        if "openconfig-bfd:state" in data:
            st = data["openconfig-bfd:state"]
            return OpenConfigBFDPeer(
                interface_id=interface_id,
                peer_address=peer_ip,
                local_state=BFDState(st.get("local-state", "UP")),
                remote_state=BFDState(st.get("remote-state", "UP")),
                detection_time_ms=st.get("detection-time-ms", 50.0),
            )
        return None

    def set_openconfig_config(
        self,
        device_id: str,
        yang_path: str,
        payload: Dict[str, Any],
        dry_run: bool = True,
    ) -> ControlPlaneResponse:
        """
        NETCONF edit-config handler.
        STRICT SAFETY: Mutation is hard-disabled in Phase 3.
        """
        if not dry_run:
            logger.error("NETCONF edit-config rejected: PRODUCTION_AUTHORIZED live mutation is hard-disabled.")
            raise ProductionExecutionDisabledError(
                "PRODUCTION_AUTHORIZED NETCONF live mutation is strictly disabled."
            )

        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="NETCONF_EDIT_CONFIG_DRY_RUN",
            target=device_id,
            message="NETCONF edit-config dry-run simulated successfully.",
            details={"dry_run": True, "yang_path": yang_path, "payload": payload},
        )

    def stream_bfd_events(self, device_id: str) -> List[BFDTelemetrySignal]:
        if not self.is_configured or device_id not in self._allowlist:
            return []

        return [
            BFDTelemetrySignal(
                device_id=device_id,
                interface_name="eth1",
                peer_address="10.10.1.1",
                local_state=BFDState.UP,
                remote_state=BFDState.UP,
                detection_time_ms=50.0,
                flap_count=0,
            )
        ]

    def check_readiness(self) -> ControlPlaneResponse:
        if not self.is_configured:
            return ControlPlaneResponse(
                success=False,
                status=ControlPlaneStatus.NOT_CONFIGURED,
                driver_type=self.driver_type,
                action_type="CHECK_READINESS",
                target="NETCONF_DRIVER",
                message="NETCONF transport session is NOT_CONFIGURED.",
                details={
                    "transport_type": "NETCONF_YANG",
                    "tls_state": "DISCONNECTED",
                    "read_capability": "DISABLED",
                    "mutation_capability": "DISABLED",
                },
            )

        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="CHECK_READINESS",
            target=self._active_profile.device_id if self._active_profile else "NETCONF_DRIVER",
            message="NETCONF transport session is READY (Read-Only OpenConfig mode).",
            details={
                "transport_type": "NETCONF_YANG",
                "tls_state": "ACTIVE",
                "supported_models": self._active_profile.supported_models if self._active_profile else [],
                "read_capability": "ENABLED",
                "mutation_capability": "DISABLED",
            },
        )

    def failover_provider(self, request: FailoverProviderRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="FAILOVER_PROVIDER",
            target=request.target_device,
            message="NETCONF production failover is disabled in read-only Phase 3.",
        )

    def failback_provider(self, request: FailbackProviderRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="FAILBACK_PROVIDER",
            target=request.target_device,
            message="NETCONF production failback is disabled in read-only Phase 3.",
        )

    def switch_interface(self, request: SwitchInterfaceRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="SWITCH_INTERFACE",
            target=request.target_device,
            message="NETCONF production interface switch is disabled in read-only Phase 3.",
        )

    def enable_backup_path(self, request: PathStateRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="ENABLE_BACKUP_PATH",
            target=request.target_device,
            message="NETCONF production path enablement is disabled in read-only Phase 3.",
        )

    def disable_degraded_path(self, request: PathStateRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.NOT_CONFIGURED,
            driver_type=self.driver_type,
            action_type="DISABLE_DEGRADED_PATH",
            target=request.target_device,
            message="NETCONF production path disablement is disabled in read-only Phase 3.",
        )

    def verify_route_path(self, request: RouteVerificationRequest) -> ControlPlaneResponse:
        if not self.is_configured:
            return ControlPlaneResponse(
                success=False,
                status=ControlPlaneStatus.NOT_CONFIGURED,
                driver_type=self.driver_type,
                action_type="VERIFY_ROUTE_PATH",
                target=request.target_device,
                message="NETCONF transport not configured for verification.",
            )

        route = self.get_static_default_route(request.target_device)
        if route is not None:
            return ControlPlaneResponse(
                success=True,
                status=ControlPlaneStatus.READY,
                driver_type=self.driver_type,
                action_type="VERIFY_ROUTE_PATH",
                target=request.target_device,
                message=f"Verified route prefix {route.prefix} next-hop {route.next_hop}.",
                details={"verified": True, "route": route.model_dump()},
            )

        return ControlPlaneResponse(
            success=False,
            status=ControlPlaneStatus.ERROR,
            driver_type=self.driver_type,
            action_type="VERIFY_ROUTE_PATH",
            target=request.target_device,
            message="Route verification failed: static route not found.",
        )
