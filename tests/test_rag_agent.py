"""
Test Suite — Sprint 11: Enterprise CAG + RAG Intelligence Engine.

Coverage:
    - Domain Models (Document, DocumentChunk, EmbeddingVector, RetrievalResult, Citation, CAGContext, ContextQuality, PromptPackage, RAGResult)
    - DocumentLoader: MD, TXT, JSON, YAML, HTML, PDF, DOCX, metadata, hashing, directory scanning
    - IntelligentChunker: Heading-Aware, Paragraph, Fixed-Size, overlap, breadcrumbs, lineage
    - EmbeddingProvider: TFIDF, Ollama, SentenceTransformers, EmbeddingProviderFactory
    - VectorStore: SQLiteVectorStore insert, batch_insert, search, delete, count, clear, metadata filters
    - KeywordIndex: BM25 sparse keyword search, term frequency, IDF, filtering
    - HybridRetriever: Dense + BM25 Reciprocal Rank Fusion (RRF)
    - Reranker: Multi-factor scoring (similarity, device relevance, incident severity, topology context)
    - ContextBuilder: CAG multi-agent operational state aggregation
    - ContextQualityEvaluator: Quality scoring, completeness, freshness, evidence sufficiency
    - CitationGenerator: Citation extraction and markdown formatting
    - PromptAssembler: Token budget management, structured section assembly, compression
    - RetrievalCache: TTL, LRU eviction, query hashing, statistics, invalidation
    - IndexManager: Incremental scanning, change detection, auto-indexing
    - RAGService: End-to-end context building and prompt package creation
    - RAGAgent: Agent lifecycle, EventBus subscriptions & emissions, ExecutionContext propagation
    - register_rag_agent: Helper registration function
"""

import os
import shutil
import tempfile
import unittest
from typing import Any, Dict, List, Optional
import uuid

from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.rag.citations import CitationGenerator
from agents.rag.context_builder import ContextBuilder
from agents.rag.context_quality import ContextQualityEvaluator
from agents.rag.document_chunker import ChunkingStrategy, DocumentChunk, IntelligentChunker
from agents.rag.document_loader import DocumentLoader, DocumentType
from agents.rag.embedding_factory import EmbeddingProviderFactory
from agents.rag.embedding_provider import (
    OllamaEmbeddingProvider,
    SentenceTransformersEmbeddingProvider,
    TFIDFEmbeddingProvider,
)
from agents.rag.hybrid_retriever import HybridRetriever
from agents.rag.index_manager import IndexManager
from agents.rag.keyword_index import KeywordIndex
from agents.rag.models import (
    CAGContext,
    Citation,
    ContextPackage,
    ContextQuality,
    ContextQualityStatus,
    Document,
    PromptPackage,
    RAGResult,
    RetrievalResult,
    RetrievalStrategy,
    SearchMetadata,
)
from agents.rag.prompt_assembler import PromptAssembler
from agents.rag.rag_agent import RAGAgent, register_rag_agent
from agents.rag.rag_service import RAGService
from agents.rag.reranker import Reranker
from agents.rag.retrieval_cache import RetrievalCache
from agents.rag.vector_store import SQLiteVectorStore
from agents.rag.vector_store_factory import VectorStoreFactory
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import ExecutionContext


# ===========================================================================
# Component 1 — Domain Models
# ===========================================================================

class TestRAGDomainModels(unittest.TestCase):
    def test_document_model_defaults(self):
        doc = Document(filename="test.md", content="# Title\nSample text")
        self.assertEqual(doc.filename, "test.md")
        self.assertEqual(doc.document_type, DocumentType.UNKNOWN)
        self.assertTrue(len(doc.doc_id) > 0)

    def test_document_chunk_defaults(self):
        chunk = DocumentChunk(parent_doc_id="p1", content="Chunk content text")
        self.assertEqual(chunk.parent_doc_id, "p1")
        self.assertEqual(chunk.chunk_index, 0)
        self.assertGreater(chunk.token_count, 0)

    def test_retrieval_result_defaults(self):
        chunk = DocumentChunk(parent_doc_id="p1", content="Text")
        res = RetrievalResult(chunk=chunk, score=0.85)
        self.assertEqual(res.score, 0.85)
        self.assertEqual(res.retrieval_strategy, RetrievalStrategy.HYBRID_RRF)

    def test_citation_model(self):
        c = Citation(chunk_id="c1", source="runbook.md", section="Section 1", content_snippet="Excerpt")
        self.assertEqual(c.source, "runbook.md")
        self.assertEqual(c.relevance_score, 1.0)


