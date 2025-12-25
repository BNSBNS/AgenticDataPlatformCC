"""
Event schema definitions for streaming ingestion.

Defines standard event schemas for different data sources.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum


class EventType(str, Enum):
    """Standard event types."""

    USER_ACTION = "user_action"
    TRANSACTION = "transaction"
    SYSTEM_EVENT = "system_event"
    SENSOR_READING = "sensor_reading"
    LOG_EVENT = "log_event"
    METRIC_EVENT = "metric_event"


@dataclass
class EventSchema:
    """
    Base event schema for platform events.

    All events should include these standard fields for lineage tracking
    and data quality monitoring.

    Attributes:
        event_id: Unique event identifier
        event_type: Type of event
        event_timestamp: When the event occurred
        source_system: System that generated the event
        payload: Event-specific data
        metadata: Additional metadata
        schema_version: Schema version for evolution
    """

    event_id: str
    event_type: str
    event_timestamp: str  # ISO 8601 format
    source_system: str
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert event to dictionary for serialization.

        Returns:
            Dictionary representation of event
        """
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_timestamp": self.event_timestamp,
            "source_system": self.source_system,
            "payload": self.payload,
            "metadata": self.metadata,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventSchema":
        """
        Create event from dictionary.

        Args:
            data: Dictionary with event data

        Returns:
            EventSchema instance
        """
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            event_timestamp=data["event_timestamp"],
            source_system=data["source_system"],
            payload=data["payload"],
            metadata=data.get("metadata", {}),
            schema_version=data.get("schema_version", "1.0"),
        )

    def validate(self) -> List[str]:
        """
        Validate event schema.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not self.event_id:
            errors.append("event_id is required")

        if not self.event_type:
            errors.append("event_type is required")

        if not self.event_timestamp:
            errors.append("event_timestamp is required")

        if not self.source_system:
            errors.append("source_system is required")

        if not isinstance(self.payload, dict):
            errors.append("payload must be a dictionary")

        # Validate timestamp format
        try:
            datetime.fromisoformat(self.event_timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            errors.append("event_timestamp must be valid ISO 8601 format")

        return errors


@dataclass
class UserActionEvent(EventSchema):
    """
    User action event schema.

    For tracking user interactions with the system.
    """

    def __init__(
        self,
        event_id: str,
        event_timestamp: str,
        source_system: str,
        user_id: str,
        action: str,
        resource: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize user action event."""
        payload = {
            "user_id": user_id,
            "action": action,
            "resource": resource,
        }

        super().__init__(
            event_id=event_id,
            event_type=EventType.USER_ACTION,
            event_timestamp=event_timestamp,
            source_system=source_system,
            payload=payload,
            metadata=metadata or {},
        )


@dataclass
class TransactionEvent(EventSchema):
    """
    Transaction event schema.

    For tracking financial or business transactions.
    """

    def __init__(
        self,
        event_id: str,
        event_timestamp: str,
        source_system: str,
        transaction_id: str,
        amount: float,
        currency: str,
        transaction_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize transaction event."""
        payload = {
            "transaction_id": transaction_id,
            "amount": amount,
            "currency": currency,
            "transaction_type": transaction_type,
        }

        super().__init__(
            event_id=event_id,
            event_type=EventType.TRANSACTION,
            event_timestamp=event_timestamp,
            source_system=source_system,
            payload=payload,
            metadata=metadata or {},
        )


@dataclass
class SystemEvent(EventSchema):
    """
    System event schema.

    For tracking system-level events (deployments, failures, etc.).
    """

    def __init__(
        self,
        event_id: str,
        event_timestamp: str,
        source_system: str,
        component: str,
        event_name: str,
        severity: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize system event."""
        payload = {
            "component": component,
            "event_name": event_name,
            "severity": severity,
            "message": message,
        }

        super().__init__(
            event_id=event_id,
            event_type=EventType.SYSTEM_EVENT,
            event_timestamp=event_timestamp,
            source_system=source_system,
            payload=payload,
            metadata=metadata or {},
        )


@dataclass
class MetricEvent(EventSchema):
    """
    Metric event schema.

    For tracking time-series metrics.
    """

    def __init__(
        self,
        event_id: str,
        event_timestamp: str,
        source_system: str,
        metric_name: str,
        metric_value: float,
        metric_unit: str,
        tags: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize metric event."""
        payload = {
            "metric_name": metric_name,
            "metric_value": metric_value,
            "metric_unit": metric_unit,
            "tags": tags or {},
        }

        super().__init__(
            event_id=event_id,
            event_type=EventType.METRIC_EVENT,
            event_timestamp=event_timestamp,
            source_system=source_system,
            payload=payload,
            metadata=metadata or {},
        )
