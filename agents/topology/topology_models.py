"""
Topology Models Module.

Defines all strongly-typed Pydantic V2 domain models for the NOC Copilot
Topology Intelligence Subsystem.  These models are used throughout the
topology repository, graph engine, service layer, and agent to carry
topology state across module boundaries without leaking raw dictionaries.

All models are immutable-friendly (model_config allows mutation where
needed for incremental construction) and fully serialisable via
model_dump(mode='json').
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class NodeRole(str, Enum):
    """Functional role of a topology node in the network graph."""

    CORE = "core"
    DISTRIBUTION = "distribution"
    ACCESS = "access"
    EDGE = "edge"
    FIREWALL = "firewall"
    ROUTER = "router"
    SWITCH = "switch"
    WAN_INTERFACE = "wan_interface"
    ENDPOINT = "endpoint"
    UNKNOWN = "unknown"


class LinkState(str, Enum):
    """Operational state of a topology link."""

    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class ImpactSeverity(str, Enum):
    """Severity classification of a topology impact."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


# ---------------------------------------------------------------------------
# Primitive topology elements
# ---------------------------------------------------------------------------


class TopologyInterface(BaseModel):
    """Represents a named interface on a topology node."""

    model_config = ConfigDict(frozen=False)

    name: str = Field(..., description="Interface name (e.g. 'eth0', 'GE0/0')")
    description: str = Field(default="", description="Human-readable description")
    bandwidth_mbps: Optional[float] = Field(
        default=None, description="Maximum bandwidth in Mbps"
    )
    state: LinkState = Field(default=LinkState.UNKNOWN, description="Operational state")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Vendor-specific or extended attributes"
    )


class TopologyNode(BaseModel):
    """Represents a network device or logical node in the topology graph."""

    model_config = ConfigDict(frozen=False)

    node_id: str = Field(..., description="Globally unique node identifier")
    name: str = Field(..., description="Human-readable device name")
    role: NodeRole = Field(default=NodeRole.UNKNOWN, description="Functional role")
    device_type: str = Field(default="", description="Vendor/platform type string")
    location: str = Field(default="", description="Physical or logical location")
    management_ip: Optional[str] = Field(
        default=None, description="Out-of-band management IP address"
    )
    interfaces: List[TopologyInterface] = Field(
        default_factory=list, description="All interfaces on this node"
    )
    services: List[str] = Field(
        default_factory=list,
        description="Service names hosted on or through this node",
    )
    criticality: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Business criticality score 1 (low) to 10 (highest)",
    )
    is_active: bool = Field(default=True, description="Whether the node is operational")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional vendor or platform attributes"
    )


class TopologyLink(BaseModel):
    """Represents a directed network link between two topology nodes."""

    model_config = ConfigDict(frozen=False)

    link_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique link identifier",
    )
    source_node_id: str = Field(..., description="Origin node ID")
    source_interface: str = Field(..., description="Origin interface name")
    target_node_id: str = Field(..., description="Destination node ID")
    target_interface: str = Field(..., description="Destination interface name")
    bandwidth_mbps: Optional[float] = Field(
        default=None, description="Link capacity in Mbps"
    )
    weight: float = Field(
        default=1.0, ge=0.0, description="Routing/cost weight (lower = preferred)"
    )
    state: LinkState = Field(default=LinkState.UP, description="Link operational state")
    is_redundant: bool = Field(
        default=False,
        description="Whether this link forms a redundant path alongside another",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional link attributes"
    )


# ---------------------------------------------------------------------------
# Computed topology artefacts
# ---------------------------------------------------------------------------