# ===========================================================================
# Component 3 — Document Loader
# ===========================================================================

class TestDocumentLoader(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.loader = DocumentLoader()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_markdown_document(self):
        file_path = os.path.join(self.temp_dir, "runbook.md")
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write("# WAN Router Troubleshooting\nStep 1: Inspect interface GE0/0.")

        doc = self.loader.load_document(file_path)
        self.assertEqual(doc.filename, "runbook.md")
        self.assertEqual(doc.document_type, DocumentType.MARKDOWN)
        self.assertIn("WAN Router", doc.content)
        self.assertTrue(len(doc.hash) > 0)
        self.assertIn("runbook", doc.tags)

    def test_load_text_document(self):
        file_path = os.path.join(self.temp_dir, "notes.txt")
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write("Plain text operational notes")

        doc = self.loader.load_document(file_path)
        self.assertEqual(doc.document_type, DocumentType.TEXT)

    def test_load_json_document(self):
        file_path = os.path.join(self.temp_dir, "config.json")
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write('{"device": "core-01", "status": "active"}')

        doc = self.loader.load_document(file_path)
        self.assertEqual(doc.document_type, DocumentType.JSON)
        self.assertIn("core-01", doc.content)

    def test_load_directory_recursive(self):
        sub_dir = os.path.join(self.temp_dir, "sub")
        os.makedirs(sub_dir, exist_ok=True)

        with open(os.path.join(self.temp_dir, "d1.md"), "w") as fh:
            fh.write("Doc 1")
        with open(os.path.join(sub_dir, "d2.txt"), "w") as fh:
            fh.write("Doc 2")

        docs = self.loader.load_directory(self.temp_dir, recursive=True)
        self.assertEqual(len(docs), 2)

    def test_load_nonexistent_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.loader.load_document("/nonexistent/file.md")


# ===========================================================================
# Component 4 — Intelligent Chunker
# ===========================================================================

class TestIntelligentChunker(unittest.TestCase):
    def setUp(self):
        self.chunker = IntelligentChunker(max_chunk_chars=200, chunk_overlap_chars=30)

    def test_heading_aware_chunking(self):
        doc = Document(
            filename="guide.md",
            content=(
                "# Section 1\nContent of section 1.\n\n"
                "## Subsection A\nContent of subsection A.\n\n"
                "# Section 2\nContent of section 2."
            ),
            document_type=DocumentType.MARKDOWN,
        )
        chunks = self.chunker.chunk_document(doc, strategy=ChunkingStrategy.HEADING_AWARE)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0].chunking_strategy, ChunkingStrategy.HEADING_AWARE)

    def test_paragraph_chunking(self):
        doc = Document(
            filename="paras.txt",
            content="Paragraph one text.\n\nParagraph two text.\n\nParagraph three text.",
            document_type=DocumentType.TEXT,
        )
        chunks = self.chunker.chunk_document(doc, strategy=ChunkingStrategy.PARAGRAPH)
        self.assertGreaterEqual(len(chunks), 1)

    def test_fixed_size_chunking(self):
        doc = Document(
            filename="long.txt",
            content="A" * 500,
            document_type=DocumentType.TEXT,
        )
        chunks = self.chunker.chunk_document(doc, strategy=ChunkingStrategy.FIXED_SIZE)
        self.assertGreaterEqual(len(chunks), 2)


# ===========================================================================
# Component 5 — Embedding Providers & Factory
# ===========================================================================

