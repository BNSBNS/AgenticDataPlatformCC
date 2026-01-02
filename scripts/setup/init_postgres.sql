-- Initialize PostgreSQL database for Data Platform

-- Create schemas
CREATE SCHEMA IF NOT EXISTS metadata;
CREATE SCHEMA IF NOT EXISTS governance;
CREATE SCHEMA IF NOT EXISTS monitoring;

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA metadata TO dataplatform;
GRANT ALL PRIVILEGES ON SCHEMA governance TO dataplatform;
GRANT ALL PRIVILEGES ON SCHEMA monitoring TO dataplatform;

-- Create metadata tables
CREATE TABLE IF NOT EXISTS metadata.tables (
    id SERIAL PRIMARY KEY,
    namespace VARCHAR(255) NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    layer VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    properties JSONB,
    UNIQUE(namespace, table_name)
);

CREATE TABLE IF NOT EXISTS metadata.schemas (
    id SERIAL PRIMARY KEY,
    table_id INTEGER REFERENCES metadata.tables(id),
    schema_json JSONB NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create governance tables
CREATE TABLE IF NOT EXISTS governance.data_quality_checks (
    id SERIAL PRIMARY KEY,
    table_id INTEGER REFERENCES metadata.tables(id),
    check_name VARCHAR(255) NOT NULL,
    check_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    result JSONB,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS governance.audit_log (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NOT NULL,
    resource_id VARCHAR(255),
    details JSONB,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address INET
);

-- Create monitoring tables
CREATE TABLE IF NOT EXISTS monitoring.job_executions (
    id SERIAL PRIMARY KEY,
    job_name VARCHAR(255) NOT NULL,
    job_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    error_message TEXT,
    metrics JSONB
);

-- Create indexes
CREATE INDEX idx_tables_namespace ON metadata.tables(namespace);
CREATE INDEX idx_tables_layer ON metadata.tables(layer);
CREATE INDEX idx_schemas_table_id ON metadata.schemas(table_id);
CREATE INDEX idx_quality_checks_table_id ON governance.data_quality_checks(table_id);
CREATE INDEX idx_quality_checks_executed_at ON governance.data_quality_checks(executed_at);
CREATE INDEX idx_audit_log_timestamp ON governance.audit_log(timestamp);
CREATE INDEX idx_audit_log_user_id ON governance.audit_log(user_id);
CREATE INDEX idx_job_executions_job_name ON monitoring.job_executions(job_name);
CREATE INDEX idx_job_executions_started_at ON monitoring.job_executions(started_at);

COMMENT ON SCHEMA metadata IS 'Metadata catalog for tables and schemas';
COMMENT ON SCHEMA governance IS 'Data governance, quality, and audit logs';
COMMENT ON SCHEMA monitoring IS 'Job execution monitoring';