class TopologyPath(BaseModel):
    """A computed path between two topology nodes."""

    model_config = ConfigDict(frozen=False)

    path_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_node_id: str = Field(..., description="Start node ID")
    target_node_id: str = Field(..., description="End node ID")
    hops: List[str] = Field(
        default_factory=list, description="Ordered list of node IDs traversed"
    )
    hop_count: int = Field(default=0, description="Total number of hops")
    total_weight: float = Field(default=0.0, description="Cumulative path weight")
    is_shortest: bool = Field(
        default=False, description="True if this is the shortest known path"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TopologyDependency(BaseModel):
    """A directed dependency relationship between two nodes."""

    model_config = ConfigDict(frozen=False)

    dependent_node_id: str = Field(
        ..., description="Node that depends on the provider"
    )
    provider_node_id: str = Field(
        ..., description="Node that the dependent relies on"
    )
    dependency_type: str = Field(
        default="network_path", description="Nature of the dependency"
    )
    is_critical: bool = Field(
        default=False,
        description="Whether loss of the provider immediately affects the dependent",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ServiceImpact(BaseModel):
    """Describes the impact on a service or logical group of services."""

    model_config = ConfigDict(frozen=False)

    service_name: str = Field(..., description="Impacted service name")
    affected_node_ids: List[str] = Field(
        default_factory=list, description="Nodes hosting or routing this service"
    )
    severity: ImpactSeverity = Field(
        default=ImpactSeverity.NONE, description="Computed severity level"
    )
    is_total_loss: bool = Field(
        default=False,
        description="True if all paths to the service are severed",
    )
    redundant_paths_available: int = Field(
        default=0, description="Number of alternative paths still operational"
    )
    estimated_user_impact: str = Field(
        default="", description="Human-readable impact summary"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BlastRadius(BaseModel):
    """
    Blast-radius assessment for a single failing node or link.

    Captures the full set of directly and transitively affected nodes,
    services, and the fraction of the network impacted.
    """

    model_config = ConfigDict(frozen=False)

    blast_radius_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    origin_node_id: str = Field(
        ..., description="Node whose failure initiated the blast-radius analysis"
    )
    directly_affected_node_ids: List[str] = Field(
        default_factory=list,
        description="Immediate neighbours that lose connectivity",
    )
    transitively_affected_node_ids: List[str] = Field(
        default_factory=list,
        description="All nodes reachable from origin that become isolated",
    )
    affected_services: List[str] = Field(
        default_factory=list, description="Services impacted by the failure"
    )
    single_points_of_failure: List[str] = Field(
        default_factory=list,
        description="Node IDs that are SPOFs in the affected subgraph",
    )
    total_affected_nodes: int = Field(
        default=0, description="Aggregate count of impacted nodes"
    )
    impact_percentage: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Fraction of total network nodes affected",
    )
    severity: ImpactSeverity = Field(
        default=ImpactSeverity.NONE,
        description="Overall blast-radius severity classification",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TopologyAnalysis(BaseModel):
    """
    Complete topology analysis result for a specific device and event.

    Aggregates blast-radius, upstream/downstream dependencies, shortest
    paths, redundant links, SPOF detection, and service impact into a
    single strongly-typed artefact that is stored in ExecutionContext.
    """

    model_config = ConfigDict(frozen=False)

    analysis_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique analysis identifier",
    )
    device_id: str = Field(..., description="Primary device under analysis")
    interface: str = Field(
        default="", description="Specific interface that triggered the analysis"
    )
    impacted_devices: List[str] = Field(
        default_factory=list, description="All device IDs directly impacted"
    )
    impacted_services: List[ServiceImpact] = Field(
        default_factory=list, description="Service-level impact assessments"
    )
    blast_radius: Optional[BlastRadius] = Field(
        default=None, description="Full blast-radius computation"
    )
    upstream_devices: List[str] = Field(
        default_factory=list,
        description="Devices this node depends on (upstream path)",
    )
    downstream_devices: List[str] = Field(
        default_factory=list,
        description="Devices that depend on this node (downstream path)",
    )
    shortest_paths: List[TopologyPath] = Field(
        default_factory=list,
        description="Shortest paths from the device to critical nodes",
    )
    dependency_tree: List[TopologyDependency] = Field(
        default_factory=list, description="Full dependency graph from this device"
    )
    redundant_links: List[TopologyLink] = Field(
        default_factory=list,
        description="Links that provide redundancy for this device",
    )
    routing_summary: str = Field(
        default="", description="Human-readable routing and connectivity summary"
    )
    overall_severity: ImpactSeverity = Field(
        default=ImpactSeverity.NONE,
        description="Aggregate severity across all impact dimensions",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the analysis",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional contextual attributes"
    )


class TopologyStatistics(BaseModel):
    """Aggregated statistics for the loaded topology graph."""

    model_config = ConfigDict(frozen=False)

    total_nodes: int = Field(default=0)
    total_links: int = Field(default=0)
    total_services: int = Field(default=0)
    active_nodes: int = Field(default=0)
    isolated_nodes: int = Field(default=0, description="Nodes with no links")
    single_points_of_failure: int = Field(
        default=0, description="Number of SPOF nodes in the graph"
    )
    average_node_degree: float = Field(
        default=0.0, description="Mean number of links per node"
    )
    topology_source: str = Field(
        default="", description="File or source from which topology was loaded"
    )
    last_loaded_at: Optional[datetime] = Field(
        default=None, description="UTC timestamp of last successful topology load"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TopologyIncidentImpact(BaseModel):
    """
    Topology-aware incident impact read model for operator investigation.

    Aggregates derived topology relationships, graph blast-radius, SPOF detection,
    downstream impact, alternative paths, and evidence provenance into a
    strongly-typed, immutable-friendly presentation artefact.
    """

    model_config = ConfigDict(frozen=False)

    target_entity: str = Field(
        ..., description="Target device or interface under investigation"
    )
    resolved_device_id: str = Field(
        default="", description="Resolved topology node ID (or UNRESOLVED)"
    )
    affected_interface: str = Field(
        default="", description="Specific interface identified as affected"
    )
    direct_dependencies: List[str] = Field(
        default_factory=list,
        description="Direct upstream and adjacent dependency node IDs",
    )
    affected_components: List[str] = Field(
        default_factory=list,
        description="Directly and transitively affected topology component IDs",
    )
    dependent_links: List[str] = Field(
        default_factory=list,
        description="Incident-affected link identifiers or endpoint descriptions",
    )
    potential_service_impact: List[str] = Field(
        default_factory=list,
        description="Human-readable potential service and business impacts",
    )
    single_points_of_failure: List[str] = Field(
        default_factory=list,
        description="Single points of failure in the affected subgraph",
    )
    blast_radius_level: ImpactSeverity = Field(
        default=ImpactSeverity.NONE,
        description="Blast-radius severity classification from graph analysis",
    )
    impact_percentage: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Percentage of total topology nodes impacted",
    )
    alternative_paths: List[str] = Field(
        default_factory=list,
        description="Available alternative candidate paths derived from topology/path services",
    )
    recommendation: str = Field(
        default="",
        description="Topology-grounded operator recommendation",
    )
    evidence_sources: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Evidence records with source, description, and provenance label",
    )
    provenance: Dict[str, str] = Field(
        default_factory=dict,
        description="Explicit provenance mapping for derived fields",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of impact assessment",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional contextual attributes"
    )
