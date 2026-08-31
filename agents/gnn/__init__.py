"""
GNN Blast-Radius Subsystem Module for NOC-Copilot v1.5.

Exposes GNNBlastRadiusEngine, GNNService, and GNN domain models.
Advisory-only failure propagation and topology blast-radius estimation.
"""

from agents.gnn.gnn_models import (
    GNNBlastRadiusRequest,
    GNNBlastRadiusResult,
    GNNEdgeFeatures,
    GNNGraphData,
    GNNNodeFeatures,
)
from agents.gnn.graph_builder import TopologyGraphBuilder
from agents.gnn.blast_radius_gnn import GNNBlastRadiusEngine
from agents.gnn.gnn_service import GNNService

__all__ = [
    "GNNBlastRadiusEngine",
    "GNNBlastRadiusRequest",
    "GNNBlastRadiusResult",
    "GNNEdgeFeatures",
    "GNNGraphData",
    "GNNNodeFeatures",
    "GNNService",
    "TopologyGraphBuilder",
]
