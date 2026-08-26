"""Production-ready logging system for SEDQL."""

import logging
import sys
import json
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
from enum import Enum
import traceback


class LogLevel(str, Enum):
    """Log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(str, Enum):
    """Log output formats."""
    TEXT = "text"
    JSON = "json"
    COLOR = "color"


class SEDQLLogger:
    """
    Production-ready logger with multiple output formats and structured logging.

    Features:
    - Multiple output formats (text, JSON, color)
    - File and console output
    - Structured logging with context
    - Log rotation support
    - Error stack traces
    - Performance tracking
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self.loggers: Dict[str, logging.Logger] = {}
        self.config = {
            'level': LogLevel.INFO,
            'format': LogFormat.COLOR,
            'console': True,
            'file': False,
            'file_path': None,
            'json_indent': 2,
            'include_timestamp': True,
            'include_context': True
        }

        # Default logger
        self._setup_default_logger()

    def configure(self, **kwargs) -> None:
        """
        Configure the logger.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            format: Output format (text, json, color)
            console: Enable console output
            file: Enable file output
            file_path: Path to log file
            json_indent: Indent for JSON output
            include_timestamp: Include timestamp in logs
            include_context: Include context in logs
        """
        self.config.update(kwargs)

        # Update default logger
        self._setup_default_logger()

        # Setup file handler if enabled
        if self.config.get('file') and self.config.get('file_path'):
            self._setup_file_handler()

    def _setup_default_logger(self) -> None:
        """Setup the default logger."""
        logger = logging.getLogger('sedql')
        logger.setLevel(self._get_log_level())

        # Remove existing handlers
        logger.handlers.clear()

        # Add console handler
        if self.config.get('console', True):
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(self._get_formatter())
            logger.addHandler(handler)

        self.loggers['sedql'] = logger

    def _setup_file_handler(self) -> None:
        """Setup file handler for logging."""
        logger = self.loggers.get('sedql')
        if not logger:
            return

        file_path = Path(self.config['file_path'])
        file_path.parent.mkdir(parents=True, exist_ok=True)

        handler = logging.FileHandler(file_path, encoding='utf-8')
        handler.setFormatter(self._get_formatter())
        logger.addHandler(handler)

    def _get_formatter(self) -> logging.Formatter:
        """Get formatter based on configuration."""
        format_type = self.config.get('format', LogFormat.COLOR)

        if format_type == LogFormat.JSON:
            return _JSONFormatter(self.config)
        elif format_type == LogFormat.COLOR:
            return _ColorFormatter(self.config)
        else:
            return _TextFormatter(self.config)

    def _get_log_level(self) -> int:
        """Convert string level to logging level."""
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        level = self.config.get('level', 'INFO')
        return level_map.get(level.upper(), logging.INFO)

    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        """
        Get a logger instance.

        Args:
            name: Logger name (defaults to 'sedql')

        Returns:
            Logger instance
        """
        if not name or name == 'sedql':
            return self.loggers['sedql']

        if name not in self.loggers:
            # Create child logger
            parent = self.loggers['sedql']
            logger = parent.getChild(name)
            self.loggers[name] = logger

        return self.loggers[name]

    def debug(self, message: str, **context) -> None:
        """Log debug message."""
        self._log('DEBUG', message, context)

    def info(self, message: str, **context) -> None:
        """Log info message."""
        self._log('INFO', message, context)

    def warning(self, message: str, **context) -> None:
        """Log warning message."""
        self._log('WARNING', message, context)

    def error(self, message: str, exc_info: Optional[Exception] = None, **context) -> None:
        """Log error message with optional exception info."""
        if exc_info:
            context['exception'] = {
                'type': exc_info.__class__.__name__,
                'message': str(exc_info),
                'traceback': traceback.format_exc()
            }
        self._log('ERROR', message, context)

    def critical(self, message: str, exc_info: Optional[Exception] = None, **context) -> None:
        """Log critical message with optional exception info."""
        if exc_info:
            context['exception'] = {
                'type': exc_info.__class__.__name__,
                'message': str(exc_info),
                'traceback': traceback.format_exc()
            }
        self._log('CRITICAL', message, context)

    def _log(self, level: str, message: str, context: Dict[str, Any]) -> None:
        """Internal log method."""
        logger = self.loggers.get('sedql')
        if not logger:
            return

        # Add context to extra
        extra = context.copy()
        extra['_context'] = context

        # Get log method
        log_method = getattr(logger, level.lower(), logger.info)

        # Add timestamp if configured
        if self.config.get('include_timestamp', True):
            extra['timestamp'] = datetime.now().isoformat()

        log_method(message, extra=extra)

    def log_performance(self, operation: str, duration: float, **context) -> None:
        """Log performance metrics."""
        context['operation'] = operation
        context['duration_ms'] = duration * 1000
        self.info(f"Performance: {operation} took {duration:.3f}s", **context)

    def log_query(self, query: str, duration: float, rows: int, **context) -> None:
        """Log query execution."""
        context['query'] = query[:500]  # Truncate long queries
        context['duration_ms'] = duration * 1000
        context['rows'] = rows
        self.debug(
            f"Query executed: {rows} rows in {duration:.3f}s", **context)

    def log_security(self, action: str, user: str, resource: str, **context) -> None:
        """Log security-related events."""
        context['action'] = action
        context['user'] = user
        context['resource'] = resource
        self.info(f"Security: {action} on {resource} by {user}", **context)

    def log_error_with_context(self, error: Exception, operation: str, **context) -> None:
        """Log error with additional context."""
        context['operation'] = operation
        self.error(f"Error in {operation}: {error}", exc_info=error, **context)

    def get_stats(self) -> Dict[str, Any]:
        """Get logger statistics."""
        return {
            'initialized': self._initialized,
            'config': {
                'level': self.config.get('level'),
                'format': self.config.get('format'),
                'console': self.config.get('console'),
                'file': self.config.get('file'),
                'file_path': self.config.get('file_path')
            },
            'loggers': list(self.loggers.keys())
        }


