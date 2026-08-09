# NOC Copilot — Atomic Agent Framework Architecture

## Overview

The **Atomic Agent Framework** provides a production-grade, highly scalable, and modular AI orchestration layer for NOC Copilot. It decouples business execution logic from framework mechanics using an Open-Closed Architecture.

Future specialized agents (`TelemetryAgent`, `PredictionAgent`, `RAGAgent`, `IncidentAgent`, `RecommendationAgent`, `TopologyAgent`, `AlertAgent`, `ReportAgent`, `SecurityAgent`, `NetworkDiscoveryAgent`) can be added cleanly by simply subclassing `BaseAgent` and registering themselves with the `AgentRegistry` — without requiring any changes to the core `AgentOrchestrator`.

---

## Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                                  APPLICATION LAYER                                |
|          (FastAPI / Streamlit / PySide6 Desktop / CLI Executable Packaging)        |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                 ORCHESTRATION LAYER                               |
|                                                                                   |
|    +-------------------+      +-----------------------+      +------------------+ |
|    |  AgentRegistry    |      |    AgentOrchestrator  |      | ServiceContainer | |
|    |  (Thread-Safe)    |      |  (DAG Topological)   |      |   (DI Container) | |
|    +-------------------+      +-----------------------+      +------------------+ |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                  AGENT FOUNDATION                                 |
|                                                                                   |
|                                  +--------------+                                 |
|                                  |  BaseAgent   |                                 |
|                                  +--------------+                                 |
|                                         |                                         |
|         +-------------------------------+-------------------------------+         |
|         |                               |                               |         |
|  +--------------+               +---------------+               +---------------+ |
|  |TelemetryAgent|               |PredictionAgent|               | IncidentAgent | |
|  +--------------+               +---------------+               +---------------+ |
|         |                               |                               |         |
+---------|-------------------------------|-------------------------------|---------+
          |                               |                               |
          +-------------------------------+-------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                 EVENT BUS SYSTEM                                  |
|            EventBus (Publish / Subscribe / Predicate Topic Filtering)              |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                   PLUGIN LAYER                                    |
|   PluginManager -> Protocol & Hardware Plugins (SNMP, Syslog, Cisco, Juniper, etc.) |
+-----------------------------------------------------------------------------------+
```

---

## Core Components

### 1. BaseAgent (`agents.base.BaseAgent`)
Abstract Base Class for all system agents. Implements `IAgent` interface protocol.
- **Lifecycle Management**: Transitions through `UNINITIALIZED -> INITIALIZING -> READY -> RUNNING -> COMPLETED / FAILED / TERMINATED`.
- **Validation**: Enforces strict payload validation (`validate_input`, `validate_output`).
- **Runtime Metrics**: Tracks total executions, elapsed timing, average runtime, failure/success counts, and state in a thread-safe `AgentMetrics` Pydantic model.
- **Structured Logging**: Zero `print()` statements. Uses `agents.logger` structured logger.

### 2. AgentRegistry (`agents.registry.AgentRegistry`)
Thread-safe centralized registry for registering, lookup, duplicate prevention, and lazy loading of agents.
- `register(agent, name, allow_override)`: Registers agent instance, class, or factory.
- `get(name)`: Resolves and lazily instantiates agent via dependency container.
- `validate_dependencies(name)`: Validates that all prerequisite agent dependencies are registered.
- `list_agents()`: Returns current state, metadata, and metrics of all agents.

### 3. AgentOrchestrator (`agents.orchestrator.AgentOrchestrator`)
Central workflow orchestrator supporting Directed Acyclic Graph (DAG) topological dependency resolution.
- Computes topological order of execution based on `agent.metadata.dependencies`.
- Detects circular dependencies automatically.
- Pass-through shared execution context (`ExecutionContext`).

### 4. Event Bus (`agents.events.EventBus`)
Decoupled publish-subscribe event broker supporting wildcard (`*`) and topic-based routing, filter predicates, and subscriber error isolation.

### 5. Service Container (`agents.core.ServiceContainer`)
Thread-safe Dependency Injection container supporting singleton registration, lazy factory binding, and type-safe resolution.

---

## Agent Lifecycle

```
    [ UNINITIALIZED ]
            |
            v
     initialize()
            |
            v
     [ INITIALIZING ]  ------ (Error) ------>  [ FAILED ]
            |
            v
       [ READY ]
            |
            v
       execute()
            |
            v
      [ RUNNING ]      ------ (Error) ------>  [ FAILED ]
            |
            v
     [ COMPLETED ] ---> Returns to [ READY ]
            |
            v
       shutdown()
            |
            v
    [ TERMINATED ]
```

---

## Developer Guide: How to Implement a New Agent

Creating a new specialized agent requires zero modifications to the framework or orchestrator:

```python
from typing import Any, Optional
from agents.base import BaseAgent
from agents.schemas import AgentMetadata, CapabilityFlags, ExecutionContext
from pydantic import BaseModel

class MyInputSchema(BaseModel):
    query: str

class MyOutputSchema(BaseModel):
    result: str

class CustomAnalysisAgent(BaseAgent):
    def __init__(self, container=None, event_bus=None):
        metadata = AgentMetadata(
            name="CustomAnalysisAgent",
            version="1.0.0",
            description="Performs custom analysis",
            dependencies=[],
            capabilities=CapabilityFlags(supports_cpu=True)
        )
        super().__init__(metadata=metadata, container=container, event_bus=event_bus)

    def validate_input(self, input_data: Any) -> MyInputSchema:
        if isinstance(input_data, dict):
            return MyInputSchema(**input_data)
        return input_data

    def _execute_internal(self, input_data: MyInputSchema, context: Optional[ExecutionContext] = None) -> MyOutputSchema:
        # Perform domain logic here
        return MyOutputSchema(result=f"Analyzed query: {input_data.query}")
```

To register and execute:
```python
from agents.registry import AgentRegistry
from agents.orchestrator import AgentOrchestrator

registry = AgentRegistry.get_global()
agent = CustomAnalysisAgent()
registry.register(agent)

orchestrator = AgentOrchestrator(registry=registry)
output = orchestrator.execute_agent("CustomAnalysisAgent", {"query": "Check bandwidth"})
```

---

## Future Roadmap & Enterprise Expansion

1. **Phase 2 — Agent Integration**: Migration of business logic into concrete `TelemetryAgent`, `PredictionAgent`, `RAGAgent`, `IncidentAgent`, and `RecommendationAgent`.
2. **Protocol & Hardware Plugins**: Addition of SNMP, Syslog, Cisco, Juniper, Fortinet plugins in `plugins/`.
3. **PySide6 Desktop Application**: Packaging with PyInstaller / Nuitka for Windows offline desktop distribution.
4. **Local Ollama Integration**: Offline local LLM inference fallback integration.
