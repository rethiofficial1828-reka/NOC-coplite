"""
Virtual Hardware Harness Models Module.

Defines Pydantic models for virtual NOS qualification, container specifications,
and cross-protocol readback consistency results.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from agents.failover.production_models import (
    NOSVendor,
    OpenConfigBFDPeer,
    OpenConfigInterfaceState,
    OpenConfigStaticRoute,
    TransportProtocol,
)


class VirtualDeviceStatus(str, Enum):
    """Lifecycle state of a virtual NOS container or simulation."""

    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    ERROR = "ERROR"
    UNAVAILABLE = "UNAVAILABLE"


class VirtualNOSSpec(BaseModel):
    """Specification of a virtual NOS test target."""

    model_config = ConfigDict(frozen=True)

    device_id: str = Field(..., description="Target device ID")
    vendor: NOSVendor = Field(..., description="NOS Vendor")
    image_name: str = Field(..., description="Docker image tag or identifier")
    management_ip: str = Field(default="127.0.0.1")
    management_port: int = Field(default=9339)
    transport: TransportProtocol = Field(default=TransportProtocol.GNMI_GRPC)
    is_image_available: bool = Field(default=False)
    tls_server_name: str = Field(default="router.test.local")
    supported_models: List[str] = Field(
        default_factory=lambda: [
            "openconfig-interfaces.yang",
            "openconfig-network-instance.yang",
            "openconfig-local-routing.yang",
            "openconfig-bfd.yang",
        ]
    )


class ReadbackVerificationResult(BaseModel):
    """Cross-protocol OpenConfig telemetry readback and verification result."""

    model_config = ConfigDict(frozen=True)

    result_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    device_id: str = Field(..., description="Device ID tested")
    protocol: TransportProtocol = Field(..., description="Transport protocol used")
    interface_state: Optional[OpenConfigInterfaceState] = Field(default=None)
    default_route: Optional[OpenConfigStaticRoute] = Field(default=None)
    bfd_state: Optional[OpenConfigBFDPeer] = Field(default=None)
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    consistency_matched: bool = Field(default=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
