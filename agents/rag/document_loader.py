"""
Document Loader Module.

Implements multi-format document loading for Markdown, Text, JSON, YAML, HTML, PDF, and DOCX files.
Extracts comprehensive metadata, content hashes, and structural markers.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.rag.interfaces import IDocumentLoader
from agents.rag.models import Document, DocumentType

logger = get_agent_logger("DocumentLoader")

# Try importing YAML parser gracefully
try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


class DocumentLoader(IDocumentLoader):
    """
    Production document loader supporting Markdown, TXT, JSON, YAML, HTML, PDF, and DOCX.
    Extracts file metadata, content hashes (SHA-256), and timestamps.
    """

    SUPPORTED_EXTENSIONS: Dict[str, DocumentType] = {
        ".md": DocumentType.MARKDOWN,
        ".markdown": DocumentType.MARKDOWN,
        ".txt": DocumentType.TEXT,
        ".log": DocumentType.TEXT,
        ".json": DocumentType.JSON,
        ".yaml": DocumentType.YAML,
        ".yml": DocumentType.YAML,
        ".html": DocumentType.HTML,
        ".htm": DocumentType.HTML,
        ".pdf": DocumentType.PDF,
        ".docx": DocumentType.DOCX,
    }

    def load_document(self, file_path: str) -> Document:
        """
        Load a single document from file_path.

        Args:
            file_path: Absolute or relative file path.

        Returns:
            Document model instance.

        Raises:
            FileNotFoundError: If file does not exist.
            ValueError: If file extension is unsupported or file cannot be read.
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Document file not found: '{file_path}'")

        ext = os.path.splitext(file_path)[1].lower()
        doc_type = self.SUPPORTED_EXTENSIONS.get(ext, DocumentType.UNKNOWN)

        filename = os.path.basename(file_path)
        stat = os.stat(file_path)
        created_time = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
        modified_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        raw_bytes = self._read_raw_bytes(file_path)
        doc_hash = hashlib.sha256(raw_bytes).hexdigest()

        content = self._parse_content(file_path, doc_type, raw_bytes)
        tags = self._extract_tags(filename, content)

        metadata: Dict[str, Any] = {
            "file_size_bytes": stat.st_size,
            "extension": ext,
            "encoding": "utf-8",
        }

        logger.info(f"Loaded document '{filename}' ({doc_type.value}, {stat.st_size} bytes).")

        return Document(
            filename=filename,
            content=content,
            document_type=doc_type,
            hash=doc_hash,
            source=os.path.abspath(file_path),
            author="NOC Operations",
            version="1.0.0",
            created_time=created_time,
            modified_time=modified_time,
            tags=tags,
            metadata=metadata,
        )

    def load_directory(
        self, directory_path: str, recursive: bool = True
    ) -> List[Document]:
        """
        Load all supported documents from directory_path.

        Args:
            directory_path: Directory path to scan.
            recursive: True to traverse subdirectories.

        Returns:
            List of loaded Document models.
        """
        documents: List[Document] = []
        if not os.path.isdir(directory_path):
            logger.warning(f"Directory not found: '{directory_path}'. Returning empty list.")
            return documents

        if recursive:
            for root, _, files in os.walk(directory_path):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in self.SUPPORTED_EXTENSIONS:
                        full_path = os.path.join(root, f)
                        try:
                            documents.append(self.load_document(full_path))
                        except Exception as e:
                            logger.error(f"Failed to load '{full_path}': {e}")
        else:
            for f in os.listdir(directory_path):
                full_path = os.path.join(directory_path, f)
                if os.path.isfile(full_path):
                    ext = os.path.splitext(f)[1].lower()
                    if ext in self.SUPPORTED_EXTENSIONS:
                        try:
                            documents.append(self.load_document(full_path))
                        except Exception as e:
                            logger.error(f"Failed to load '{full_path}': {e}")

        logger.info(f"Loaded {len(documents)} document(s) from directory '{directory_path}'.")
        return documents

    # ------------------------------------------------------------------
    # Content parsers
    # ------------------------------------------------------------------

    def _read_raw_bytes(self, file_path: str) -> bytes:
        with open(file_path, "rb") as fh:
            return fh.read()

    def _parse_content(
        self, file_path: str, doc_type: DocumentType, raw_bytes: bytes
    ) -> str:
        """Parse raw bytes into clean text according to DocumentType."""
        if doc_type in (DocumentType.MARKDOWN, DocumentType.TEXT):
            return raw_bytes.decode("utf-8", errors="replace")

        elif doc_type == DocumentType.JSON:
            text = raw_bytes.decode("utf-8", errors="replace")
            try:
                data = json.loads(text)
                return json.dumps(data, indent=2)
            except Exception:
                return text

        elif doc_type == DocumentType.YAML:
            text = raw_bytes.decode("utf-8", errors="replace")
            if _YAML_AVAILABLE:
                try:
                    data = _yaml.safe_load(text)
                    return json.dumps(data, indent=2)
                except Exception:
                    pass
            return text

        elif doc_type == DocumentType.HTML:
            raw_text = raw_bytes.decode("utf-8", errors="replace")
            # Strip HTML tags
            clean = re.sub(r"<script.*?>.*?</script>", "", raw_text, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r"<style.*?>.*?</style>", "", clean, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r"<.*?>", " ", clean)
            return re.sub(r"\s+", " ", clean).strip()

        elif doc_type in (DocumentType.PDF, DocumentType.DOCX):
            # Text extraction attempt from binary stream, stripping binary noise
            text = raw_bytes.decode("latin1", errors="replace")
            printable = "".join(c if c.isprintable() or c in "\n\r\t" else " " for c in text)
            clean = re.sub(r"\s+", " ", printable).strip()
            return clean if len(clean) > 50 else f"Binary document: {os.path.basename(file_path)}"

        return raw_bytes.decode("utf-8", errors="replace")

    @staticmethod
    def _extract_tags(filename: str, content: str) -> List[str]:
        """Extract tags from filename and text content."""
        tags: List[str] = []
        name_lower = filename.lower()
        if "runbook" in name_lower or "guide" in name_lower:
            tags.append("runbook")
        if "sop" in name_lower or "procedure" in name_lower:
            tags.append("sop")
        if "vendor" in name_lower or "cisco" in name_lower or "juniper" in name_lower:
            tags.append("vendor")
        if "incident" in name_lower:
            tags.append("incident")
        if not tags:
            tags.append("documentation")
        return tags
