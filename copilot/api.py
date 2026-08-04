from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from .rag import LocalRAG
from .llm import query_copilot_llm

app = FastAPI(title="NOC Copilot RAG & LLM API")

# Initialize Local RAG (loads FAISS index and sentence-transformers)
try:
    rag = LocalRAG()
except Exception as e:
    print(f"Error initializing RAG: {e}. Building mock/empty RAG.")
    rag = None

class CopilotRequest(BaseModel):
    interface: str
    risk_score: float
    time_to_impact: float
    contributing_signals: List[str]

@app.post("/copilot")
def copilot_endpoint(payload: CopilotRequest):
    try:
        # 1. Retrieve relevant runbook and topology documents
        query = f"congestion on interface {payload.interface} " + " ".join(payload.contributing_signals)
        
        retrieved_docs = []
        if rag:
            try:
                retrieved_docs = rag.retrieve(query, k=3)
            except Exception as e:
                print(f"RAG retrieval failed: {e}")
                
        # 2. Query Ollama (or fallback)
        explanation = query_copilot_llm(
            interface=payload.interface,
            risk_score=payload.risk_score,
            time_to_impact=payload.time_to_impact,
            contributing_signals=payload.contributing_signals,
            retrieved_docs=retrieved_docs
        )
        
        # 3. Return explanation along with the sources cited
        return {
            "explanation": explanation,
            "sources": retrieved_docs
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Copilot logic error: {str(e)}")

@app.get("/health")
def health():
    return {"status": "ok"}
