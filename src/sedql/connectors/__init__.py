"""Database connectors with production-ready features."""

from .base import BaseConnector, ConnectionConfig
from .postgres import PostgresConnector
from .mysql import MySQLConnector
from .sqlite import SQLiteConnector


def get_connector(connection_url: str, config: ConnectionConfig = None) -> BaseConnector:
    """
    Get the appropriate connector for a database URL.

    Args:
        connection_url: Database connection URL
        config: Connection configuration

    Returns:
        BaseConnector instance

    Raises:
        ValueError: If database type is not supported
    """
    url_lower = connection_url.lower()

    if 'postgresql' in url_lower or 'postgres' in url_lower:
        return PostgresConnector(connection_url, config)
    elif 'mysql' in url_lower:
        return MySQLConnector(connection_url, config)
    elif 'sqlite' in url_lower:
        return SQLiteConnector(connection_url, config)
    else:
        supported = ['postgresql', 'postgres', 'mysql', 'sqlite']
        raise ValueError(
            f"Unsupported database: {connection_url}. Supported: {supported}")


__all__ = [
    "BaseConnector",
    "ConnectionConfig",
    "PostgresConnector",
    "MySQLConnector",
    "SQLiteConnector",
    "get_connector"
]
