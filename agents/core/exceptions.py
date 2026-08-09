"""
Custom Exception Classes for Atomic Agent System.

Inheritance Tree:
    AgentError (Base Exception)
    ├── RegistrationError
    ├── ExecutionError
    ├── ValidationError
    ├── ConfigurationError
    ├── EventError
    └── ContainerError
"""


class AgentError(Exception):
    """Base exception for all agent framework errors."""

    def __init__(self, message: str, details: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class RegistrationError(AgentError):
    """Raised when agent registration or duplicate checking fails."""

    pass


class ExecutionError(AgentError):
    """Raised when an agent execution fails at runtime."""

    pass


class ValidationError(AgentError):
    """Raised when input/output schema validation fails."""

    pass


class ConfigurationError(AgentError):
    """Raised when configuration or context setup is invalid."""

    pass


class EventError(AgentError):
    """Raised when event publishing, subscription, or dispatch fails."""

    pass


class ContainerError(AgentError):
    """Raised when dependency resolution or service lookup fails."""

    pass