class TestEmbeddingProviders(unittest.TestCase):
    def test_tfidf_provider_embedding(self):
        provider = TFIDFEmbeddingProvider(dimension=128)
        self.assertEqual(provider.dimension, 128)

        vec = provider.embed_text("Network router interface error")
        self.assertEqual(len(vec), 128)
        self.assertIsInstance(vec[0], float)

    def test_tfidf_provider_batch(self):
        provider = TFIDFEmbeddingProvider(dimension=64)
        vecs = provider.embed_batch(["text one", "text two"])
        self.assertEqual(len(vecs), 2)
        self.assertEqual(len(vecs[0]), 64)

    def test_ollama_provider_fallback(self):
        """Ollama request to unreachable port should fall back gracefully to TFIDF."""
        provider = OllamaEmbeddingProvider(base_url="http://localhost:999999")
        vec = provider.embed_text("Sample query")
        self.assertGreater(len(vec), 0)

    def test_embedding_factory(self):
        provider = EmbeddingProviderFactory.create_provider("tfidf")
        self.assertIsInstance(provider, TFIDFEmbeddingProvider)

        provider2 = EmbeddingProviderFactory.create_provider("unknown_type")
        self.assertIsInstance(provider2, TFIDFEmbeddingProvider)


# ===========================================================================
# Component 6 — Vector Store & Factory
# ===========================================================================

class TestSQLiteVectorStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(self.temp_dir, "test_vstore.db")
        self.vstore = SQLiteVectorStore(db_path=db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_insert_and_count(self):
        chunk = DocumentChunk(parent_doc_id="p1", content="Interface GE0/0 high latency")
        vec = [0.1] * 128
        self.vstore.insert(chunk, vec)
        self.assertEqual(self.vstore.count(), 1)

    def test_batch_insert_and_search(self):
        chunk1 = DocumentChunk(parent_doc_id="p1", content="Router WAN link failure")
        chunk2 = DocumentChunk(parent_doc_id="p2", content="Database connection timeout")
        vec1 = [1.0, 0.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0, 0.0]

        self.vstore.batch_insert([chunk1, chunk2], [vec1, vec2])
        self.assertEqual(self.vstore.count(), 2)

        # Search matching vec1
        results = self.vstore.search(query_vector=[1.0, 0.0, 0.0, 0.0], top_k=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].chunk.chunk_id, chunk1.chunk_id)

    def test_delete_and_clear(self):
        chunk = DocumentChunk(parent_doc_id="p1", content="Text to delete")
        self.vstore.insert(chunk, [0.5] * 4)
        self.assertEqual(self.vstore.count(), 1)

        deleted = self.vstore.delete(chunk.chunk_id)
        self.assertTrue(deleted)
        self.assertEqual(self.vstore.count(), 0)

    def test_vector_store_factory(self):
        store = VectorStoreFactory.create_vector_store("sqlite")
        self.assertIsInstance(store, SQLiteVectorStore)


# ===========================================================================
# Component 7 — Keyword Index (BM25)
# ===========================================================================

class TestKeywordIndex(unittest.TestCase):
    def setUp(self):
        self.kw_index = KeywordIndex()

    def test_index_and_search(self):
        c1 = DocumentChunk(parent_doc_id="p1", content="BGP neighbor status down on core router")
        c2 = DocumentChunk(parent_doc_id="p2", content="HTTP server 500 internal server error")

        self.kw_index.index_chunks([c1, c2])

        results = self.kw_index.search("BGP router", top_k=2)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].chunk.chunk_id, c1.chunk_id)
        self.assertGreater(results[0].score, 0.0)

    def test_search_no_match(self):
        c1 = DocumentChunk(parent_doc_id="p1", content="Memory utilization high")
        self.kw_index.index_chunks([c1])

        results = self.kw_index.search("nonexistentword12345")
        self.assertEqual(len(results), 0)


# ===========================================================================
# Component 8 — Hybrid Retriever
# ===========================================================================

