"""
GNN Models Module for NOC-Copilot GNN Blast-Radius Subsystem.

Defines Pydantic V2 domain models representing node feature vectors,
edge feature vectors, graph tensor representations, propagation requests,
and advisory blast-radius predictions.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class GNNProvenance(str, Enum):
    """Origin of the GNN blast-radius prediction."""

    NEURAL_GNN_INFERENCE = "NEURAL_GNN_INFERENCE"
    DETERMINISTIC_PROPAGATION_FALLBACK = "DETERMINISTIC_PROPAGATION_FALLBACK"


class GNNNodeFeatures(BaseModel):
    """Feature vector representation of a topology node for message passing."""

    model_config = ConfigDict(frozen=False)

    node_id: str = Field(..., description="Unique node identifier")
    role_idx: int = Field(default=0, description="Encoded role (0=router, 1=core, 2=firewall, 3=hub)")
    criticality: float = Field(default=5.0, ge=1.0, le=10.0, description="Business criticality (1-10)")
    health_score: float = Field(default=100.0, ge=0.0, le=100.0, description="Health score (0-100)")
    degree: int = Field(default=2, ge=0, description="Node degree (connected link count)")
    risk_score: float = Field(default=0.05, ge=0.0, le=1.0, description="XGBoost failure risk (0.0-1.0)")


class GNNEdgeFeatures(BaseModel):
    """Feature vector representation of a topology link for message passing."""

    model_config = ConfigDict(frozen=False)

    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    bandwidth_mbps: float = Field(default=1000.0, description="Nominal bandwidth in Mbps")
    utilization_percent: float = Field(default=35.0, description="Link utilization percentage")
    is_redundant: bool = Field(default=False, description="Whether parallel link exists")
    weight: float = Field(default=1.0, description="Routing distance weight")


class GNNGraphData(BaseModel):
    """Topology graph structure ready for GNN / message-passing evaluation."""

    model_config = ConfigDict(frozen=False)

    nodes: Dict[str, GNNNodeFeatures] = Field(default_factory=dict)
    edges: List[GNNEdgeFeatures] = Field(default_factory=list)
    num_nodes: int = Field(default=0)
    num_edges: int = Field(default=0)


class GNNBlastRadiusRequest(BaseModel):
    """Request payload for GNN failure propagation evaluation."""

    model_config = ConfigDict(frozen=False)

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_entity: str = Field(..., description="Failing node, interface, or provider")
    scenario: str = Field(default="PROVIDER_FAILURE", description="Simulated scenario")
    initial_perturbation: float = Field(default=0.40, ge=0.0, le=1.0, description="Initial risk impulse")
    attenuation_factor: float = Field(default=0.35, ge=0.0, le=1.0, description="Per-hop propagation damping factor")
    max_propagation_depth: int = Field(default=4, ge=1, le=10, description="Maximum message passing radius")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GNNBlastRadiusResult(BaseModel):
    """Advisory prediction result from GNN Blast-Radius Engine."""

    model_config = ConfigDict(frozen=False)

    result_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = Field(...)
    target_entity: str = Field(...)
    predicted_blast_radius_pct: float = Field(default=0.0, ge=0.0, le=100.0, description="Predicted network impact percentage")
    high_risk_nodes: List[str] = Field(default_factory=list, description="Nodes with propagation probability >= 0.50")
    propagation_probabilities: Dict[str, float] = Field(default_factory=dict, description="Risk propagation score per node")
    impacted_service_count: int = Field(default=0, description="Estimated number of affected services")
    confidence_score: float = Field(default=0.90, ge=0.0, le=1.0, description="Model prediction confidence")
    provenance: GNNProvenance = Field(default=GNNProvenance.DETERMINISTIC_PROPAGATION_FALLBACK)
    advisory_notes: List[str] = Field(default_factory=list, description="Advisory guidance for operator")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
