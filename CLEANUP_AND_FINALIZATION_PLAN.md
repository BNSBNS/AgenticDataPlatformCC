# Repository Cleanup and Finalization Plan

**Date**: 2025-12-26
**Status**: In Progress
**Priority**: Production Readiness

---

## Executive Summary

Comprehensive analysis identified 38 of 48 Python files (79%) with improvement opportunities across:
- 8 Critical security/data loss issues
- 24 High priority reliability/maintainability issues
- 31 Medium priority performance/best practice issues

This document outlines immediate fixes and long-term improvements.

---

## CRITICAL FIXES (Immediate - Same Day)

### 1. SQL Injection Vulnerability (CRITICAL)

**Location**: `src/common/security.py` lines 275-303

**Issue**: `sanitize_sql()` uses string replacement which is bypassable
```python
# UNSAFE - Current implementation
sanitized = query
for pattern in sql_patterns:
    sanitized = sanitized.replace(pattern, "")  # Can be bypassed with encoding
```

**Fix**: Remove sanitize_sql() and enforce parameterized queries only
```python
# Add to security.py
def validate_parameterized_query(query: str, params: Dict) -> bool:
    """
    Validate that query uses parameterized placeholders.

    Args:
        query: SQL query with placeholders
        params: Query parameters

    Returns:
        True if valid, False otherwise

    Raises:
        SecurityError: If query appears to have inline values
    """
    # Check for suspicious patterns that suggest unparameterized queries
    dangerous_patterns = [
        r"'\s*OR\s*'",  # Classic SQL injection
        r"--",  # SQL comments
        r"/\*",  # Block comments
        r";\s*DROP",  # Command chaining
        r"UNION\s+SELECT",  # Union-based injection
    ]

    import re
    for pattern in dangerous_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            raise SecurityError(f"Query contains suspicious pattern: {pattern}")

    # Verify placeholders are used
    if params and not any(placeholder in query for placeholder in ['?', ':param', '%s']):
        raise SecurityError("Query has parameters but no placeholders detected")

    return True
```

**Update**: Modify all query execution to use parameterized queries
- `src/query/trino/executor.py`: Enforce parameterized queries
- `src/lakehouse/iceberg/table_manager.py`: Validate filters before execution

**Testing**: Add unit tests for injection attempt detection

**Estimated Time**: 2 hours

---

### 2. Idempotency Tracking for Event Publishing (CRITICAL)

**Location**: `src/ingestion/streaming/event_producer.py` lines 69-135

**Issue**: No idempotency tracking - duplicate events can be published

**Fix**: Add idempotency key tracking
```python
from datetime import datetime, timedelta
from typing import Set
import threading

class EventProducer:
    def __init__(self):
        # ... existing init ...
        self._idempotency_cache: Dict[str, datetime] = {}
        self._cache_lock = threading.Lock()
        self._cache_ttl = timedelta(hours=24)

    def _check_idempotency(self, idempotency_key: str) -> bool:
        """Check if event with this key was already published."""
        with self._cache_lock:
            # Clean expired entries
            now = datetime.utcnow()
            expired = [k for k, v in self._idempotency_cache.items() if now - v > self._cache_ttl]
            for k in expired:
                del self._idempotency_cache[k]

            # Check if key exists
            if idempotency_key in self._idempotency_cache:
                logger.warning(
                    "Duplicate event detected, skipping",
                    idempotency_key=idempotency_key
                )
                return False

            # Mark as published
            self._idempotency_cache[idempotency_key] = now
            return True

    def publish_event(self, event: EventSchema, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Publish event with idempotency support.

        Args:
            event: Event to publish
            idempotency_key: Optional key for deduplication (defaults to event_id)
        """
        # Use event_id as idempotency key if not provided
        key = idempotency_key or event.event_id

        # Check idempotency
        if not self._check_idempotency(key):
            return {
                "success": True,
                "skipped": True,
                "reason": "duplicate_event",
                "idempotency_key": key
            }

        # ... rest of publish logic ...
```

**Alternative**: Use Redis for distributed idempotency tracking in production

**Testing**: Add tests for duplicate event detection

**Estimated Time**: 3 hours

---

### 3. Missing Input Validation (CRITICAL)

**Locations**: Multiple files

**Fix 1**: Add validation to `src/query/trino/executor.py`
```python
def execute(self, query: str, schema: Optional[str] = None, parameters: Optional[Dict] = None):
    """Execute SQL query with validation."""
    # Validate query is not empty
    if not query or not query.strip():
        raise QueryError("Query cannot be empty")

    # Validate parameterized query if parameters provided
    if parameters:
        from src.common.security import validate_parameterized_query
        validate_parameterized_query(query, parameters)

    # Validate schema name (prevent injection in schema switch)
    if schema:
        if not re.match(r'^[a-zA-Z0-9_]+$', schema):
            raise QueryError(f"Invalid schema name: {schema}")

    # ... rest of execution ...
```

