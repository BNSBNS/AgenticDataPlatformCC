"""
Resilience patterns for external service calls.

Provides circuit breakers, retry logic, and other fault-tolerance mechanisms.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Any, Optional, Tuple
from functools import wraps
import threading
import time
import random

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
    """
    Configuration for circuit breaker.

    Attributes:
        failure_threshold: Number of failures before opening circuit
        success_threshold: Number of successes to close circuit from half-open
        timeout_seconds: Time to wait before attempting reset
        name: Circuit breaker name for logging
    """

    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: int = 60
    name: str = "default"


class CircuitBreaker:
    """
    Circuit breaker for external service calls.

    Prevents cascading failures by failing fast when service is down.
    Implements the circuit breaker pattern with three states:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Service is down, calls fail immediately
    - HALF_OPEN: Testing if service recovered
    """

    def __init__(self, config: CircuitBreakerConfig):
        """
        Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration
        """
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self._lock = threading.Lock()

        logger.info(
            "Circuit breaker initialized",
            name=self.config.name,
            failure_threshold=self.config.failure_threshold,
            timeout_seconds=self.config.timeout_seconds,
        )

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
                        name=self.config.name,
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
        """
        Check if enough time has passed to attempt reset.

        Returns:
            True if should attempt reset
        """
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
                        name=self.config.name,
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
                    failures=self.failure_count,
                )

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.success_count = 0


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retriable_exceptions: Tuple[type, ...] = (Exception,),
):
    """
    Decorator for retry logic with exponential backoff.

    Implements exponential backoff with optional jitter to prevent
    thundering herd problem.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential calculation
        jitter: Add random jitter to prevent thundering herd
        retriable_exceptions: Tuple of exceptions to retry on

    Example:
        @retry_with_backoff(max_retries=3, retriable_exceptions=(ConnectionError,))
        def fetch_data():
            return requests.get("https://api.example.com/data")
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
                            "Max retries exceeded",
                            function=func.__name__,
                            max_retries=max_retries,
                            error=str(e),
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(initial_delay * (exponential_base**attempt), max_delay)

                    # Add jitter
                    if jitter:
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        "Retrying after failure",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay_seconds=delay,
                        error=str(e),
                    )

                    time.sleep(delay)

            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def timeout(seconds: float):
    """
    Decorator to add timeout to function execution.

    Args:
        seconds: Timeout in seconds

    Raises:
        TimeoutError: If function execution exceeds timeout

    Note:
        This is a basic implementation. For production, consider
        using asyncio or multiprocessing-based timeouts.
    """
    import signal

    def decorator(func: Callable) -> Callable:
        def _timeout_handler(signum, frame):
            raise TimeoutError(f"Function {func.__name__} timed out after {seconds}s")

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Set signal handler
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(int(seconds))

            try:
                result = func(*args, **kwargs)
            finally:
                # Restore old handler
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

            return result

        return wrapper

    return decorator
