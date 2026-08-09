"""
Topology Agent Package — Sprint 10.

Provides the production-grade Topology Intelligence Subsystem for NOC Copilot.
This package integrates with the Atomic Agent architecture to deliver network
graph analysis, blast-radius calculation, dependency traversal, and service
impact assessment.

Exported symbols:
    TopologyAgent               — BaseAgent subclass; subscribes to incident events
    TopologyService             — Business logic layer
    TopologyRepository          — Thread-safe topology data source
    TopologyGraph               — Pure adjacency-list graph engine (no NetworkX)
    TopologyValidator           — Structural graph validation
    TopologyNode                — Pydantic model for a network node
    TopologyLink                — Pydantic model for a directed network link
    TopologyPath                — Pydantic model for a computed path
    TopologyDependency          — Pydantic model for a dependency relationship
    ServiceImpact               — Pydantic model for service-level impact
    BlastRadius                 — Pydantic model for blast-radius result
    TopologyAnalysis            — Pydantic model for a complete topology analysis
    TopologyStatistics          — Pydantic model for aggregated statistics
    register_topology_agent     — Convenience registration helper
"""

from agents.topology.topology_models import (
    BlastRadius,
    ServiceImpact,
    TopologyAnalysis,
    TopologyDependency,
    TopologyLink,
    TopologyNode,
    TopologyPath,
    TopologyStatistics,
)
from agents.topology.topology_graph import TopologyGraph
from agents.topology.topology_repository import TopologyRepository
from agents.topology.topology_validator import TopologyValidator
from agents.topology.topology_service import TopologyService
from agents.topology.topology_agent import TopologyAgent, register_topology_agent

__all__ = [
    "TopologyNode",
    "TopologyLink",
    "TopologyPath",
    "TopologyDependency",
    "ServiceImpact",
    "BlastRadius",
    "TopologyAnalysis",
    "TopologyStatistics",
    "TopologyGraph",
    "TopologyRepository",
    "TopologyValidator",
    "TopologyService",
    "TopologyAgent",
    "register_topology_agent",
]
