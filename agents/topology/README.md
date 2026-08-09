# Topology Intelligence Subsystem — Sprint 10

## Overview

The **Topology Agent** is the sixth production agent in the NOC Copilot Atomic
Agent architecture.  It subscribes to network incident events, analyses the
live topology graph, and publishes richly structured `TopologyAnalysis` results
that flow downstream to the `KnowledgeAgent` and ultimately to the Qwen LLM.

---

## Architecture

```
TelemetryAgent
    │ telemetry.updated
    ▼
PredictionAgent
    │ prediction.generated
    ▼
IncidentAgent
    │ incident.created / incident.updated
    ▼
RecommendationAgent
    │ recommendation.generated
    ▼
TopologyAgent           ← THIS SUBSYSTEM
    │ topology.analysis.completed
    ▼
KnowledgeAgent
    │ knowledge.generated
    ▼
OllamaProvider → Qwen
```

### Package Layout

```
agents/topology/
├── __init__.py               Package exports
├── topology_models.py        Pydantic V2 domain models
├── topology_graph.py         Pure-Python adjacency-list graph engine
├── topology_repository.py    Thread-safe topology data source
├── topology_validator.py     Structural topology validation
├── topology_service.py       Business-logic analysis layer
├── topology_agent.py         BaseAgent subclass
└── README.md                 This file
```

---

## Graph Engine

`TopologyGraph` implements all algorithms using adjacency lists — no external
graph library (NetworkX, igraph, etc.) is required.

| Algorithm | Method | Complexity |
|-----------|--------|------------|
| Shortest path | `find_shortest_path()` | O((V+E) log V) — Dijkstra |
| Upstream traversal | `get_upstream()` | O(V+E) — reverse BFS |
| Downstream traversal | `get_downstream()` | O(V+E) — forward BFS |
| Blast radius | `calculate_blast_radius()` | O(V+E) — BFS + SPOF pass |
| Dependency tree | `calculate_dependency_tree()` | O(V+E) — bidirectional BFS |
| Redundant paths | `find_redundant_paths()` | O(k·(V+E) log V) — repeated Dijkstra |
| SPOF detection | `find_single_points_of_failure()` | O(V+E) — Tarjan articulation DFS |
| Service impact | `calculate_service_impact()` | O(V+E) — per-service BFS |

All algorithms are **deterministic** (sorted outputs, consistent heap ordering).

---

## Blast Radius Algorithm

1. **BFS from failing node** — collect all transitively downstream nodes.
2. **Isolation test** — for each downstream node, check whether all its
   incoming edges originate from within the downstream set.  Nodes with no
   alternative upstream path are classified as *directly affected*.
3. **Service collection** — union of services hosted on all affected nodes.
4. **SPOF detection** — run Tarjan articulation-point DFS over the affected
   subgraph to identify nodes whose removal further fragments the network.
5. **Severity classification**:

| Impact % | SPOFs | Severity |
|----------|-------|----------|
| ≥ 50% | any | CRITICAL |
| ≥ 25% | ≥ 2 | HIGH |
| ≥ 10% | ≥ 1 | MEDIUM |
| > 0% | 0 | LOW |
| 0% | 0 | NONE |

---

## Dependency Analysis

`calculate_dependency_tree()` performs a bidirectional BFS from a target node:

- **Upstream edges** — devices the target depends on (providers).
- **Downstream edges** — devices that depend on the target (dependants).

Each dependency is marked `is_critical=True` when the target node has no
alternative path (single incoming edge from that provider).

---

## Service Impact

Each service is associated with the nodes that host or route it.  When a node
fails, the engine determines:

- Which service-hosting nodes are in the downstream blast radius.
- How many healthy (non-affected) hosting nodes remain.
- Whether the service has zero remaining nodes (`is_total_loss=True`).

Severity is assigned per service:

| Remaining nodes | Severity |
|-----------------|----------|
| 0 | CRITICAL |
| 1 | HIGH |
| > 1 but some affected | MEDIUM |
| None affected | NONE |

---

## Topology Repository

`TopologyRepository` loads topology from two sources:

### 1. ContainerLab YAML (`topology.clab.yml`)

```yaml
topology:
  nodes:
    hub:
      kind: linux
      image: frrouting/frr:latest
      mgmt-ipv4: 172.20.20.10
    branch1:
      kind: linux
      image: frrouting/frr:latest
  links:
    - endpoints:
        - "hub:eth1"
        - "branch1:eth1"
```

Nodes are extracted from `topology.nodes`, links from `topology.links`.
ContainerLab links are **bidirectional** by convention, so each link is
inserted as both a forward and a reverse directed edge.

### 2. `config.settings.DEVICE_REGISTRY`

Each registry entry becomes a `TopologyNode`.  Devices already present from
the YAML file are enriched (location, device_type) rather than duplicated.

### Cache Invalidation

The repository stores the `mtime` of `topology.clab.yml`.  On every call to
`get_graph()` the current mtime is compared; if it has changed, the topology
is fully reloaded.  Call `reload()` to force an immediate refresh.

---

## Topology Validator

`TopologyValidator.validate()` runs the following checks:

| Check | Action on failure |
|-------|------------------|
| Duplicate node IDs | Raise `TopologyValidationError` |
| Duplicate link IDs | Raise `TopologyValidationError` |
| Broken link references | Raise `TopologyValidationError` |
| Invalid interface references | Log WARNING |
| Missing required metadata | Raise `TopologyValidationError` |
| Cyclic dependencies | Log WARNING (cycles are valid in ring topologies) |
| Orphan devices (no links) | Log WARNING |

---

## KnowledgeAgent Integration

When `TopologyAgent` completes an analysis it stores the result in:

```python
ExecutionContext.shared_state["latest_topology"][analysis_id]
```

`KnowledgeService` checks for a `topology_analysis` key in the recommendation
metadata dict.  When present, `KnowledgePromptBuilder.build_topology_section()`
renders a `TOPOLOGY INTELLIGENCE` block injected into the LLM prompt before
inference, giving the model graph-level network context.

Use `KnowledgeService.generate_knowledge_with_topology()` to explicitly supply
a `TopologyAnalysis` dict alongside a recommendation record.

---

## Developer Guide

### Register TopologyAgent

```python
from agents.topology import register_topology_agent

agent = register_topology_agent()
agent.initialize()
```

### Direct execution

```python
from agents.topology import TopologyAgent

agent = TopologyAgent()
agent.initialize()

incident = {
    "incident_id": "INC-2026-001",
    "affected_entities": ["core-01"],
    "severity": "CRITICAL",
    "details": {"interface": "GE0/0"},
}
results = agent.execute(incident)
analysis = results[0]
print(analysis.blast_radius.impact_percentage)
```

### Query the service directly

```python
from agents.topology import TopologyService

service = TopologyService()
analysis = service.analyze_device("core-01", interface="GE0/0")
summary  = service.summarize_network_state()
```

---

## Future Roadmap

| Feature | Description |
|---------|-------------|
| JSON topology source | Load topology from REST APIs or JSON files |
| Live link-state updates | Subscribe to SNMP traps / streaming telemetry to update link state in real-time |
| Multi-layer topology | Layer 2 / Layer 3 topology separation with cross-layer correlation |
| Weighted risk scoring | Incorporate telemetry risk scores into edge weights for risk-aware Dijkstra |
| Topology diff alerts | Publish `topology.changed` events when the graph structure changes |
| Path visualisation | Export `TopologyPath` results as DOT/SVG for the Streamlit dashboard |
| gRPC discovery integration | Automatic device discovery via gNMI/gRPC for zero-touch topology |
