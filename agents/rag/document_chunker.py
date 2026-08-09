"""
Document Chunker Module.

Implements intelligent chunking strategies (heading-aware, paragraph, fixed-size)
with overlap support, heading hierarchy breadcrumbs, and parent-child lineage.
"""

import re
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.rag.interfaces import IDocumentChunker
from agents.rag.models import ChunkingStrategy, Document, DocumentChunk

logger = get_agent_logger("DocumentChunker")


class IntelligentChunker(IDocumentChunker):
    """
    Production document chunker supporting Heading-Aware, Paragraph, and Fixed-Size strategies.
    Preserves heading breadcrumbs, token budgets, overlap, and document lineage.
    """

    def __init__(
        self,
        default_strategy: ChunkingStrategy = ChunkingStrategy.HEADING_AWARE,
        max_chunk_chars: int = 1000,
        chunk_overlap_chars: int = 150,
    ) -> None:
        """
        Initialize IntelligentChunker.

        Args:
            default_strategy: Strategy to use when document type does not mandate one.
            max_chunk_chars: Target character limit per chunk.
            chunk_overlap_chars: Number of overlapping characters between adjacent chunks.
        """
        self._default_strategy = default_strategy
        self._max_chunk_chars = max_chunk_chars
        self._chunk_overlap_chars = chunk_overlap_chars

    def chunk_document(
        self,
        document: Document,
        strategy: Optional[ChunkingStrategy] = None,
    ) -> List[DocumentChunk]:
        """
        Chunk a Document into a list of DocumentChunk objects.

        Args:
            document: Document model instance.
            strategy: Optional explicit ChunkingStrategy override.

        Returns:
            List of DocumentChunk instances.
        """
        chosen_strategy = strategy or self._default_strategy

        if chosen_strategy == ChunkingStrategy.HEADING_AWARE and document.content.startswith("#") or "# " in document.content:
            chunks = self._chunk_heading_aware(document)
        elif chosen_strategy == ChunkingStrategy.PARAGRAPH:
            chunks = self._chunk_by_paragraph(document)
        else:
            chunks = self._chunk_fixed_size(document)

        logger.info(
            f"Chunked document '{document.filename}' into {len(chunks)} chunk(s) "
            f"using strategy '{chosen_strategy.value}'."
        )
        return chunks

    # ------------------------------------------------------------------
    # Strategy implementations
    # ------------------------------------------------------------------

    def _chunk_heading_aware(self, document: Document) -> List[DocumentChunk]:
        """Split Markdown document into chunks based on header hierarchy."""
        lines = document.content.splitlines()
        chunks: List[DocumentChunk] = []

        current_hierarchy: List[str] = []
        current_buffer: List[str] = []
        chunk_idx = 0

        for line in lines:
            header_match = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
            if header_match:
                # Flushed buffered text before starting new section
                if current_buffer:
                    chunk_text = "\n".join(current_buffer).strip()
                    if chunk_text:
                        chunks.append(
                            self._create_chunk(
                                document=document,
                                text=chunk_text,
                                index=chunk_idx,
                                hierarchy=list(current_hierarchy),
                                strategy=ChunkingStrategy.HEADING_AWARE,
                            )
                        )
                        chunk_idx += 1
                    current_buffer = []

                level = len(header_match.group(1))
                title = header_match.group(2).strip()

                # Adjust hierarchy depth
                current_hierarchy = current_hierarchy[: level - 1]
                current_hierarchy.append(title)
                current_buffer.append(line)
            else:
                current_buffer.append(line)

        # Flush final buffer
        if current_buffer:
            chunk_text = "\n".join(current_buffer).strip()
            if chunk_text:
                chunks.append(
                    self._create_chunk(
                        document=document,
                        text=chunk_text,
                        index=chunk_idx,
                        hierarchy=list(current_hierarchy),
                        strategy=ChunkingStrategy.HEADING_AWARE,
                    )
                )

        # Fallback to paragraph if heading chunking produced 1 huge chunk
        if len(chunks) == 1 and len(chunks[0].content) > self._max_chunk_chars * 2:
            return self._chunk_by_paragraph(document)

        return chunks

    def _chunk_by_paragraph(self, document: Document) -> List[DocumentChunk]:
        """Split document by double newlines (paragraphs)."""
        paragraphs = re.split(r"\n\s*\n", document.content)
        chunks: List[DocumentChunk] = []
        chunk_idx = 0

        current_buffer: List[str] = []
        current_len = 0

        for p in paragraphs:
            p_str = p.strip()
            if not p_str:
                continue

            if current_len + len(p_str) > self._max_chunk_chars and current_buffer:
                chunk_text = "\n\n".join(current_buffer)
                chunks.append(
                    self._create_chunk(
                        document=document,
                        text=chunk_text,
                        index=chunk_idx,
                        hierarchy=[],
                        strategy=ChunkingStrategy.PARAGRAPH,
                    )
                )
                chunk_idx += 1
                current_buffer = []
                current_len = 0

            current_buffer.append(p_str)
            current_len += len(p_str)

        if current_buffer:
            chunk_text = "\n\n".join(current_buffer)
            chunks.append(
                self._create_chunk(
                    document=document,
                    text=chunk_text,
                    index=chunk_idx,
                    hierarchy=[],
                    strategy=ChunkingStrategy.PARAGRAPH,
                )
            )

        return chunks

    def _chunk_fixed_size(self, document: Document) -> List[DocumentChunk]:
        """Split text into fixed character windows with overlap."""
        text = document.content
        text_len = len(text)
        chunks: List[DocumentChunk] = []
        chunk_idx = 0

        start = 0
        while start < text_len:
            end = min(start + self._max_chunk_chars, text_len)
            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append(
                    self._create_chunk(
                        document=document,
                        text=chunk_text,
                        index=chunk_idx,
                        hierarchy=[],
                        strategy=ChunkingStrategy.FIXED_SIZE,
                    )
                )
                chunk_idx += 1

            start += self._max_chunk_chars - self._chunk_overlap_chars
            if start >= text_len or end == text_len:
                break

        return chunks

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _create_chunk(
        self,
        document: Document,
        text: str,
        index: int,
        hierarchy: List[str],
        strategy: ChunkingStrategy,
    ) -> DocumentChunk:
        """Construct a DocumentChunk model instance."""
        token_count = max(1, len(text.split()))
        return DocumentChunk(
            parent_doc_id=document.doc_id,
            chunk_index=index,
            content=text,
            token_count=token_count,
            heading_hierarchy=hierarchy,
            chunking_strategy=strategy,
            source=document.source or document.filename,
            tags=list(document.tags),
            metadata={
                "filename": document.filename,
                "document_type": document.document_type.value,
                "document_hash": document.hash,
                "hierarchy_str": " > ".join(hierarchy) if hierarchy else "Root",
            },
        )
