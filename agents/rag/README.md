# Enterprise CAG + RAG Intelligence Engine — Sprint 11

## Overview

The **Enterprise Context-Augmented Generation (CAG) + Retrieval-Augmented Generation (RAG) Subsystem** (`agents/rag/`) transforms NOC Copilot into a production-ready AI reasoning engine.

It merges live operational telemetry, risk predictions, active incident details, remediation plans, and topology graph analysis (CAG) with enterprise knowledge runbooks, vendor documentation, and historical incident memory (Hybrid RAG).

---

## Target Pipeline Architecture

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
TopologyAgent
    │ topology.analysis.completed
    ▼
ContextBuilder (CAG) ──► HybridRetriever (RAG) ──► Reranker ──► ContextQuality ──► PromptAssembler
                                                                                            │
                                                                                            ▼
                                                                                   KnowledgeAgent
                                                                                            │
                                                                                            ▼
                                                                                     OllamaProvider (Qwen)
```

---

## Subsystem Package Structure

```
agents/rag/
├── __init__.py                Subsystem exports
├── models.py                  Strongly typed Pydantic V2 domain models
├── interfaces.py              Formal Abstract Base Classes (interfaces)
├── document_loader.py         Multi-format document loader (MD, TXT, JSON, YAML, HTML, PDF, DOCX)
├── document_chunker.py        Intelligent chunker (Heading-Aware, Paragraph, Fixed-Size)
├── embedding_provider.py      TF-IDF (100% offline), SentenceTransformers, Ollama, OpenAI, BGE, Nomic
├── embedding_factory.py       Dynamic embedding provider factory
├── vector_store.py            Persistent SQLite + NumPy cosine similarity VectorStore
├── vector_store_factory.py    Dynamic VectorStore factory
├── keyword_index.py           BM25 sparse keyword search engine
├── retrieval_cache.py         LRU/TTL cache with statistics & invalidation
├── hybrid_retriever.py        Dense + BM25 Reciprocal Rank Fusion (RRF) retriever
├── reranker.py                Multi-factor semantic reranking engine
├── context_builder.py         Context-Augmented Generation (CAG) operational state builder
├── context_quality.py         Context quality & evidence sufficiency evaluator
├── prompt_assembler.py        Token-budgeted prompt assembler with compression
├── citations.py               Structured evidence citation generator
├── index_manager.py           Incremental file change scanner & indexer
├── rag_service.py             Central RAG business logic service
├── rag_agent.py               BaseAgent subclass emitting sub-step EventBus events
└── README.md                  This documentation
```

---

## Detailed Components

### 1. Domain Models (`models.py`)
Provides Pydantic V2 models:
- `Document`: Raw document metadata and content.
- `DocumentChunk`: Segmented chunk with breadcrumb headings and lineage.
- `RetrievalResult`: Ranked candidate match with dense, sparse, and rerank scores.
- `Citation`: Traceable evidence attribution (source, section, snippet, score).
- `CAGContext`: Unified multi-agent operational state.
- `ContextQuality`: Quality evaluation score, status, and missing evidence warnings.
- `PromptPackage`: Assembled prompt text, system prompt, token budget, and citations.
- `RAGResult`: End-to-end output payload.

### 2. Document Loader & Intelligent Chunker (`document_loader.py`, `document_chunker.py`)
Parses Markdown, Text, JSON, YAML, HTML, PDF, and DOCX files. Preserves heading breadcrumb hierarchies (`# Section > ## Subsection`) and supports overlap and lineage tracking.

### 3. Embedding Providers (`embedding_provider.py`, `embedding_factory.py`)
- `TFIDFEmbeddingProvider`: 100% offline, zero-dependency 256-dimensional feature hashing provider.
- `OllamaEmbeddingProvider`: Ollama HTTP API embeddings (`/api/embeddings`).
- `SentenceTransformersEmbeddingProvider`: HuggingFace `sentence-transformers` integration.
- `OpenAIEmbeddingProvider`, `BGEEmbeddingProvider`, `NomicEmbeddingProvider`.

