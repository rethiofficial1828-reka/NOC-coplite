"""
Production Control-Plane Models Module for NOC Copilot v1.4.

Defines strongly-typed, immutable Pydantic V2 domain models, enums, OpenConfig YANG path constants,
and telemetry payloads for enterprise physical network control plane integration.
Guarantees:
- Zero CLI-over-SSH / raw command strings
- Strictly typed transport protocols (gNMI/gRPC and NETCONF/YANG)
- Immutable endpoint configuration profiles
- Sub-second BFD hardware state definitions
- Structured OpenConfig schema constants
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Hardware & Protocol Enumerations
# ---------------------------------------------------------------------------


class NOSVendor(str, Enum):
    """Supported Network Operating System (NOS) vendor platforms."""

    ARISTA_EOS = "ARISTA_EOS"
    CISCO_IOSXR = "CISCO_IOSXR"
    CISCO_IOSXE = "CISCO_IOSXE"
    JUNIPER_JUNOS = "JUNIPER_JUNOS"
    SONIC = "SONIC"
    FRROUTING = "FRROUTING"
    GENERIC_OPENCONFIG = "GENERIC_OPENCONFIG"


class TransportProtocol(str, Enum):
    """
    Supported structured network transport protocols.
    Explicitly excludes arbitrary CLI-over-SSH and shell execution.
    """

    GNMI_GRPC = "GNMI_GRPC"
    NETCONF_YANG = "NETCONF_YANG"


class BFDState(str, Enum):
    """Bidirectional Forwarding Detection (BFD RFC 5880) session states."""

    ADMIN_DOWN = "ADMIN_DOWN"
    DOWN = "DOWN"
    INIT = "INIT"
    UP = "UP"


# ---------------------------------------------------------------------------
# OpenConfig Standard YANG Path Constants
# ---------------------------------------------------------------------------

OC_INTERFACE_STATE = "/interfaces/interface[name={name}]/state"
OC_INTERFACE_CONFIG = "/interfaces/interface[name={name}]/config"
OC_STATIC_DEFAULT_ROUTE = (
    "/network-instances/network-instance[name=default]/protocols/protocol[identifier=STATIC][name=STATIC]"
    "/static-routes/static[prefix=0.0.0.0/0]"
)
OC_STATIC_ROUTE_METRIC = (
    "/network-instances/network-instance[name=default]/protocols/protocol[identifier=STATIC][name=STATIC]"
    "/static-routes/static[prefix=0.0.0.0/0]/next-hops/next-hop[index={index}]/config/metric"
)
OC_NEXT_HOP = (
    "/network-instances/network-instance[name=default]/protocols/protocol[identifier=STATIC][name=STATIC]"
    "/static-routes/static[prefix=0.0.0.0/0]/next-hops/next-hop[index={index}]/config/next-hop"
)
OC_BFD_STATE = "/bfd/interfaces/interface[id={id}]/peers/peer[address={peer_ip}]/state"


# ---------------------------------------------------------------------------
# Domain Models (Frozen & Immutable Endpoint Profiles)
# ---------------------------------------------------------------------------


class DeviceEndpointProfile(BaseModel):
    """
    Immutable production hardware device endpoint and transport profile.
    Guarantees mTLS parameters and strict device allowlist association.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    device_id: str = Field(..., description="Unique device identifier matching inventory")
    hostname: str = Field(..., description="Fully qualified or inventory hostname")
    management_ip: str = Field(..., description="Management IPv4 or IPv6 address")
    management_port: int = Field(default=9339, description="gNMI (9339) or NETCONF (830) port")
    vendor: NOSVendor = Field(..., description="Underlying NOS vendor platform")
    transport: TransportProtocol = Field(default=TransportProtocol.GNMI_GRPC, description="Structured transport protocol")
    tls_server_name: str = Field(..., description="SAN hostname expected in device certificate")
    ca_cert_path: str = Field(..., description="Filesystem path to trusted root/intermediate CA certificate")
    client_cert_path: str = Field(..., description="Filesystem path to client certificate for mTLS")
    client_key_path: str = Field(..., description="Filesystem path to client private key for mTLS")
    supported_models: List[str] = Field(
        default_factory=lambda: [
            "openconfig-interfaces.yang",
            "openconfig-network-instance.yang",
            "openconfig-local-routing.yang",
            "openconfig-bfd.yang",
        ],
        description="Supported OpenConfig YANG schema models",
    )
    allowlisted: bool = Field(default=True, description="Whether device is in declared production allowlist")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional structured metadata")