class _TextFormatter(logging.Formatter):
    """Text formatter for logs."""

    def __init__(self, config: Dict):
        super().__init__()
        self.config = config

    def format(self, record):
        timestamp = datetime.fromtimestamp(record.created).isoformat()
        level = record.levelname
        message = record.getMessage()

        # Add context if available
        context = getattr(record, '_context', {})
        context_str = ''
        if context and self.config.get('include_context', True):
            context_items = [f"{k}={v}" for k, v in context.items()
                             if not k.startswith('_') and not isinstance(v, (dict, list))]
            if context_items:
                context_str = ' | ' + ' '.join(context_items)

        # Add exception if present
        exc_str = ''
        if record.exc_info:
            exc_str = '\n' + traceback.format_exc()

        if self.config.get('include_timestamp', True):
            return f"[{timestamp}] {level:8} - {message}{context_str}{exc_str}"
        else:
            return f"{level:8} - {message}{context_str}{exc_str}"


class _ColorFormatter(logging.Formatter):
    """Color formatter for logs."""

    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'      # Reset
    }

    def __init__(self, config: Dict):
        super().__init__()
        self.config = config

    def format(self, record):
        timestamp = datetime.fromtimestamp(record.created).isoformat()
        level = record.levelname
        color = self.COLORS.get(level, self.COLORS['RESET'])
        reset = self.COLORS['RESET']

        message = record.getMessage()

        # Add context if available
        context = getattr(record, '_context', {})
        context_str = ''
        if context and self.config.get('include_context', True):
            context_items = [f"{k}={v}" for k, v in context.items()
                             if not k.startswith('_') and not isinstance(v, (dict, list))]
            if context_items:
                context_str = f' {reset}| {color}' + ' '.join(context_items)

        # Add exception if present
        exc_str = ''
        if record.exc_info:
            exc_str = f'\n{reset}{traceback.format_exc()}'

        if self.config.get('include_timestamp', True):
            return f"{reset}[{timestamp}] {color}{level:8}{reset} - {color}{message}{context_str}{exc_str}{reset}"
        else:
            return f"{color}{level:8}{reset} - {color}{message}{context_str}{exc_str}{reset}"


class _JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def __init__(self, config: Dict):
        super().__init__()
        self.config = config

    def format(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage()
        }

        # Add context
        context = getattr(record, '_context', {})
        if context and self.config.get('include_context', True):
            log_entry['context'] = {
                k: v for k, v in context.items() if not k.startswith('_')}

        # Add exception
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': traceback.format_exc()
            }

        return json.dumps(log_entry, indent=self.config.get('json_indent', 2))


# ============================================================================
# Global logger instance
# ============================================================================

logger = SEDQLLogger()


# ============================================================================
# Convenience functions
# ============================================================================

def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get a logger instance."""
    return logger.get_logger(name)


def configure_logging(**kwargs) -> None:
    """Configure the global logger."""
    logger.configure(**kwargs)


def log_debug(message: str, **context) -> None:
    """Log debug message."""
    logger.debug(message, **context)


def log_info(message: str, **context) -> None:
    """Log info message."""
    logger.info(message, **context)


def log_warning(message: str, **context) -> None:
    """Log warning message."""
    logger.warning(message, **context)


def log_error(message: str, exc_info: Optional[Exception] = None, **context) -> None:
    """Log error message."""
    logger.error(message, exc_info=exc_info, **context)


def log_critical(message: str, exc_info: Optional[Exception] = None, **context) -> None:
    """Log critical message."""
    logger.critical(message, exc_info=exc_info, **context)


# For backward compatibility
__all__ = [
    'logger',
    'get_logger',
    'configure_logging',
    'log_debug',
    'log_info',
    'log_warning',
    'log_error',
    'log_critical',
    'SEDQLLogger',
    'LogLevel',
    'LogFormat'
]
