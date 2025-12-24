#!/bin/bash

# Create Kafka Topics for Data Platform

set -e

echo "Creating Kafka topics..."

KAFKA_BROKER="localhost:9092"

# Function to create topic
create_topic() {
    local topic_name=$1
    local partitions=$2
    local replication_factor=$3
    local retention_ms=$4

    echo "Creating topic: $topic_name"

    docker exec kafka-1 kafka-topics \
        --create \
        --if-not-exists \
        --bootstrap-server $KAFKA_BROKER \
        --topic $topic_name \
        --partitions $partitions \
        --replication-factor $replication_factor \
        --config retention.ms=$retention_ms \
        --config cleanup.policy=delete

    echo "✓ Topic $topic_name created"
}

# Create topics based on configuration
create_topic "raw-events" 6 3 604800000        # 7 days
create_topic "cdc-streams" 6 3 2592000000       # 30 days
create_topic "api-events" 3 3 604800000         # 7 days
create_topic "mcp-requests" 3 3 259200000       # 3 days
create_topic "dead-letter-queue" 3 3 2592000000 # 30 days

# Additional topics for different data sources
create_topic "bronze-events" 6 3 7776000000     # 90 days
create_topic "silver-events" 6 3 63072000000    # 730 days (2 years)
create_topic "gold-events" 3 3 220752000000     # 2555 days (7 years)

# Data quality topics
create_topic "data-quality-results" 3 3 2592000000  # 30 days

# Lineage tracking
create_topic "lineage-events" 3 3 2592000000    # 30 days

# Agent communication
create_topic "agent-requests" 3 3 604800000     # 7 days
create_topic "agent-responses" 3 3 604800000    # 7 days

echo ""
echo "✓ All Kafka topics created successfully!"
echo ""
echo "List of created topics:"
docker exec kafka-1 kafka-topics --list --bootstrap-server $KAFKA_BROKER