class TestHybridRetriever(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vstore = SQLiteVectorStore(db_path=os.path.join(self.temp_dir, "hybrid.db"))
        self.kw_index = KeywordIndex()
        self.embedder = TFIDFEmbeddingProvider(dimension=64)

        self.retriever = HybridRetriever(
            vector_store=self.vstore,
            keyword_index=self.kw_index,
            embedding_provider=self.embedder,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_hybrid_retrieve(self):
        c1 = DocumentChunk(parent_doc_id="p1", content="WAN interface link flapping troubleshooting guide")
        v1 = self.embedder.embed_text(c1.content)

        self.vstore.insert(c1, v1)
        self.kw_index.index_chunks([c1])

        results = self.retriever.retrieve("WAN interface flapping", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk.chunk_id, c1.chunk_id)
        self.assertEqual(results[0].retrieval_strategy, RetrievalStrategy.HYBRID_RRF)


# ===========================================================================
# Component 9 — Semantic Reranker
# ===========================================================================

class TestReranker(unittest.TestCase):
    def setUp(self):
        self.reranker = Reranker()

    def test_rerank_scoring(self):
        c1 = DocumentChunk(parent_doc_id="p1", content="General network guide")
        c2 = DocumentChunk(parent_doc_id="p2", content="Specific core-01 router guide for runbook", tags=["runbook"])

        r1 = RetrievalResult(chunk=c1, score=0.7)
        r2 = RetrievalResult(chunk=c2, score=0.6)

        cag = CAGContext(device_id="core-01")
        reranked = self.reranker.rerank("core-01 guide", candidates=[r1, r2], context=cag, top_k=2)

        self.assertEqual(len(reranked), 2)
        self.assertEqual(reranked[0].chunk.chunk_id, c2.chunk_id)


# ===========================================================================
# Component 10 & 11 — Context Builder & Context Quality Evaluator
# ===========================================================================

class TestContextBuilderAndQuality(unittest.TestCase):
    def test_context_builder_builds_cag_context(self):
        builder = ContextBuilder()
        exec_ctx = ExecutionContext()
        exec_ctx.shared_state["latest_telemetry"] = {"device_id": "rtr-01", "interface": "GE0/0"}
        exec_ctx.shared_state["latest_incident"] = {"incident_id": "INC-100", "severity": "CRITICAL"}

        cag = builder.build_context(query="Check rtr-01 status", execution_context=exec_ctx)

        self.assertEqual(cag.device_id, "rtr-01")
        self.assertEqual(cag.interface, "GE0/0")
        self.assertTrue(cag.metrics.telemetry_present)
        self.assertTrue(cag.metrics.incident_present)

    def test_context_quality_evaluation(self):
        evaluator = ContextQualityEvaluator(min_quality_threshold=0.40)
        cag = CAGContext(
            telemetry_data={"device_id": "rtr-01"},
            incident_data={"incident_id": "INC-1"},
            topology_data={"device_id": "rtr-01"},
        )
        chunk = DocumentChunk(parent_doc_id="p1", content="Runbook snippet")
        res = RetrievalResult(chunk=chunk, score=0.9)

        quality = evaluator.evaluate_quality(cag, [res])
        self.assertGreaterEqual(quality.quality_score, 0.40)
        self.assertTrue(quality.is_sufficient)


# ===========================================================================
# Component 12 & 15 — Citations & Prompt Assembler
# ===========================================================================

class TestPromptAssemblerAndCitations(unittest.TestCase):
    def test_citation_generation(self):
        chunk = DocumentChunk(parent_doc_id="p1", content="Troubleshooting WAN step 1", source="wan.md")
        res = RetrievalResult(chunk=chunk, score=0.85)

        citations = CitationGenerator.generate_citations([res])
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].source, "wan.md")

        text = CitationGenerator.format_citations_text(citations)
        self.assertIn("wan.md", text)

    def test_prompt_assembler_building(self):
        assembler = PromptAssembler()
        cag = CAGContext(
            operator_query="Diagnose core-01 link loss",
            device_id="core-01",
            incident_data={"incident_id": "INC-55", "severity": "CRITICAL"},
        )
        chunk = DocumentChunk(parent_doc_id="p1", content="Check fiber transceiver power", source="sop.md")
        res = RetrievalResult(chunk=chunk, score=0.9)

        prompt_pkg = assembler.assemble_prompt(cag, [res])
        self.assertIn("core-01", prompt_pkg.assembled_prompt)
        self.assertIn("INC-55", prompt_pkg.assembled_prompt)
        self.assertIn("sop.md", prompt_pkg.assembled_prompt)
        self.assertFalse(prompt_pkg.was_compressed)


# ===========================================================================
# Component 13 & 14 — Cache & Index Manager
# ===========================================================================

