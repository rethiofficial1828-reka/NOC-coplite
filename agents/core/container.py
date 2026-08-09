"""
Service Container for Dependency Injection.

Supports service registration, lazy singleton creation, factory binding,
and dependency lookup.
"""

import threading
from typing import Any, Callable, Dict, Optional, Type, TypeVar

from agents.core.exceptions import ContainerError

T = TypeVar("T")


class ServiceContainer:
    """
    Thread-safe Service Container implementing Dependency Injection.
    """

    _global_instance: Optional["ServiceContainer"] = None
    _global_lock = threading.Lock()

    def __init__(self) -> None:
        self._instances: Dict[Any, Any] = {}
        self._factories: Dict[Any, Callable[["ServiceContainer"], Any]] = {}
        self._singletons: Dict[Any, bool] = {}
        self._lock = threading.RLock()

    @classmethod
    def get_global(cls) -> "ServiceContainer":
        """Get or initialize global singleton ServiceContainer."""
        if cls._global_instance is None:
            with cls._global_lock:
                if cls._global_instance is None:
                    cls._global_instance = cls()
        return cls._global_instance

    def register_instance(self, service_type: Type[T], instance: T) -> None:
        """Register a pre-constructed service instance."""
        with self._lock:
            if not isinstance(instance, service_type):
                raise ContainerError(
                    f"Instance {instance} is not an instance of {service_type}"
                )
            self._instances[service_type] = instance

    def register_factory(
        self,
        service_type: Type[T],
        factory: Callable[["ServiceContainer"], T],
        singleton: bool = True,
    ) -> None:
        """
        Register a factory function for lazy service resolution.

        Args:
            service_type: Type/Interface key for the service.
            factory: Callable accepting ServiceContainer and returning service instance.
            singleton: If True, caches resolved instance on first resolution.
        """
        with self._lock:
            self._factories[service_type] = factory
            self._singletons[service_type] = singleton
            # Remove any previous cached instance
            self._instances.pop(service_type, None)

    def has_service(self, service_type: Any) -> bool:
        """Check if service is registered."""
        with self._lock:
            return service_type in self._instances or service_type in self._factories

    def resolve(self, service_type: Type[T]) -> T:
        """
        Resolve service instance by type/key.

        Returns:
            Resolved service instance.

        Raises:
            ContainerError: If service is not registered or factory fails.
        """
        with self._lock:
            if service_type in self._instances:
                return self._instances[service_type]

            if service_type in self._factories:
                factory = self._factories[service_type]
                try:
                    instance = factory(self)
                except Exception as e:
                    raise ContainerError(
                        f"Failed to instantiate service '{service_type}': {e}"
                    ) from e

                if self._singletons.get(service_type, True):
                    self._instances[service_type] = instance

                return instance

            raise ContainerError(
                f"Service '{service_type}' is not registered in ServiceContainer."
            )

    def unregister(self, service_type: Any) -> None:
        """Remove a service registration."""
        with self._lock:
            self._instances.pop(service_type, None)
            self._factories.pop(service_type, None)
            self._singletons.pop(service_type, None)

    def reset(self) -> None:
        """Clear all service registrations."""
        with self._lock:
            self._instances.clear()
            self._factories.clear()
            self._singletons.clear()
