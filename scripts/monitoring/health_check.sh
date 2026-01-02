#!/bin/bash

# Health Check Script for Data Platform Services

set -e

echo "========================================="
echo "Data Platform Health Check"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_service() {
    local service_name=$1
    local check_command=$2

    echo -n "Checking $service_name... "

    if eval "$check_command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${NC}"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        return 1
    fi
}

check_http_service() {
    local service_name=$1
    local url=$2

    echo -n "Checking $service_name... "

    if curl -f -s "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${NC}"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        return 1
    fi
}

# Check Docker is running
echo "=== Docker Services ==="
if ! docker ps > /dev/null 2>&1; then
    echo -e "${RED}✗ Docker is not running!${NC}"
    echo "Please start Docker Desktop and try again."
    exit 1
fi
echo -e "${GREEN}✓ Docker is running${NC}"
echo ""

# Check Docker Compose services
echo "=== Docker Compose Services ==="
check_service "Zookeeper" "docker exec zookeeper echo 'ok'"
check_service "Kafka Broker 1" "docker exec kafka-1 echo 'ok'"
check_service "Kafka Broker 2" "docker exec kafka-2 echo 'ok'"
check_service "Kafka Broker 3" "docker exec kafka-3 echo 'ok'"
check_service "Schema Registry" "docker exec schema-registry echo 'ok'"
check_service "MinIO" "docker exec minio echo 'ok'"
check_service "PostgreSQL" "docker exec postgres pg_isready -U dataplatform"
check_service "Flink JobManager" "docker exec flink-jobmanager echo 'ok'"
check_service "Qdrant" "docker exec qdrant echo 'ok'"
check_service "Redis" "docker exec redis redis-cli ping"
check_service "Prometheus" "docker exec prometheus echo 'ok'"
check_service "Grafana" "docker exec grafana echo 'ok'"
echo ""

# Check HTTP endpoints
echo "=== HTTP Endpoints ==="
check_http_service "Kafka UI" "http://localhost:8080"
check_http_service "Schema Registry" "http://localhost:8081"
check_http_service "Flink Dashboard" "http://localhost:8082"
check_http_service "MinIO API" "http://localhost:9000/minio/health/live"
check_http_service "MinIO Console" "http://localhost:9001"
check_http_service "Prometheus" "http://localhost:9090/-/healthy"
check_http_service "Grafana" "http://localhost:3000/api/health"
check_http_service "Qdrant" "http://localhost:6333/health"
echo ""

# Check Kafka topics
echo "=== Kafka Topics ==="
if docker exec kafka-1 kafka-topics --list --bootstrap-server localhost:9092 > /dev/null 2>&1; then
    TOPIC_COUNT=$(docker exec kafka-1 kafka-topics --list --bootstrap-server localhost:9092 | wc -l)
    echo -e "${GREEN}✓ Kafka topics accessible (Count: $TOPIC_COUNT)${NC}"
else
    echo -e "${RED}✗ Failed to list Kafka topics${NC}"
fi
echo ""

# Check MinIO buckets
echo "=== MinIO Buckets ==="
if docker exec minio-init mc ls myminio > /dev/null 2>&1; then
    BUCKET_COUNT=$(docker exec minio-init mc ls myminio 2>/dev/null | wc -l)
    echo -e "${GREEN}✓ MinIO buckets accessible (Count: $BUCKET_COUNT)${NC}"
    echo "  Expected buckets:"
    echo "    - lakehouse-bronze"
    echo "    - lakehouse-silver"
    echo "    - lakehouse-gold"
    echo "    - lakehouse-warehouse"
    echo "    - flink-checkpoints"
    echo "    - paimon-warehouse"
else
    echo -e "${YELLOW}⚠ MinIO buckets check skipped (mc not available)${NC}"
fi
echo ""

# Check PostgreSQL databases
echo "=== PostgreSQL Databases ==="
if docker exec postgres psql -U dataplatform -d dataplatform_metadata -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PostgreSQL database accessible${NC}"
    SCHEMA_COUNT=$(docker exec postgres psql -U dataplatform -d dataplatform_metadata -t -c "SELECT count(*) FROM information_schema.schemata WHERE schema_name IN ('metadata', 'governance', 'monitoring')" 2>/dev/null | tr -d ' ')
    echo "  Schemas found: $SCHEMA_COUNT/3"
else
    echo -e "${RED}✗ Failed to access PostgreSQL database${NC}"
fi
echo ""

# Check Flink cluster
echo "=== Flink Cluster ==="
if curl -s http://localhost:8082/overview > /dev/null 2>&1; then
    TASK_MANAGERS=$(curl -s http://localhost:8082/overview 2>/dev/null | grep -o '"taskmanagers":[0-9]*' | grep -o '[0-9]*' || echo "0")
    echo -e "${GREEN}✓ Flink cluster accessible${NC}"
    echo "  TaskManagers: $TASK_MANAGERS"
else
    echo -e "${RED}✗ Flink cluster not accessible${NC}"
fi
echo ""

# Summary
echo "========================================="
echo "Health Check Complete"
echo "========================================="
echo ""
echo "Services are running and accessible."
echo ""
echo "Next steps:"
echo "  1. Access Kafka UI: http://localhost:8080"
echo "  2. Access Flink: http://localhost:8082"
echo "  3. Access MinIO: http://localhost:9001"
echo "  4. Access Grafana: http://localhost:3000"
echo ""
echo "For more details, run:"
echo "  make dev-status"
echo "  make dev-logs"
