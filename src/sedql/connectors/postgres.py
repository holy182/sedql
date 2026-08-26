"""PostgreSQL connector with production-ready features."""

from typing import Dict, List, Any, Optional
from urllib.parse import urlparse

from .base import BaseConnector, ConnectionConfig
from ..utils.logger import logger


class PostgresConnector(BaseConnector):
    """Production-ready PostgreSQL connector."""

    def __init__(self, connection_url: str, config: Optional[ConnectionConfig] = None):
        """
        Initialize PostgreSQL connector.

        Args:
            connection_url: PostgreSQL connection URL
            config: Connection configuration
        """
        super().__init__(connection_url, config)
        self._schema = 'public'
        self._extract_schema()

    def _extract_schema(self) -> None:
        """Extract schema from URL."""
        parsed = urlparse(self.connection_url)
        # PostgreSQL URLs: postgresql://user:pass@host:port/db?options
        # Schema can be specified in options or defaults to public
        if parsed.query:
            for param in parsed.query.split('&'):
                if param.startswith('schema='):
                    self._schema = param.split('=')[1]
                    break

    def get_table_names(self, schema: Optional[str] = None) -> List[str]:
        """Get table names with schema support."""
        if not self.engine or not self._connected:
            self.connect()

        schema_to_use = schema or self._schema

        try:
            # Use SQLAlchemy inspector with schema
            inspector = inspect(self.engine)
            return inspector.get_table_names(schema=schema_to_use)
        except:
            # Fallback
            return super().get_table_names()

    def get_columns(self, table: str, schema: Optional[str] = None) -> List[Dict]:
        """Get columns with schema support."""
        if not self.engine or not self._connected:
            self.connect()

        schema_to_use = schema or self._schema

        try:
            inspector = inspect(self.engine)
            return inspector.get_columns(table, schema=schema_to_use)
        except:
            return super().get_columns(table)

    def get_primary_keys(self, table: str, schema: Optional[str] = None) -> List[str]:
        """Get primary keys with schema support."""
        if not self.engine or not self._connected:
            self.connect()

        schema_to_use = schema or self._schema

        try:
            inspector = inspect(self.engine)
            pk = inspector.get_pk_constraint(table, schema=schema_to_use)
            return pk.get('constrained_columns', [])
        except:
            return super().get_primary_keys(table)

    def get_foreign_keys(self, table: str, schema: Optional[str] = None) -> List[Dict]:
        """Get foreign keys with schema support."""
        if not self.engine or not self._connected:
            self.connect()

        schema_to_use = schema or self._schema

        try:
            inspector = inspect(self.engine)
            return inspector.get_foreign_keys(table, schema=schema_to_use)
        except:
            return super().get_foreign_keys(table)

    def get_indexes(self, table: str, schema: Optional[str] = None) -> List[Dict]:
        """Get indexes with schema support."""
        if not self.engine or not self._connected:
            self.connect()

        schema_to_use = schema or self._schema

        try:
            inspector = inspect(self.engine)
            return inspector.get_indexes(table, schema=schema_to_use)
        except:
            return super().get_indexes(table)

    def get_table_comment(self, table: str) -> str:
        """Get table comment."""
        try:
            query = f"""
                SELECT obj_description('{table}'::regclass) as comment
            """
            results = self.execute_query(query)
            return results[0].get('comment', '') if results else ''
        except:
            return ''

    def get_schema_info(self, schema: Optional[str] = None) -> Dict[str, Any]:
        """Get PostgreSQL schema information."""
        schema_to_use = schema or self._schema

        info = {
            'tables': [],
            'views': [],
            'functions': [],
            'sequences': []
        }

        try:
            # Get tables
            tables_query = f"""
                SELECT table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = '{schema_to_use}'
            """
            results = self.execute_query(tables_query)

            for row in results:
                if row.get('table_type') == 'VIEW':
                    info['views'].append(row['table_name'])
                else:
                    info['tables'].append(row['table_name'])

            # Get sequences
            seq_query = f"""
                SELECT sequence_name
                FROM information_schema.sequences
                WHERE sequence_schema = '{schema_to_use}'
            """
            seq_results = self.execute_query(seq_query)
            info['sequences'] = [row['sequence_name'] for row in seq_results]

        except Exception as e:
            logger.warning(f"Failed to get PostgreSQL schema info: {e}")

        return info

    def get_relation_sizes(self) -> Dict[str, int]:
        """Get sizes of all relations."""
        sizes = {}
        try:
            query = """
                SELECT 
                    relname,
                    pg_total_relation_size(relid) as total_size,
                    pg_relation_size(relid) as data_size,
                    pg_indexes_size(relid) as index_size
                FROM pg_catalog.pg_statio_user_tables
            """
            results = self.execute_query(query)
            for row in results:
                sizes[row['relname']] = {
                    'total': row['total_size'],
                    'data': row['data_size'],
                    'index': row['index_size']
                }
        except Exception as e:
            logger.warning(f"Failed to get relation sizes: {e}")

        return sizes

    def vacuum_analyze(self, table: Optional[str] = None) -> None:
        """Run VACUUM ANALYZE on a table or all tables."""
        try:
            if table:
                self.execute_query(f"VACUUM ANALYZE {table}")
                logger.info(f"Vacuum analyzed table: {table}")
            else:
                self.execute_query("VACUUM ANALYZE")
                logger.info("Vacuum analyzed all tables")
        except Exception as e:
            logger.error(f"Vacuum analyze failed: {e}")

    def explain(self, query: str, format: str = 'json') -> Dict[str, Any]:
        """Get query execution plan."""
        try:
            explain_query = f"EXPLAIN (FORMAT {format}) {query}"
            results = self.execute_query(explain_query)
            return {'plan': results}
        except Exception as e:
            logger.error(f"Explain failed: {e}")
            return {'error': str(e)}

    def get_table_stats(self, table: str) -> Dict[str, Any]:
        """Get PostgreSQL table statistics."""
        stats = {}
        try:
            query = f"""
                SELECT 
                    n_live_tup as live_rows,
                    n_dead_tup as dead_rows,
                    n_mod_since_analyze as modified_since_analyze,
                    last_analyze,
                    last_autoanalyze,
                    last_vacuum,
                    last_autovacuum
                FROM pg_stat_user_tables
                WHERE relname = '{table}'
            """
            results = self.execute_query(query)
            if results:
                stats = results[0]
        except Exception as e:
            logger.warning(f"Failed to get table stats for {table}: {e}")

        return stats
