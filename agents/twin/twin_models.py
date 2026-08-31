"""
Digital Twin Models Module for NOC-Copilot Network Digital Twin Subsystem.

Defines strongly-typed Pydantic V2 domain models representing device twin states,
interface twin states, link twin states, route twin states, digital twin snapshots,
what-if simulation outcomes, and affected component summaries.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class TwinSimulationScenario(str, Enum):
    """Scenarios for Network Digital Twin simulation."""

    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    LINK_FAILURE = "LINK_FAILURE"
    FAILOVER = "FAILOVER"
    FAILBACK = "FAILBACK"
    TRAFFIC_SURGE = "TRAFFIC_SURGE"
    NODE_ISOLATION = "NODE_ISOLATION"


class DeviceTwinState(BaseModel):
    """State representation of a network device within the Digital Twin."""

    model_config = ConfigDict(frozen=False)

    device_id: str = Field(..., description="Device unique identifier")
    name: str = Field(..., description="Human-readable device name")
    role: str = Field(default="router", description="Device role: core, router, firewall, wan_interface")
    is_active: bool = Field(default=True, description="Whether device is currently operational")
    health_score: float = Field(default=100.0, ge=0.0, le=100.0, description="Normalized operational health 0-100")
    active_interfaces: List[str] = Field(default_factory=list, description="Active interface identifiers")
    services: List[str] = Field(default_factory=list, description="Services hosted on or traversing this node")
    criticality: int = Field(default=5, ge=1, le=10, description="Business criticality rating (1-10)")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InterfaceTwinState(BaseModel):
    """State representation of a network interface within the Digital Twin."""

    model_config = ConfigDict(frozen=False)

    interface_id: str = Field(..., description="Interface unique identifier")
    device_id: str = Field(..., description="Parent device ID")
    name: str = Field(..., description="Interface port name (e.g. eth1, ge-0/0/0)")
    ip_address: Optional[str] = Field(default=None, description="Assigned IP address/subnet")
    bandwidth_mbps: float = Field(default=1000.0, description="Interface link speed in Mbps")
    is_up: bool = Field(default=True, description="Operational link state")
    current_provider: Optional[str] = Field(default=None, description="Associated WAN provider name")
    is_simulated: bool = Field(default=False, description="Whether interface is physically present or simulated")
    utilization_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LinkTwinState(BaseModel):
    """State representation of a network link within the Digital Twin."""

    model_config = ConfigDict(frozen=False)

    link_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_device: str = Field(..., description="Source device ID")
    source_interface: str = Field(..., description="Source interface name")
    target_device: str = Field(..., description="Target device ID")
    target_interface: str = Field(..., description="Target interface name")
    is_up: bool = Field(default=True, description="Link operational status")
    weight: float = Field(default=1.0, ge=0.0, description="Routing cost weight")
    bandwidth_mbps: float = Field(default=1000.0, description="Link nominal capacity")
    is_redundant: bool = Field(default=False, description="Whether link has parallel redundant path")
    is_simulated: bool = Field(default=False, description="Whether link is simulated or physically wired in lab")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RouteTwinState(BaseModel):
    """State representation of an IP route within the Digital Twin forwarding table."""

    model_config = ConfigDict(frozen=False)

    route_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    prefix: str = Field(default="0.0.0.0/0", description="Destination network prefix")
    next_hop: str = Field(..., description="Next-hop IP address")
    interface: str = Field(..., description="Egress interface name")
    distance: int = Field(default=10, description="Administrative distance / metric")
    provider_name: str = Field(..., description="Associated WAN provider")
    is_active: bool = Field(default=True, description="Whether route is currently selected primary")
    is_simulated: bool = Field(default=False, description="Whether route egresses via a simulated provider")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AffectedComponentsSummary(BaseModel):
    """Summary of affected components from a topology event."""

    model_config = ConfigDict(frozen=False)

    origin_entity: str = Field(..., description="Entity triggering the evaluation")
    directly_affected: List[str] = Field(default_factory=list, description="Directly severed nodes/links")
    transitively_affected: List[str] = Field(default_factory=list, description="Downstream isolated components")
    affected_services: List[str] = Field(default_factory=list, description="Impacted services")
    single_points_of_failure: List[str] = Field(default_factory=list, description="SPOF nodes exposed")
    impact_score: float = Field(default=0.0, ge=0.0, le=100.0, description="Aggregate impact percentage")


class TwinSimulationResult(BaseModel):
    """Result of a What-If simulation run inside the Network Digital Twin."""

    model_config = ConfigDict(frozen=False)

    simulation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scenario: TwinSimulationScenario = Field(..., description="Executed simulation scenario")
    target_entity: str = Field(..., description="Device, provider, or link under simulation")
    affected_node_ids: List[str] = Field(default_factory=list, description="Impacted device IDs")
    affected_link_ids: List[str] = Field(default_factory=list, description="Impacted link IDs")
    affected_services: List[str] = Field(default_factory=list, description="Impacted service names")
    isolated_nodes: List[str] = Field(default_factory=list, description="Nodes with zero remaining paths")
    rerouted_paths: Dict[str, List[str]] = Field(default_factory=dict, description="Computed alternative paths")
    predicted_reachability: Dict[str, bool] = Field(default_factory=dict, description="Reachability map per device")
    impact_severity: str = Field(default="LOW", description="LOW, MEDIUM, HIGH, CRITICAL")
    blast_radius_pct: float = Field(default=0.0, ge=0.0, le=100.0, description="Percentage of network affected")
    summary: str = Field(default="", description="Human-readable simulation summary")
    provenance: str = Field(default="DIGITAL_TWIN_SIMULATED")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DigitalTwinSnapshot(BaseModel):
    """Complete immutable snapshot of the Network Digital Twin state at a point in time."""

    model_config = ConfigDict(frozen=False)

    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: str = Field(default="1.5.0", description="Digital Twin schema version")
    devices: Dict[str, DeviceTwinState] = Field(default_factory=dict, description="Map of device states")
    interfaces: Dict[str, InterfaceTwinState] = Field(default_factory=dict, description="Map of interface states")
    links: Dict[str, LinkTwinState] = Field(default_factory=dict, description="Map of link states")
    routes: List[RouteTwinState] = Field(default_factory=list, description="Active and backup routes")
    providers: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Registered WAN providers")
    health_summary: Dict[str, float] = Field(default_factory=dict, description="Health score by device/provider")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
