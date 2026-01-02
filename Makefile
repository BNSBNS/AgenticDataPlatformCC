# ==============================================================================
# AGENTIC DATA PLATFORM - MAKEFILE
# ==============================================================================
# Common operations for development, testing, and deployment
#
# Usage:
#   make help              Show this help message
#   make setup             Initial project setup
#   make dev               Start local development environment
#   make test              Run tests
#   make deploy-aws        Deploy to AWS
# ==============================================================================

.PHONY: help
help:  ## Show this help message
	@echo "Agentic Data Platform - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ==============================================================================
# SETUP & INSTALLATION
# ==============================================================================

.PHONY: setup
setup: ## Initial project setup (install dependencies, create .env)
	@echo "Setting up project..."
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env file from .env.example"; \
	fi
	@poetry install
	@echo "✓ Setup complete!"

.PHONY: install
install: ## Install dependencies with Poetry
	poetry install

.PHONY: install-dev
install-dev: ## Install dependencies including dev tools
	poetry install --with dev

.PHONY: update
update: ## Update dependencies
	poetry update

# ==============================================================================
# DEVELOPMENT ENVIRONMENT
# ==============================================================================

.PHONY: dev
dev: ## Start local development environment (Docker Compose)
	@echo "Starting development environment..."
	docker-compose up -d
	@echo "✓ Development environment started!"
	@echo ""
	@echo "Services:"
	@echo "  Kafka UI:         http://localhost:8080"
	@echo "  Flink Dashboard:  http://localhost:8082"
	@echo "  MinIO Console:    http://localhost:9001"
	@echo "  Grafana:          http://localhost:3000"
	@echo "  Prometheus:       http://localhost:9090"
	@echo ""

.PHONY: dev-stop
dev-stop: ## Stop development environment
	docker-compose down

.PHONY: dev-restart
dev-restart: ## Restart development environment
	docker-compose restart

.PHONY: dev-clean
dev-clean: ## Stop and remove all containers, volumes, and networks
	docker-compose down -v --remove-orphans
	@echo "✓ Development environment cleaned!"

.PHONY: dev-logs
dev-logs: ## View logs from all services
	docker-compose logs -f

.PHONY: dev-status
dev-status: ## Check status of development services
	docker-compose ps

# ==============================================================================
# CODE QUALITY
# ==============================================================================

.PHONY: format
format: ## Format code with black and isort
	@echo "Formatting code..."
	poetry run black src tests
	poetry run isort src tests
	@echo "✓ Code formatted!"

.PHONY: lint
lint: ## Lint code with ruff and mypy
	@echo "Linting code..."
	poetry run ruff check src tests
	poetry run mypy src
	@echo "✓ Linting complete!"

.PHONY: lint-fix
lint-fix: ## Auto-fix linting issues
	poetry run ruff check --fix src tests

.PHONY: type-check
type-check: ## Run type checking with mypy
	poetry run mypy src

# ==============================================================================
# TESTING
# ==============================================================================

.PHONY: test
test: ## Run tests
	@echo "Running tests..."
	poetry run pytest
	@echo "✓ Tests complete!"

.PHONY: test-unit
test-unit: ## Run unit tests only
	poetry run pytest tests/unit -v

.PHONY: test-integration
test-integration: ## Run integration tests only
	poetry run pytest tests/integration -v

.PHONY: test-coverage
test-coverage: ## Run tests with coverage report
	poetry run pytest --cov=src --cov-report=html --cov-report=term
	@echo "Coverage report: htmlcov/index.html"

.PHONY: test-watch
test-watch: ## Run tests in watch mode
	poetry run pytest-watch

# ==============================================================================
# DATABASE & MIGRATIONS
# ==============================================================================

.PHONY: db-init
db-init: ## Initialize database schemas
	@echo "Initializing database..."
	python scripts/setup/init_database.py
	@echo "✓ Database initialized!"

.PHONY: db-migrate
db-migrate: ## Run database migrations
	python scripts/migration/migrate.py

.PHONY: db-reset
db-reset: ## Reset database (WARNING: destroys all data)
	@echo "WARNING: This will destroy all data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		python scripts/setup/reset_database.py; \
		echo "✓ Database reset!"; \
	fi

# ==============================================================================
# KAFKA
# ==============================================================================

.PHONY: kafka-topics-create
kafka-topics-create: ## Create Kafka topics
	@echo "Creating Kafka topics..."
	bash scripts/setup/create_kafka_topics.sh
	@echo "✓ Kafka topics created!"

.PHONY: kafka-topics-list
kafka-topics-list: ## List Kafka topics
	docker exec kafka-1 kafka-topics --list --bootstrap-server localhost:9092

.PHONY: kafka-topics-delete
kafka-topics-delete: ## Delete all Kafka topics (WARNING: destroys data)
	@echo "WARNING: This will delete all Kafka topics!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker exec kafka-1 kafka-topics --delete --all --bootstrap-server localhost:9092; \
		echo "✓ Kafka topics deleted!"; \
	fi

# ==============================================================================
# LAKEHOUSE
# ==============================================================================

.PHONY: iceberg-catalog-init
iceberg-catalog-init: ## Initialize Iceberg catalog
	@echo "Initializing Iceberg catalog..."
	poetry run dataplatform catalog init
	@echo "✓ Iceberg catalog initialized!"

