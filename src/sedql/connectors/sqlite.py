"""SQLite connector with production-ready features."""

from typing import Dict, List, Any, Optional
from pathlib import Path
import sqlite3

from .base import BaseConnector, ConnectionConfig
from ..utils.logger import logger


class SQLiteConnector(BaseConnector):
    """Production-ready SQLite connector."""

    def __init__(self, connection_url: str, config: Optional[ConnectionConfig] = None):
        """
        Initialize SQLite connector.

        Args:
            connection_url: SQLite connection URL (sqlite:///path/to/db.db)
            config: Connection configuration
        """
        super().__init__(connection_url, config)
        self._db_path = self._extract_db_path()

    def _extract_db_path(self) -> str:
        """Extract database file path from URL."""
        # Remove sqlite:/// prefix
        path = self.connection_url.replace(
            'sqlite:///', '').replace('sqlite://', '')

        # Handle in-memory database
        if path == ':memory:':
            return ':memory:'

        # Handle relative paths
        if not Path(path).is_absolute():
            path = str(Path.cwd() / path)

        return path

    def connect(self) -> None:
        """Connect to SQLite database."""
        if not self._db_path:
            raise ValueError("No database path specified")

        try:
            # Create parent directory if needed
            if self._db_path != ':memory:':
                Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

            self.engine = create_engine(
                self.connection_url,
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                pool_timeout=self.config.pool_timeout,
                pool_recycle=self.config.pool_recycle,
                pool_pre_ping=True,
                connect_args={
                    'timeout': self.config.connect_timeout,
                    'check_same_thread': False,  # Allow multiple threads
                }
            )

            # Test connection
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            self.metadata.reflect(bind=self.engine)
            self._connected = True
            logger.info(f"Connected to SQLite: {self._db_path}")

        except Exception as e:
            logger.error(f"SQLite connection failed: {e}")
            raise

    def get_table_names(self) -> List[str]:
        """Get all table names."""
        if not self.engine or not self._connected:
            self.connect()

        # SQLite doesn't support schema parameter
        query = "SELECT name FROM sqlite_master WHERE type='table'"
        results = self.execute_query(query)
        return [row['name'] for row in results]

    def get_views(self) -> List[str]:
        """Get all view names."""
        if not self.engine or not self._connected:
            self.connect()

        query = "SELECT name FROM sqlite_master WHERE type='view'"
        results = self.execute_query(query)
        return [row['name'] for row in results]

    def get_triggers(self) -> List[str]:
        """Get all trigger names."""
        if not self.engine or not self._connected:
            self.connect()

        query = "SELECT name FROM sqlite_master WHERE type='trigger'"
        results = self.execute_query(query)
        return [row['name'] for row in results]

    def get_indexes(self, table: str) -> List[Dict]:
        """Get indexes of a table."""
        if not self.engine or not self._connected:
            self.connect()

        try:
            query = f"PRAGMA index_list({table})"
            return self.execute_query(query)
        except:
            return []

    def get_table_info(self, table: str) -> List[Dict]:
        """Get detailed table information using PRAGMA."""
        if not self.engine or not self._connected:
            self.connect()

        try:
            query = f"PRAGMA table_info({table})"
            return self.execute_query(query)
        except:
            return []

    def get_foreign_key_info(self, table: str) -> List[Dict]:
        """Get foreign key information using PRAGMA."""
        if not self.engine or not self._connected:
            self.connect()

        try:
            query = f"PRAGMA foreign_key_list({table})"
            return self.execute_query(query)
        except:
            return []

    def get_database_size(self) -> int:
        """Get database file size in bytes."""
        if self._db_path == ':memory:':
            return 0

        try:
            return Path(self._db_path).stat().st_size
        except:
            return 0

    def vacuum(self) -> None:
        """Run VACUUM to optimize database."""
        if self._db_path == ':memory:':
            return

        try:
            self.execute_query("VACUUM")
            logger.info("SQLite vacuum completed")
        except Exception as e:
            logger.error(f"Vacuum failed: {e}")

    def backup(self, backup_path: str) -> bool:
        """Backup SQLite database."""
        if self._db_path == ':memory:' or not self.engine:
            return False

        try:
            # Use SQLite backup API
            source = sqlite3.connect(self._db_path)
            dest = sqlite3.connect(backup_path)
            source.backup(dest)
            dest.close()
            source.close()

            logger.info(f"Backup created: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return False

    def get_foreign_keys(self, table: str) -> List[Dict]:
        """Get foreign keys using PRAGMA."""
        if not self.engine or not self._connected:
            self.connect()

        try:
            query = f"PRAGMA foreign_key_list({table})"
            results = self.execute_query(query)

            # Convert PRAGMA format to standard format
            fks = []
            for row in results:
                fks.append({
                    'constrained_columns': [row.get('from', '')],
                    'referred_table': row.get('table', ''),
                    'referred_columns': [row.get('to', '')],
                    'name': f"fk_{row.get('id', '')}"
                })
            return fks
        except:
            return []

    def get_primary_keys(self, table: str) -> List[str]:
        """Get primary keys using PRAGMA."""
        if not self.engine or not self._connected:
            self.connect()

        try:
            query = f"PRAGMA table_info({table})"
            results = self.execute_query(query)
            return [row['name'] for row in results if row.get('pk', 0) > 0]
        except:
            return []

    def get_schema_info(self) -> Dict[str, Any]:
        """Get SQLite schema information."""
        info = {
            'tables': self.get_table_names(),
            'views': self.get_views(),
            'triggers': self.get_triggers(),
            'size': self.get_database_size()
        }

        # Get detailed table info
        table_details = {}
        for table in info['tables']:
            try:
                table_details[table] = {
                    'columns': self.get_table_info(table),
                    'foreign_keys': self.get_foreign_key_info(table),
                    'indexes': self.get_indexes(table)
                }
            except:
                pass

        info['table_details'] = table_details

        return info

    def execute_script(self, script: str) -> int:
        """
        Execute a SQL script (multiple statements).

        Returns:
            Number of affected rows
        """
        if not self.engine or not self._connected:
            self.connect()

        affected = 0
        with self.get_connection() as conn:
            # SQLite can execute multiple statements
            # But need to handle them carefully
            statements = script.split(';')
            for stmt in statements:
                stmt = stmt.strip()
                if stmt:
                    try:
                        result = conn.execute(text(stmt))
                        affected += result.rowcount if result else 0
                    except Exception as e:
                        logger.error(f"Script execution failed: {e}")
                        raise

        return affected

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.vacuum()  # Optimize on exit
        self.disconnect()
