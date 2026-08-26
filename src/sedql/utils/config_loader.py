"""Production-ready configuration loader with validation and environment support."""

import json
import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, List, Union
from dataclasses import dataclass, field
from datetime import datetime
import re

from .logger import logger


@dataclass
class ConfigValidation:
    """Configuration validation result."""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConfigLoader:
    """
    Production-ready configuration loader with advanced features.

    Features:
    - Multiple format support (JSON, YAML)
    - Environment variable interpolation
    - Default configuration
    - Configuration validation
    - Schema-based validation
    - Hot reload support
    - Configuration merging
    - Secret redaction
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        default_config: Optional[Dict[str, Any]] = None,
        allow_env_override: bool = True
    ):
        """
        Initialize configuration loader.

        Args:
            config_path: Path to configuration file
            default_config: Default configuration
            allow_env_override: Allow environment variable overrides
        """
        self.config_path = config_path
        self.default_config = default_config or {}
        self.allow_env_override = allow_env_override
        self._config: Dict[str, Any] = {}
        self._env_cache: Dict[str, str] = {}
        self._loaded_at: Optional[datetime] = None

        # Load configuration
        self.load()

    def load(self) -> Dict[str, Any]:
        """
        Load configuration from file and environment.

        Returns:
            Loaded configuration
        """
        # Start with defaults
        config = self.default_config.copy()

        # Load from file
        if self.config_path and self.config_path.exists():
            file_config = self._load_file(self.config_path)
            if file_config:
                config = self._merge_configs(config, file_config)

        # Apply environment overrides
        if self.allow_env_override:
            config = self._apply_env_overrides(config)

        # Interpolate environment variables
        config = self._interpolate_env_vars(config)

        self._config = config
        self._loaded_at = datetime.now()

        logger.info(f"Configuration loaded from: {self.config_path}")

        return config

    def reload(self) -> Dict[str, Any]:
        """Reload configuration from file."""
        if self.config_path:
            logger.info(f"Reloading configuration from: {self.config_path}")
        return self.load()

    def _load_file(self, path: Path) -> Dict[str, Any]:
        """Load configuration file based on extension."""
        try:
            suffix = path.suffix.lower()

            if suffix in ['.json']:
                with open(path) as f:
                    return json.load(f)
            elif suffix in ['.yaml', '.yml']:
                with open(path) as f:
                    return yaml.safe_load(f)
            else:
                logger.warning(f"Unknown config format: {suffix}")
                return {}

        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            return {}

    def _merge_configs(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two configurations."""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value

        return result

    def _apply_env_overrides(self, config: Dict) -> Dict:
        """Apply environment variable overrides."""
        env_prefix = "SEDQL_"

        for key, value in config.items():
            env_key = f"{env_prefix}{key.upper()}"

            if env_key in os.environ:
                config[key] = self._parse_env_value(os.environ[env_key])

            # Check nested keys
            if isinstance(value, dict):
                config[key] = self._apply_env_overrides(value)

        return config

    def _parse_env_value(self, value: str) -> Any:
        """Parse environment variable value."""
        # Try to parse as JSON
        try:
            return json.loads(value)
        except:
            pass

        # Try to parse as boolean
        if value.lower() == 'true':
            return True
        if value.lower() == 'false':
            return False

        # Try to parse as number
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except:
            pass

        return value

    def _interpolate_env_vars(self, config: Dict) -> Dict:
        """Interpolate environment variables in configuration."""
        for key, value in config.items():
            if isinstance(value, str):
                config[key] = self._interpolate_string(value)
            elif isinstance(value, dict):
                config[key] = self._interpolate_env_vars(value)
            elif isinstance(value, list):
                config[key] = [self._interpolate_string(item) if isinstance(item, str) else item
                               for item in value]

        return config

    def _interpolate_string(self, value: str) -> str:
        """Interpolate environment variables in a string."""
        if not value:
            return value

        pattern = r'\${([^}]+)}'

        def replace_match(match):
            var_name = match.group(1)
            var_value = os.environ.get(var_name)

            if var_value is None:
                logger.warning(f"Environment variable {var_name} not found")
                return match.group(0)

            return var_value

        return re.sub(pattern, replace_match, value)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.

        Args:
            key: Configuration key (e.g., "database.host")
            default: Default value if key not found

        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value using dot notation.

        Args:
            key: Configuration key (e.g., "database.host")
            value: Value to set
        """
        keys = key.split('.')
        target = self._config

        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]

        target[keys[-1]] = value

    def get_database_url(self) -> Optional[str]:
        """Get database connection URL."""
        # Check environment first
        db_url = os.environ.get('DATABASE_URL')
        if db_url:
            return db_url

        # Check config
        return self.get('database.url')

    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration."""
        return self.get('database', {})

    def get_semantic_config(self) -> Dict[str, Any]:
        """Get semantic layer configuration."""
        return self.get('semantic', {})

    def get_rules_config(self) -> Dict[str, Any]:
        """Get business rules configuration."""
        return self.get('rules', {})

    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration."""
        return self.get('security', {})

    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration."""
        return self.get('logging', {})

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration."""
        return self._config.copy()

    def validate(self, schema: Optional[Dict[str, Any]] = None) -> ConfigValidation:
        """
        Validate configuration against a schema.

        Args:
            schema: Validation schema

        Returns:
            ConfigValidation result
        """
        errors = []
        warnings = []

        if schema:
            self._validate_schema(self._config, schema, errors, warnings, '')

        # Check required fields
        if not self.get('database.url') and not os.environ.get('DATABASE_URL'):
            warnings.append("No database URL configured")

        return ConfigValidation(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            metadata={'config_path': str(
                self.config_path) if self.config_path else None}
        )

    def _validate_schema(
        self,
        config: Dict,
        schema: Dict,
        errors: List[str],
        warnings: List[str],
        prefix: str
    ) -> None:
        """Validate configuration against schema."""
        for key, rules in schema.items():
            full_key = f"{prefix}.{key}" if prefix else key

            if isinstance(rules, dict):
                # Check if this is a type definition or nested schema
                if 'type' in rules:
                    # Type validation
                    if key not in config:
                        if rules.get('required', False):
                            errors.append(
                                f"Missing required field: {full_key}")
                        continue

                    value = config[key]
                    expected_type = rules['type']

                    if not self._check_type(value, expected_type):
                        errors.append(
                            f"Invalid type for {full_key}: expected {expected_type}, got {type(value).__name__}"
                        )

                    # Check allowed values
                    if 'allowed' in rules and value not in rules['allowed']:
                        errors.append(
                            f"Invalid value for {full_key}: {value} not in {rules['allowed']}"
                        )

                    # Check min/max for numbers
                    if expected_type == 'number':
                        if 'min' in rules and value < rules['min']:
                            errors.append(
                                f"Value {value} for {full_key} below minimum {rules['min']}")
                        if 'max' in rules and value > rules['max']:
                            errors.append(
                                f"Value {value} for {full_key} above maximum {rules['max']}")

                    # Check min/max length for strings
                    if expected_type == 'string':
                        if 'min_length' in rules and len(value) < rules['min_length']:
                            errors.append(
                                f"String length for {full_key} below minimum {rules['min_length']}")
                        if 'max_length' in rules and len(value) > rules['max_length']:
                            errors.append(
                                f"String length for {full_key} above maximum {rules['max_length']}")

                elif key in config and isinstance(config[key], dict):
                    # Nested schema
                    self._validate_schema(
                        config[key], rules, errors, warnings, full_key)

                else:
                    # Skip nested validation if key not present
                    pass

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type."""
        type_map = {
            'string': str,
            'number': (int, float),
            'integer': int,
            'boolean': bool,
            'array': list,
            'object': dict,
            'null': type(None),
            'any': object
        }

        expected = type_map.get(expected_type, object)
        return isinstance(value, expected)

    def get_redacted(self, key: str) -> Any:
        """
        Get a configuration value with sensitive data redacted.

        Args:
            key: Configuration key

        Returns:
            Configuration value with sensitive data redacted
        """
        value = self.get(key)
        return self._redact_sensitive(value)

    def _redact_sensitive(self, value: Any) -> Any:
        """Redact sensitive information from configuration."""
        if isinstance(value, str):
            # Check if it looks like a secret
            if len(value) > 8 and any(c in value for c in ['password', 'secret', 'key', 'token']):
                return f"{value[:4]}...{value[-4:]}"
            return value

        if isinstance(value, dict):
            result = {}
            for k, v in value.items():
                if k.lower() in ['password', 'secret', 'api_key', 'token', 'private_key']:
                    result[k] = '***REDACTED***'
                else:
                    result[k] = self._redact_sensitive(v)
            return result

        if isinstance(value, list):
            return [self._redact_sensitive(item) for item in value]

        return value

    def get_loaded_at(self) -> Optional[datetime]:
        """Get when configuration was loaded."""
        return self._loaded_at

    def get_summary(self) -> Dict[str, Any]:
        """Get configuration summary."""
        return {
            'loaded_at': self._loaded_at.isoformat() if self._loaded_at else None,
            'config_path': str(self.config_path) if self.config_path else None,
            'config_keys': list(self._config.keys()),
            'has_database_url': bool(self.get_database_url()),
            'redacted_config': self._redact_sensitive(self._config)
        }

    def save(self, path: Optional[Path] = None) -> None:
        """
        Save configuration to file.

        Args:
            path: Path to save configuration (uses config_path if not provided)
        """
        save_path = path or self.config_path

        if not save_path:
            logger.error("No save path provided")
            return

        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)

            with open(save_path, 'w') as f:
                json.dump(self._config, f, indent=2)

            logger.info(f"Configuration saved to: {save_path}")

        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass


# ============================================================================
# Global config instance
# ============================================================================

config = ConfigLoader()


# ============================================================================
# Convenience functions
# ============================================================================

def get_config(key: str, default: Any = None) -> Any:
    """Get a configuration value."""
    return config.get(key, default)


def set_config(key: str, value: Any) -> None:
    """Set a configuration value."""
    config.set(key, value)


def reload_config() -> None:
    """Reload configuration."""
    config.reload()


def get_database_url() -> Optional[str]:
    """Get database connection URL."""
    return config.get_database_url()


# For backward compatibility
__all__ = [
    'config',
    'get_config',
    'set_config',
    'reload_config',
    'get_database_url',
    'ConfigLoader',
    'ConfigValidation'
]