**Fix 2**: Add validation to `src/lakehouse/medallion/silver_layer.py`
```python
def deduplicate(self, data, key_columns: List[str]) -> Any:
    """Deduplicate data with validation."""
    # Validate key_columns exist in data
    df = data.to_pandas()
    missing_columns = set(key_columns) - set(df.columns)
    if missing_columns:
        raise ValueError(
            f"Key columns not found in data: {missing_columns}. "
            f"Available columns: {list(df.columns)}"
        )

    # Validate key_columns is not empty
    if not key_columns:
        raise ValueError("At least one key column required for deduplication")

    # ... rest of deduplication ...
```

**Estimated Time**: 2 hours

---

## HIGH PRIORITY FIXES (Within 1 Week)

### 4. Circuit Breaker Pattern for External Services

**Locations**:
- `src/query/trino/executor.py`
- `src/vector/stores/qdrant_store.py`

**Implementation**: Add circuit breaker utility

**File**: `src/common/resilience.py` (NEW)
```python
"""
Resilience patterns for external service calls.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Any, Optional
import threading

from src.common.logging import get_logger
from src.common.exceptions import CircuitBreakerOpenError

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: int = 60
    name: str = "default"


class CircuitBreaker:
    """
    Circuit breaker for external service calls.

    Prevents cascading failures by failing fast when service is down.
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self._lock = threading.Lock()

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    logger.info(
                        "Circuit breaker half-open, attempting recovery",
                        name=self.config.name
                    )
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker open for {self.config.name}"
                    )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True

        elapsed = datetime.utcnow() - self.last_failure_time
        return elapsed.total_seconds() >= self.config.timeout_seconds

    def _on_success(self):
        """Handle successful call."""
        with self._lock:
            self.failure_count = 0

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.success_count = 0
                    logger.info(
                        "Circuit breaker closed, service recovered",
                        name=self.config.name
                    )

    def _on_failure(self):
        """Handle failed call."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.utcnow()

            if self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN
                logger.error(
                    "Circuit breaker opened due to failures",
                    name=self.config.name,
                    failures=self.failure_count
                )

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.success_count = 0
```

**Usage Example**: Update `src/query/trino/executor.py`
```python
from src.common.resilience import CircuitBreaker, CircuitBreakerConfig

class TrinoQueryExecutor:
    def __init__(self, ...):
        # ... existing init ...
        self.circuit_breaker = CircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout_seconds=30,
                name="trino_executor"
            )
        )

    def execute(self, query: str, ...):
        """Execute with circuit breaker protection."""
        return self.circuit_breaker.call(self._execute_internal, query, ...)

    def _execute_internal(self, query: str, ...):
        """Internal execution logic."""
        # ... existing execution code ...
```

**Estimated Time**: 4 hours

---

### 5. Retry Mechanisms with Exponential Backoff

**File**: `src/common/resilience.py` (add to above)

```python
from functools import wraps
import time
import random

def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retriable_exceptions: tuple = (Exception,)
):
    """
    Decorator for retry logic with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential calculation
        jitter: Add random jitter to prevent thundering herd
        retriable_exceptions: Tuple of exceptions to retry on
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retriable_exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"Max retries ({max_retries}) exceeded",
                            function=func.__name__,
                            error=str(e)
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(
                        initial_delay * (exponential_base ** attempt),
                        max_delay
                    )

                    # Add jitter
                    if jitter:
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"Retry attempt {attempt + 1}/{max_retries}",
                        function=func.__name__,
                        delay=delay,
                        error=str(e)
                    )

                    time.sleep(delay)

            raise last_exception

        return wrapper
    return decorator
```

**Usage Example**: Update Kafka consumer
```python
from src.common.resilience import retry_with_backoff
from confluent_kafka import KafkaException

@retry_with_backoff(
    max_retries=3,
    retriable_exceptions=(KafkaException,)
)
def consume(self, timeout_ms: int = 1000, max_messages: Optional[int] = None):
    """Consume with automatic retry."""
    # ... existing consume logic ...
```

**Estimated Time**: 3 hours

---

### 6. Comprehensive Error Handling

**Fix**: Update exception handling to be specific

**File**: `src/streaming/kafka/consumer.py` lines 186-190
```python
# BEFORE (too broad)
try:
    value = json.loads(value.decode("utf-8"))
except:
    pass

# AFTER (specific with logging)
try:
    value = json.loads(value.decode("utf-8"))
except (json.JSONDecodeError, UnicodeDecodeError) as e:
    logger.warning(
        "Failed to deserialize message value",
        topic=msg.topic(),
        partition=msg.partition(),
        offset=msg.offset(),
        error=str(e)
    )
    # Keep raw value
    value = msg.value()
```

**Estimated Time**: 2 hours for all files

---

## MEDIUM PRIORITY (Within 2 Weeks)

### 7. Refactor Long Functions

**Targets**:
- `src/lakehouse/medallion/gold_layer.py::aggregate_from_silver()` (75 lines)
- `src/streaming/kafka/admin.py::get_topic_offsets()` (50 lines)

