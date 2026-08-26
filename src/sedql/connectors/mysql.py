"""MySQL connector with production-ready features."""

from typing import Dict, List, Any, Optional
from urllib.parse import urlparse

from .base import BaseConnector, ConnectionConfig
from ..utils.logger import logger


class MySQLConnector(BaseConnector):
    """Production-ready MySQL connector."""

    def __init__(self, connection_url: str, config: Optional[ConnectionConfig] = None):
        """
        Initialize MySQL connector.

        Args:
            connection_url: MySQL connection URL
            config: Connection configuration
        """
        super().__init__(connection_url, config)
        self._database = self._extract_database()

    def _extract_database(self) -> str:
        """Extract database name from URL."""
        parsed = urlparse(self.connection_url)
        return parsed.path.strip('/') if parsed.path else ''

    def get_table_names(self, database: Optional[str] = None) -> List[str]:
        """Get table names with database support."""
        if not self.engine or not self._connected:
            self.connect()

        db_to_use = database or self._database

        try:
            inspector = inspect(self.engine)
            return inspector.get_table_names()
        except:
            return super().get_table_names()

    def get_table_comment(self, table: str) -> str:
        """Get table comment."""
        try:
            query = f"""
                SELECT TABLE_COMMENT as comment
                FROM information_schema.TABLES
                WHERE TABLE_NAME = '{table}'
            """
            results = self.execute_query(query)
            return results[0].get('comment', '') if results else ''
        except:
            return ''

    def get_column_comments(self, table: str) -> Dict[str, str]:
        """Get column comments."""
        comments = {}
        try:
            query = f"""
                SELECT COLUMN_NAME, COLUMN_COMMENT
                FROM information_schema.COLUMNS
                WHERE TABLE_NAME = '{table}'
            """
            results = self.execute_query(query)
            for row in results:
                if row.get('COLUMN_COMMENT'):
                    comments[row['COLUMN_NAME']] = row['COLUMN_COMMENT']
        except:
            pass

        return comments

    def get_engine_info(self, table: str) -> Optional[str]:
        """Get MySQL table engine (InnoDB, MyISAM, etc.)."""
        try:
            query = f"""
                SELECT ENGINE as engine
                FROM information_schema.TABLES
                WHERE TABLE_NAME = '{table}'
            """
            results = self.execute_query(query)
            return results[0].get('engine') if results else None
        except:
            return None

    def get_character_set(self, table: str) -> Optional[str]:
        """Get MySQL character set."""
        try:
            query = f"""
                SELECT TABLE_COLLATION as collation
                FROM information_schema.TABLES
                WHERE TABLE_NAME = '{table}'
            """
            results = self.execute_query(query)
            if results and results[0].get('collation'):
                return results[0]['collation'].split('_')[0]
        except:
            pass
        return None

    def get_schema_info(self) -> Dict[str, Any]:
        """Get MySQL schema information."""
        info = {
            'tables': [],
            'views': [],
            'procedures': [],
            'functions': [],
            'triggers': [],
            'events': []
        }

        try:
            # Get tables and views
            query = """
                SELECT 
                    TABLE_NAME,
                    TABLE_TYPE,
                    TABLE_COMMENT
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
            """
            results = self.execute_query(query)

            for row in results:
                if row.get('TABLE_TYPE') == 'VIEW':
                    info['views'].append(row['TABLE_NAME'])
                else:
                    info['tables'].append(row['TABLE_NAME'])

            # Get procedures
            proc_query = """
                SELECT ROUTINE_NAME
                FROM information_schema.ROUTINES
                WHERE ROUTINE_SCHEMA = DATABASE()
                AND ROUTINE_TYPE = 'PROCEDURE'
            """
            proc_results = self.execute_query(proc_query)
            info['procedures'] = [row['ROUTINE_NAME'] for row in proc_results]

            # Get functions
            func_query = """
                SELECT ROUTINE_NAME
                FROM information_schema.ROUTINES
                WHERE ROUTINE_SCHEMA = DATABASE()
                AND ROUTINE_TYPE = 'FUNCTION'
            """
            func_results = self.execute_query(func_query)
            info['functions'] = [row['ROUTINE_NAME'] for row in func_results]

            # Get triggers
            trigger_query = """
                SELECT TRIGGER_NAME
                FROM information_schema.TRIGGERS
                WHERE TRIGGER_SCHEMA = DATABASE()
            """
            trigger_results = self.execute_query(trigger_query)
            info['triggers'] = [row['TRIGGER_NAME'] for row in trigger_results]

        except Exception as e:
            logger.warning(f"Failed to get MySQL schema info: {e}")

        return info

    def get_table_sizes(self) -> Dict[str, int]:
        """Get table sizes in bytes."""
        sizes = {}
        try:
            query = """
                SELECT 
                    table_name,
                    data_length + index_length as total_size,
                    data_length as data_size,
                    index_length as index_size
                FROM information_schema.TABLES
                WHERE table_schema = DATABASE()
            """
            results = self.execute_query(query)
            for row in results:
                sizes[row['table_name']] = {
                    'total': row['total_size'],
                    'data': row['data_size'],
                    'index': row['index_size']
                }
        except Exception as e:
            logger.warning(f"Failed to get table sizes: {e}")

        return sizes

    def get_table_status(self, table: str) -> Dict[str, Any]:
        """Get MySQL table status."""
        try:
            query = f"""
                SHOW TABLE STATUS LIKE '{table}'
            """
            results = self.execute_query(query)
            return results[0] if results else {}
        except Exception as e:
            logger.warning(f"Failed to get table status for {table}: {e}")
            return {}

    def get_variables(self) -> Dict[str, str]:
        """Get MySQL system variables."""
        variables = {}
        try:
            query = "SHOW VARIABLES"
            results = self.execute_query(query)
            for row in results:
                variables[row['Variable_name']] = row['Value']
        except Exception as e:
            logger.warning(f"Failed to get MySQL variables: {e}")

        return variables

    def get_process_list(self) -> List[Dict]:
        """Get MySQL process list."""
        try:
            query = "SHOW PROCESSLIST"
            return self.execute_query(query)
        except Exception as e:
            logger.warning(f"Failed to get process list: {e}")
            return []

    def kill_connection(self, connection_id: int) -> bool:
        """Kill a MySQL connection."""
        try:
            self.execute_query(f"KILL {connection_id}")
            logger.info(f"Killed connection: {connection_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to kill connection {connection_id}: {e}")
            return False
