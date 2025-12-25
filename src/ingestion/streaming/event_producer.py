"""
Event producer for streaming data ingestion.

Provides high-level API for publishing events to Kafka topics.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid

from src.common.config import get_config
from src.common.logging import get_logger
from src.common.exceptions import IngestionError
from src.streaming.kafka.producer import KafkaProducerManager, ProducerConfig
from src.ingestion.streaming.event_schemas import EventSchema

logger = get_logger(__name__)


class EventProducer:
    """
    High-level event producer for data ingestion.

    Handles event validation, enrichment, and publishing to Kafka topics
    with automatic routing based on event type.
    """

    # Topic routing based on event type
    TOPIC_ROUTING = {
        "user_action": "raw-events",
        "transaction": "raw-transactions",
        "system_event": "raw-system-events",
        "sensor_reading": "raw-sensor-data",
        "log_event": "raw-logs",
        "metric_event": "raw-metrics",
    }

    def __init__(
        self,
        bootstrap_servers: Optional[str] = None,
        producer_config: Optional[ProducerConfig] = None,
    ):
        """
        Initialize event producer.

        Args:
            bootstrap_servers: Kafka bootstrap servers
            producer_config: Custom producer configuration
        """
        self.config = get_config()

        # Initialize producer
        if producer_config:
            self.producer = KafkaProducerManager(producer_config)
        else:
            servers = bootstrap_servers or self.config.kafka_bootstrap_servers
            default_config = ProducerConfig(
                bootstrap_servers=servers,
                client_id="event-producer",
                acks="all",
                retries=3,
                compression_type="snappy",
                value_serializer="json",
            )
            self.producer = KafkaProducerManager(default_config)

        logger.info("Event producer initialized")

    def publish_event(
        self,
        event: EventSchema,
        topic: Optional[str] = None,
        validate: bool = True,
    ) -> Dict[str, Any]:
        """
        Publish a single event.

        Args:
            event: Event to publish
            topic: Target topic (auto-routed if None)
            validate: Validate event schema before publishing

        Returns:
            Publish result

        Raises:
            IngestionError: If validation or publishing fails
        """
        try:
            # Validate event
            if validate:
                validation_errors = event.validate()
                if validation_errors:
                    raise IngestionError(
                        f"Event validation failed: {validation_errors}"
                    )

            # Determine topic
            target_topic = topic or self._route_event(event)

            # Add ingestion metadata
            enriched_event = self._enrich_event(event)

            # Publish to Kafka
            result = self.producer.send_message(
                topic=target_topic,
                message=enriched_event,
                key=event.event_id,
                headers={
                    "event_type": event.event_type,
                    "source_system": event.source_system,
                    "schema_version": event.schema_version,
                },
            )

            if result["success"]:
                logger.info(
                    "Event published successfully",
                    event_id=event.event_id,
                    topic=target_topic,
                    partition=result["partition"],
                    offset=result["offset"],
                )
            else:
                logger.error(
                    "Failed to publish event",
                    event_id=event.event_id,
                    error=result.get("error"),
                )

            return result

        except Exception as e:
            logger.error(f"Event publishing failed: {e}", event_id=event.event_id)
            raise IngestionError(f"Failed to publish event: {e}")

    def publish_batch(
        self,
        events: List[EventSchema],
        topic: Optional[str] = None,
        validate: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Publish multiple events in batch.

        Args:
            events: List of events to publish
            topic: Target topic (auto-routed if None)
            validate: Validate events before publishing

        Returns:
            List of publish results
        """
        results = []

        for event in events:
            result = self.publish_event(event, topic=topic, validate=validate)
            results.append(result)

        successful = sum(1 for r in results if r.get("success", False))
        logger.info(
            f"Batch publish complete",
            total=len(events),
            successful=successful,
            failed=len(events) - successful,
        )

        return results

    def publish_raw_data(
        self,
        topic: str,
        data: Dict[str, Any],
        source_system: str,
        event_type: str = "raw_data",
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Publish raw data without strict schema validation.

        Useful for ingesting arbitrary data that will be processed later.

        Args:
            topic: Target topic
            data: Raw data to publish
            source_system: Source system identifier
            event_type: Event type classification
            event_id: Optional event ID (generated if None)

        Returns:
            Publish result
        """
        try:
            # Create minimal event wrapper
            event = EventSchema(
                event_id=event_id or str(uuid.uuid4()),
                event_type=event_type,
                event_timestamp=datetime.utcnow().isoformat() + "Z",
                source_system=source_system,
                payload=data,
            )

            # Publish without validation
            return self.publish_event(event, topic=topic, validate=False)

        except Exception as e:
            logger.error(f"Raw data publishing failed: {e}")
            raise IngestionError(f"Failed to publish raw data: {e}")

    def _route_event(self, event: EventSchema) -> str:
        """
        Determine target topic based on event type.

        Args:
            event: Event to route

        Returns:
            Topic name
        """
        topic = self.TOPIC_ROUTING.get(event.event_type, "raw-events")
        logger.debug(f"Routing event {event.event_id} to topic {topic}")
        return topic

    def _enrich_event(self, event: EventSchema) -> Dict[str, Any]:
        """
        Enrich event with ingestion metadata.

        Args:
            event: Event to enrich

        Returns:
            Enriched event dictionary
        """
        enriched = event.to_dict()

        # Add ingestion metadata
        enriched["metadata"]["ingestion_timestamp"] = (
            datetime.utcnow().isoformat() + "Z"
        )
        enriched["metadata"]["ingestion_system"] = "dataplatform"
        enriched["metadata"]["producer_version"] = "1.0.0"

        return enriched

    def flush(self):
        """Flush pending messages."""
        self.producer.flush()
        logger.debug("Producer flushed")

    def close(self):
        """Close producer connection."""
        self.producer.close()
        logger.info("Event producer closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
