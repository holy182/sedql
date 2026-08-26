"""Role-based access control for SEDQL."""

from typing import Dict, List, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import re
import json
from pathlib import Path

from ..utils.logger import logger


class AccessLevel(str, Enum):
    """Access levels for users."""
    ADMIN = "admin"
    READ = "read"
    READ_WRITE = "read_write"
    READ_ONLY = "read_only"
    NONE = "none"


class ResourceType(str, Enum):
    """Types of resources."""
    TABLE = "table"
    COLUMN = "column"
    SCHEMA = "schema"
    DATABASE = "database"
    VIEW = "view"
    FUNCTION = "function"
    PROCEDURE = "procedure"


@dataclass
class UserContext:
    """User context for access control."""
    user_id: str
    username: str
    role: str
    access_level: AccessLevel
    groups: List[str] = field(default_factory=list)
    permissions: Dict[str, List[str]] = field(default_factory=dict)
    department: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AccessRule:
    """Access control rule."""
    id: str
    name: str
    description: str
    resource_type: ResourceType
    resource_name: str  # Can use wildcards: *, table.*, *.*
    access_level: AccessLevel
    allowed_operations: List[str]  # SELECT, INSERT, UPDATE, DELETE
    conditions: List[str] = field(default_factory=list)  # SQL conditions
    is_enabled: bool = True
    priority: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class AccessDecision:
    """Decision result for access check."""
    allowed: bool
    reason: str
    rule: Optional[AccessRule] = None
    suggestions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AccessController:
    """Role-based access control for SEDQL."""

    DEFAULT_RULES = {
        AccessLevel.ADMIN: {
            "tables": "*",
            "operations": ["SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP"]
        },
        AccessLevel.READ_WRITE: {
            "tables": "*",
            "operations": ["SELECT", "INSERT", "UPDATE"]
        },
        AccessLevel.READ_ONLY: {
            "tables": "*",
            "operations": ["SELECT"]
        },
        AccessLevel.READ: {
            "tables": "*",
            "operations": ["SELECT"]
        },
        AccessLevel.NONE: {
            "tables": "",
            "operations": []
        }
    }

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize access controller.

        Args:
            config_path: Path to access control configuration
        """
        self.config = self._load_config(config_path)
        self.rules: List[AccessRule] = []
        self.user_context: Optional[UserContext] = None
        self._custom_hooks: Dict[str, Callable] = {}

        # Load rules
        self._load_rules()

    def _load_config(self, config_path: Optional[Path]) -> Dict[str, Any]:
        """Load access control configuration."""
        if config_path and config_path.exists():
            try:
                with open(config_path) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load access config: {e}")

        return {
            "default_level": "read_only",
            "rules": [],
            "role_mappings": {}
        }

    def _load_rules(self) -> None:
        """Load access rules from configuration."""
        # Load custom rules from config
        for rule_config in self.config.get("rules", []):
            try:
                rule = AccessRule(
                    id=rule_config["id"],
                    name=rule_config.get("name", rule_config["id"]),
                    description=rule_config.get("description", ""),
                    resource_type=ResourceType(
                        rule_config.get("resource_type", "table")),
                    resource_name=rule_config.get("resource_name", "*"),
                    access_level=AccessLevel(
                        rule_config.get("access_level", "read_only")),
                    allowed_operations=rule_config.get(
                        "allowed_operations", ["SELECT"]),
                    conditions=rule_config.get("conditions", []),
                    is_enabled=rule_config.get("is_enabled", True),
                    priority=rule_config.get("priority", 0)
                )
                self.rules.append(rule)
            except Exception as e:
                logger.warning(
                    f"Failed to load rule {rule_config.get('id', 'unknown')}: {e}")

        # Add default rules based on role mappings
        role_mappings = self.config.get("role_mappings", {})
        for role, access_config in role_mappings.items():
            level = access_config.get("level", "read_only")
            try:
                level_enum = AccessLevel(level)
                rule = AccessRule(
                    id=f"role_{role}",
                    name=f"Role: {role}",
                    description=f"Default access for role {role}",
                    resource_type=ResourceType.TABLE,
                    resource_name="*",
                    access_level=level_enum,
                    allowed_operations=self.DEFAULT_RULES.get(
                        level_enum, ["SELECT"]),
                    is_enabled=True,
                    priority=10
                )
                self.rules.append(rule)
            except Exception as e:
                logger.warning(f"Failed to create role rule for {role}: {e}")

    def set_user_context(self, context: UserContext) -> None:
        """Set the current user context."""
        self.user_context = context
        logger.info(f"User context set: {context.username} ({context.role})")

    def clear_user_context(self) -> None:
        """Clear the current user context."""
        self.user_context = None
        logger.info("User context cleared")

    def check_access(
        self,
        resource_type: ResourceType,
        resource_name: str,
        operation: str,
        user_context: Optional[UserContext] = None
    ) -> AccessDecision:
        """
        Check if a user has access to a resource.

        Args:
            resource_type: Type of resource
            resource_name: Name of the resource
            operation: Operation to perform (SELECT, INSERT, UPDATE, DELETE)
            user_context: User context (uses current if not provided)

        Returns:
            AccessDecision object
        """
        context = user_context or self.user_context

        if not context:
            return AccessDecision(
                allowed=False,
                reason="No user context provided",
                suggestions=["Set user context with set_user_context()"]
            )

        # Get user's access level
        access_level = context.access_level

        # Check if user has admin level
        if access_level == AccessLevel.ADMIN:
            return AccessDecision(
                allowed=True,
                reason="Admin access granted",
                suggestions=[]
            )

        # Find applicable rules
        applicable_rules = []
        for rule in self.rules:
            if not rule.is_enabled:
                continue

            # Check if rule applies to this resource
            if not self._rule_applies(rule, resource_type, resource_name):
                continue

            # Check if rule's access level is sufficient
            if not self._level_sufficient(rule.access_level, operation):
                continue

            applicable_rules.append(rule)

        # Sort by priority (highest first)
        applicable_rules.sort(key=lambda r: r.priority, reverse=True)

        # Check each rule
        for rule in applicable_rules:
            # Check if operation is allowed
            if operation in rule.allowed_operations:
                # Check conditions
                if self._check_conditions(rule.conditions, resource_name, context):
                    return AccessDecision(
                        allowed=True,
                        reason=f"Rule matched: {rule.name}",
                        rule=rule,
                        suggestions=[]
                    )

        # No matching rule found
        return AccessDecision(
            allowed=False,
            reason=f"Access denied for {operation} on {resource_type.value} {resource_name}",
            suggestions=[
                f"Request higher access level (current: {access_level.value})",
                "Contact administrator for permissions"
            ],
            metadata={
                "resource_type": resource_type.value,
                "resource_name": resource_name,
                "operation": operation,
                "user_role": context.role
            }
        )

    def _rule_applies(self, rule: AccessRule, resource_type: ResourceType, resource_name: str) -> bool:
        """Check if a rule applies to a resource."""
        # Check resource type
        if rule.resource_type != resource_type:
            return False

        # Check resource name (wildcard support)
        rule_pattern = rule.resource_name

        if rule_pattern == "*":
            return True

        if rule_pattern.endswith("*"):
            # Prefix match
            prefix = rule_pattern[:-1]
            return resource_name.startswith(prefix)

        if rule_pattern.startswith("*"):
            # Suffix match
            suffix = rule_pattern[1:]
            return resource_name.endswith(suffix)

        # Exact match
        return resource_name == rule_pattern

    def _level_sufficient(self, rule_level: AccessLevel, operation: str) -> bool:
        """Check if a rule's access level allows an operation."""
        # Define operation requirements
        requirements = {
            "SELECT": AccessLevel.READ,
            "INSERT": AccessLevel.READ_WRITE,
            "UPDATE": AccessLevel.READ_WRITE,
            "DELETE": AccessLevel.READ_WRITE,
            "CREATE": AccessLevel.ADMIN,
            "DROP": AccessLevel.ADMIN
        }

        required = requirements.get(operation, AccessLevel.NONE)

        # Compare access levels
        levels = [AccessLevel.NONE, AccessLevel.READ,
                  AccessLevel.READ_WRITE, AccessLevel.ADMIN]
        return levels.index(rule_level) >= levels.index(required)

    def _check_conditions(self, conditions: List[str], resource_name: str, context: UserContext) -> bool:
        """Check if conditions are satisfied."""
        if not conditions:
            return True

        # Simple condition checking
        for condition in conditions:
            # Replace placeholders
            condition = condition.replace("$user_id", context.user_id)
            condition = condition.replace("$username", context.username)
            condition = condition.replace("$role", context.role)
            condition = condition.replace(
                "$department", context.department or "none")
            condition = condition.replace("$resource", resource_name)

            # Evaluate condition (simplified)
            # In production, you'd use a proper expression evaluator
            try:
                # Simple string replacement checks
                if "=" in condition:
                    left, right = condition.split("=", 1)
                    left = left.strip()
                    right = right.strip().strip("'\"")

                    if left in ["$user_id", "$username", "$role", "$department"]:
                        # Already replaced above
                        pass

                    # For simple equality checks
                    if "'" in left or '"' in left:
                        # String comparison
                        pass

                    return True  # Assume true if we can parse
                else:
                    return True
            except:
                logger.warning(f"Failed to evaluate condition: {condition}")
                return False

        return True

    def add_rule(self, rule: AccessRule) -> None:
        """Add a new access rule."""
        self.rules.append(rule)
        logger.info(f"Added access rule: {rule.name}")

    def remove_rule(self, rule_id: str) -> bool:
        """Remove an access rule."""
        original_count = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        removed = len(self.rules) < original_count

        if removed:
            logger.info(f"Removed access rule: {rule_id}")
        else:
            logger.warning(f"Rule not found: {rule_id}")

        return removed

    def enable_rule(self, rule_id: str) -> bool:
        """Enable an access rule."""
        for rule in self.rules:
            if rule.id == rule_id:
                rule.is_enabled = True
                logger.info(f"Enabled rule: {rule.name}")
                return True

        logger.warning(f"Rule not found: {rule_id}")
        return False

    def disable_rule(self, rule_id: str) -> bool:
        """Disable an access rule."""
        for rule in self.rules:
            if rule.id == rule_id:
                rule.is_enabled = False
                logger.info(f"Disabled rule: {rule.name}")
                return True

        logger.warning(f"Rule not found: {rule_id}")
        return False

    def get_rules_for_user(self, user_context: Optional[UserContext] = None) -> List[AccessRule]:
        """Get all rules applicable to a user."""
        context = user_context or self.user_context

        if not context:
            return []

        return [
            rule for rule in self.rules
            if rule.is_enabled and self._level_sufficient(rule.access_level, "SELECT")
        ]

    def get_user_permissions(
        self,
        user_context: Optional[UserContext] = None
    ) -> Dict[str, List[str]]:
        """
        Get all permissions for a user.

        Returns:
            Dictionary mapping resource names to allowed operations
        """
        context = user_context or self.user_context

        if not context:
            return {}

        permissions = {}

        for rule in self.rules:
            if not rule.is_enabled:
                continue

            if not self._level_sufficient(rule.access_level, "SELECT"):
                continue

            # Add operations to resource
            if rule.resource_name not in permissions:
                permissions[rule.resource_name] = []

            permissions[rule.resource_name].extend(rule.allowed_operations)

        return permissions

    def filter_accessible_data(
        self,
        data: List[Dict[str, Any]],
        resource_name: str,
        user_context: Optional[UserContext] = None
    ) -> List[Dict[str, Any]]:
        """Filter data based on access rules."""
        context = user_context or self.user_context

        if not context:
            return []

        # Get applicable rules
        rules = []
        for rule in self.rules:
            if not rule.is_enabled:
                continue

            if self._rule_applies(rule, ResourceType.TABLE, resource_name):
                rules.append(rule)

        # If no rules, return empty
        if not rules:
            return []

        # Apply rules to filter data
        filtered_data = []
        for row in data:
            # Check if row satisfies any rule
            allowed = False
            for rule in rules:
                if self._check_conditions(rule.conditions, resource_name, context):
                    allowed = True
                    break

            if allowed:
                filtered_data.append(row)

        return filtered_data

    def get_summary(self) -> Dict[str, Any]:
        """Get access control summary."""
        return {
            "total_rules": len(self.rules),
            "enabled_rules": len([r for r in self.rules if r.is_enabled]),
            "user_context_set": self.user_context is not None,
            "rules_by_type": {
                resource_type.value: len(
                    [r for r in self.rules if r.resource_type == resource_type])
                for resource_type in ResourceType
            },
            "rules_by_level": {
                level.value: len(
                    [r for r in self.rules if r.access_level == level])
                for level in AccessLevel
            }
        }
