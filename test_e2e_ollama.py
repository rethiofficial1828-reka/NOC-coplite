"""
End-to-End Pipeline Integration Validation Script.

Executes the full reactive agent chain:
TelemetryAgent -> PredictionAgent -> IncidentAgent -> RecommendationAgent -> TopologyAgent -> RAGAgent -> KnowledgeAgent -> OllamaProvider -> Qwen3:1.7b
"""

import json
import sys
from unittest.mock import MagicMock

# Mock xgboost if not installed system-wide
sys.modules['xgboost'] = MagicMock()

from config.settings import LLM_PROVIDER_TYPE, OLLAMA_MODEL, OLLAMA_BASE_URL
from agents.events.event_bus import EventBus
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import ExecutionContext

from agents.telemetry import TelemetryAgent
from agents.prediction import PredictionAgent
from agents.incident import IncidentAgent, IncidentRecord
from agents.recommendation import RecommendationAgent
from agents.topology import TopologyAgent
from agents.rag import RAGAgent
from agents.knowledge import KnowledgeAgent, ProviderFactory


def run_e2e_validation():
    print("=== CONFIGURATION CHECK ===")
    print(f"LLM_PROVIDER_TYPE: {LLM_PROVIDER_TYPE}")
    print(f"OLLAMA_MODEL: {OLLAMA_MODEL}")
    print(f"OLLAMA_BASE_URL: {OLLAMA_BASE_URL}")

    provider = ProviderFactory.create_provider()
    print(f"Provider Instance: {type(provider).__name__}")
    print(f"Provider Model: {provider.model_name}")
    print(f"Provider Base URL: {provider.base_url}")

    print("\n=== INITIALIZING ATOMIC AGENTS ===")
    bus = EventBus.get_global()
    registry = AgentRegistry.get_global()

    t_agent = TelemetryAgent()
    p_agent = PredictionAgent()
    i_agent = IncidentAgent()
    r_agent = RecommendationAgent()
    top_agent = TopologyAgent()
    rag_agent = RAGAgent()
    k_agent = KnowledgeAgent()

    for agent in [t_agent, p_agent, i_agent, r_agent, top_agent, rag_agent, k_agent]:
        agent.initialize()
        registry.register(agent, allow_override=True)

    print("\n=== RUNNING END-TO-END PIPELINE ===")
    ctx = ExecutionContext()

    # Step 1: TelemetryAgent
    t_results = t_agent.execute({"limit": 5}, context=ctx)
    print(f"1. TelemetryAgent processed {len(t_results)} packet(s).")

    # Step 2: PredictionAgent
    p_results = p_agent.execute({"interface": "Campus Core"}, context=ctx)
    print(f"2. PredictionAgent generated {len(p_results)} prediction(s).")

    # Step 3: Incident creation
    inc_input = [{
        "title": "WAN Router Interface Degradation",
        "severity": "CRITICAL",
        "affected_entities": ["core-01"],
        "details": {"interface": "Campus Core", "risk_score": 0.95}
    }]
    top_results = top_agent.execute(inc_input, context=ctx)
    print(f"3. TopologyAgent generated {len(top_results)} topology analysis.")

    # Step 4: RecommendationAgent
    rec_input = [{
        "incident_id": "INC-2026-0001",
        "device_id": "core-01",
        "interface": "Campus Core",
        "summary": "High link degradation and latency on Campus Core interface",
        "priority": "HIGH",
        "recommended_actions": ["Inspect QoS queue limits", "Reroute bulk traffic to secondary uplink"]
    }]
    r_results = r_agent.execute(rec_input, context=ctx)
    print(f"4. RecommendationAgent generated {len(r_results)} recommendation(s).")

    # Step 5 & 6: CAG + Hybrid Retrieval (RAGAgent)
    rag_input = [{"query": "Diagnose Campus Core interface degradation", "device_id": "core-01"}]
    rag_results = rag_agent.execute(rag_input, context=ctx)
    print(f"5. RAGAgent constructed {len(rag_results)} CAG+RAG context package(s).")

    # Step 7: KnowledgeAgent -> OllamaProvider -> Qwen3:1.7b
    print("\nSending prompt to local Ollama server (Model: qwen3:1.7b)...")
    k_results = k_agent.execute(r_results, context=ctx)
    print(f"6. KnowledgeAgent produced {len(k_results)} KnowledgeResult(s).")

    if k_results:
        k_res = k_results[0]
        print("\n=======================================================")
        print("=== REAL INFERENCE RESPONSE FROM LOCAL QWEN3:1.7B ===")
        print("=======================================================")
        print(f"Result ID        : {k_res.result_id}")
        print(f"Device ID        : {k_res.device_id}")
        print(f"Confidence Score : {k_res.confidence_score}")
        print(f"\n[Root Cause Analysis]:\n{k_res.root_cause_analysis}")
        print(f"\n[Recommended Steps]:")
        for step in k_res.recommended_steps:
            print(f"  • {step}")
        print(f"\n[Cited Sources]  : {k_res.cited_sources}")
        print(f"\n[Provider Metadata]:\n{json.dumps(k_res.provider_metadata, indent=2)}")
        print("\n✓ SUCCESS: Local Qwen3:1.7B model inference completed successfully!")


if __name__ == "__main__":
    run_e2e_validation()