.PHONY: iceberg-tables-list
iceberg-tables-list: ## List Iceberg tables
	poetry run dataplatform catalog list

.PHONY: paimon-catalog-init
paimon-catalog-init: ## Initialize Paimon catalog
	@echo "Initializing Paimon catalog..."
	poetry run dataplatform paimon init
	@echo "✓ Paimon catalog initialized!"

# ==============================================================================
# FLINK JOBS
# ==============================================================================

.PHONY: flink-submit-bronze-to-silver
flink-submit-bronze-to-silver: ## Submit Bronze to Silver Flink job
	poetry run dataplatform flink submit bronze-to-silver

.PHONY: flink-submit-silver-to-gold
flink-submit-silver-to-gold: ## Submit Silver to Gold Flink job
	poetry run dataplatform flink submit silver-to-gold

.PHONY: flink-jobs-list
flink-jobs-list: ## List running Flink jobs
	curl -s http://localhost:8082/jobs | jq

.PHONY: flink-jobs-cancel-all
flink-jobs-cancel-all: ## Cancel all running Flink jobs
	@echo "Cancelling all Flink jobs..."
	poetry run dataplatform flink cancel --all

# ==============================================================================
# DATA GENERATION
# ==============================================================================

.PHONY: generate-sample-data
generate-sample-data: ## Generate sample data for testing
	@echo "Generating sample data..."
	poetry run python scripts/data_generation/generate_sample_data.py
	@echo "✓ Sample data generated!"

.PHONY: load-test-data
load-test-data: ## Load test data into platform
	poetry run python scripts/data_generation/load_test_data.py

# ==============================================================================
# API & SERVICES
# ==============================================================================

.PHONY: api-dev
api-dev: ## Start API server in development mode
	poetry run uvicorn src.api.rest.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: api-prod
api-prod: ## Start API server in production mode
	poetry run gunicorn src.api.rest.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

.PHONY: mcp-servers-start
mcp-servers-start: ## Start all MCP servers
	@echo "Starting MCP servers..."
	poetry run dataplatform mcp start --all

.PHONY: dashboard
dashboard: ## Start monitoring dashboard
	poetry run streamlit run src/monitoring/lineage_dashboard/app.py

# ==============================================================================
# DOCUMENTATION
# ==============================================================================

.PHONY: docs-serve
docs-serve: ## Serve documentation locally
	poetry run mkdocs serve

.PHONY: docs-build
docs-build: ## Build documentation
	poetry run mkdocs build

.PHONY: docs-deploy
docs-deploy: ## Deploy documentation to GitHub Pages
	poetry run mkdocs gh-deploy

# ==============================================================================
# DEPLOYMENT
# ==============================================================================

.PHONY: deploy-aws
deploy-aws: ## Deploy to AWS (Terraform)
	@echo "Deploying to AWS..."
	cd infrastructure/terraform/aws && terraform init && terraform apply
	@echo "✓ Deployed to AWS!"

.PHONY: deploy-k8s
deploy-k8s: ## Deploy to Kubernetes
	@echo "Deploying to Kubernetes..."
	kubectl apply -k infrastructure/kubernetes/overlays/prod
	@echo "✓ Deployed to Kubernetes!"

.PHONY: deploy-vm
deploy-vm: ## Deploy to VMs (Ansible)
	@echo "Deploying to VMs..."
	cd infrastructure/ansible && ansible-playbook -i inventory/prod playbooks/setup_platform.yml
	@echo "✓ Deployed to VMs!"

.PHONY: destroy-aws
destroy-aws: ## Destroy AWS infrastructure
	@echo "WARNING: This will destroy all AWS resources!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		cd infrastructure/terraform/aws && terraform destroy; \
		echo "✓ AWS infrastructure destroyed!"; \
	fi

# ==============================================================================
# UTILITIES
# ==============================================================================

.PHONY: shell
shell: ## Open Poetry shell
	poetry shell

.PHONY: jupyter
jupyter: ## Start Jupyter Lab
	poetry run jupyter lab

.PHONY: clean
clean: ## Clean up temporary files
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".DS_Store" -delete
	rm -rf htmlcov/ .coverage build/ dist/ *.egg-info
	@echo "✓ Cleanup complete!"

.PHONY: clean-all
clean-all: clean dev-clean ## Clean everything (code + docker)
	@echo "✓ All cleaned!"

.PHONY: health-check
health-check: ## Run health check on all services
	@echo "Checking service health..."
	@poetry run python scripts/monitoring/health_check.sh

.PHONY: version
version: ## Show version information
	@poetry version
	@echo "Python: $(shell python --version)"
	@echo "Poetry: $(shell poetry --version)"

# ==============================================================================
# CI/CD
# ==============================================================================

.PHONY: ci
ci: lint test ## Run CI pipeline locally
	@echo "✓ CI pipeline complete!"

.PHONY: pre-commit
pre-commit: format lint test ## Run pre-commit checks
	@echo "✓ Pre-commit checks complete!"

# ==============================================================================
# DEFAULT
# ==============================================================================

.DEFAULT_GOAL := help
