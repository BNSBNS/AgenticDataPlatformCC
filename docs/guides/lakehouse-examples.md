# Lakehouse Usage Examples

Complete examples for working with the Medallion Architecture.

## Table of Contents
- [Getting Started](#getting-started)
- [Bronze Layer Examples](#bronze-layer-examples)
- [Silver Layer Examples](#silver-layer-examples)
- [Gold Layer Examples](#gold-layer-examples)
- [End-to-End Pipeline](#end-to-end-pipeline)
- [Advanced Patterns](#advanced-patterns)

## Getting Started

### Prerequisites

```bash
# Start development environment
make dev

# Initialize Iceberg catalog
python -c "
from src.lakehouse.iceberg import IcebergCatalogManager
catalog = IcebergCatalogManager()
catalog.initialize_medallion_namespaces()
"
```

### Import Required Modules

```python
from src.lakehouse.iceberg import IcebergCatalogManager, IcebergTableManager
from src.lakehouse.medallion import BronzeLayer, SilverLayer, GoldLayer
from pyiceberg.schema import Schema
from pyiceberg.types import NestedField, LongType, StringType, DoubleType, TimestampType
import pyarrow as pa
from datetime import datetime
```

## Bronze Layer Examples

### Example 1: Ingest API Events

```python
from src.lakehouse.medallion import BronzeLayer

# Initialize Bronze layer
bronze = BronzeLayer()

# Define schema
schema = Schema(
    NestedField(1, "event_id", LongType(), required=True),
    NestedField(2, "user_id", LongType(), required=True),
    NestedField(3, "event_type", StringType(), required=True),
    NestedField(4, "event_timestamp", TimestampType(), required=True),
    NestedField(5, "properties", StringType(), required=False),
)

# Create table (first time only)
bronze.create_table("api_events", schema, add_metadata=True)

# Ingest raw events
events = [
    {
        "event_id": 1,
        "user_id": 101,
        "event_type": "page_view",
        "event_timestamp": 1735100000000,
        "properties": '{"page": "/home"}',
    },
    {
        "event_id": 2,
        "user_id": 102,
        "event_type": "click",
        "event_timestamp": 1735100001000,
        "properties": '{"button": "signup"}',
    },
]

# Ingest with metadata
bronze.ingest_raw_data(
    table_name="api_events",
    data=events,
    source_system="web_api",
    source_file="events_2024-01-01.json",
    add_metadata=True,
)

print(f"✓ Ingested {len(events)} events to Bronze layer")
```

### Example 2: Ingest CSV Files

```python
import pandas as pd
from src.lakehouse.medallion import BronzeLayer

bronze = BronzeLayer()

# Read CSV
df = pd.read_csv("data/transactions.csv")

# Convert to PyArrow
arrow_table = pa.Table.from_pandas(df)

# Define schema from data
schema = arrow_table.schema

# Create table
bronze.create_table("transactions", schema)

# Ingest
bronze.ingest_raw_data(
    "transactions",
    arrow_table,
    source_system="payment_gateway",
    source_file="transactions.csv",
)
```

### Example 3: Query Bronze Data

```python
from src.lakehouse.medallion import BronzeLayer

bronze = BronzeLayer()

# Read all data
data = bronze.read_data("api_events")
print(f"Total events: {len(data)}")

# Read specific columns
data = bronze.read_data("api_events", columns=["event_id", "event_type", "user_id"])

# Read with limit
recent_events = bronze.read_data("api_events", limit=100)

# Get table statistics
stats = bronze.get_table_stats("api_events")
print(f"Table stats: {stats}")

# List all bronze tables
tables = bronze.list_tables()
print(f"Bronze tables: {tables}")
```

## Silver Layer Examples

### Example 4: Transform Bronze to Silver

```python
from src.lakehouse.medallion import BronzeLayer, SilverLayer

bronze = BronzeLayer()
silver = SilverLayer()

# Read from Bronze
bronze_data = bronze.read_data("api_events")

# Define Silver schema (validated schema)
schema = Schema(
    NestedField(1, "event_id", LongType(), required=True),
    NestedField(2, "user_id", LongType(), required=True),
    NestedField(3, "event_type", StringType(), required=True),
    NestedField(4, "event_timestamp", TimestampType(), required=True),
    NestedField(5, "event_date", LongType(), required=True),  # Derived field
)

# Create Silver table
silver.create_table("events", schema, partition_field="event_date")

# Transform with deduplication and validation
silver.transform_from_bronze(
    table_name="events",
    bronze_data=bronze_data,
    deduplicate=True,
    dedupe_keys=["event_id"],  # Unique key
    validate=True,
)

print("✓ Transformed Bronze to Silver with validation")
```

### Example 5: Data Cleansing

```python
from src.lakehouse.medallion import SilverLayer

silver = SilverLayer()

# Messy data with whitespace and duplicates
messy_data = [
    {"id": 1, "name": "  Alice  ", "email": "alice@example.com"},
    {"id": 2, "name": "Bob   ", "email": "bob@example.com  "},
    {"id": 1, "name": "  Alice  ", "email": "alice@example.com"},  # Duplicate
]

# Cleanse data
clean_data = silver.cleanse_data(messy_data)
print(f"Cleansed {len(messy_data)} → {len(clean_data)} records")

# Deduplicate
deduped_data = silver.deduplicate(clean_data, key_columns=["id"])
print(f"Deduplicated to {len(deduped_data)} unique records")
```

### Example 6: Read Silver Data with Filters

```python
from src.lakehouse.medallion import SilverLayer
from pyiceberg import expressions as expr

silver = SilverLayer()

# Read all data
all_data = silver.read_data("events")

# Read specific columns
user_events = silver.read_data(
    "events",
    columns=["user_id", "event_type", "event_timestamp"],
)

# Read with limit
recent = silver.read_data("events", limit=1000)

# Read with filter (using Iceberg expressions)
# Note: Full filter support requires Iceberg expression API
filtered = silver.read_data("events", limit=100)
```

## Gold Layer Examples

### Example 7: Daily Aggregations

```python
from src.lakehouse.medallion import SilverLayer, GoldLayer
from datetime import datetime

silver = SilverLayer()
gold = GoldLayer()

# Read Silver data
silver_data = silver.read_data("events")

# Define Gold schema for aggregations
from pyiceberg.schema import Schema
from pyiceberg.types import NestedField, StringType, LongType, DoubleType

agg_schema = Schema(
    NestedField(1, "date", LongType(), required=True),
    NestedField(2, "event_type", StringType(), required=True),
    NestedField(3, "event_count", LongType(), required=True),
    NestedField(4, "unique_users", LongType(), required=True),
)

# Create Gold table
gold.create_table(
    "daily_event_metrics",
    agg_schema,
    partition_field="date",
    partition_transform="month",
)

# Aggregate by date and event type
gold.aggregate_from_silver(
    table_name="daily_event_metrics",
    silver_data=silver_data,
    group_by=["date", "event_type"],
    aggregations={
        "event_count": "count",
        "user_id": "count",  # Unique users
    },
)

print("✓ Created daily aggregations in Gold layer")
```

### Example 8: Business Metrics

```python
from src.lakehouse.medallion import GoldLayer

gold = GoldLayer()

# Revenue data from Silver
revenue_data = [
    {"date": "2024-01-01", "revenue": 10000, "cost": 6000, "orders": 100},
    {"date": "2024-01-02", "revenue": 12000, "cost": 7000, "orders": 120},
    {"date": "2024-01-03", "revenue": 11000, "cost": 6500, "orders": 110},
]

# Compute business metrics
metrics = gold.compute_metrics(
    revenue_data,
    metrics={
        "total_revenue": "sum(revenue)",
        "total_cost": "sum(cost)",
        "total_orders": "sum(orders)",
    },
)

print(f"Business Metrics:")
print(f"  Total Revenue: ${metrics['total_revenue']:,}")
print(f"  Total Cost: ${metrics['total_cost']:,}")
print(f"  Total Orders: {metrics['total_orders']:,}")
print(f"  Profit: ${metrics['total_revenue'] - metrics['total_cost']:,}")
```

### Example 9: ML Feature Store

```python
from src.lakehouse.medallion import GoldLayer

gold = GoldLayer()

# User behavior data from Silver
user_data = [
    {"user_id": 1, "age": 25, "tenure_days": 365, "purchases": 12, "avg_order_value": 85.5, "churned": 0},
    {"user_id": 2, "age": 34, "tenure_days": 730, "purchases": 24, "avg_order_value": 120.0, "churned": 0},
    {"user_id": 3, "age": 45, "tenure_days": 180, "purchases": 3, "avg_order_value": 65.0, "churned": 1},
]

# Define feature schema
from pyiceberg.schema import Schema
from pyiceberg.types import NestedField, LongType, DoubleType

feature_schema = Schema(
    NestedField(1, "user_id", LongType(), required=True),
    NestedField(2, "age", LongType(), required=True),
    NestedField(3, "tenure_days", LongType(), required=True),
    NestedField(4, "purchases", LongType(), required=True),
    NestedField(5, "avg_order_value", DoubleType(), required=True),
    NestedField(6, "churned", LongType(), required=True),
)

# Create feature table
gold.create_table("user_churn_features", feature_schema)

# Populate features
gold.create_ml_features(
    table_name="user_churn_features",
    data=user_data,
    feature_columns=["age", "tenure_days", "purchases", "avg_order_value"],
    target_column="churned",
)

print("✓ Created ML feature table in Gold layer")
```

## End-to-End Pipeline

### Example 10: Complete Data Pipeline

```python
"""
Complete end-to-end pipeline: API → Bronze → Silver → Gold
"""

from src.lakehouse.medallion import BronzeLayer, SilverLayer, GoldLayer
from pyiceberg.schema import Schema
from pyiceberg.types import NestedField, LongType, StringType, DoubleType
import json

# Step 1: Initialize layers
bronze = BronzeLayer()
silver = SilverLayer()
gold = GoldLayer()

# Step 2: Define schemas
raw_schema = Schema(
    NestedField(1, "order_id", LongType(), required=True),
    NestedField(2, "customer_id", LongType(), required=True),
    NestedField(3, "product_id", StringType(), required=True),
    NestedField(4, "amount", DoubleType(), required=True),
    NestedField(5, "order_date", StringType(), required=True),
)

# Step 3: Create tables
bronze.create_table("orders", raw_schema)
silver.create_table("orders", raw_schema, partition_field="order_date")

gold_schema = Schema(
    NestedField(1, "order_date", StringType(), required=True),
    NestedField(2, "product_id", StringType(), required=True),
    NestedField(3, "total_amount", DoubleType(), required=True),
    NestedField(4, "order_count", LongType(), required=True),
)
gold.create_table("daily_product_sales", gold_schema, partition_field="order_date")

# Step 4: Ingest raw data (Bronze)
raw_orders = [
    {"order_id": 1, "customer_id": 101, "product_id": "P001", "amount": 99.99, "order_date": "2024-01-01"},
    {"order_id": 2, "customer_id": 102, "product_id": "P002", "amount": 149.99, "order_date": "2024-01-01"},
    {"order_id": 3, "customer_id": 101, "product_id": "P001", "amount": 99.99, "order_date": "2024-01-02"},
]

bronze.ingest_raw_data(
    "orders",
    raw_orders,
    source_system="ecommerce_api",
    source_file="orders.json",
)
print("✓ Step 1: Ingested to Bronze")

# Step 5: Transform to Silver
bronze_data = bronze.read_data("orders")
silver.transform_from_bronze(
    "orders",
    bronze_data,
    deduplicate=True,
    dedupe_keys=["order_id"],
    validate=True,
)
print("✓ Step 2: Transformed to Silver")

# Step 6: Aggregate to Gold
silver_data = silver.read_data("orders")
gold.aggregate_from_silver(
    "daily_product_sales",
    silver_data,
    group_by=["order_date", "product_id"],
    aggregations={
        "amount": "sum",
        "order_id": "count",
    },
)
print("✓ Step 3: Aggregated to Gold")

# Step 7: Query results
daily_sales = gold.read_data("daily_product_sales")
print(f"\n✓ Pipeline complete! Generated {len(daily_sales)} daily aggregations")
```

## Advanced Patterns

### Example 11: Time Travel Queries

```python
from src.lakehouse.iceberg import TimeTravelManager
from datetime import datetime, timedelta

time_travel = TimeTravelManager()

# List all snapshots
snapshots = time_travel.list_snapshots("bronze.orders")
print(f"Found {len(snapshots)} snapshots")

# Query as of yesterday
yesterday = datetime.now() - timedelta(days=1)
historical_data = time_travel.read_at_timestamp(
    "bronze.orders",
    timestamp=yesterday,
)
print(f"Orders as of yesterday: {len(historical_data)}")

# Rollback if needed (careful!)
# time_travel.rollback_to_snapshot("bronze.orders", snapshot_id=12345)
```

### Example 12: Incremental Processing

```python
from src.lakehouse.medallion import BronzeLayer
from datetime import datetime, timedelta

bronze = BronzeLayer()

# Get last processing timestamp
last_processed = datetime(2024, 1, 1, 0, 0, 0)

# Read only new data (pseudo-code - actual implementation needs Iceberg filters)
new_data = bronze.read_data(
    "events",
    # filter_expr=expr.greater_than("ingestion_timestamp", last_processed),
    limit=10000,
)

print(f"Processing {len(new_data)} new records")
```

### Example 13: Schema Evolution

```python
from src.lakehouse.iceberg import IcebergTableManager

table_mgr = IcebergTableManager()

# Load existing table
table = table_mgr.catalog_manager.load_table("bronze.events")

# Schema evolution operations (pseudo-code)
# Actual implementation requires Iceberg schema evolution API

# Add new column
# table.update_schema().add_column("new_field", StringType()).commit()

# Rename column
# table.update_schema().rename_column("old_name", "new_name").commit()

# Note: Full schema evolution support requires Iceberg Python API enhancements
```

## Best Practices

### 1. Always Use Transactions

```python
# Good: Atomic operations
bronze.ingest_raw_data("events", data)  # ACID transaction

# Bad: Manual file writes (not atomic)
# Don't manually write Parquet files to S3
```

### 2. Partition Appropriately

```python
# Good: Partition by commonly filtered column
bronze.create_table("events", schema)  # Auto-partitioned by ingestion_timestamp

# Good: Business-appropriate partitioning
silver.create_table("events", schema, partition_field="event_date", partition_transform="day")

# Bad: Too fine-grained (creates too many files)
# partition_transform="hour"  # Unless you have very high volume
```

### 3. Use Schema Validation in Silver+

```python
# Good: Enforce schema in Silver
silver = SilverLayer(enforce_schema_validation=True)

# Good: Validate explicitly
silver.validate_data(data, schema)

# Bad: Skip validation (Bronze only)
# silver = SilverLayer(enforce_schema_validation=False)
```

### 4. Monitor Table Health

```python
# Check table stats regularly
stats = bronze.get_table_stats("events")
print(f"Row count: {stats['row_count']}")
print(f"Size: {stats['size_bytes'] / (1024**3):.2f} GB")
print(f"Snapshots: {len(stats['snapshots'])}")

# Clean up old snapshots if needed
# table.expire_snapshots(older_than=timedelta(days=7))
```

## Troubleshooting

### Issue: "Table already exists"

```python
# Check if table exists before creating
from src.lakehouse.iceberg import IcebergCatalogManager

catalog = IcebergCatalogManager()

if not catalog.table_exists("bronze.events"):
    bronze.create_table("events", schema)
else:
    print("Table already exists, skipping creation")
```

### Issue: "Schema mismatch"

```python
# Ensure data matches schema
import pyarrow as pa

# Get table schema
table = catalog.load_table("bronze.events")
expected_schema = table.schema()

# Validate data schema matches
data_table = pa.Table.from_pylist(data)
# Compare schemas and cast if needed
```

## Next Steps

- [Streaming Integration](./streaming-examples.md)
- [Data Quality Checks](./data-quality.md)
- [Performance Optimization](./optimization.md)
- [Production Deployment](./production.md)
