"""
Centralized Logging Module for Atomic Agent Framework.

Provides structured logging with timestamps, agent identifiers, execution duration,
and exception traces. Zero print statements.
"""

import logging
import sys
from typing import Optional


class AgentLogFormatter(logging.Formatter):
    """Custom log formatter ensuring standardized agent log output."""

    DEFAULT_FORMAT = (
        "[%(asctime)s] [%(levelname)s] [agent=%(agent_name)s] "
        "[status=%(status)s] [exec_time_ms=%(exec_time_ms)s] - %(message)s"
    )

    def __init__(self, fmt: Optional[str] = None) -> None:
        super().__init__(fmt=fmt or self.DEFAULT_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "agent_name"):
            record.agent_name = getattr(record, "name", "AgentSystem")
        if not hasattr(record, "status"):
            record.status = "INFO"
        if not hasattr(record, "exec_time_ms"):
            record.exec_time_ms = "N/A"
        return super().format(record)


def get_agent_logger(agent_name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Get or create a dedicated logger for a specific agent.

    Args:
        agent_name: Unique identifier for the agent.
        level: Logging level (default logging.INFO).

    Returns:
        logging.Logger configured with AgentLogFormatter.
    """
    logger_id = f"agent.{agent_name}"
    logger = logging.getLogger(logger_id)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(AgentLogFormatter())
        logger.addHandler(handler)

    logger.propagate = False
    return logger


def log_execution_event(
    logger: logging.Logger,
    agent_name: str,
    status: str,
    message: str,
    exec_time_ms: Optional[float] = None,
    level: int = logging.INFO,
    exc_info: bool = False,
) -> None:
    """Log structured execution event with metadata."""
    extra = {
        "agent_name": agent_name,
        "status": status,
        "exec_time_ms": f"{exec_time_ms:.2f}" if exec_time_ms is not None else "N/A",
    }
    logger.log(level, message, extra=extra, exc_info=exc_info)
