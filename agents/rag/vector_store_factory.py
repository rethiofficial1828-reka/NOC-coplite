"""
Vector Store Factory Module.

Provides dynamic creation and resolution of IVectorStore instances.
"""

from typing import Dict, Optional, Type

from agents.core.logger import get_agent_logger
from agents.rag.interfaces import IVectorStore
from agents.rag.vector_store import SQLiteVectorStore

logger = get_agent_logger("VectorStoreFactory")


class VectorStoreFactory:
    """
    Factory for resolving and creating IVectorStore backend instances.
    """

    _registry: Dict[str, Type[IVectorStore]] = {
        "sqlite": SQLiteVectorStore,
    }

    @classmethod
    def register_store(cls, name: str, store_cls: Type[IVectorStore]) -> None:
        """Register a custom VectorStore class."""
        key = name.lower().strip()
        cls._registry[key] = store_cls
        logger.info(f"Registered VectorStore provider '{key}'.")

    @classmethod
    def create_vector_store(
        cls, store_type: str = "sqlite", **kwargs
    ) -> IVectorStore:
        """
        Create an instance of IVectorStore.

        Args:
            store_type: Key identifier ('sqlite', etc.)
            kwargs: Parameters passed to constructor.

        Returns:
            Configured IVectorStore instance.
        """
        key = store_type.lower().strip()
        store_cls = cls._registry.get(key, SQLiteVectorStore)

        try:
            instance = store_cls(**kwargs)
            logger.info(f"Created VectorStore instance using backend '{key}'.")
            return instance
        except Exception as e:
            logger.warning(
                f"Failed to create VectorStore '{key}' ({e}). Falling back to SQLiteVectorStore."
            )
            return SQLiteVectorStore()