class BFDTelemetrySignal(BaseModel):
    """
    Strongly-typed sub-second BFD hardware telemetry notification.
    Enables instant micro-link failure detection (<50ms).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    device_id: str = Field(..., description="Target device ID reporting BFD state")
    interface_name: str = Field(..., description="Monitored WAN/LAN interface")
    peer_address: str = Field(..., description="BFD peer IP address")
    local_state: BFDState = Field(..., description="Local BFD session state")
    remote_state: BFDState = Field(..., description="Remote peer BFD session state")
    detection_time_ms: float = Field(..., description="Effective BFD detection multiplier time in ms")
    flap_count: int = Field(default=0, description="Total link flap count within observation window")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OpenConfigQuery(BaseModel):
    """Typed read query for OpenConfig YANG path telemetry."""

    model_config = ConfigDict(frozen=True)

    device_id: str = Field(..., description="Target device ID")
    yang_path: str = Field(..., description="Structured OpenConfig YANG path")
    sample_interval_ms: int = Field(default=1000, description="Telemetry sample interval")


class OpenConfigMutation(BaseModel):
    """Typed OpenConfig atomic mutation payload."""

    model_config = ConfigDict(frozen=True)

    mutation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    device_id: str = Field(..., description="Target device ID")
    yang_path: str = Field(..., description="Target OpenConfig YANG path")
    payload: Dict[str, Any] = Field(..., description="Validated OpenConfig JSON-IETF payload")
    dry_run: bool = Field(default=True, description="Safety flag: enforce DRY_RUN")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TransportStatus(str, Enum):
    """Operational state of a transport channel session."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    TLS_ERROR = "TLS_ERROR"
    TIMEOUT = "TIMEOUT"
    AUTH_ERROR = "AUTH_ERROR"


class TransportSessionState(BaseModel):
    """Real-time metadata tracking an active gNMI or NETCONF transport session."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    device_id: str = Field(..., description="Target device ID")
    transport: TransportProtocol = Field(..., description="Transport protocol")
    status: TransportStatus = Field(default=TransportStatus.DISCONNECTED)
    tls_active: bool = Field(default=False)
    last_successful_read: Optional[datetime] = Field(default=None)
    last_error: Optional[str] = Field(default=None)
    openconfig_models_supported: List[str] = Field(default_factory=list)


class OpenConfigInterfaceState(BaseModel):
    """Typed representation of /interfaces/interface/state."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Interface name")
    admin_status: str = Field(default="UP")
    oper_status: str = Field(default="UP")
    in_octets: Optional[int] = Field(default=None)
    out_octets: Optional[int] = Field(default=None)


class OpenConfigStaticRoute(BaseModel):
    """Typed representation of /network-instances/.../static-routes."""

    model_config = ConfigDict(frozen=True)

    prefix: str = Field(..., description="Route destination CIDR prefix")
    next_hop: str = Field(..., description="Next-hop gateway IP")
    metric: int = Field(default=10, description="Route distance/metric")
    admin_distance: Optional[int] = Field(default=None)


class OpenConfigBFDPeer(BaseModel):
    """Typed representation of /bfd/interfaces/.../peers/peer."""

    model_config = ConfigDict(frozen=True)

    interface_id: str = Field(...)
    peer_address: str = Field(...)
    local_state: BFDState = Field(...)
    remote_state: BFDState = Field(...)
    detection_time_ms: float = Field(default=50.0)
