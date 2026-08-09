"""
Index Manager Module.

Implements IndexManager for incremental document scanning, hash-based change detection,
chunking, embedding, and indexing into VectorStore and KeywordIndex.
"""

import os
import threading
from typing import Dict, List, Optional, Set

from agents.core.logger import get_agent_logger
from agents.rag.document_chunker import IntelligentChunker
from agents.rag.document_loader import DocumentLoader
from agents.rag.interfaces import IDocumentChunker, IDocumentLoader, IEmbeddingProvider, IKeywordIndex, IVectorStore
from agents.rag.models import Document, DocumentChunk

logger = get_agent_logger("IndexManager")


class IndexManager:
    """
    Manages document discovery, incremental change indexing, chunking, and embedding.
    """

    def __init__(
        self,
        vector_store: IVectorStore,
        keyword_index: IKeywordIndex,
        embedding_provider: IEmbeddingProvider,
        loader: Optional[IDocumentLoader] = None,
        chunker: Optional[IDocumentChunker] = None,
    ) -> None:
        self._vector_store = vector_store
        self._keyword_index = keyword_index
        self._embedding_provider = embedding_provider
        self._loader = loader or DocumentLoader()
        self._chunker = chunker or IntelligentChunker()
        self._lock = threading.RLock()

        # Document registry: doc_path -> hash
        self._indexed_hashes: Dict[str, str] = {}

    def index_directory(self, directory_path: str, recursive: bool = True) -> int:
        """
        Scan directory for new or modified documents and incrementally index them.

        Args:
            directory_path: Target folder path.
            recursive: True to scan subfolders.

        Returns:
            Number of newly indexed or updated documents.
        """
        with self._lock:
            docs = self._loader.load_directory(directory_path, recursive=recursive)
            indexed_count = 0

            for doc in docs:
                if self._should_index(doc):
                    self.index_document(doc)
                    indexed_count += 1

            logger.info(f"IndexManager indexed {indexed_count} new/updated document(s) from '{directory_path}'.")
            return indexed_count

    def index_document(self, document: Document) -> List[DocumentChunk]:
        """
        Chunk, embed, and index a single Document model instance.

        Args:
            document: Document model to index.

        Returns:
            List of generated DocumentChunk instances.
        """
        with self._lock:
            chunks = self._chunker.chunk_document(document)
            if not chunks:
                return []

            texts = [c.content for c in chunks]
            vectors = self._embedding_provider.embed_batch(texts)

            # Insert into Vector Store
            self._vector_store.batch_insert(chunks, vectors)

            # Insert into Keyword Index
            self._keyword_index.index_chunks(chunks)

            # Register hash
            self._indexed_hashes[document.source] = document.hash

            logger.info(f"Indexed document '{document.filename}' ({len(chunks)} chunks).")
            return chunks

    def _should_index(self, document: Document) -> bool:
        """Return True if document is new or content hash changed."""
        old_hash = self._indexed_hashes.get(document.source)
        return old_hash != document.hash
