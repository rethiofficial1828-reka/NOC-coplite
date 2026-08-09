"""
Dynamic DAG Scheduler for Enterprise AI Investigation Platform.

Executes investigation workflow DAGs dynamically using thread pool parallelism,
respects topological dependencies, skips unnecessary work, propagates failures,
executes agent retries, and supports early stopping on confidence thresholds.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from typing import Any, Dict, List, Optional

from agents.core.container import ServiceContainer
from agents.core.exceptions import ExecutionError
from agents.core.logger import get_agent_logger
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.interfaces.agent_interface import IAgent
from agents.orchestrator_ai.execution_graph import ExecutionGraph
from agents.orchestrator_ai.execution_monitor import ExecutionMonitor
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.orchestrator_ai.investigation_models import PlanStatus
from agents.registry.registry import AgentRegistry

logger = get_agent_logger("DynamicScheduler")


class DynamicScheduler:
    """
    DAG-based dynamic execution scheduler for Atomic Agent workflows.
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._max_workers = max_workers

    def execute_graph(
        self,
        graph: ExecutionGraph,
        context: InvestigationContext,
        agent_registry: Optional[AgentRegistry] = None,
        event_bus: Optional[EventBus] = None,
    ) -> ExecutionMonitor:
        """
        Execute the investigation DAG in topological parallel layers.

        Args:
            graph: ExecutionGraph DAG instance.
            context: Shared InvestigationContext.
            agent_registry: Optional AgentRegistry for resolving agent instances.
            event_bus: Optional EventBus for lifecycle event publishing.

        Returns:
            Completed ExecutionMonitor containing runtime metrics.
        """
        registry = agent_registry or AgentRegistry.get_global()
        bus = event_bus or EventBus.get_global()
        monitor = ExecutionMonitor(request_id=context.request.request_id)
        monitor.start_monitoring()

        target_confidence = context.plan.target_confidence if context.plan else 0.85

        try:
            execution_layers = graph.get_execution_levels()
            logger.info(
                f"Scheduler starting DAG execution for request '{context.request.request_id}' "
                f"({len(execution_layers)} layers, max_workers={self._max_workers})"
            )

            for layer_idx, layer in enumerate(execution_layers, start=1):
                # Filter nodes in layer that are pending
                pending_nodes = [
                    n_id for n_id in layer if graph.get_node(n_id) and graph.get_node(n_id).status == PlanStatus.PENDING
                ]

                if not pending_nodes:
                    continue

                logger.debug(f"Executing Layer {layer_idx}/{len(execution_layers)}: {pending_nodes}")

                # Execute pending nodes in layer concurrently
                with ThreadPoolExecutor(max_workers=min(self._max_workers, len(pending_nodes))) as executor:
                    future_to_node = {
                        executor.submit(
                            self._execute_single_node,
                            node_id,
                            graph,
                            context,
                            registry,
                            bus,
                            monitor,
                        ): node_id
                        for node_id in pending_nodes
                    }

                    for future in as_completed(future_to_node):
                        n_id = future_to_node[future]
                        try:
                            future.result()
                        except Exception as e:
                            logger.error(f"Unhandled exception executing node '{n_id}': {e}", exc_info=True)

                # Early stopping check after layer completion
                curr_confidence = context.get_latest_confidence()
                if curr_confidence >= target_confidence and layer_idx < len(execution_layers):
                    logger.info(
                        f"Early stopping threshold reached: confidence {curr_confidence:.2f} >= target {target_confidence:.2f}. "
                        "Skipping remaining downstream layers."
                    )
                    for remaining_layer in execution_layers[layer_idx:]:
                        for rem_id in remaining_layer:
                            rem_node = graph.get_node(rem_id)
                            if rem_node and rem_node.status == PlanStatus.PENDING:
                                graph.update_node_status(
                                    rem_id,
                                    PlanStatus.SKIPPED,
                                    error="Skipped due to early stopping confidence threshold reached.",
                                )
                                monitor.on_node_skipped(rem_id, "Early stopping threshold reached.")
                    break

        finally:
            monitor.stop_monitoring()
            logger.info(
                f"DAG execution completed for request '{context.request.request_id}' "
                f"in {monitor.get_elapsed_ms():.2f}ms (Parallelism={monitor.get_parallelism_factor():.2f}x)"
            )

        return monitor

    def _execute_single_node(
        self,
        node_id: str,
        graph: ExecutionGraph,
        context: InvestigationContext,
        registry: AgentRegistry,
        event_bus: EventBus,
        monitor: ExecutionMonitor,
    ) -> None:
        """
        Execute an individual agent node with dependency validation, retries, and metrics tracking.
        """
        node = graph.get_node(node_id)
        if not node:
            return

        # Check dependency statuses
        for dep_id in node.dependencies:
            dep_node = graph.get_node(dep_id)
            if not dep_node or dep_node.status != PlanStatus.COMPLETED:
                if dep_node and dep_node.status in (PlanStatus.FAILED, PlanStatus.SKIPPED) and node.mandatory:
                    graph.update_node_status(
                        node_id,
                        PlanStatus.SKIPPED,
                        error=f"Dependency '{dep_id}' was not completed successfully.",
                    )
                    monitor.on_node_skipped(node_id, f"Dependency '{dep_id}' failed or skipped.")
                    return

        # Start node execution
        graph.update_node_status(node_id, PlanStatus.RUNNING)
        monitor.on_node_started(node_id)
        event_bus.publish(
            Event(
                event_type="agent.execution.started",
                source=f"Scheduler.{node_id}",
                payload={"node_id": node_id, "request_id": context.request.request_id},
            )
        )

        start_time = time.perf_counter()
        agent_instance = self._resolve_agent(node.agent_name, registry)
        if not agent_instance:
            err_msg = f"Agent '{node.agent_name}' could not be resolved from registry or container."
            graph.update_node_status(node_id, PlanStatus.FAILED, error=err_msg)
            monitor.on_node_failed(node_id, 0.0)
            event_bus.publish(
                Event(
                    event_type="agent.execution.failed",
                    source=f"Scheduler.{node_id}",
                    payload={"node_id": node_id, "error": err_msg},
                )
            )
            if node.mandatory:
                graph.propagate_failure(node_id)
            return

        # Build input payload for agent from context / request / upstream outputs
        input_payload = self._build_agent_input(node.agent_name, context)

        # Retry loop
        attempt = 0
        last_error: Optional[Exception] = None

        while attempt <= node.max_retries:
            try:
                attempt += 1
                raw_output = agent_instance.execute(input_payload, context)
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0

                # Execution success
                graph.update_node_status(
                    node_id,
                    PlanStatus.COMPLETED,
                    result={"status": "success"},
                    duration_ms=elapsed_ms,
                    output_payload=raw_output,
                )
                context.set_agent_output(node.agent_name, raw_output, elapsed_ms)

                # Register evidence & confidence
                confidence = self._extract_confidence_and_register_evidence(node.agent_name, raw_output, context)
                context.record_confidence_sample(node.agent_name, confidence, f"Executed {node.agent_name}")
                monitor.record_confidence(confidence, node.agent_name)
                monitor.on_node_completed(node_id, elapsed_ms)

                event_bus.publish(
                    Event(
                        event_type="agent.execution.completed",
                        source=f"Scheduler.{node_id}",
                        payload={
                            "node_id": node_id,
                            "request_id": context.request.request_id,
                            "duration_ms": elapsed_ms,
                        },
                    )
                )
                return

            except Exception as e:
                last_error = e
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                if attempt <= node.max_retries:
                    graph.increment_retry(node_id)
                    monitor.on_node_failed(node_id, elapsed_ms, is_retry=True)
                    time.sleep(0.05 * attempt)  # Brief backoff retry delay
                else:
                    break

        # Max retries exhausted -> Failure
        err_str = str(last_error) if last_error else "Execution failed"
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        graph.update_node_status(node_id, PlanStatus.FAILED, error=err_str, duration_ms=elapsed_ms)
        monitor.on_node_failed(node_id, elapsed_ms, is_retry=False)

        event_bus.publish(
            Event(
                event_type="agent.execution.failed",
                source=f"Scheduler.{node_id}",
                payload={"node_id": node_id, "error": err_str},
            )
        )

        if node.mandatory:
            graph.propagate_failure(node_id)

    def _resolve_agent(self, agent_name: str, registry: AgentRegistry) -> Optional[IAgent]:
        """Resolve agent instance from AgentRegistry or ServiceContainer."""
        try:
            if hasattr(registry, "exists") and registry.exists(agent_name):
                return registry.get(agent_name)
            elif hasattr(registry, "has_agent") and registry.has_agent(agent_name):
                return registry.get_agent(agent_name)
        except Exception:
            pass

        container = ServiceContainer.get_global()
        try:
            if container.has_service(agent_name):
                return container.resolve(agent_name)
        except Exception:
            pass

        return None

    def _build_agent_input(self, agent_name: str, context: InvestigationContext) -> Any:
        """Construct input payload tailored to the specific target agent requirements."""
        req = context.request
        if agent_name == "TelemetryAgent":
            return {
                "device_id": req.device_id or "Branch3-Uplink",
                "interface": req.interface or "eth0",
                "metrics": req.parameters.get("metrics", {"bandwidth_utilization": 85.0, "packet_loss": 0.02}),
            }
        elif agent_name == "PredictionAgent":
            telemetry_output = context.get_agent_output("TelemetryAgent")
            return telemetry_output or {"device_id": req.device_id or "Branch3-Uplink", "interface": req.interface or "eth0"}
        elif agent_name == "IncidentAgent":
            prediction_output = context.get_agent_output("PredictionAgent")
            return prediction_output or {"device_id": req.device_id or "Branch3-Uplink", "risk_score": 0.88}
        elif agent_name == "RecommendationAgent":
            incident_output = context.get_agent_output("IncidentAgent")
            return incident_output or {"incident_id": "INC-LOCAL-001", "title": req.operator_query}
        elif agent_name == "KnowledgeAgent":
            rec_output = context.get_agent_output("RecommendationAgent")
            return rec_output or {"query": req.operator_query}
        elif agent_name == "TopologyAgent":
            return {"device_id": req.device_id or "Branch3-Uplink"}
        else:
            return req.parameters or {"query": req.operator_query}

    def _extract_confidence_and_register_evidence(
        self, agent_name: str, output: Any, context: InvestigationContext
    ) -> float:
        """Extract confidence score from agent output and register evidence into EvidenceRegistry."""
        confidence = 0.80
        device_id = context.request.device_id

        if hasattr(output, "confidence"):
            confidence = float(getattr(output, "confidence"))
        elif isinstance(output, dict) and "confidence" in output:
            confidence = float(output["confidence"])

        payload = output.model_dump() if hasattr(output, "model_dump") else (output if isinstance(output, dict) else {"data": str(output)})

        context.evidence_registry.register(
            source_agent=agent_name,
            evidence_type=agent_name.lower().replace("agent", ""),
            payload=payload,
            confidence=confidence,
            device_id=device_id,
        )
        return confidence
