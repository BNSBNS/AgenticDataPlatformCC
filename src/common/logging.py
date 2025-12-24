"""
Logging Configuration

Structured logging using structlog for better observability.
"""

import logging
import sys
from typing import Any, Optional

import structlog
from structlog.types import EventDict, Processor

from src.common.config import get_config


def add_app_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Add application context to log events.

    Args:
        logger: Logger instance
        method_name: Method name
        event_dict: Event dictionary

    Returns:
        Updated event dictionary with app context
    """
    config = get_config()
    event_dict["environment"] = config.environment.value
    event_dict["service"] = "data-platform"
    return event_dict


def setup_logging(
    level: Optional[str] = None,
    json_logs: bool = False,
    correlation_id_enabled: bool = True,
) -> None:
    """
    Setup structured logging with structlog.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logs: Whether to output logs in JSON format
        correlation_id_enabled: Whether to include correlation IDs
    """
    config = get_config()
    log_level = level or config.log_level

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Define processors
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        add_app_context,
    ]

    # Add correlation ID processor if enabled
    if correlation_id_enabled:
        processors.insert(0, structlog.processors.CallsiteParameterAdder())

    # Add appropriate renderer based on json_logs setting
    if json_logs or config.is_production:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (usually __name__ of the module)

    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


# Setup logging on module import
setup_logging()
