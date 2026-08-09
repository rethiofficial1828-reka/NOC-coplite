"""
Comprehensive Unit Test Suite for Atomic Agent Foundation & Architectural Hardening.
"""

import json
import os
import tempfile
import unittest
from typing import Any, Optional

from agents.base import BaseAgent
from agents.core.container import ServiceContainer
from agents.exceptions import (
    AgentError,
    ExecutionError,
    RegistrationError,
    ValidationError,
)
from agents.events import Event, EventBus
from agents.orchestrator import AgentOrchestrator
from agents.registry import AgentRegistry
from agents.schemas import (
    AgentMetadata,
    AgentMetrics,
    AgentState,
    CapabilityFlags,
    DeviceHealth,
    ExecutionContext,
    Incident,
    PredictionResult,
    Recommendation,
    TelemetryPacket,
    TopologyState,
)
from config.config_manager import ConfigManager
from plugins.base import Plugin
from plugins.manager import PluginManager


class SampleDummyAgent(BaseAgent):
    """Concrete dummy agent for testing framework execution."""

    def __init__(self, metadata: Optional[AgentMetadata] = None, container=None, event_bus=None):
        meta = metadata or AgentMetadata(
            name="SampleDummyAgent",
            version="1.0.0",
            description="Dummy agent for testing",
            dependencies=[],
        )
        super().__init__(metadata=meta, container=container, event_bus=event_bus)

    def validate_input(self, input_data: Any) -> Any:
        if input_data == "INVALID":
            raise ValidationError("Input payload is invalid")
        return input_data

    def _execute_internal(self, input_data: Any, context: Optional[ExecutionContext] = None) -> Any:
        if input_data == "FAIL":
            raise ValueError("Intentional execution failure")
        return {"processed": input_data, "status": "ok"}


class DependencyTestAgent(BaseAgent):
    """Agent that depends on SampleDummyAgent."""

    def __init__(self, container=None, event_bus=None):
        meta = AgentMetadata(
            name="DependencyTestAgent",
            version="1.0.0",
            dependencies=["SampleDummyAgent"],
        )
        super().__init__(metadata=meta, container=container, event_bus=event_bus)

    def _execute_internal(self, input_data: Any, context: Optional[ExecutionContext] = None) -> Any:
        return {"upstream": input_data, "step": "completed"}


class SampleTestPlugin(Plugin):
    """Sample plugin for testing PluginManager."""

    @property
    def plugin_name(self) -> str:
        return "SampleTestPlugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    def initialize(self) -> None:
        self.init_called = True

    def shutdown(self) -> None:
        self.shutdown_called = True