**Example**: Extract conversion logic from aggregate_from_silver
```python
def aggregate_from_silver(self, table_name, silver_data, ...):
    """Aggregate with extracted helper methods."""
    # Convert to pandas
    df = self._convert_to_pandas(silver_data)

    # Perform aggregation
    aggregated = self._perform_aggregation(df, aggregations)

    # Write results
    self._write_aggregated_data(table_name, aggregated, partition_by)

def _convert_to_pandas(self, arrow_table) -> pd.DataFrame:
    """Extract conversion logic."""
    return arrow_table.to_pandas()

def _perform_aggregation(self, df, aggregations):
    """Extract aggregation logic."""
    # ... aggregation code ...

def _write_aggregated_data(self, table_name, df, partition_by):
    """Extract write logic."""
    # ... write code ...
```

**Estimated Time**: 4 hours

---

### 8. Remove Redundant Code

**Items to Clean**:

1. **`src/streaming/kafka/producer.py::_serialize_json()`** - Remove, use inline
2. **`src/streaming/kafka/consumer.py`** - Consolidate seek methods
3. **`src/common/security.py::sanitize_sql()`** - Remove (security risk)

**Estimated Time**: 2 hours

---

### 9. Add Missing Type Hints

**Example**: `src/vector/embeddings/generator.py`
```python
from typing import List

def generate_batch(self, texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for multiple texts.

    Args:
        texts: List of input texts

    Returns:
        List of embedding vectors
    """
    # ... implementation ...
```

**Estimated Time**: 3 hours

---

### 10. Configuration Externalization

**Fix**: Move hardcoded values to config

**File**: `src/common/config.py` - Add new fields
```python
class Settings(BaseSettings):
    # ... existing fields ...

    # Kafka settings
    kafka_producer_flush_timeout: int = Field(default=10, description="Producer flush timeout in seconds")
    kafka_consumer_poll_timeout: float = Field(default=1.0, description="Consumer poll timeout in seconds")

    # Lakehouse settings
    partition_field_id_start: int = Field(default=1000, description="Starting ID for partition fields")

    # Query settings
    query_log_max_length: int = Field(default=100, description="Max query length to log")

    # Idempotency settings
    idempotency_cache_ttl_hours: int = Field(default=24, description="TTL for idempotency cache")
```

**Estimated Time**: 2 hours

---

## LOW PRIORITY (Nice to Have)

### 11. Performance Optimizations

1. **Batch hash computation**: Move to vectorized operations
2. **Lazy loading**: Don't load all tables for stats
3. **Connection pooling**: Reuse Trino connections

**Estimated Time**: 6 hours

---

### 12. Test Coverage Improvements

**Target**: Increase from current ~40% to 70%+

**Priority Areas**:
1. Medallion layer transformations (integration tests)
2. Error recovery scenarios
3. Idempotency checks
4. Circuit breaker behavior

**Estimated Time**: 12 hours

---

### 13. Documentation Updates

**Items**:
1. Add module docstrings to partition_evolution.py
2. Document partition field ID strategy
3. Create schema migration guide
4. Create failure recovery runbook

**Estimated Time**: 4 hours

---

## Implementation Schedule

### Day 1 (Today - 2025-12-26)
- ✅ Create this plan document
- 🔄 Fix #1: SQL injection vulnerability (2h)
- 🔄 Fix #2: Idempotency tracking (3h)
- 🔄 Fix #3: Input validation (2h)
**Total**: 7 hours

### Day 2-3
- Fix #4: Circuit breaker pattern (4h)
- Fix #5: Retry mechanisms (3h)
- Fix #6: Error handling (2h)
**Total**: 9 hours

### Week 2
- Fix #7: Refactor long functions (4h)
- Fix #8: Remove redundant code (2h)
- Fix #9: Type hints (3h)
- Fix #10: Configuration (2h)
**Total**: 11 hours

### Week 3-4 (Optional)
- Fix #11: Performance (6h)
- Fix #12: Test coverage (12h)
- Fix #13: Documentation (4h)
**Total**: 22 hours

---

## Success Criteria

### Critical (Must Have)
- [ ] No SQL injection vulnerabilities
- [ ] Idempotency tracking implemented
- [ ] Input validation on all public APIs
- [ ] All tests passing

### High Priority (Should Have)
- [ ] Circuit breakers on external services
- [ ] Retry logic with backoff
- [ ] Specific error handling (no bare except)
- [ ] Type hints coverage >80%

### Medium Priority (Nice to Have)
- [ ] Functions <50 lines
- [ ] All config externalized
- [ ] Test coverage >70%
- [ ] Complete documentation

---

## Risk Assessment

### Low Risk Changes
- Type hints addition
- Documentation updates
- Logging improvements
- Configuration externalization

### Medium Risk Changes
- Refactoring long functions
- Adding retry logic
- Input validation (may break existing callers)

### High Risk Changes
- Removing sanitize_sql() - requires query audit
- Adding circuit breakers - may cause false positives
- Idempotency cache - memory concerns

---

## Rollback Plan

For each high-risk change:
1. Create feature branch
2. Run full test suite
3. Manual testing in dev environment
4. Gradual rollout with monitoring
5. Keep previous version for 48h

---

**Status**: READY TO EXECUTE
**Next Action**: Begin implementing critical fixes
**Estimated Total Time**: 49 hours (1-2 weeks with testing)