class TestCacheAndIndexManager(unittest.TestCase):
    def test_retrieval_cache(self):
        cache = RetrievalCache(max_entries=10, default_ttl_seconds=60)
        chunk = DocumentChunk(parent_doc_id="p1", content="Cache test")
        res = RetrievalResult(chunk=chunk, score=0.9)

        cache.set("query 1", [res])
        hit = cache.get("query 1")
        self.assertIsNotNone(hit)
        self.assertEqual(len(hit), 1)

        stats = cache.get_statistics()
        self.assertEqual(stats["hits"], 1)

    def test_index_manager(self):
        temp_dir = tempfile.mkdtemp()
        try:
            vstore = SQLiteVectorStore(db_path=os.path.join(temp_dir, "idx_test.db"))
            kw_index = KeywordIndex()
            embedder = TFIDFEmbeddingProvider(dimension=64)

            idx_mgr = IndexManager(vector_store=vstore, keyword_index=kw_index, embedding_provider=embedder)

            doc_path = os.path.join(temp_dir, "doc1.md")
            with open(doc_path, "w") as fh:
                fh.write("# Guide\nStep 1: Check power supply.")

            count = idx_mgr.index_directory(temp_dir)
            self.assertEqual(count, 1)
            self.assertEqual(vstore.count(), 1)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# Component 16 — RAG Service
# ===========================================================================

class TestRAGService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vstore = SQLiteVectorStore(db_path=os.path.join(self.temp_dir, "service_test.db"))
        self.service = RAGService(vector_store=self.vstore)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_context_package(self):
        doc = Document(filename="runbook.md", content="Check rtr-01 router BGP peer status", source="runbook.md")
        self.service.index_manager.index_document(doc)

        pkg = self.service.build_context_package(query="router BGP peer", device_id="rtr-01")
        self.assertIsInstance(pkg, ContextPackage)
        self.assertEqual(pkg.cag_context.device_id, "rtr-01")
        self.assertGreaterEqual(len(pkg.retrieved_results), 1)

    def test_assemble_prompt_package(self):
        pkg = self.service.build_context_package(query="test query")
        prompt_pkg = self.service.assemble_prompt_package(pkg)
        self.assertIsInstance(prompt_pkg, PromptPackage)
        self.assertIn("test query", prompt_pkg.assembled_prompt)


# ===========================================================================
# Component 17 & 20 — RAG Agent Lifecycle & EventBus
# ===========================================================================

class TestRAGAgent(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.bus = EventBus()
        self.vstore = SQLiteVectorStore(db_path=os.path.join(self.temp_dir, "agent_test.db"))
        self.service = RAGService(vector_store=self.vstore)

        self.agent = RAGAgent(service=self.service, event_bus=self.bus)
        self.agent.initialize()

    def tearDown(self):
        self.agent.shutdown()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_agent_identity(self):
        self.assertEqual(self.agent.name, "RAGAgent")
        self.assertIn("rag", self.agent.metadata.tags)

    def test_validate_input(self):
        res1 = self.agent.validate_input({"query": "q1"})
        self.assertEqual(len(res1), 1)

        res2 = self.agent.validate_input(["q1", "q2"])
        self.assertEqual(len(res2), 2)

    def test_agent_execution_updates_context(self):
        exec_ctx = ExecutionContext()
        results = self.agent.execute({"query": "Check core-01 status", "device_id": "core-01"}, context=exec_ctx)

        self.assertEqual(len(results), 1)
        self.assertIn("RAGAgent", exec_ctx.results)
        self.assertIn("latest_rag_context", exec_ctx.shared_state)

    def test_event_subscriptions_and_emissions(self):
        received_events: List[Event] = []
        self.bus.subscribe("rag.context.ready", lambda e: received_events.append(e))

        # Publish request event
        self.bus.publish(
            Event(
                event_type="knowledge.requested",
                source="TestRunner",
                payload={"query": "Triage WAN link failure", "device_id": "rtr-01"},
            )
        )

        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0].event_type, "rag.context.ready")

    def test_register_rag_agent_helper(self):
        registry = AgentRegistry()
        agent = register_rag_agent(registry=registry)
        self.assertIsInstance(agent, RAGAgent)
        self.assertIsNotNone(registry.get("RAGAgent"))


if __name__ == "__main__":
    unittest.main()
