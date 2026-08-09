"""
Citations Module.

Generates structured, traceable evidence citations from candidate retrieval results.
"""

from typing import List, Optional

from agents.core.logger import get_agent_logger
from agents.rag.models import Citation, RetrievalResult

logger = get_agent_logger("Citations")


class CitationGenerator:
    """
    Generates structured, explainable Citation models from candidate retrieval results.
    """

    @staticmethod
    def generate_citations(
        results: List[RetrievalResult], max_citations: int = 5
    ) -> List[Citation]:
        """
        Convert top RetrievalResult candidates into structured Citation models.

        Args:
            results: List of ranked RetrievalResult objects.
            max_citations: Maximum number of citations to build.

        Returns:
            List of Citation model instances.
        """
        citations: List[Citation] = []

        for res in results[:max_citations]:
            chunk = res.chunk
            source = chunk.source or chunk.metadata.get("filename", "Knowledge Document")
            hierarchy = chunk.heading_hierarchy
            section = " > ".join(hierarchy) if hierarchy else chunk.metadata.get("hierarchy_str", "General")

            # Extract first 150 characters as snippet
            snippet = chunk.content[:180].replace("\n", " ").strip() + ("..." if len(chunk.content) > 180 else "")

            citations.append(
                Citation(
                    chunk_id=chunk.chunk_id,
                    source=source,
                    section=section,
                    content_snippet=snippet,
                    confidence=round(min(1.0, res.score * 1.1), 2),
                    relevance_score=round(res.score, 2),
                    metadata={
                        "parent_doc_id": chunk.parent_doc_id,
                        "chunk_index": chunk.chunk_index,
                        "strategy": str(chunk.chunking_strategy),
                    },
                )
            )

        logger.info(f"Generated {len(citations)} structured citation(s).")
        return citations

    @staticmethod
    def format_citations_text(citations: List[Citation]) -> str:
        """Format Citations list into markdown text for prompt injection or display."""
        if not citations:
            return "No citations available."

        lines: List[str] = ["--- CITATIONS & EVIDENCE SOURCES ---"]
        for i, c in enumerate(citations, start=1):
            lines.append(
                f"[{i}] {c.source} | Section: {c.section} (Relevance: {c.relevance_score:.2f})\n"
                f"    Snippet: \"{c.content_snippet}\""
            )

        return "\n".join(lines)
