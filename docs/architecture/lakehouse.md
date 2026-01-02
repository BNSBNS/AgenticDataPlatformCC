# Lakehouse Architecture

## Overview

The platform implements a **Lakehouse Architecture** using **Apache Iceberg** as the primary table format and **Apache Paimon** for streaming workloads. This combines the best of data lakes (low-cost storage, schema flexibility) with data warehouses (ACID transactions, schema enforcement).

## Why Lakehouse?

Traditional architectures force a choice between:
- **Data Lakes**: Cheap, flexible, but lack ACID guarantees and performance
- **Data Warehouses**: Fast, structured, but expensive and inflexible

Lakehouse architecture provides:
✅ **ACID Transactions** - Reliable, consistent data operations
✅ **Schema Evolution** - Change schemas without breaking pipelines
✅ **Time Travel** - Query historical versions of data
✅ **Scalability** - Handle petabytes of data cost-effectively
✅ **Performance** - Optimized for analytics queries
✅ **Open Standards** - No vendor lock-in

## Technology Choices

### Apache Iceberg (Primary)

**Why Iceberg?**
- **Production-ready**: Battle-tested at Netflix, Apple, Adobe
- **ACID compliance**: Full transactional guarantees
- **Schema evolution**: Safe, automatic schema changes
- **Hidden partitioning**: Automatic partition pruning
- **Time travel**: Query any point in history
- **Incremental reads**: Efficiently process only new data
- **AWS integration**: First-class Glue Catalog support

**Use Cases:**
- Primary storage for Bronze, Silver, Gold layers
- Historical data analysis
- Batch processing workloads
- Data warehouse replacement

### Apache Paimon (Streaming)

**Why Paimon?**
- **Streaming-first**: Designed for real-time data
- **Changelog support**: Native CDC (Change Data Capture)
- **Flink integration**: Seamless with Apache Flink
- **Low latency**: Real-time updates
- **Compaction**: Automatic file management

**Use Cases:**
- Real-time data marts
- Streaming aggregations
- CDC from databases
- Low-latency analytics

## Medallion Architecture

The platform organizes data into three layers (Bronze → Silver → Gold) following Databricks' Medallion Architecture pattern.

### 🥉 Bronze Layer - Raw Data

**Purpose**: Land raw, immutable data from sources

**Characteristics:**
- **Append-only**: No updates or deletes
- **Schema-on-read**: Minimal transformation
- **Full audit trail**: Complete lineage
- **Partition strategy**: Day (ingestion_timestamp)
- **Compression**: Snappy (fast writes)
- **Retention**: 90 days

**Metadata Columns:**
```python
- ingestion_timestamp: When data was ingested
- source_system: Origin system name
- source_file: Source file/identifier
- record_hash: MD5 hash for deduplication
```

**Example:**
```python
from src.lakehouse.medallion import BronzeLayer

bronze = BronzeLayer()

# Create table
bronze.create_table("events", schema)

# Ingest raw data
bronze.ingest_raw_data(
    "events",
    data=events,
    source_system="api",
    source_file="2024-01-01.json"
)

# Read data
data = bronze.read_data("events", limit=1000)
```

### 🥈 Silver Layer - Refined Data

**Purpose**: Store validated, cleansed, standardized data

**Characteristics:**
- **Schema validation**: Enforced data types
- **Deduplication**: Remove duplicate records
- **Data cleansing**: Trim whitespace, handle nulls
- **Standardization**: Consistent formats
- **Partition strategy**: Day or Month (business_date)
- **Compression**: Zstandard (better compression)
- **Retention**: 2 years (730 days)

**Transformations:**
1. **Cleansing**: Trim strings, handle nulls
2. **Deduplication**: Based on business keys
3. **Validation**: Type checking, constraints
4. **Standardization**: Date formats, units

**Example:**
```python
from src.lakehouse.medallion import SilverLayer

silver = SilverLayer()

# Create table
silver.create_table("events", schema, partition_field="event_date")

# Transform from bronze
silver.transform_from_bronze(
    "events",
    bronze_data=bronze_table,
    deduplicate=True,
    dedupe_keys=["event_id"],
    validate=True
)

# Read validated data
data = silver.read_data("events", limit=1000)
```

### 🥇 Gold Layer - Business Data

**Purpose**: Curated, aggregated, BI-ready data

**Characteristics:**
- **Denormalized**: Wide tables for query performance
- **Aggregated**: Business-level metrics
- **Optimized**: Sorted, partitioned for analytics
- **Partition strategy**: Month or Year
- **Compression**: Zstandard (maximum compression)
- **Retention**: 7 years (2555 days)

**Patterns:**
1. **Aggregations**: Daily/weekly/monthly rollups
2. **Denormalization**: Join facts with dimensions
3. **Feature Engineering**: ML-ready feature tables
4. **Business Metrics**: KPIs, ratios, trends

**Example:**
```python
from src.lakehouse.medallion import GoldLayer

gold = GoldLayer()

# Create metrics table
gold.create_table("daily_metrics", schema, partition_field="date", partition_transform="month")

# Aggregate from silver
gold.aggregate_from_silver(
    "daily_metrics",
    silver_data=silver_table,
    group_by=["date", "product"],
    aggregations={
        "revenue": "sum",
        "orders": "count",
        "avg_order_value": "avg"
    }
)

# Create ML features
gold.create_ml_features(
    "user_features",
    data=user_data,
    feature_columns=["age", "tenure", "purchases"],
    target_column="churn"
)
```

