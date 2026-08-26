"""Query executor with security, caching, and result processing."""

import re
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import json
import time
from collections import OrderedDict

from ..connectors import BaseConnector
from ..rules.engine import RulesEngine
from ..utils.logger import logger


@dataclass
class QueryResult:
    """Result of a query execution."""
    query: str
    sql: str
    data: List[Dict[str, Any]]
    row_count: int
    column_count: int
    columns: List[str]
    execution_time: float
    cache_hit: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "query": self.query,
            "sql": self.sql,
            "data": self.data,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "columns": self.columns,
            "execution_time": self.execution_time,
            "cache_hit": self.cache_hit,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata
        }

    def to_json(self) -> str:
        """Convert result to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)

    def to_markdown(self) -> str:
        """Convert result to markdown table."""
        if not self.data:
            return "No results found."

        lines = []
        lines.append(f"### Query Results ({self.row_count} rows)")
        lines.append("")

        # Table header
        lines.append("| " + " | ".join(self.columns) + " |")
        lines.append("|" + "|".join(["---" for _ in self.columns]) + "|")

        # Table rows (limit to 100 for display)
        for row in self.data[:100]:
            values = []
            for col in self.columns:
                val = row.get(col, "")
                if val is None:
                    val = "NULL"
                elif isinstance(val, (dict, list)):
                    val = json.dumps(val)[:50] + "..."
                else:
                    val = str(val)[:50]
                values.append(val)
            lines.append("| " + " | ".join(values) + " |")

        if len(self.data) > 100:
            lines.append("")
            lines.append(f"... and {len(self.data) - 100} more rows")

        lines.append("")
        lines.append(f"*Execution time: {self.execution_time:.3f}s*")

        if self.warnings:
            lines.append("")
            lines.append("⚠️ Warnings:")
            for warning in self.warnings:
                lines.append(f"- {warning}")

        return "\n".join(lines)


@dataclass
class QueryPlan:
    """Query execution plan."""
    sql: str
    estimated_cost: float
    estimated_rows: int
    tables: List[str]
    columns: List[str]
    operations: List[str] = field(default_factory=list)
    index_usage: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class QueryCache:
    """Simple in-memory query cache with TTL."""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: OrderedDict = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[QueryResult]:
        """Get a cached result."""
        if key in self.cache:
            entry = self.cache[key]
            if datetime.now() - entry['timestamp'] < timedelta(seconds=self.ttl_seconds):
                self.hits += 1
                self.cache.move_to_end(key)
                return entry['result']
            else:
                del self.cache[key]
        self.misses += 1
        return None

    def set(self, key: str, result: QueryResult) -> None:
        """Cache a result."""
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)

        self.cache[key] = {
            'result': result,
            'timestamp': datetime.now()
        }

    def clear(self) -> None:
        """Clear the cache."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "size": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / (self.hits + self.misses) if (self.hits + self.misses) > 0 else 0
        }


