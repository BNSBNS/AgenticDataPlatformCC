# Quick Start Guide

Get the Agentic Data Platform running in 5 minutes!

## Prerequisites

- **Docker Desktop** (with at least 8GB RAM allocated)
- **Python 3.11+**
- **Poetry** (install with `pip install poetry`)
- **Git**

## Step 1: Clone and Setup

```bash
# Clone the repository
git clone https://github.com/BNSBNS/AgenticDataPlatformCC.git
cd AgenticDataPlatformCC

# Run automated setup
make setup
```

This will:
- Copy `.env.example` to `.env`
- Install all Python dependencies via Poetry

## Step 2: Start Development Environment

```bash
make dev
```

This starts Docker Compose with:
- ✅ Kafka cluster (3 brokers)
- ✅ Apache Flink (JobManager + TaskManagers)
- ✅ MinIO (S3-compatible storage)
- ✅ PostgreSQL (metadata database)
- ✅ Qdrant (vector database)
- ✅ Redis (caching)
- ✅ Prometheus + Grafana (monitoring)
- ✅ Kafka UI (management interface)

**Wait 2-3 minutes** for all services to start.

## Step 3: Verify Services

Check that all services are running:

```bash
make dev-status
```

You should see all services in "Up" state.

## Step 4: Access Web UIs

Open these URLs in your browser:

| Service | URL | Credentials |
|---------|-----|-------------|
| Kafka UI | http://localhost:8080 | None |
| Flink Dashboard | http://localhost:8082 | None |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | None |

## Step 5: Initialize Platform

```bash
# Create Kafka topics
make kafka-topics-create

# Initialize PostgreSQL database
# (This happens automatically on first start)

# When Phase 2 is complete, initialize Iceberg catalog:
# make iceberg-catalog-init
```

## Step 6: Test the Platform

Run a quick health check:

```bash
make health-check
```

## Step 7: Explore

### View Kafka Topics

```bash
make kafka-topics-list
```

### Check Logs

```bash
# View all logs
make dev-logs

# View specific service
docker-compose logs -f kafka-1
docker-compose logs -f flink-jobmanager
```

### Interactive Python Shell

```bash
# Enter Poetry shell
make shell

# Now you can import and use platform components:
# >>> from src.common import get_logger, settings
# >>> logger = get_logger(__name__)
# >>> logger.info("Hello from data platform!")
```

## Step 8: Stop Environment

When you're done:

```bash
# Stop services (preserves data)
make dev-stop

# Stop and remove all data
make dev-clean
```

## Troubleshooting

### Services Won't Start

```bash
# Check Docker Desktop is running
docker ps

# Restart Docker Desktop and try again
make dev-restart
```

### Port Conflicts

If you see port conflict errors, check what's using the ports:

```bash
# Windows
netstat -ano | findstr "9092"
netstat -ano | findstr "8080"

# Linux/Mac
lsof -i :9092
lsof -i :8080
```

### Out of Memory

Docker Desktop needs at least 8GB RAM. To configure:
1. Open Docker Desktop
2. Settings → Resources
3. Increase Memory to 8GB or more
4. Apply & Restart

### Clean Start

If something goes wrong, clean everything and start fresh:

```bash
make clean-all
make dev
```

## Next Steps

Once your environment is running:

1. **Read the Architecture**: Check `docs/architecture/` for design details
2. **Explore Examples**: See `examples/` for sample notebooks
3. **Check Status**: Review `IMPLEMENTATION_STATUS.md` for what's ready
4. **Develop**: Follow the plan in `.claude/plans/temporal-sparking-hare.md`

## Learning Resources

### Kafka

```bash
# List topics
make kafka-topics-list

# Check topic details
docker exec kafka-1 kafka-topics --describe --topic raw-events --bootstrap-server localhost:9092

# Produce test message
docker exec -it kafka-1 kafka-console-producer --topic raw-events --bootstrap-server localhost:9092
# Type a message and press Enter
# Press Ctrl+C to exit

# Consume messages
docker exec -it kafka-1 kafka-console-consumer --topic raw-events --from-beginning --bootstrap-server localhost:9092
```

### MinIO

1. Go to http://localhost:9001
2. Login: minioadmin / minioadmin
3. Browse buckets:
   - `lakehouse-bronze`
   - `lakehouse-silver`
   - `lakehouse-gold`

### PostgreSQL

```bash
# Connect to database
docker exec -it postgres psql -U dataplatform -d dataplatform_metadata

# List schemas
\dn

# List tables in metadata schema
\dt metadata.*

# Query tables
SELECT * FROM metadata.tables;

# Exit
\q
```

## Common Development Commands

```bash
# Code quality
make format        # Format code with black
make lint          # Run linters
make type-check    # Type checking with mypy

# Testing
make test          # Run all tests
make test-unit     # Unit tests only
make test-coverage # Coverage report

# Development
make jupyter       # Start Jupyter Lab
make shell         # Enter Poetry shell
```

## Getting Help

- Check `README.md` for comprehensive documentation
- Review `IMPLEMENTATION_STATUS.md` for current progress
- See `Makefile` for all available commands
- Open an issue on GitHub for bugs/questions

---

**You're all set!** 🚀

The platform foundation is ready. Continue with Phase 2 to build the lakehouse layer.