### 4. Enterprise Vector Store & BM25 Keyword Index (`vector_store.py`, `keyword_index.py`)
- `SQLiteVectorStore`: Thread-safe, persistent SQLite database storing float vector blobs and metadata. Calculates NumPy cosine similarity.
- `KeywordIndex`: BM25 term frequency normalization and inverse document frequency (IDF) index with metadata filtering.

### 5. Hybrid Retrieval & Semantic Reranking (`hybrid_retriever.py`, `reranker.py`)
- `HybridRetriever`: Combines Dense Vector Search and BM25 Sparse Search using **Reciprocal Rank Fusion (RRF)**:
  $$\text{RRF\_Score}(d) = w_{\text{dense}} \cdot \frac{1}{k + \text{rank}_{\text{dense}}(d)} + w_{\text{sparse}} \cdot \frac{1}{k + \text{rank}_{\text{sparse}}(d)}$$
- `Reranker`: Computes multi-factor score:
  $$\text{Score} = w_1 \cdot \text{Similarity} + w_2 \cdot \text{DeviceRel} + w_3 \cdot \text{IncRel} + w_4 \cdot \text{TopRel} + w_5 \cdot \text{Freshness}$$

### 6. CAG Context Builder & Quality Engine (`context_builder.py`, `context_quality.py`)
- `ContextBuilder`: Collects live state across `TelemetryAgent`, `PredictionAgent`, `IncidentAgent`, `RecommendationAgent`, `TopologyAgent`, and `ExecutionContext`.
- `ContextQualityEvaluator`: Evaluates completeness, relevance, diversity, and freshness. Flags `is_sufficient=False` if quality is below minimum threshold (0.40).

### 7. Prompt Assembler & Citations (`prompt_assembler.py`, `citations.py`)
- `PromptAssembler`: Constructs structured prompt string with token budgeting (~4 chars/token). Dynamically compresses context if budget is exceeded.
- `CitationGenerator`: Formats structured evidence citations with source file, section header, relevance score, and text snippet.

---

## Developer Guide & Usage Examples

### 1. Register RAGAgent

```python
from agents.rag import register_rag_agent

rag_agent = register_rag_agent()
rag_agent.initialize()
```

### 2. Direct RAG Service Execution

```python
from agents.rag import RAGService

service = RAGService()

# Index enterprise documentation folder
service.index_manager.index_directory("copilot/docs")

# Build context package for a query/device
package = service.build_context_package(
    query="How do I troubleshoot WAN router interface degradation?",
    device_id="rtr-01"
)

print(f"Context Quality: {package.quality.quality_score} ({package.quality.status.value})")
print(f"Retrieved Chunks: {len(package.retrieved_results)}")
print(f"Citations: {len(package.citations)}")
```

---

## EventBus Subscriptions & Emissions

| Trigger Event | Subscribed By | Emitted Event | Description |
|---------------|---------------|---------------|-------------|
| `knowledge.requested` / `rag.requested` | `RAGAgent` | `context.build.started` | Initiates CAG state aggregation |
| — | `RAGAgent` | `retrieval.started` | Triggers hybrid search |
| — | `RAGAgent` | `reranking.completed` | Candidate reranking finished |
| — | `RAGAgent` | `context.quality.completed` | Context quality evaluated |
| — | `RAGAgent` | `prompt.assembled` | Token budget prompt constructed |
| — | `RAGAgent` | `rag.context.ready` | `ContextPackage` ready for `KnowledgeAgent` |
| — | `RAGAgent` | `rag.completed` | RAG execution finished |

---

## Future Roadmap

| Feature | Description |
|---------|-------------|
| GraphRAG Integration | Knowledge graph entity extraction and multi-hop relationship traversal |
| FAISS / Qdrant Backend | Native C++ GPU/CPU vector index backends for >1M documents |
| Streaming RAG Response | SSE/WebSocket token streaming with real-time citation popups |
| Adaptive Chunking | LLM-assisted semantic boundary chunking |
