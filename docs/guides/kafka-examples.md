# Kafka Usage Examples - Agentic Data Platform

Practical examples for using Kafka infrastructure in the data platform.

---

## Table of Contents

1. [Admin Operations](#admin-operations)
2. [Event Publishing](#event-publishing)
3. [Event Consumption](#event-consumption)
4. [Schema Management](#schema-management)
5. [Error Handling](#error-handling)
6. [Advanced Patterns](#advanced-patterns)

---

## Admin Operations

### Example 1: Create Topics for Medallion Architecture

```python
from src.streaming.kafka.admin import KafkaAdminManager, TopicConfig

# Initialize admin manager
admin = KafkaAdminManager(bootstrap_servers="localhost:9092")

# Define topic configurations for different layers
topics = [
    TopicConfig(
        name="raw-events",
        num_partitions=6,
        replication_factor=3,
        retention_ms=604800000,  # 7 days
        compression_type="snappy",
        min_insync_replicas=2,
    ),
    TopicConfig(
        name="bronze-events",
        num_partitions=6,
        replication_factor=3,
        retention_ms=7776000000,  # 90 days
        compression_type="zstd",
        min_insync_replicas=2,
    ),
    TopicConfig(
        name="silver-events",
        num_partitions=6,
        replication_factor=3,
        retention_ms=63072000000,  # 2 years
        compression_type="zstd",
        min_insync_replicas=2,
    ),
]

# Create all topics
results = admin.create_topics_batch(topics, skip_if_exists=True)

for topic_name, success in results.items():
    if success:
        print(f"✓ Created topic: {topic_name}")
    else:
        print(f"✗ Failed to create topic: {topic_name}")
```

### Example 2: List and Describe Topics

```python
from src.streaming.kafka.admin import KafkaAdminManager

admin = KafkaAdminManager(bootstrap_servers="localhost:9092")

# List all topics
topics = admin.list_topics()
print(f"Found {len(topics)} topics:")
for topic in topics:
    print(f"  - {topic}")

# Describe specific topic
topic_info = admin.describe_topic("raw-events")
print(f"\nTopic: {topic_info['name']}")
print(f"Partitions: {topic_info['num_partitions']}")

for partition in topic_info['partitions']:
    print(f"  Partition {partition['partition']}: Leader={partition['leader']}")
```

### Example 3: Monitor Consumer Groups

```python
from src.streaming.kafka.admin import KafkaAdminManager

admin = KafkaAdminManager(bootstrap_servers="localhost:9092")

# List consumer groups
groups = admin.get_consumer_groups()
print(f"Active consumer groups: {len(groups)}")

# Describe a specific group
group_info = admin.describe_consumer_group("bronze-writer")
print(f"\nGroup: {group_info['group_id']}")
print(f"State: {group_info['state']}")
print(f"Members: {len(group_info['members'])}")

for member in group_info['members']:
    print(f"  - {member['client_id']} ({member['member_id']})")
```

### Example 4: Check Topic Offsets

```python
from src.streaming.kafka.admin import KafkaAdminManager

admin = KafkaAdminManager(bootstrap_servers="localhost:9092")

# Get offset information for a topic
offsets = admin.get_topic_offsets("raw-events")

print("Partition Offsets:")
for partition, offset_info in offsets.items():
    earliest = offset_info['earliest']
    latest = offset_info['latest']
    lag = latest - earliest
    print(f"  Partition {partition}: {earliest} -> {latest} (lag: {lag})")
```

---

## Event Publishing

### Example 5: Publish User Action Events

```python
from src.ingestion.streaming import EventProducer, UserActionEvent
from datetime import datetime
import uuid

# Initialize producer
producer = EventProducer(bootstrap_servers="localhost:9092")

# Create user action events
events = [
    UserActionEvent(
        event_id=str(uuid.uuid4()),
        event_timestamp=datetime.utcnow().isoformat() + "Z",
        source_system="web-app",
        user_id="user-123",
        action="login",
        resource="dashboard",
        metadata={"ip_address": "192.168.1.1", "user_agent": "Chrome/120.0"},
    ),
    UserActionEvent(
        event_id=str(uuid.uuid4()),
        event_timestamp=datetime.utcnow().isoformat() + "Z",
        source_system="web-app",
        user_id="user-123",
        action="view_product",
        resource="product-456",
        metadata={"session_id": "session-789"},
    ),
    UserActionEvent(
        event_id=str(uuid.uuid4()),
        event_timestamp=datetime.utcnow().isoformat() + "Z",
        source_system="web-app",
        user_id="user-123",
        action="add_to_cart",
        resource="product-456",
        metadata={"quantity": "2"},
    ),
]

# Publish events
results = producer.publish_batch(events)

# Check results
successful = sum(1 for r in results if r.get('success', False))
print(f"Published {successful}/{len(events)} events successfully")

# Close producer
producer.close()
```

### Example 6: Publish Transaction Events

```python
from src.ingestion.streaming import EventProducer, TransactionEvent
from datetime import datetime
import uuid

with EventProducer(bootstrap_servers="localhost:9092") as producer:
    # Create transaction event
    event = TransactionEvent(
        event_id=str(uuid.uuid4()),
        event_timestamp=datetime.utcnow().isoformat() + "Z",
        source_system="payment-gateway",
        transaction_id=f"txn-{uuid.uuid4()}",
        amount=99.99,
        currency="USD",
        transaction_type="purchase",
        metadata={
            "payment_method": "credit_card",
            "card_last_four": "4242",
            "merchant_id": "merchant-789",
        },
    )

    # Publish event
    result = producer.publish_event(event)

    if result['success']:
        print(f"✓ Transaction published to partition {result['partition']}")
        print(f"  Offset: {result['offset']}")
    else:
        print(f"✗ Failed to publish: {result.get('error')}")
```

### Example 7: Publish Metric Events

```python
from src.ingestion.streaming import EventProducer, MetricEvent
from datetime import datetime
import uuid
import time

producer = EventProducer(bootstrap_servers="localhost:9092")

# Simulate metrics collection
for i in range(10):
    event = MetricEvent(
        event_id=str(uuid.uuid4()),
        event_timestamp=datetime.utcnow().isoformat() + "Z",
        source_system="api-server",
        metric_name="request_latency_ms",
        metric_value=45.0 + (i * 2.5),  # Simulated latency
        metric_unit="milliseconds",
        tags={
            "endpoint": "/api/users",
            "method": "GET",
            "status_code": "200",
        },
    )

    result = producer.publish_event(event)
    print(f"Metric {i+1}: Partition {result.get('partition')}, Offset {result.get('offset')}")

    time.sleep(0.1)  # 100ms interval

producer.close()
```

### Example 8: Publish Raw Data Without Schema

```python
from src.ingestion.streaming import EventProducer
import uuid

producer = EventProducer(bootstrap_servers="localhost:9092")

# Publish arbitrary data (useful for legacy systems)
raw_data = {
    "sensor_id": "sensor-001",
    "temperature": 23.5,
    "humidity": 65.2,
    "timestamp": "2025-12-25T10:30:00Z",
    "location": "warehouse-a",
}

result = producer.publish_raw_data(
    topic="raw-sensor-data",
    data=raw_data,
    source_system="iot-gateway",
    event_type="sensor_reading",
)

if result['success']:
    print(f"✓ Raw data published successfully")

producer.close()
```

---

## Event Consumption

### Example 9: Basic Event Consumption

```python
from src.streaming.kafka.consumer import KafkaConsumerManager, ConsumerConfig

# Configure consumer
config = ConsumerConfig(
    bootstrap_servers="localhost:9092",
    group_id="analytics-consumer",
    topics=["raw-events"],
    auto_offset_reset="earliest",
    enable_auto_commit=True,
)

# Create consumer
consumer = KafkaConsumerManager(config)

# Consume messages
print("Consuming messages (Ctrl+C to stop)...")
try:
    while True:
        messages = consumer.consume(timeout_ms=1000, max_messages=10)

        for message in messages:
            print(f"Topic: {message['topic']}, Partition: {message['partition']}")
            print(f"Offset: {message['offset']}, Key: {message['key']}")
            print(f"Value: {message['value']}")
            print("-" * 60)

except KeyboardInterrupt:
    print("\nStopping consumer...")
finally:
    consumer.close()
```

### Example 10: Manual Offset Management

```python
from src.streaming.kafka.consumer import KafkaConsumerManager, ConsumerConfig

config = ConsumerConfig(
    bootstrap_servers="localhost:9092",
    group_id="manual-commit-consumer",
    topics=["raw-events"],
    enable_auto_commit=False,  # Manual commit
)

with KafkaConsumerManager(config) as consumer:
    batch_size = 100
    processed = 0

    while True:
        messages = consumer.consume(timeout_ms=5000, max_messages=batch_size)

        if not messages:
            break

        for message in messages:
            # Process message
            process_event(message['value'])
            processed += 1

        # Commit after processing batch
        consumer.commit()
        print(f"Processed and committed {processed} messages")
```

### Example 11: Seek to Specific Offset

```python
from src.streaming.kafka.consumer import KafkaConsumerManager, ConsumerConfig

config = ConsumerConfig(
    bootstrap_servers="localhost:9092",
    group_id="replay-consumer",
    topics=["raw-events"],
    enable_auto_commit=False,
)

consumer = KafkaConsumerManager(config)

# Get current offsets
current_offsets = consumer.get_offsets()
print("Current offsets:", current_offsets)

# Seek to specific offset (replay from earlier point)
consumer.seek("raw-events", partition=0, offset=1000)
consumer.seek("raw-events", partition=1, offset=1000)

print("Seeked to offset 1000 for partitions 0 and 1")

# Consume from new position
messages = consumer.consume(timeout_ms=1000, max_messages=50)
print(f"Consumed {len(messages)} messages from offset 1000")

consumer.close()
```

### Example 12: Pause and Resume Consumption

```python
from src.streaming.kafka.consumer import KafkaConsumerManager, ConsumerConfig
import time

config = ConsumerConfig(
    bootstrap_servers="localhost:9092",
    group_id="pausable-consumer",
    topics=["raw-events"],
)

consumer = KafkaConsumerManager(config)

# Consume normally
messages = consumer.consume(timeout_ms=1000)
print(f"Consumed {len(messages)} messages")

# Pause specific partitions
consumer.pause([("raw-events", 0), ("raw-events", 1)])
print("Paused partitions 0 and 1")

time.sleep(5)

# Try to consume (should get no messages from paused partitions)
messages = consumer.consume(timeout_ms=1000)
print(f"Consumed {len(messages)} messages (paused partitions excluded)")

# Resume partitions
consumer.resume([("raw-events", 0), ("raw-events", 1)])
print("Resumed partitions 0 and 1")

# Consume again
messages = consumer.consume(timeout_ms=1000)
print(f"Consumed {len(messages)} messages (all partitions)")

consumer.close()
```

---

## Schema Management

### Example 13: Event Validation

```python
from src.ingestion.streaming import EventSchema
from datetime import datetime
import uuid

# Create event with valid data
valid_event = EventSchema(
    event_id=str(uuid.uuid4()),
    event_type="user_action",
    event_timestamp=datetime.utcnow().isoformat() + "Z",
    source_system="web-app",
    payload={"action": "login", "user_id": "user-123"},
)

# Validate event
errors = valid_event.validate()
if not errors:
    print("✓ Event is valid")
else:
    print(f"✗ Validation errors: {errors}")

# Create event with invalid data
invalid_event = EventSchema(
    event_id="",  # Empty ID (invalid)
    event_type="user_action",
    event_timestamp="invalid-timestamp",  # Invalid format
    source_system="web-app",
    payload="not a dict",  # Wrong type
)

errors = invalid_event.validate()
print(f"\nInvalid event errors: {errors}")
```

### Example 14: Custom Event Types

```python
from dataclasses import dataclass
from typing import Dict, Any, Optional
from src.ingestion.streaming.event_schemas import EventSchema, EventType

@dataclass
class OrderEvent(EventSchema):
    """Custom event type for e-commerce orders."""

    def __init__(
        self,
        event_id: str,
        event_timestamp: str,
        source_system: str,
        order_id: str,
        customer_id: str,
        total_amount: float,
        items: list,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize order event."""
        payload = {
            "order_id": order_id,
            "customer_id": customer_id,
            "total_amount": total_amount,
            "items": items,
        }

        super().__init__(
            event_id=event_id,
            event_type="order",  # Custom event type
            event_timestamp=event_timestamp,
            source_system=source_system,
            payload=payload,
            metadata=metadata or {},
        )

# Use custom event type
from src.ingestion.streaming import EventProducer
from datetime import datetime
import uuid

producer = EventProducer(bootstrap_servers="localhost:9092")

order_event = OrderEvent(
    event_id=str(uuid.uuid4()),
    event_timestamp=datetime.utcnow().isoformat() + "Z",
    source_system="e-commerce",
    order_id="order-789",
    customer_id="customer-123",
    total_amount=299.99,
    items=[
        {"product_id": "prod-1", "quantity": 2, "price": 99.99},
        {"product_id": "prod-2", "quantity": 1, "price": 100.01},
    ],
    metadata={"payment_method": "credit_card"},
)

# Publish to custom topic
result = producer.publish_event(order_event, topic="raw-orders")
print(f"Order event published: {result['success']}")

producer.close()
```

---

## Error Handling

### Example 15: Producer Retry Logic

```python
from src.streaming.kafka.producer import KafkaProducerManager, ProducerConfig

# Configure producer with retries
config = ProducerConfig(
    bootstrap_servers="localhost:9092",
    acks="all",
    retries=5,  # Retry up to 5 times
    compression_type="snappy",
)

producer = KafkaProducerManager(config)

# Send message with retry
result = producer.send_message(
    topic="raw-events",
    message={"data": "important event"},
    key="event-123",
    max_retries=3,  # Override default retries
)

if result['success']:
    print(f"✓ Message sent successfully after {result.get('attempts', 1)} attempt(s)")
else:
    print(f"✗ Message failed after {result.get('attempts')} attempts")
    print(f"  Error: {result.get('error')}")

producer.close()
```

### Example 16: Dead Letter Queue Pattern

```python
from src.streaming.kafka.consumer import KafkaConsumerManager, ConsumerConfig
from src.streaming.kafka.producer import KafkaProducerManager, ProducerConfig
from datetime import datetime

# Setup consumer and DLQ producer
consumer_config = ConsumerConfig(
    bootstrap_servers="localhost:9092",
    group_id="dlq-processor",
    topics=["raw-events"],
    enable_auto_commit=False,
)

producer_config = ProducerConfig(
    bootstrap_servers="localhost:9092",
)

consumer = KafkaConsumerManager(consumer_config)
dlq_producer = KafkaProducerManager(producer_config)

try:
    messages = consumer.consume(timeout_ms=1000, max_messages=10)

    for message in messages:
        try:
            # Process message
            process_event(message['value'])

            # Success - commit offset
            consumer.commit_offsets({
                (message['topic'], message['partition']): message['offset'] + 1
            })

        except Exception as e:
            # Processing failed - send to DLQ
            dlq_message = {
                "original_topic": message['topic'],
                "original_partition": message['partition'],
                "original_offset": message['offset'],
                "original_value": message['value'],
                "error": str(e),
                "error_timestamp": datetime.utcnow().isoformat() + "Z",
            }

            dlq_producer.send_message(
                topic="dlq-events",
                message=dlq_message,
                key=message['key'],
            )

            # Commit offset (don't reprocess)
            consumer.commit_offsets({
                (message['topic'], message['partition']): message['offset'] + 1
            })

            print(f"✗ Message sent to DLQ: {e}")

finally:
    consumer.close()
    dlq_producer.close()
```

---

## Advanced Patterns

### Example 17: Exactly-Once Processing (Idempotent Producer)

```python
from src.streaming.kafka.producer import KafkaProducerManager, ProducerConfig

# Enable idempotent producer
config = ProducerConfig(
    bootstrap_servers="localhost:9092",
    acks="all",
    retries=Integer.MAX_VALUE,  # Unlimited retries
    additional_config={
        "enable.idempotence": True,  # Exactly-once semantics
        "max.in.flight.requests.per.connection": 1,
    },
)

producer = KafkaProducerManager(config)

# Messages will be deduplicated automatically
for i in range(100):
    result = producer.send_message(
        topic="raw-events",
        message={"event_id": f"event-{i}", "data": f"value-{i}"},
        key=f"key-{i}",
    )

producer.close()
```

### Example 18: Transactional Producer

```python
from src.streaming.kafka.producer import KafkaProducerManager, ProducerConfig

# Configure transactional producer
config = ProducerConfig(
    bootstrap_servers="localhost:9092",
    transactional_id="my-transaction-id",  # Required for transactions
    acks="all",
)

producer = KafkaProducerManager(config)

try:
    # Begin transaction
    producer._producer.begin_transaction()

    # Send multiple messages atomically
    producer.send_message("raw-events", {"id": 1, "data": "first"})
    producer.send_message("raw-events", {"id": 2, "data": "second"})
    producer.send_message("raw-events", {"id": 3, "data": "third"})

    # Commit transaction (all or nothing)
    producer._producer.commit_transaction()
    print("✓ Transaction committed successfully")

except Exception as e:
    # Abort transaction on error
    producer._producer.abort_transaction()
    print(f"✗ Transaction aborted: {e}")

finally:
    producer.close()
```

### Example 19: Monitoring Consumer Lag

```python
from src.streaming.kafka.consumer import KafkaConsumerManager, ConsumerConfig
from src.common.metrics import kafka_consumer_lag

config = ConsumerConfig(
    bootstrap_servers="localhost:9092",
    group_id="monitored-consumer",
    topics=["raw-events"],
)

consumer = KafkaConsumerManager(config)

# Get watermarks for each partition
for partition in consumer.get_partitions("raw-events"):
    watermarks = consumer.get_watermarks("raw-events", partition)
    current_offset = consumer.get_offsets().get(("raw-events", partition), 0)

    lag = watermarks['high'] - current_offset

    # Record metric
    kafka_consumer_lag.labels(
        topic="raw-events",
        partition=str(partition),
        group_id="monitored-consumer"
    ).set(lag)

    print(f"Partition {partition}: Lag = {lag} messages")

consumer.close()
```

---

## Next Steps

1. **Setup Kafka**: Follow [QUICKSTART.md](../../QUICKSTART.md) to start Kafka cluster
2. **Create Topics**: Use Example 1 to initialize topics
3. **Implement Producers**: Integrate EventProducer into your applications
4. **Deploy Consumers**: Create Flink jobs or standalone consumers
5. **Monitor Performance**: Setup Prometheus metrics and Grafana dashboards

---

**Related Documentation:**

- [Streaming Architecture](../architecture/streaming.md) - Architecture overview
- [Lakehouse Examples](lakehouse-examples.md) - Integration with lakehouse
- [Testing Guide](../../TESTING_GUIDE.md) - Running tests

---

*Last Updated: 2025-12-25*
*Total Examples: 19*