## Data Flow

```
Sources (APIs, DBs, Files)
         ↓
    [Ingestion]
         ↓
    🥉 BRONZE (Raw)
    - Append-only
    - Full history
    - 90 days
         ↓
    [Validation & Cleansing]
         ↓
    🥈 SILVER (Refined)
    - Deduplicated
    - Validated
    - 2 years
         ↓
    [Aggregation & Enrichment]
         ↓
    🥇 GOLD (Curated)
    - Business metrics
    - ML features
    - 7 years
         ↓
    [Consumption]
    - BI Tools
    - ML Models
    - APIs
    - Reports
```

## Partitioning Strategy

### Bronze Layer
**Partition by**: Day (ingestion_timestamp)
**Why**: Efficient data lifecycle management, easy to delete old data

```sql
PARTITION BY day(ingestion_timestamp)
```

### Silver Layer
**Partition by**: Day or Month (business_date)
**Why**: Balance between query performance and file count

```sql
PARTITION BY day(event_date)  -- For recent data queries
PARTITION BY month(event_date)  -- For historical analysis
```

### Gold Layer
**Partition by**: Month or Year
**Why**: Long-term storage, fewer files, better for aggregate queries

```sql
PARTITION BY month(metric_date)  -- Most common
PARTITION BY year(metric_date)   -- For very long retention
```

## Schema Evolution

Iceberg supports safe schema evolution:

```python
# Add new column (non-breaking)
ALTER TABLE bronze.events ADD COLUMN user_agent string

# Rename column
ALTER TABLE bronze.events RENAME COLUMN old_name TO new_name

# Change column type (if compatible)
ALTER TABLE bronze.events ALTER COLUMN value TYPE double

# Drop column
ALTER TABLE bronze.events DROP COLUMN deprecated_field
```

## Time Travel

Query historical versions of data:

```python
from src.lakehouse.iceberg import TimeTravelManager
from datetime import datetime

time_travel = TimeTravelManager()

# Query at specific snapshot
data = time_travel.read_at_snapshot(
    table="bronze.events",
    snapshot_id=1234567890
)

# Query as of timestamp
data = time_travel.read_at_timestamp(
    table="bronze.events",
    timestamp=datetime(2024, 1, 1, 12, 0, 0)
)

# Rollback to previous version
time_travel.rollback_to_snapshot(
    table="bronze.events",
    snapshot_id=1234567890
)
```

## Performance Optimization

### 1. Partition Pruning
Iceberg automatically prunes partitions based on filters:

```python
# Only scans relevant partitions
SELECT * FROM bronze.events
WHERE ingestion_timestamp >= '2024-01-01'
  AND ingestion_timestamp < '2024-01-02'
```

### 2. File Compaction
Merge small files into larger ones:

```python
# Compact table
table.compact()

# Or via Flink/Spark job
```

### 3. Sorting
Sort data by commonly filtered columns:

```python
# Table properties
{
    "write.distribution-mode": "hash",
    "write.target-file-size-bytes": "134217728"  # 128 MB
}
```

### 4. Caching
Leverage query result caching:

```python
# Metadata caching in Iceberg
# Query result caching in Trino/Spark
```

## Monitoring

Track lakehouse health with Prometheus metrics:

```python
# Table size
storage_table_size_bytes{layer="bronze", table="events"}

# Row count
storage_table_rows_count{layer="silver", table="users"}

# Write latency
storage_write_duration_seconds{layer="gold", operation="aggregate"}

# Snapshot count
storage_snapshot_count{layer="bronze", table="events"}
```

## Best Practices

### 1. Bronze Layer
✅ **DO**:
- Preserve raw data exactly as received
- Add audit metadata columns
- Use append-only pattern
- Partition by ingestion_timestamp

❌ **DON'T**:
- Transform or clean data
- Drop records
- Update existing records
- Skip metadata

### 2. Silver Layer
✅ **DO**:
- Enforce schema validation
- Deduplicate based on business keys
- Standardize formats consistently
- Document transformation logic

❌ **DON'T**:
- Skip validation
- Lose source system context
- Create overly complex transformations
- Ignore data quality issues

### 3. Gold Layer
✅ **DO**:
- Create denormalized views
- Pre-aggregate common metrics
- Optimize for query patterns
- Document business logic

❌ **DON'T**:
- Create redundant aggregations
- Skip documentation
- Ignore partition strategy
- Forget about refresh schedules

## Troubleshooting

### Issue: Slow Queries

**Diagnosis**:
```python
# Check partition pruning
EXPLAIN SELECT * FROM bronze.events WHERE date = '2024-01-01'

# Check file count
SELECT * FROM table_metadata
```

**Solution**:
- Compact small files
- Optimize partition strategy
- Add sort order
- Review filter predicates

### Issue: Schema Conflicts

**Diagnosis**:
```python
# Check schema history
SELECT * FROM table_schema_versions
```

**Solution**:
- Use schema evolution (ALTER TABLE)
- Version schemas explicitly
- Document breaking changes
- Test thoroughly

### Issue: High Storage Costs

**Diagnosis**:
```python
# Check retention
SELECT layer, SUM(size_bytes) FROM tables GROUP BY layer
```

**Solution**:
- Enforce retention policies
- Compact old data
- Optimize compression
- Archive to cheaper storage

## Next Steps

- [Query Layer Documentation](./query-layer.md)
- [Data Governance](./governance.md)
- [Streaming Architecture](./streaming.md)
- [Usage Examples](../guides/lakehouse-examples.md)