class TestAtomicAgentFoundation(unittest.TestCase):

    def setUp(self):
        # Reset singletons before each test
        ServiceContainer.get_global().reset()
        EventBus.get_global().clear()
        AgentRegistry.get_global().clear()
        ConfigManager.get_instance().reset_overrides()

    def test_01_pydantic_schemas(self):
        """Test domain Pydantic schemas initialization and serialization."""
        meta = AgentMetadata(name="TestAgent", version="1.2.3")
        self.assertEqual(meta.name, "TestAgent")
        self.assertEqual(meta.version, "1.2.3")
        self.assertTrue(meta.capabilities.supports_cpu)

        telemetry = TelemetryPacket(
            device_id="rtr-01",
            interface="Branch3-Uplink",
            metrics={"utilization": 75.5, "latency": 22.0},
        )
        self.assertEqual(telemetry.device_id, "rtr-01")
        self.assertEqual(telemetry.metrics["utilization"], 75.5)

        pred = PredictionResult(
            interface="Branch3-Uplink",
            risk_score=0.85,
            time_to_impact=12.5,
            contributing_signals=["latency_slope_rising"],
        )
        self.assertEqual(pred.risk_score, 0.85)

        ctx = ExecutionContext()
        self.assertIsNotNone(ctx.context_id)

    def test_02_service_container(self):
        """Test Dependency Injection ServiceContainer."""
        container = ServiceContainer()
        container.register_instance(str, "TestConfigValue")
        self.assertTrue(container.has_service(str))
        self.assertEqual(container.resolve(str), "TestConfigValue")

        # Factory binding
        container.register_factory(int, lambda c: 42, singleton=True)
        self.assertEqual(container.resolve(int), 42)

    def test_03_base_agent_lifecycle_and_metrics(self):
        """Test BaseAgent lifecycle state transitions and thread-safe metrics."""
        agent = SampleDummyAgent()
        self.assertEqual(agent.status, AgentState.UNINITIALIZED.value)

        agent.initialize()
        self.assertEqual(agent.status, AgentState.READY.value)

        # Successful execution
        output = agent.execute("test_payload")
        self.assertEqual(output, {"processed": "test_payload", "status": "ok"})
        metrics = agent.metrics
        self.assertEqual(metrics.execution_count, 1)
        self.assertEqual(metrics.success_count, 1)
        self.assertEqual(metrics.failure_count, 0)
        self.assertTrue(metrics.last_runtime_ms >= 0.0)

        # Validation error execution
        with self.assertRaises(ValidationError):
            agent.execute("INVALID")
        self.assertEqual(agent.metrics.failure_count, 1)

        # Exception execution
        with self.assertRaises(ExecutionError):
            agent.execute("FAIL")
        self.assertEqual(agent.metrics.failure_count, 2)

        # Reset metrics
        agent.reset_metrics()
        self.assertEqual(agent.metrics.execution_count, 0)

        # Shutdown
        agent.shutdown()
        self.assertEqual(agent.status, AgentState.TERMINATED.value)

    def test_04_agent_registry(self):
        """Test AgentRegistry registration, duplicate check, resolution, and dependency validation."""
        registry = AgentRegistry()
        agent = SampleDummyAgent()

        registry.register(agent)
        self.assertTrue(registry.exists("SampleDummyAgent"))
        self.assertEqual(registry.get("SampleDummyAgent"), agent)

        # Duplicate registration error
        with self.assertRaises(RegistrationError):
            registry.register(agent)

        # Allow override
        registry.register(agent, allow_override=True)

        # Dependency validation missing
        dep_agent = DependencyTestAgent()
        registry.register(dep_agent)
        self.assertTrue(registry.validate_dependencies("DependencyTestAgent"))

        # Unregister
        registry.unregister("SampleDummyAgent")
        with self.assertRaises(RegistrationError):
            registry.validate_dependencies("DependencyTestAgent")

    def test_05_agent_orchestrator_dag_execution(self):
        """Test AgentOrchestrator DAG dependency ordering and workflow execution."""
        registry = AgentRegistry()
        agent1 = SampleDummyAgent()
        agent2 = DependencyTestAgent()

        registry.register(agent1)
        registry.register(agent2)

        orchestrator = AgentOrchestrator(registry=registry)

        # Topological sorting test
        sorted_order = orchestrator.resolve_dependency_order(["DependencyTestAgent"])
        self.assertEqual(sorted_order, ["SampleDummyAgent", "DependencyTestAgent"])

        # Workflow execution
        orchestrator.register_workflow("test_pipeline", ["SampleDummyAgent", "DependencyTestAgent"])
        ctx = orchestrator.execute_workflow("test_pipeline", initial_input="start_data")

        self.assertIn("SampleDummyAgent", ctx.results)
        self.assertIn("DependencyTestAgent", ctx.results)
        self.assertEqual(ctx.results["DependencyTestAgent"]["step"], "completed")

    def test_06_event_bus(self):
        """Test EventBus publishing, subscription, filtering, and isolation."""
        event_bus = EventBus()
        received_events = []

        def callback(evt: Event):
            received_events.append(evt)

        sub_id = event_bus.subscribe("telemetry.received", callback)
        self.assertIsNotNone(sub_id)

        evt = Event(
            event_type="telemetry.received",
            source="TestSensor",
            payload={"metric": 100},
        )

        notified = event_bus.publish(evt)
        self.assertEqual(notified, 1)
        self.assertEqual(len(received_events), 1)

        # Unsubscribe
        event_bus.unsubscribe(sub_id)
        event_bus.publish(evt)
        self.assertEqual(len(received_events), 1)

    def test_07_config_manager(self):
        """Test ConfigManager overrides and JSON loading."""
        config = ConfigManager.get_instance()
        self.assertEqual(config.get("ENGINE_PORT"), 8000)

        # Set runtime override
        config.set_override("ENGINE_PORT", 9999)
        self.assertEqual(config.get("ENGINE_PORT"), 9999)

        # Remove override
        config.remove_override("ENGINE_PORT")
        self.assertEqual(config.get("ENGINE_PORT"), 8000)

        # JSON file loading
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
            json.dump({"CUSTOM_KEY": "CUSTOM_VALUE"}, f)
            temp_path = f.name

        try:
            config.load_from_json(temp_path)
            self.assertEqual(config.get("CUSTOM_KEY"), "CUSTOM_VALUE")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_08_plugin_manager(self):
        """Test PluginManager registration and lifecycle."""
        manager = PluginManager()
        plugin = SampleTestPlugin()

        manager.register_plugin(plugin)
        self.assertTrue(plugin.init_called)
        self.assertTrue(plugin.is_active)

        manager.shutdown_all()
        self.assertTrue(plugin.shutdown_called)
        self.assertFalse(plugin.is_active)


if __name__ == "__main__":
    unittest.main()
