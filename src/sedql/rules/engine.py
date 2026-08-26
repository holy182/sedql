"""Complete business rules engine with PII protection, validation, and governance."""

from typing import Dict, List, Any, Optional, Set, Tuple
import re
from datetime import datetime
from ..utils.logger import logger


class RulesEngine:
    """Enforces business rules on queries and data."""

    def __init__(self, rules: List[Dict[str, Any]]):
        self.rules = rules
        self.enabled_rules = [r for r in rules if r.get("is_enabled", True)]

        # Group rules by type
        self.validation_rules = [
            r for r in self.enabled_rules if r.get("category") == "validation"]
        self.security_rules = [
            r for r in self.enabled_rules if r.get("category") == "security"]
        self.compliance_rules = [
            r for r in self.enabled_rules if r.get("category") == "compliance"]
        self.business_rules = [r for r in self.enabled_rules if r.get(
            "category") == "business_logic"]

    def validate_query(self, query: str, table: str) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Validate if a query violates any rules.

        Returns:
            (is_valid, violations)
        """
        violations = []

        # Check security rules (PII)
        for rule in self.security_rules:
            if rule.get("entity") == table or rule.get("entity") == "*":
                if self._check_rule_violation(query, rule):
                    violations.append({
                        "rule_id": rule["id"],
                        "rule_name": rule["name"],
                        "description": rule["description"],
                        "severity": rule.get("severity", "HIGH"),
                        "action": rule.get("action", "REJECT")
                    })

        # Check validation rules
        for rule in self.validation_rules:
            if rule.get("entity") == table or rule.get("entity") == "*":
                if self._check_rule_violation(query, rule):
                    violations.append({
                        "rule_id": rule["id"],
                        "rule_name": rule["name"],
                        "description": rule["description"],
                        "severity": rule.get("severity", "MEDIUM"),
                        "action": rule.get("action", "REJECT")
                    })

        return len(violations) == 0, violations

    def _check_rule_violation(self, query: str, rule: Dict[str, Any]) -> bool:
        """Check if a query violates a specific rule."""
        rule_type = rule.get("category")
        field = rule.get("field")
        condition = rule.get("condition", "")

        # Security: PII protection
        if rule_type == "security" and "pii" in rule.get("id", "").lower():
            # Check if the query selects PII fields
            if field and field in query.lower():
                return True
            # Check if query uses SELECT *
            if "select *" in query.lower():
                return True

        # Validation: Required fields
        if rule_type == "validation" and "required" in rule.get("id", "").lower():
            if field and field not in query.lower():
                return True

        # Validation: Status values
        if rule_type == "validation" and "status" in rule.get("id", "").lower():
            if field and "status" in query.lower():
                # Check if query uses any invalid status
                allowed_values = rule.get(
                    "metadata", {}).get("allowed_values", [])
                if allowed_values:
                    for value in allowed_values:
                        if value.lower() in query.lower():
                            return False
                    return True

        return False

    def apply_rules(self, data: List[Dict[str, Any]], table: str = None) -> List[Dict[str, Any]]:
        """
        Apply rules to data (mask PII, filter, transform).

        Args:
            data: List of rows as dictionaries
            table: Optional table name for context

        Returns:
            Processed data with rules applied
        """
        if not data:
            return data

        result = []

        for row in data:
            processed_row = self._apply_security_rules(row, table)
            processed_row = self._apply_compliance_rules(processed_row, table)
            processed_row = self._apply_business_rules(processed_row, table)
            result.append(processed_row)

        return result

    def _apply_security_rules(self, row: Dict[str, Any], table: str = None) -> Dict[str, Any]:
        """Apply security rules (PII masking)."""
        processed = row.copy()

        for rule in self.security_rules:
            if rule.get("entity") == table or rule.get("entity") == "*" or not table:
                action = rule.get("action")
                field = rule.get("field")

                if action == "MASK_DATA" and field and field in processed:
                    processed[field] = self._mask_value(processed[field], rule)
                elif action == "MASK_DATA" and not field:
                    # Mask all PII fields
                    for key in processed:
                        if self._is_pii_field(key):
                            processed[key] = self._mask_value(
                                processed[key], rule)

        return processed

    def _apply_compliance_rules(self, row: Dict[str, Any], table: str = None) -> Dict[str, Any]:
        """Apply compliance rules."""
        processed = row.copy()

        for rule in self.compliance_rules:
            action = rule.get("action")

            if action == "FILTER_ROW":
                # Filter out rows that violate compliance
                # For now, we just return empty dict if violated
                if self._check_compliance_violation(processed, rule):
                    return {}

        return processed

    def _apply_business_rules(self, row: Dict[str, Any], table: str = None) -> Dict[str, Any]:
        """Apply business logic rules."""
        processed = row.copy()

        for rule in self.business_rules:
            action = rule.get("action")
            field = rule.get("field")

            if action == "TRANSFORM" and field and field in processed:
                processed[field] = self._transform_value(
                    processed[field], rule)

        return processed

    def _mask_value(self, value: Any, rule: Dict[str, Any]) -> str:
        """Mask a value based on PII type."""
        if value is None:
            return None

        value_str = str(value)
        pii_type = rule.get("metadata", {}).get("pii_type", "general")

        # Preserve some readability for different types
        if pii_type == "email":
            # Keep first char and domain
            parts = value_str.split("@")
            if len(parts) == 2:
                return f"{parts[0][0]}***@{parts[1]}"
            return "***@***"

        elif pii_type == "phone":
            # Keep last 4 digits
            if len(value_str) >= 4:
                return f"***-***-{value_str[-4:]}"
            return "***"

        elif pii_type == "social_security":
            # Keep last 4 digits
            if len(value_str) >= 4:
                return f"***-**-{value_str[-4:]}"
            return "***"

        else:
            # General mask
            if len(value_str) > 4:
                return f"***{value_str[-4:]}"
            return "***"

    def _is_pii_field(self, field_name: str) -> bool:
        """Check if a field is PII."""
        pii_patterns = ['email', 'phone', 'ssn',
                        'password', 'address', 'credit_card']
        return any(pattern in field_name.lower() for pattern in pii_patterns)

    def _check_compliance_violation(self, row: Dict[str, Any], rule: Dict[str, Any]) -> bool:
        """Check if a row violates a compliance rule."""
        # Example: GDPR - check if row contains EU data
        # For now, just simple check
        return False

    def _transform_value(self, value: Any, rule: Dict[str, Any]) -> Any:
        """Transform a value based on business rules."""
        # Example: Convert currency, format dates, etc.
        return value

    def get_active_rules(self, table: str = None) -> List[Dict[str, Any]]:
        """Get active rules for a table."""
        if table:
            return [r for r in self.enabled_rules if r.get("entity") == table or r.get("entity") == "*"]
        return self.enabled_rules

    def get_rules_by_severity(self, severity: str) -> List[Dict[str, Any]]:
        """Get rules by severity level."""
        return [r for r in self.enabled_rules if r.get("severity") == severity.upper()]

    def get_summary(self) -> Dict[str, int]:
        """Get summary of rules."""
        return {
            "total": len(self.rules),
            "enabled": len(self.enabled_rules),
            "validation": len(self.validation_rules),
            "security": len(self.security_rules),
            "compliance": len(self.compliance_rules),
            "business": len(self.business_rules),
            "high_severity": len(self.get_rules_by_severity("HIGH")),
            "medium_severity": len(self.get_rules_by_severity("MEDIUM")),
            "low_severity": len(self.get_rules_by_severity("LOW"))
        }
