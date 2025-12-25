# Streaming Architecture - Agentic Data Platform

Complete guide to the streaming infrastructure using Apache Kafka and Apache Flink.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Kafka Infrastructure](#kafka-infrastructure)
4. [Data Ingestion](#data-ingestion)
5. [Flink Processing](#flink-processing)
6. [Event Schemas](#event-schemas)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## Overview

The streaming layer provides real-time data processing capabilities using:

- **Apache Kafka**: Distributed event streaming platform
- **Apache Flink**: Stream processing framework
- **Schema Registry**: Schema management and evolution
- **Exactly-once semantics**: Reliable event processing

### Key Features

✅ **Real-time Ingestion**: Publish events with sub-second latency
✅ **Reliable Delivery**: At-least-once and exactly-once guarantees
✅ **Schema Evolution**: Backward/forward compatible schemas
✅ **Scalable Processing**: Horizontal scaling with partitioning
✅ **Monitoring**: Comprehensive Prometheus metrics

---

## Architecture

```
┌──────────────┐
│ Data Sources │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ Event Producers  │  ← Application code, APIs, services
└──────┬───────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│          Apache Kafka Topics             │
│  ┌────────────┐  ┌────────────┐         │
│  │ raw-events │  │raw-metrics │  ...    │
│  └────────────┘  └────────────┘         │
└──────┬──────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│         Apache Flink Jobs                │
│  ┌───────────────────────────────────┐   │
│  │  Bronze → Silver Transformation   │   │
│  │  Silver → Gold Aggregation        │   │
│  │  Real-time Quality Checks         │   │
│  └───────────────────────────────────┘   │
└──────┬──────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│      Iceberg/Paimon Lakehouse            │
│   Bronze  →  Silver  →  Gold             │
└──────────────────────────────────────────┘
```

### Data Flow

1. **Ingestion**: Events published to raw Kafka topics
2. **Bronze Layer**: Flink writes to Bronze (raw, immutable)
3. **Silver Layer**: Flink transforms Bronze → Silver (validated, cleaned)
4. **Gold Layer**: Flink aggregates Silver → Gold (business metrics)

---

## Kafka Infrastructure

### Topic Organization

The platform uses a structured topic naming convention:

```
<layer>-<data_type>

Examples:
- raw-events         # User actions, system events
- raw-transactions   # Financial transactions
- raw-metrics        # Time-series metrics
- bronze-events      # Bronze layer events
- silver-events      # Refined events
- gold-metrics       # Aggregated metrics
```

### Topic Configuration

**Standard Configuration:**

```python
from src.streaming.kafka.admin import KafkaAdminManager, TopicConfig

admin = KafkaAdminManager(bootstrap_servers="localhost:9092")

# Create a topic
topic_config = TopicConfig(
    name="raw-events",
    num_partitions=6,
    replication_factor=3,
    retention_ms=604800000,  # 7 days
    compression_type="snappy",
    min_insync_replicas=2,
)

admin.create_topic(topic_config)
```

**Partitioning Strategy:**

- **User Events**: Partition by `user_id` for ordering
- **Transactions**: Partition by `account_id` or `transaction_id`
- **Metrics**: Partition by `metric_name` or `source`
- **Logs**: Partition by `application` or `severity`

### Retention Policies

| Layer | Retention | Rationale |
|-------|-----------|-----------|
| Raw Topics | 7 days | Short-term buffer, data in Bronze |
| Bronze Topics | 90 days | Historical replay, debugging |
| Silver Topics | 2 years | Compliance, auditing |
| Gold Topics | 7 years | Long-term analytics |

---

## Data Ingestion

### Event Producer

High-level API for publishing events with validation and routing:

```python
from src.ingestion.streaming import EventProducer, EventSchema
from datetime import datetime
import uuid

# Initialize producer
producer = EventProducer(bootstrap_servers="localhost:9092")

# Create an event
event = EventSchema(
    event_id=str(uuid.uuid4()),
    event_type="user_action",
    event_timestamp=datetime.utcnow().isoformat() + "Z",
    source_system="web-app",
    payload={
        "user_id": "user-123",
        "action": "purchase",
        "product_id": "prod-456",
        "amount": 99.99,
    },
    metadata={
        "session_id": "session-789",
        "ip_address": "192.168.1.1",
    },
)

# Publish event (auto-routed to correct topic)
result = producer.publish_event(event)

print(f"Published to partition {result['partition']} at offset {result['offset']}")
```

### Topic Routing

Events are automatically routed based on `event_type`:

| Event Type | Target Topic |
|------------|--------------|
| `user_action` | `raw-events` |
| `transaction` | `raw-transactions` |
| `system_event` | `raw-system-events` |
| `metric_event` | `raw-metrics` |
| `log_event` | `raw-logs` |

### Batch Publishing

For high-throughput scenarios:

```python
from src.ingestion.streaming import UserActionEvent, TransactionEvent

events = [
    UserActionEvent(
        event_id=str(uuid.uuid4()),
        event_timestamp=datetime.utcnow().isoformat() + "Z",
        source_system="mobile-app",
        user_id="user-123",
        action="view_product",
        resource="product-789",
    ),
    TransactionEvent(
        event_id=str(uuid.uuid4()),
        event_timestamp=datetime.utcnow().isoformat() + "Z",
        source_system="payment-service",
        transaction_id="txn-456",
        amount=149.99,
        currency="USD",
        transaction_type="purchase",
    ),
]

results = producer.publish_batch(events)
print(f"Published {len([r for r in results if r['success']])} events")
```

---

## Flink Processing

### Job Architecture

**Bronze → Silver Job:**

```
Kafka Source (raw-events)
    ↓
Schema Validation
    ↓
Data Cleansing
    ↓
Deduplication
    ↓
Iceberg Sink (bronze.events)
```

**Silver → Gold Job:**

```
Iceberg Source (silver.events)
    ↓
Windowing (tumbling, 5 min)
    ↓
Aggregation (count, sum, avg)
    ↓
Iceberg Sink (gold.metrics)
```

### Exactly-Once Semantics

Flink provides exactly-once guarantees through:

1. **Checkpointing**: Periodic state snapshots
2. **Two-Phase Commit**: Coordinated commits to Kafka and Iceberg
3. **Idempotent Writes**: Duplicate detection

**Configuration:**

```python
# In Flink job configuration
env.enable_checkpointing(60000)  # Every 60 seconds
env.get_checkpoint_config().set_checkpointing_mode(CheckpointingMode.EXACTLY_ONCE)
env.get_checkpoint_config().set_min_pause_between_checkpoints(30000)
```

---

## Event Schemas

### Base Event Schema

All events extend the base `EventSchema`:

```python
@dataclass
class EventSchema:
    event_id: str                    # Unique identifier
    event_type: str                  # Event classification
    event_timestamp: str             # ISO 8601 timestamp
    source_system: str               # Origin system
    payload: Dict[str, Any]          # Event-specific data
    metadata: Dict[str, Any]         # Additional context
    schema_version: str = "1.0"      # Schema version
```

### Specialized Schemas

**User Action Event:**

```python
event = UserActionEvent(
    event_id="evt-123",
    event_timestamp="2025-12-25T10:30:00Z",
    source_system="web-app",
    user_id="user-456",
    action="login",
    resource="dashboard",
)
```

**Transaction Event:**

```python
event = TransactionEvent(
    event_id="evt-789",
    event_timestamp="2025-12-25T10:30:00Z",
    source_system="payment-gateway",
    transaction_id="txn-123",
    amount=99.99,
    currency="USD",
    transaction_type="payment",
)
```

**Metric Event:**

```python
event = MetricEvent(
    event_id="evt-456",
    event_timestamp="2025-12-25T10:30:00Z",
    source_system="api-server",
    metric_name="request_latency_ms",
    metric_value=45.2,
    metric_unit="milliseconds",
    tags={"endpoint": "/api/users", "method": "GET"},
)
```

### Schema Evolution

The platform supports backward and forward compatible schema changes:

**Backward Compatible** (consumers can read new events):
- Adding optional fields
- Adding enum values
- Removing optional fields

**Forward Compatible** (producers can send to old consumers):
- Adding required fields with defaults
- Removing fields

---

## Best Practices

### 1. Event Design

✅ **DO:**
- Use meaningful event IDs (UUID v4)
- Include ISO 8601 timestamps with timezone
- Add correlation IDs for distributed tracing
- Version your schemas
- Keep payloads under 1MB

❌ **DON'T:**
- Include PII without encryption
- Use local timestamps (always UTC)
- Embed large binary data (use references)
- Change event semantics in same version

### 2. Producer Configuration

**Reliability:**

```python
config = ProducerConfig(
    acks="all",                    # Wait for all replicas
    retries=3,                     # Retry on failure
    compression_type="snappy",     # Compress messages
    max_request_size=1048576,      # 1MB limit
)
```

**Throughput:**

```python
config = ProducerConfig(
    acks="1",                      # Leader only
    batch_size=32768,              # 32KB batches
    linger_ms=100,                 # Wait 100ms for batch
    compression_type="lz4",        # Fast compression
)
```

### 3. Consumer Configuration

**At-Least-Once:**

```python
config = ConsumerConfig(
    enable_auto_commit=False,      # Manual offset commit
    auto_offset_reset="earliest",  # Start from beginning
    max_poll_records=100,          # Process in batches
)
```

**Exactly-Once:**

```python
config = ConsumerConfig(
    enable_auto_commit=False,
    isolation_level="read_committed",  # Only committed messages
)
# Coordinate with Flink checkpointing
```

### 4. Error Handling

**Dead Letter Queue Pattern:**

```python
try:
    # Process message
    process_event(message)
    consumer.commit()
except ProcessingError as e:
    # Send to DLQ for later analysis
    dlq_producer.send_message("dlq-events", {
        "original_message": message,
        "error": str(e),
        "timestamp": datetime.utcnow().isoformat(),
    })
    consumer.commit()  # Don't reprocess
```

### 5. Monitoring

Track key metrics:

```python
# In your Flink job
kafka_messages_consumed_total.labels(
    topic="raw-events",
    group_id="bronze-writer",
    status="success"
).inc()

kafka_producer_latency_seconds.labels(
    topic="bronze-events"
).observe(latency)
```

---

## Troubleshooting

### Common Issues

#### 1. Consumer Lag

**Symptom**: Consumer group falling behind producers

**Diagnosis:**

```bash
# Check consumer group lag
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group bronze-writer
```

**Solutions:**
- Increase consumer instances (scale horizontally)
- Increase `max_poll_records` for batch processing
- Optimize processing logic
- Add more topic partitions

#### 2. Message Loss

**Symptom**: Messages not appearing in topic

**Diagnosis:**

```python
# Check producer metrics
metrics = producer.get_metrics()
error_rate = metrics.get("record-error-rate", 0)
```

**Solutions:**
- Use `acks="all"` for durability
- Increase `retries` configuration
- Check broker logs for errors
- Verify network connectivity

#### 3. Duplicate Messages

**Symptom**: Same event processed multiple times

**Diagnosis:**

```python
# Check for duplicate event IDs
SELECT event_id, COUNT(*)
FROM bronze.events
GROUP BY event_id
HAVING COUNT(*) > 1
```

**Solutions:**
- Use idempotent producers (`enable_idempotence=True`)
- Implement deduplication in Flink job
- Use exactly-once semantics
- Add unique constraints in sink

#### 4. Serialization Errors

**Symptom**: Messages fail to deserialize

**Diagnosis:**

```python
# Validate event schema
errors = event.validate()
if errors:
    print(f"Validation errors: {errors}")
```

**Solutions:**
- Validate events before publishing
- Use schema registry for enforcement
- Handle schema evolution properly
- Add error handling for malformed messages

---

## Performance Tuning

### Producer Optimization

| Parameter | Development | Production |
|-----------|-------------|------------|
| `acks` | `1` | `all` |
| `batch_size` | `16384` | `32768` |
| `linger_ms` | `0` | `100` |
| `compression_type` | `none` | `snappy` |
| `buffer_memory` | `33554432` | `67108864` |

### Consumer Optimization

| Parameter | Low Latency | High Throughput |
|-----------|-------------|-----------------|
| `max_poll_records` | `100` | `500` |
| `fetch_min_bytes` | `1` | `1024` |
| `fetch_max_wait_ms` | `0` | `500` |

### Topic Optimization

| Metric | Formula | Example |
|--------|---------|---------|
| Partitions | `max(throughput/partition_throughput, num_consumers)` | `max(1000/100, 6) = 10` |
| Replication | `min(num_brokers, 3)` | `min(5, 3) = 3` |
| Retention | `avg_message_size * messages_per_day * retention_days` | `1KB * 1M * 7 = 7GB` |

---

## Next Steps

1. **Deploy Kafka Cluster**: See `QUICKSTART.md` for local setup
2. **Configure Topics**: Use admin utilities to create topics
3. **Implement Producers**: Use `EventProducer` for application integration
4. **Deploy Flink Jobs**: Implement Bronze → Silver → Gold pipeline
5. **Monitor Performance**: Setup Grafana dashboards
6. **Tune Configuration**: Optimize for your workload

---

**Related Documentation:**

- [Lakehouse Architecture](lakehouse.md) - Integration with Iceberg/Paimon
- [Lakehouse Examples](../guides/lakehouse-examples.md) - End-to-end examples
- [Deployment Guide](../../QUICKSTART.md) - Platform setup

---

*Last Updated: 2025-12-25*
*Status: Phase 3 Complete*
