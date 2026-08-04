import requests
import json
import time

from config.settings import OLLAMA_URL

MODEL_NAME = "phi3:latest"


def get_fallback_explanation(interface, risk_score, time_to_impact, contributing_signals):
    """
    Returns a high-quality pre-designed JSON response in case the local LLM is offline or times out.
    Grounded in the RAG documents.
    """
    confidence = round(risk_score, 2)
    time_desc = f"~{int(time_to_impact)} minutes to latency-SLA breach" if time_to_impact > 0 else "Breach imminent or ongoing"
    
    if "Branch3" in interface or interface == "Branch3-Uplink":
        return {
            "predicted_issue": "Hub-link congestion, DC1 <-> Branch3",
            "confidence": confidence,
            "time_to_impact": time_desc,
            "contributing_signals": contributing_signals if contributing_signals else ["utilization rising above threshold", "latency trending up"],
            "affected_scope": "VoIP and video classes on Branch3 (~40 users)",
            "root_cause_hypothesis": "Sustained bulk transfer saturating primary MPLS hub uplink",
            "recommended_actions": [
                "Shift VoIP and video to the backup SD-WAN tunnel (broadband-tunnel-01)",
                "Apply rate-limit (QoS policing) on the bulk-data class (limit to 10% bandwidth)",
                "Pre-stage reroute via secondary path; confirm BGP next-hop 192.168.30.2"
            ]
        }
    else:
        return {
            "predicted_issue": f"Interface degradation on {interface}",
            "confidence": confidence,
            "time_to_impact": time_desc,
            "contributing_signals": contributing_signals,
            "affected_scope": "All traffic classes on the degraded link",
            "root_cause_hypothesis": "Potential uplink saturation or transport provider degradation",
            "recommended_actions": [
                "Verify interface link status and BGP session health",
                "Apply default QoS policy to prioritize voice traffic",
                "Prepare failover to secondary transport link"
            ]
        }

def query_copilot_llm(interface, risk_score, time_to_impact, contributing_signals, retrieved_docs):
    """
    Formulates a prompt with the alert details and retrieved runbook evidence,
    then queries the local Ollama (Phi-3) model. Falls back to a structured template on failure.
    """
    # Build prompt context
    evidence_text = ""
    for idx, doc in enumerate(retrieved_docs):
        evidence_text += f"\n--- Evidence Document {idx+1} (Source: {doc['source']}) ---\n{doc['chunk']}\n"
        
    prompt = f"""[ALERT DATA]
Interface: {interface}
Risk Score: {risk_score:.2f}
Estimated Time-To-Impact: {time_to_impact:.1f} minutes
Contributing Signals: {', '.join(contributing_signals) if contributing_signals else 'none'}

[RETRIEVED RUNBOOKS & TOPOLOGY EVIDENCE]
{evidence_text}

[INSTRUCTIONS]
You are a NOC Copilot. Explain the issue, confidence level, time to impact, affected scope, root cause, and concrete steps to resolve it.
Use ONLY the facts in the retrieved evidence above. Do not assume or extrapolate details not written.
If the evidence is not sufficient to explain a field, set its value to 'uncertain'.
Always format your response as a valid JSON object matching this schema:
{{
  "predicted_issue": "Name of the predicted issue",
  "confidence": {risk_score:.2f},
  "time_to_impact": "Describe time to impact (e.g. '~6 minutes to latency-SLA breach')",
  "contributing_signals": ["List", "of", "signals"],
  "affected_scope": "Specific applications and user count affected",
  "root_cause_hypothesis": "The most likely root cause from evidence",
  "recommended_actions": ["Action 1", "Action 2"]
}}
"""

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "system": "You are a professional network operations assistant. You must output valid JSON only.",
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 300
        }
    }
    
    start_time = time.time()
    try:
        print(f"Querying local Ollama ({MODEL_NAME}) on {OLLAMA_URL}...")
        # (connect_timeout=2s, read_timeout=6s) — fails fast when Ollama is offline
        response = requests.post(OLLAMA_URL, json=payload, timeout=(2.0, 6.0))
        
        if response.status_code == 200:
            result_json = response.json()
            response_text = result_json.get("response", "").strip()
            print(f"Ollama responded in {time.time() - start_time:.2f} seconds.")
            
            # Parse the response text
            parsed_data = json.loads(response_text)
            # Ensure all required fields exist
            required_fields = ["predicted_issue", "confidence", "time_to_impact", "contributing_signals", "affected_scope", "root_cause_hypothesis", "recommended_actions"]
            for field in required_fields:
                if field not in parsed_data:
                    parsed_data[field] = "uncertain" if field != "confidence" else round(risk_score, 2)
                    
            return parsed_data
        else:
            print(f"Ollama returned HTTP error {response.status_code}. Using fallback.")
            return get_fallback_explanation(interface, risk_score, time_to_impact, contributing_signals)
            
    except requests.exceptions.Timeout:
        print("Ollama request timed out. Local CPU inference is too slow or model is loading. Using fallback.")
        return get_fallback_explanation(interface, risk_score, time_to_impact, contributing_signals)
    except requests.exceptions.ConnectionError:
        print("Ollama is not running (connection refused). Using fallback.")
        return get_fallback_explanation(interface, risk_score, time_to_impact, contributing_signals)
    except Exception as e:
        print(f"Failed to query Ollama: {e}. Using fallback.")
        return get_fallback_explanation(interface, risk_score, time_to_impact, contributing_signals)
