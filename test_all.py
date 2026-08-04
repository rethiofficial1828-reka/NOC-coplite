import os
import sys
import unittest
import pandas as pd
import numpy as np

# Add the noc-copilot folder directly to the Python path
# This allows importing engine, copilot, and faultsim directly, bypassing the dash in 'noc-copilot'
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(project_root, "noc-copilot"))

class TestNocCopilot(unittest.TestCase):
    
    def test_01_imports(self):
        """Verify that all core modules can be imported without errors."""
        try:
            import faultsim.generate_dataset as generate_dataset
            import faultsim.inject_fault as inject_fault
            import engine.features as features
            import engine.model as model
            import engine.api as api
            import copilot.rag as rag
            import copilot.llm as llm
            import copilot.api as copilot_api
            print("  [PASS] All modules successfully imported.")
        except ImportError as e:
            self.fail(f"Module import failed: {e}")

    def test_02_feature_extraction(self):
        """Verify feature extraction logic on mock telemetry."""
        from engine.features import extract_features_from_df
        
        # Create a mock telemetry window of 30 samples (60 seconds)
        mock_data = pd.DataFrame({
            "utilization": np.linspace(40.0, 80.0, 30),
            "latency": np.linspace(20.0, 100.0, 30),
            "jitter": np.linspace(2.0, 10.0, 30),
            "drops": np.zeros(30),
            "routing_flaps": np.zeros(30)
        })
        
        features = extract_features_from_df(mock_data)
        
        # Assertions
        self.assertIn("utilization_current", features)
        self.assertIn("latency_slope_60s", features)
        self.assertIn("utilization_delta_baseline", features)
        self.assertEqual(features["utilization_current"], 80.0)
        self.assertEqual(features["latency_current"], 100.0)
        self.assertTrue(features["utilization_slope_60s"] > 0) # Slope should be positive
        print("  [PASS] Feature extraction verified.")

    def test_03_risk_predictor(self):
        """Verify RiskPredictor predicts risk and time-to-impact without errors."""
        from engine.model import RiskPredictor
        
        predictor = RiskPredictor()
        
        # Mock telemetry
        mock_data = pd.DataFrame({
            "utilization": np.linspace(50.0, 92.0, 30),
            "latency": np.linspace(20.0, 140.0, 30),
            "jitter": np.linspace(3.0, 12.0, 30),
            "drops": np.zeros(30),
            "routing_flaps": np.zeros(30)
        })
        
        result = predictor.predict(mock_data)
        
        # Assertions
        self.assertIn("risk_score", result)
        self.assertIn("time_to_impact", result)
        self.assertIn("contributing_signals", result)
        self.assertTrue(0.0 <= result["risk_score"] <= 1.0)
        self.assertTrue(result["time_to_impact"] > 0 or result["time_to_impact"] == -1.0)
        print("  [PASS] Risk predictor calculations verified.")

    def test_04_rag_retrieval(self):
        """Verify local RAG index loading and query retrieval."""
        from copilot.rag import LocalRAG
        
        rag = LocalRAG()
        results = rag.retrieve("congestion mitigation on Branch3 Link", k=2)
        
        # Assertions
        self.assertTrue(len(results) > 0)
        for doc in results:
            self.assertIn("chunk", doc)
            self.assertIn("source", doc)
            self.assertIn("score", doc)
        print("  [PASS] RAG retrieval verified.")

    def test_05_llm_query_and_fallback(self):
        """Verify LLM query engine produces a structured JSON output."""
        from copilot.llm import query_copilot_llm
        
        retrieved_docs = [
            {"chunk": "Direct primary link between Branch3 and DC1", "source": "network_topology.txt", "score": 0.9}
        ]
        
        explanation = query_copilot_llm(
            interface="Branch3-Uplink",
            risk_score=0.8,
            time_to_impact=6.0,
            contributing_signals=["utilization rising 0.45%/sample"],
            retrieved_docs=retrieved_docs
        )
        
        # Assertions
        self.assertIn("predicted_issue", explanation)
        self.assertIn("confidence", explanation)
        self.assertIn("affected_scope", explanation)
        self.assertIn("recommended_actions", explanation)
        self.assertEqual(explanation["confidence"], 0.8)
        self.assertTrue(isinstance(explanation["recommended_actions"], list))
        print("  [PASS] LLM query/fallback structured schema verified.")

if __name__ == "__main__":
    print("=== Running NOC Copilot Codebase Test Suite ===")
    unittest.main()