class QueryExecutor:
    """Execute SQL queries with security, caching, and result processing."""

    def __init__(
        self,
        connector: BaseConnector,
        rules_engine: Optional[RulesEngine] = None,
        enable_cache: bool = True,
        cache_ttl: int = 300,
        max_rows: int = 10000,
        timeout_seconds: int = 30
    ):
        """
        Initialize query executor.

        Args:
            connector: Database connector
            rules_engine: Rules engine for validation
            enable_cache: Enable query result caching
            cache_ttl: Cache TTL in seconds
            max_rows: Maximum rows to return
            timeout_seconds: Query timeout in seconds
        """
        self.connector = connector
        self.connector.connect()

        self.rules_engine = rules_engine
        self.enable_cache = enable_cache
        self.max_rows = max_rows
        self.timeout_seconds = timeout_seconds

        if enable_cache:
            self.cache = QueryCache(max_size=100, ttl_seconds=cache_ttl)
        else:
            self.cache = None

    def execute(
        self,
        query: str,
        sql: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        validate_rules: bool = True,
        timeout: Optional[int] = None
    ) -> QueryResult:
        """
        Execute a query with full processing pipeline.

        Args:
            query: Original query (natural language)
            sql: SQL to execute (if None, use query as SQL)
            params: Query parameters
            use_cache: Whether to use cache
            validate_rules: Whether to validate against business rules
            timeout: Query timeout in seconds

        Returns:
            QueryResult object
        """
        start_time = time.time()

        # Use query as SQL if no SQL provided
        sql_to_execute = sql or query

        # Clean SQL
        sql_to_execute = self._clean_sql(sql_to_execute)

        # Extract table name for rule validation
        table_name = self._extract_table_name(sql_to_execute)

        # Check cache
        cache_key = self._generate_cache_key(sql_to_execute, params)
        if use_cache and self.cache:
            cached_result = self.cache.get(cache_key)
            if cached_result:
                logger.debug(f"Cache hit for query: {query[:50]}...")
                cached_result.cache_hit = True
                return cached_result

        # Validate against rules
        warnings = []
        errors = []

        if validate_rules and self.rules_engine and table_name:
            is_valid, violations = self.rules_engine.validate_query(
                sql_to_execute, table_name)
            if not is_valid:
                for violation in violations:
                    if violation.get('severity') == 'HIGH':
                        errors.append(
                            f"Rule violation: {violation['description']}")
                    else:
                        warnings.append(
                            f"Rule warning: {violation['description']}")

        # Check if we should proceed
        if errors:
            # Return error result
            return QueryResult(
                query=query,
                sql=sql_to_execute,
                data=[],
                row_count=0,
                column_count=0,
                columns=[],
                execution_time=time.time() - start_time,
                errors=errors,
                warnings=warnings
            )

        # Execute the query
        try:
            data = self._execute_sql(sql_to_execute, params, timeout)

            # Apply rules to data
            if self.rules_engine and table_name:
                data = self.rules_engine.apply_rules(data, table_name)

            # Build result
            columns = list(data[0].keys()) if data else []
            row_count = len(data)

            result = QueryResult(
                query=query,
                sql=sql_to_execute,
                data=data[:self.max_rows],
                row_count=row_count,
                column_count=len(columns),
                columns=columns,
                execution_time=time.time() - start_time,
                cache_hit=False,
                warnings=warnings,
                metadata={
                    "truncated": row_count > self.max_rows,
                    "original_row_count": row_count,
                    "table": table_name,
                    "params": params
                }
            )

            # Cache result
            if use_cache and self.cache and not errors:
                self.cache.set(cache_key, result)

            logger.info(
                f"Query executed in {result.execution_time:.3f}s, {result.row_count} rows")

            return result

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return QueryResult(
                query=query,
                sql=sql_to_execute,
                data=[],
                row_count=0,
                column_count=0,
                columns=[],
                execution_time=time.time() - start_time,
                errors=[str(e)],
                warnings=warnings
            )

    def _execute_sql(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Execute SQL with timeout and parameters."""
        # Apply timeout
        timeout_seconds = timeout or self.timeout_seconds

        # Execute with timer
        start = time.time()

        try:
            # Execute query
            results = self.connector.execute_query(sql)

            # Check timeout
            elapsed = time.time() - start
            if elapsed > timeout_seconds:
                logger.warning(
                    f"Query took {elapsed:.2f}s, exceeded timeout of {timeout_seconds}s")

            return results

        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            raise

    def execute_many(
        self,
        queries: List[Tuple[str, Optional[str]]],
        use_cache: bool = True,
        validate_rules: bool = True
    ) -> List[QueryResult]:
        """
        Execute multiple queries.

        Args:
            queries: List of (query, sql) tuples
            use_cache: Whether to use cache
            validate_rules: Whether to validate rules

        Returns:
            List of QueryResult objects
        """
        results = []
        for query, sql in queries:
            result = self.execute(
                query=query,
                sql=sql,
                use_cache=use_cache,
                validate_rules=validate_rules
            )
            results.append(result)

        return results

    def explain(self, sql: str) -> QueryPlan:
        """
        Get execution plan for a query.

        Args:
            sql: SQL query

        Returns:
            QueryPlan object
        """
        try:
            # Get explain plan
            explain_sql = f"EXPLAIN {sql}"
            results = self.connector.execute_query(explain_sql)

            # Parse plan
            tables = self._extract_tables_from_query(sql)
            columns = self._extract_columns_from_query(sql)

            # Estimate cost from plan if available
            estimated_cost = 1.0
            estimated_rows = 10

            for row in results:
                # Try to extract cost information
                if 'cost' in str(row).lower():
                    # Simple parsing
                    pass

            return QueryPlan(
                sql=sql,
                estimated_cost=estimated_cost,
                estimated_rows=estimated_rows,
                tables=tables,
                columns=columns,
                operations=self._extract_operations(results),
                index_usage=self._extract_index_usage(results)
            )

        except Exception as e:
            logger.warning(f"Failed to get explain plan: {e}")
            return QueryPlan(
                sql=sql,
                estimated_cost=1.0,
                estimated_rows=10,
                tables=[],
                columns=[],
                operations=[],
                index_usage=[],
                warnings=[f"Could not generate explain plan: {e}"]
            )

    def _clean_sql(self, sql: str) -> str:
        """Clean and normalize SQL."""
        # Remove trailing semicolons
        sql = sql.rstrip(';')

        # Remove multiple spaces
        sql = ' '.join(sql.split())

        return sql

    def _extract_table_name(self, sql: str) -> Optional[str]:
        """Extract the main table name from SQL."""
        sql_lower = sql.lower()

        # Look for FROM clause
        from_match = re.search(r'from\s+([^\s,;]+)', sql_lower)
        if from_match:
            return from_match.group(1)

        # Look for UPDATE clause
        update_match = re.search(r'update\s+([^\s,;]+)', sql_lower)
        if update_match:
            return update_match.group(1)

        # Look for INSERT INTO
        insert_match = re.search(r'insert\s+into\s+([^\s,;]+)', sql_lower)
        if insert_match:
            return insert_match.group(1)

        return None

    def _extract_tables_from_query(self, sql: str) -> List[str]:
        """Extract all tables from a query."""
        import re
        tables = []
        sql_lower = sql.lower()

        # Find all table references
        from_matches = re.findall(r'from\s+([^\s,;]+)', sql_lower)
        join_matches = re.findall(r'join\s+([^\s,;]+)', sql_lower)

        tables.extend(from_matches)
        tables.extend(join_matches)

        return list(set(tables))

    def _extract_columns_from_query(self, sql: str) -> List[str]:
        """Extract columns from a query."""
        import re
        columns = []
        sql_lower = sql.lower()

        # Look for SELECT columns
        select_match = re.search(r'select\s+(.+?)\s+from', sql_lower)
        if select_match:
            select_part = select_match.group(1)
            # Split by commas, but handle functions
            parts = []
            current = []
            depth = 0
            for char in select_part:
                if char == '(':
                    depth += 1
                elif char == ')':
                    depth -= 1
                elif char == ',' and depth == 0:
                    parts.append(''.join(current).strip())
                    current = []
                    continue
                current.append(char)
            if current:
                parts.append(''.join(current).strip())

            for part in parts:
                # Extract alias or column name
                if ' as ' in part:
                    column = part.split(' as ')[1].strip()
                elif ' ' in part and '(' not in part:
                    column = part.split(' ')[-1].strip()
                else:
                    column = part.strip()
                columns.append(column)

        return columns

    def _extract_operations(self, plan_results: List[Dict]) -> List[str]:
        """Extract operations from explain plan."""
        operations = []
        for row in plan_results:
            if 'seq scan' in str(row).lower():
                operations.append('Seq Scan')
            elif 'index scan' in str(row).lower():
                operations.append('Index Scan')
            elif 'index only scan' in str(row).lower():
                operations.append('Index Only Scan')
            elif 'hash join' in str(row).lower():
                operations.append('Hash Join')
            elif 'merge join' in str(row).lower():
                operations.append('Merge Join')
            elif 'nested loop' in str(row).lower():
                operations.append('Nested Loop')
            elif 'sort' in str(row).lower():
                operations.append('Sort')
            elif 'aggregate' in str(row).lower():
                operations.append('Aggregate')
            elif 'limit' in str(row).lower():
                operations.append('Limit')
        return list(set(operations))

    def _extract_index_usage(self, plan_results: List[Dict]) -> List[str]:
        """Extract index usage from explain plan."""
        indexes = []
        for row in plan_results:
            row_str = str(row).lower()
            if 'index' in row_str:
                # Try to extract index name
                import re
                match = re.search(r'index\s+scan\s+using\s+([^\s,]+)', row_str)
                if match:
                    indexes.append(match.group(1))
        return list(set(indexes))

    def _generate_cache_key(self, sql: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Generate a cache key for a query."""
        key = sql
        if params:
            key += json.dumps(params, sort_keys=True)
        return hashlib.md5(key.encode()).hexdigest()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        if self.cache:
            return self.cache.get_stats()
        return {"enabled": False}

    def clear_cache(self) -> None:
        """Clear the query cache."""
        if self.cache:
            self.cache.clear()
            logger.info("Query cache cleared")

    def get_summary(self) -> Dict[str, Any]:
        """Get executor summary."""
        return {
            "cache_enabled": self.enable_cache,
            "cache_stats": self.get_cache_stats() if self.cache else None,
            "max_rows": self.max_rows,
            "timeout_seconds": self.timeout_seconds,
            "rules_enabled": self.rules_engine is not None
        }


# Helper function for pagination
def paginate_results(results: List[Dict], page: int = 1, page_size: int = 50) -> Dict[str, Any]:
    """
    Paginate query results.

    Args:
        results: List of rows
        page: Page number (1-indexed)
        page_size: Number of rows per page

    Returns:
        Paginated results with metadata
    """
    total_rows = len(results)
    total_pages = (total_rows + page_size -
                   1) // page_size if total_rows > 0 else 1

    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total_rows)

    paginated_data = results[start_idx:end_idx]

    return {
        "data": paginated_data,
        "pagination": {
            "current_page": page,
            "page_size": page_size,
            "total_rows": total_rows,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
            "start_row": start_idx + 1 if paginated_data else 0,
            "end_row": end_idx
        }
    }


# Import re for SQL parsing
