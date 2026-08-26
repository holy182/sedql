"""Base database connector with production-ready features."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import time
import json
from contextlib import contextmanager
from urllib.parse import urlparse

from sqlalchemy import create_engine, MetaData, inspect, text, event
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError, OperationalError, IntegrityError

from ..utils.logger import logger


@dataclass
class ConnectionConfig:
    """Database connection configuration."""
    url: str
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = False
    connect_timeout: int = 10
    retry_attempts: int = 3
    retry_delay: int = 1
    statement_timeout: Optional[int] = None

    @classmethod
    def from_url(cls, url: str) -> 'ConnectionConfig':
        """Create config from URL."""
        return cls(url=url)


class ConnectionPool:
    """Enhanced connection pool with monitoring."""

    def __init__(self, config: ConnectionConfig):
        self.config = config
        self.engine: Optional[Engine] = None
        self._connections_created = 0
        self._connections_checked_out = 0
        self._total_queries = 0
        self._slow_queries = 0
        self._query_times: List[float] = []
        self._errors = 0

    def create_engine(self) -> Engine:
        """Create engine with pool configuration."""
        pool_kwargs = {
            'pool_size': self.config.pool_size,
            'max_overflow': self.config.max_overflow,
            'pool_timeout': self.config.pool_timeout,
            'pool_recycle': self.config.pool_recycle,
            'pool_pre_ping': True,  # Check connection before using
        }

        # Create engine
        engine = create_engine(
            self.config.url,
            poolclass=QueuePool,
            pool_kwargs=pool_kwargs,
            echo=self.config.echo,
            connect_args=self._get_connect_args()
        )

        # Add event listeners
        self._setup_event_listeners(engine)

        self.engine = engine
        return engine

    def _get_connect_args(self) -> Dict[str, Any]:
        """Get database-specific connect arguments."""
        args = {
            'connect_timeout': self.config.connect_timeout,
        }

        # Parse URL for database type
        parsed = urlparse(self.config.url)
        scheme = parsed.scheme.lower()

        if 'postgres' in scheme or 'postgresql' in scheme:
            args.update({
                'connect_timeout': self.config.connect_timeout,
                'keepalives_idle': 60,
                'keepalives_interval': 10,
                'keepalives_count': 5,
            })
        elif 'mysql' in scheme:
            args.update({
                'connect_timeout': self.config.connect_timeout,
                'charset': 'utf8mb4',
            })

        return args

    def _setup_event_listeners(self, engine: Engine) -> None:
        """Setup SQLAlchemy event listeners."""
        @event.listens_for(engine, 'before_execute')
        def before_execute(conn, clause, multiparams, params):
            conn.info['start_time'] = time.time()
            self._total_queries += 1

        @event.listens_for(engine, 'after_execute')
        def after_execute(conn, clause, multiparams, params, result):
            start_time = conn.info.get('start_time')
            if start_time:
                elapsed = time.time() - start_time
                self._query_times.append(elapsed)

                if elapsed > 1.0:  # Slow query > 1s
                    self._slow_queries += 1
                    sql = str(clause) if clause else ''
                    logger.warning(f"Slow query ({elapsed:.2f}s): {sql[:200]}")

        @event.listens_for(engine, 'checkout')
        def checkout(dbapi_conn, connection_ref, connection_proxy):
            self._connections_checked_out += 1

        @event.listens_for(engine, 'checkin')
        def checkin(dbapi_conn, connection_ref):
            self._connections_checked_out -= 1

        @event.listens_for(engine, 'connect')
        def connect(dbapi_conn, connection_ref):
            self._connections_created += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        avg_query_time = sum(self._query_times) / \
            len(self._query_times) if self._query_times else 0

        return {
            'connections_created': self._connections_created,
            'connections_checked_out': self._connections_checked_out,
            'total_queries': self._total_queries,
            'slow_queries': self._slow_queries,
            'avg_query_time': avg_query_time,
            'errors': self._errors,
            'pool_size': self.config.pool_size,
            'max_overflow': self.config.max_overflow
        }


class BaseConnector(ABC):
    """Production-ready base connector with retry logic, pooling, and error handling."""

    def __init__(self, connection_url: str, config: Optional[ConnectionConfig] = None):
        """
        Initialize database connector.

        Args:
            connection_url: Database connection URL
            config: Connection configuration (optional)
        """
        self.connection_url = connection_url
        self.config = config or ConnectionConfig.from_url(connection_url)
        self.pool = ConnectionPool(self.config)
        self.engine: Optional[Engine] = None
        self.metadata = MetaData()
        self._connected = False

    def connect(self, retry: bool = True) -> None:
        """
        Establish database connection with retry logic.

        Args:
            retry: Whether to retry on failure
        """
        attempts = 0
        max_attempts = self.config.retry_attempts if retry else 1

        while attempts < max_attempts:
            try:
                attempts += 1
                self.engine = self.pool.create_engine()

                # Test connection
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))

                self.metadata.reflect(bind=self.engine)
                self._connected = True
                logger.info(f"Connected to database: {self.engine.url}")
                return

            except Exception as e:
                logger.warning(
                    f"Connection attempt {attempts}/{max_attempts} failed: {e}")

                if attempts < max_attempts and retry:
                    time.sleep(self.config.retry_delay * attempts)
                else:
                    logger.error(
                        f"Failed to connect after {attempts} attempts")
                    raise

        raise RuntimeError("Connection failed")

    def disconnect(self) -> None:
        """Close database connection and dispose pool."""
        if self.engine:
            try:
                self.engine.dispose()
                logger.info("Database connection closed")
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
        self._connected = False

    def is_connected(self) -> bool:
        """Check if connected to database."""
        if not self._connected or not self.engine:
            return False

        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except:
            return False

    @contextmanager
    def get_connection(self) -> Connection:
        """
        Get a database connection from the pool with context manager.

        Yields:
            SQLAlchemy Connection

        Raises:
            RuntimeError: If not connected
        """
        if not self.engine:
            self.connect()

        if not self.engine:
            raise RuntimeError("No database connection available")

        conn = None
        try:
            conn = self.engine.connect()
            yield conn
        except OperationalError as e:
            self._connected = False
            logger.error(f"Operational error: {e}")
            raise
        except IntegrityError as e:
            logger.error(f"Integrity error: {e}")
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    @contextmanager
    def transaction(self) -> Connection:
        """
        Get a database connection with transaction support.

        Yields:
            SQLAlchemy Connection with active transaction
        """
        with self.get_connection() as conn:
            try:
                trans = conn.begin()
                yield conn
                trans.commit()
            except Exception as e:
                trans.rollback()
                logger.error(f"Transaction rolled back: {e}")
                raise

    def execute_query_with_retry(self, query: str, params: Optional[Dict] = None, retry_count: int = 3) -> List[Dict]:
        """
        Execute a query with retry logic.

        Args:
            query: SQL query string
            params: Query parameters
            retry_count: Number of retry attempts

        Returns:
            List of rows as dictionaries
        """
        last_error = None

        for attempt in range(retry_count):
            try:
                return self.execute_query(query, params)
            except OperationalError as e:
                last_error = e
                if attempt < retry_count - 1:
                    wait_time = self.config.retry_delay * (attempt + 1)
                    logger.warning(
                        f"Query failed, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                    # Attempt to reconnect
                    self._connected = False
                    self.connect()
                else:
                    logger.error(
                        f"Query failed after {retry_count} attempts: {e}")
                    raise

        if last_error:
            raise last_error

        return []

    def execute_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        Execute a query and return results.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            List of rows as dictionaries
        """
        if not self.engine:
            self.connect()

        results = []

        try:
            with self.get_connection() as conn:
                # Apply statement timeout if configured
                if self.config.statement_timeout:
                    if 'postgres' in self.connection_url:
                        conn.execute(
                            text(f"SET statement_timeout = {self.config.statement_timeout * 1000}"))

                if params:
                    result = conn.execute(text(query), params)
                else:
                    result = conn.execute(text(query))

                # Handle different result types
                for row in result:
                    if hasattr(row, '_mapping'):
                        results.append(dict(row._mapping))
                    elif hasattr(row, '_asdict'):
                        results.append(row._asdict())
                    else:
                        results.append(dict(row))

        except Exception as e:
            self.pool._errors += 1
            logger.error(f"Query execution failed: {e}\nQuery: {query[:200]}")
            raise

        return results

    def execute_many(self, query: str, params_list: List[Dict]) -> int:
        """
        Execute a query with multiple parameter sets.

        Args:
            query: SQL query string
            params_list: List of parameter dictionaries

        Returns:
            Number of affected rows
        """
        if not self.engine:
            self.connect()

        total_affected = 0

        try:
            with self.get_connection() as conn:
                # Execute in batches to avoid memory issues
                batch_size = 1000
                for i in range(0, len(params_list), batch_size):
                    batch = params_list[i:i + batch_size]
                    result = conn.execute(text(query), batch)
                    total_affected += result.rowcount

        except Exception as e:
            self.pool._errors += 1
            logger.error(f"Bulk query execution failed: {e}")
            raise

        return total_affected

    def get_table_names(self) -> List[str]:
        """Get all table names."""
        if not self.engine or not self._connected:
            self.connect()

        return self.engine.table_names() if hasattr(self.engine, 'table_names') else []

    def get_columns(self, table: str) -> List[Dict]:
        """Get columns of a table."""
        if not self.engine or not self._connected:
            self.connect()

        inspector = inspect(self.engine)
        return inspector.get_columns(table)

    def get_primary_keys(self, table: str) -> List[str]:
        """Get primary keys of a table."""
        if not self.engine or not self._connected:
            self.connect()

        inspector = inspect(self.engine)
        pk = inspector.get_pk_constraint(table)
        return pk.get('constrained_columns', [])

    def get_foreign_keys(self, table: str) -> List[Dict]:
        """Get foreign keys of a table."""
        if not self.engine or not self._connected:
            self.connect()

        inspector = inspect(self.engine)
        return inspector.get_foreign_keys(table)

    def get_indexes(self, table: str) -> List[Dict]:
        """Get indexes of a table."""
        if not self.engine or not self._connected:
            self.connect()

        inspector = inspect(self.engine)
        return inspector.get_indexes(table)

    def get_schema_info(self) -> 'SchemaInfo':
        """Get complete schema information."""
        from ..core.schema_parser import ParsedSchema, ParsedTable, ParsedColumn

        schema = ParsedSchema(
            database_name=str(self.engine.url.database) if self.engine else "",
            database_type=self.get_database_type()
        )

        tables = self.get_table_names()

        for table_name in tables:
            try:
                columns = self.get_columns(table_name)
                pk = self.get_primary_keys(table_name)
                fks = self.get_foreign_keys(table_name)
                indexes = self.get_indexes(table_name)

                parsed_table = ParsedTable(
                    name=table_name,
                    row_count=self.get_table_row_count(table_name)
                )

                for col in columns:
                    parsed_column = ParsedColumn(
                        name=col['name'],
                        data_type=str(col['type']),
                        nullable=col.get('nullable', True),
                        is_primary=col['name'] in pk,
                        is_foreign=any(col['name'] in fk.get(
                            'constrained_columns', []) for fk in fks)
                    )
                    parsed_table.columns.append(parsed_column)

                parsed_table.primary_keys = pk
                parsed_table.columns_count = len(columns)
                schema.tables.append(parsed_table)

            except Exception as e:
                logger.warning(
                    f"Failed to get info for table {table_name}: {e}")

        return schema

    def get_table_row_count(self, table: str) -> int:
        """Get row count of a table."""
        try:
            query = f"SELECT COUNT(*) as count FROM {table}"
            results = self.execute_query(query)
            return results[0].get('count', 0) if results else 0
        except:
            return 0

    def get_sample_data(self, table: str, limit: int = 5) -> List[Dict]:
        """Get sample data from a table."""
        try:
            query = f"SELECT * FROM {table} LIMIT {limit}"
            return self.execute_query(query)
        except:
            return []

    def get_database_type(self) -> str:
        """Get database type from URL."""
        parsed = urlparse(self.connection_url)
        scheme = parsed.scheme.lower()

        if 'postgres' in scheme or 'postgresql' in scheme:
            return 'postgresql'
        elif 'mysql' in scheme:
            return 'mysql'
        elif 'sqlite' in scheme:
            return 'sqlite'
        elif 'mssql' in scheme:
            return 'mssql'
        else:
            return scheme

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        return self.pool.get_stats()

    def get_version(self) -> Optional[str]:
        """Get database version."""
        try:
            if 'postgres' in self.connection_url:
                query = "SELECT version()"
            elif 'mysql' in self.connection_url:
                query = "SELECT VERSION()"
            elif 'sqlite' in self.connection_url:
                query = "SELECT sqlite_version()"
            else:
                return None

            results = self.execute_query(query)
            if results:
                return str(list(results[0].values())[0])
        except:
            pass

        return None

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
