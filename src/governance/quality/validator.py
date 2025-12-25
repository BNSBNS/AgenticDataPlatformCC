"""
Data quality validation framework.
"""

from typing import Dict, Any, List, Optional
import pyarrow as pa

from src.common.logging import get_logger
from src.common.metrics import data_quality_checks_total, data_quality_failures_total

logger = get_logger(__name__)


class DataQualityValidator:
    """
    Validate data quality using configurable rules.
    """

    def __init__(self):
        """Initialize data quality validator."""
        logger.info("Data quality validator initialized")

    def validate_not_null(
        self,
        data: pa.Table,
        column: str,
        layer: str = "unknown",
        table: str = "unknown",
    ) -> Dict[str, Any]:
        """
        Validate that column has no null values.

        Args:
            data: PyArrow table
            column: Column to check
            layer: Data layer
            table: Table name

        Returns:
            Validation result
        """
        try:
            null_count = data.column(column).null_count

            passed = null_count == 0

            # Record metrics
            status = "success" if passed else "failure"
            data_quality_checks_total.labels(
                layer=layer, table=table, status=status
            ).inc()

            if not passed:
                data_quality_failures_total.labels(
                    layer=layer, table=table, check_type="not_null"
                ).inc()

            return {
                "check": "not_null",
                "column": column,
                "passed": passed,
                "null_count": null_count,
            }

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return {"check": "not_null", "passed": False, "error": str(e)}

    def validate_unique(
        self,
        data: pa.Table,
        column: str,
        layer: str = "unknown",
        table: str = "unknown",
    ) -> Dict[str, Any]:
        """
        Validate that column has unique values.

        Args:
            data: PyArrow table
            column: Column to check
            layer: Data layer
            table: Table name

        Returns:
            Validation result
        """
        try:
            total_rows = len(data)
            unique_values = len(data.column(column).unique())

            passed = total_rows == unique_values

            # Record metrics
            status = "success" if passed else "failure"
            data_quality_checks_total.labels(
                layer=layer, table=table, status=status
            ).inc()

            if not passed:
                data_quality_failures_total.labels(
                    layer=layer, table=table, check_type="unique"
                ).inc()

            return {
                "check": "unique",
                "column": column,
                "passed": passed,
                "total_rows": total_rows,
                "unique_values": unique_values,
            }

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return {"check": "unique", "passed": False, "error": str(e)}
