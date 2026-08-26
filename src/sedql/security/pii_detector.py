"""PII (Personally Identifiable Information) detection and classification."""

from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re
import json
from pathlib import Path

from ..utils.logger import logger


class PIIType(str, Enum):
    """Types of PII data."""
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    ADDRESS = "address"
    NAME = "name"
    DATE_OF_BIRTH = "date_of_birth"
    PASSPORT = "passport"
    DRIVERS_LICENSE = "drivers_license"
    BANK_ACCOUNT = "bank_account"
    IP_ADDRESS = "ip_address"
    GPS_COORDINATES = "gps_coordinates"
    MEDICAL_RECORD = "medical_record"
    FINANCIAL = "financial"
    PASSWORD = "password"
    USERNAME = "username"
    GENERAL = "general_pii"


@dataclass
class PIIInfo:
    """Information about detected PII."""
    type: PIIType
    column: str
    table: str
    confidence: float  # 0-1
    pattern_matched: str
    sample_values: List[str] = field(default_factory=list)
    severity: str = "HIGH"  # HIGH, MEDIUM, LOW
    masking_rule: str = "***"
    detection_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PIIAnalysis:
    """Complete PII analysis result."""
    detected_items: List[PIIInfo] = field(default_factory=list)
    total_pii_columns: int = 0
    pii_by_type: Dict[str, int] = field(default_factory=dict)
    pii_by_table: Dict[str, int] = field(default_factory=dict)
    high_severity_count: int = 0
    medium_severity_count: int = 0
    low_severity_count: int = 0
    coverage_percentage: float = 0.0
    summary: str = ""


class PIIDetector:
    """Detect and classify PII in database schemas and data."""

    # PII patterns for detection
    PII_PATTERNS = {
        PIIType.EMAIL: {
            'pattern': r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            'column_patterns': ['email', 'e-mail', 'mail', 'email_address'],
            'severity': 'HIGH',
            'masking_rule': '***@***'
        },
        PIIType.PHONE: {
            'pattern': r'^\+?1?\d{9,15}$',
            'column_patterns': ['phone', 'mobile', 'cell', 'telephone', 'phone_number'],
            'severity': 'HIGH',
            'masking_rule': '***-***-****'
        },
        PIIType.SSN: {
            'pattern': r'\d{3}-\d{2}-\d{4}',
            'column_patterns': ['ssn', 'social', 'social_security', 'socialsecurity'],
            'severity': 'CRITICAL',
            'masking_rule': '***-**-****'
        },
        PIIType.CREDIT_CARD: {
            'pattern': r'\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}',
            'column_patterns': ['credit', 'card', 'cc_number', 'card_number', 'credit_card'],
            'severity': 'CRITICAL',
            'masking_rule': '****-****-****-****'
        },
        PIIType.ADDRESS: {
            'pattern': r'\d+\s+[a-zA-Z]+\s+[a-zA-Z]+',
            'column_patterns': ['address', 'street', 'location', 'mailing_address'],
            'severity': 'MEDIUM',
            'masking_rule': '*** ADDRESS ***'
        },
        PIIType.NAME: {
            'pattern': r'[A-Z][a-z]+ [A-Z][a-z]+',
            'column_patterns': ['name', 'full_name', 'first_name', 'last_name'],
            'severity': 'MEDIUM',
            'masking_rule': '***'
        },
        PIIType.DATE_OF_BIRTH: {
            'pattern': r'\d{4}-\d{2}-\d{2}',
            'column_patterns': ['dob', 'birth', 'date_of_birth', 'birth_date'],
            'severity': 'HIGH',
            'masking_rule': '****-**-**'
        },
        PIIType.PASSPORT: {
            'pattern': r'[A-Z]{2}\d{7}',
            'column_patterns': ['passport', 'passport_number'],
            'severity': 'CRITICAL',
            'masking_rule': '***-***'
        },
        PIIType.DRIVERS_LICENSE: {
            'pattern': r'[A-Z]\d{7,8}',
            'column_patterns': ['drivers_license', 'license_number', 'driver_license'],
            'severity': 'HIGH',
            'masking_rule': '***-***'
        },
        PIIType.BANK_ACCOUNT: {
            'pattern': r'\d{10,12}',
            'column_patterns': ['bank_account', 'account_number', 'bank_account_number'],
            'severity': 'CRITICAL',
            'masking_rule': '***-***'
        },
        PIIType.PASSWORD: {
            'pattern': r'.+',
            'column_patterns': ['password', 'passwd', 'pwd', 'password_hash'],
            'severity': 'CRITICAL',
            'masking_rule': '********'
        },
        PIIType.USERNAME: {
            'pattern': r'[a-zA-Z0-9_]{3,20}',
            'column_patterns': ['username', 'user_name', 'login'],
            'severity': 'LOW',
            'masking_rule': '***'
        },
        PIIType.IP_ADDRESS: {
            'pattern': r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',
            'column_patterns': ['ip', 'ip_address', 'client_ip'],
            'severity': 'MEDIUM',
            'masking_rule': '***.***.***.***'
        },
        PIIType.GPS_COORDINATES: {
            'pattern': r'-?\d+\.\d+,\s*-?\d+\.\d+',
            'column_patterns': ['gps', 'location', 'coordinates', 'lat', 'long'],
            'severity': 'MEDIUM',
            'masking_rule': '***,***'
        },
        PIIType.MEDICAL_RECORD: {
            'pattern': r'MRN\d{7,10}',
            'column_patterns': ['medical', 'patient', 'diagnosis', 'treatment'],
            'severity': 'CRITICAL',
            'masking_rule': '***-***'
        },
        PIIType.FINANCIAL: {
            'pattern': r'\$\d+\.\d{2}',
            'column_patterns': ['salary', 'income', 'financial', 'compensation'],
            'severity': 'HIGH',
            'masking_rule': '***'
        }
    }

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize PII detector.

        Args:
            config_path: Path to PII configuration file
        """
        self.config = self._load_config(config_path)
        self.patterns = self._build_patterns()
        self.detected_pii: Dict[str, PIIInfo] = {}

    def _load_config(self, config_path: Optional[Path]) -> Dict[str, Any]:
        """Load PII configuration from file."""
        if config_path and config_path.exists():
            try:
                with open(config_path) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load PII config: {e}")

        # Default config
        return {
            "enabled": True,
            "scan_data": True,
            "confidence_threshold": 0.6,
            "custom_patterns": {}
        }

    def _build_patterns(self) -> Dict[PIIType, Dict]:
        """Build detection patterns from config."""
        patterns = {}

        # Base patterns
        for pii_type, config in self.PII_PATTERNS.items():
            patterns[pii_type] = {
                'pattern': re.compile(config['pattern']),
                'column_patterns': config['column_patterns'],
                'severity': config['severity'],
                'masking_rule': config['masking_rule']
            }

        # Add custom patterns from config
        custom = self.config.get('custom_patterns', {})
        for name, config in custom.items():
            try:
                pii_type = PIIType(name.lower())
                patterns[pii_type] = {
                    'pattern': re.compile(config['pattern']),
                    'column_patterns': config.get('column_patterns', []),
                    'severity': config.get('severity', 'MEDIUM'),
                    'masking_rule': config.get('masking_rule', '***')
                }
            except Exception as e:
                logger.warning(f"Invalid custom PII pattern {name}: {e}")

        return patterns

    def detect_in_schema(
        self,
        tables: List[Dict[str, Any]],
        sample_data: Optional[Dict[str, List[Dict[str, Any]]]] = None
    ) -> PIIAnalysis:
        """
        Detect PII in database schema.

        Args:
            tables: List of table definitions
            sample_data: Sample data for each table

        Returns:
            PIIAnalysis object
        """
        logger.info("Detecting PII in schema...")

        detected = []

        for table in tables:
            table_name = table.get('name', '')
            columns = table.get('columns', [])

            for column in columns:
                column_name = column.get('name', '')
                column_type = column.get('type', '')

                # Check if column is PII
                pii_info = self._detect_pii_column(
                    table_name,
                    column_name,
                    column_type,
                    sample_data.get(table_name, []) if sample_data else []
                )

                if pii_info:
                    detected.append(pii_info)

        # Build analysis
        analysis = self._build_analysis(detected)

        logger.info(f"Detected {analysis.total_pii_columns} PII columns")

        return analysis

    def _detect_pii_column(
        self,
        table: str,
        column: str,
        column_type: str,
        sample_values: List[Any]
    ) -> Optional[PIIInfo]:
        """
        Detect PII in a single column.

        Args:
            table: Table name
            column: Column name
            column_type: Column data type
            sample_values: Sample values from column

        Returns:
            PIIInfo or None
        """
        column_lower = column.lower()

        # First check if this is likely a PII column
        for pii_type, config in self.patterns.items():
            # Check column name patterns
            for pattern in config['column_patterns']:
                if pattern in column_lower:
                    # Check sample data
                    confidence = 0.7  # Base confidence from column name

                    if sample_values and self.config.get('scan_data', True):
                        # Check values against pattern
                        pattern_regex = config['pattern']
                        matches = 0
                        total = 0

                        for value in sample_values[:10]:  # Check first 10
                            if value:
                                total += 1
                                if pattern_regex.search(str(value)):
                                    matches += 1

                        if total > 0:
                            confidence = 0.5 + (0.5 * (matches / total))

                    # Only return if confidence is above threshold
                    if confidence >= self.config.get('confidence_threshold', 0.6):
                        return PIIInfo(
                            type=pii_type,
                            column=column,
                            table=table,
                            confidence=confidence,
                            pattern_matched=str(config['pattern']),
                            sample_values=[str(v)
                                           for v in sample_values[:5] if v],
                            severity=config['severity'],
                            masking_rule=config['masking_rule'],
                            detection_reason=f"Column name contains '{pattern}', data matches pattern",
                            metadata={
                                'column_type': column_type,
                                'sample_count': len(sample_values)
                            }
                        )

        return None

    def detect_in_data(self, data: List[Dict[str, Any]]) -> Dict[str, List[PIIInfo]]:
        """
        Detect PII in data values.

        Args:
            data: List of rows as dictionaries

        Returns:
            Dictionary mapping column names to PII info
        """
        results = {}

        if not data:
            return results

        # Get all columns
        columns = list(data[0].keys()) if data else []

        for column in columns:
            values = [row.get(column) for row in data if row.get(column)]
            if not values:
                continue

            # Check if this column contains PII
            for pii_type, config in self.patterns.items():
                pattern = config['pattern']
                matches = 0

                for value in values[:20]:  # Check first 20
                    if pattern.search(str(value)):
                        matches += 1

                confidence = matches / len(values) if values else 0

                if confidence >= 0.5:
                    if column not in results:
                        results[column] = []

                    results[column].append(PIIInfo(
                        type=pii_type,
                        column=column,
                        table="unknown",
                        confidence=confidence,
                        pattern_matched=str(pattern),
                        sample_values=[str(v) for v in values[:3]],
                        severity=config['severity'],
                        masking_rule=config['masking_rule'],
                        detection_reason=f"Data matches PII pattern with {confidence:.0%} confidence"
                    ))
                    break

        return results

    def _build_analysis(self, detected: List[PIIInfo]) -> PIIAnalysis:
        """Build analysis from detected items."""
        pii_by_type = {}
        pii_by_table = {}
        high = medium = low = 0

        for item in detected:
            pii_by_type[item.type] = pii_by_type.get(item.type, 0) + 1
            pii_by_table[item.table] = pii_by_table.get(item.table, 0) + 1

            if item.severity == 'CRITICAL':
                high += 1
            elif item.severity == 'HIGH':
                high += 1
            elif item.severity == 'MEDIUM':
                medium += 1
            elif item.severity == 'LOW':
                low += 1

        total_pii = len(detected)

        # Generate summary
        summary_parts = [
            f"Found {total_pii} PII columns across {len(pii_by_table)} tables",
            f"Types: {', '.join([f'{k.value}: {v}' for k, v in pii_by_type.items()])}",
            f"Severities: HIGH: {high}, MEDIUM: {medium}, LOW: {low}"
        ]

        return PIIAnalysis(
            detected_items=detected,
            total_pii_columns=total_pii,
            pii_by_type=pii_by_type,
            pii_by_table=pii_by_table,
            high_severity_count=high,
            medium_severity_count=medium,
            low_severity_count=low,
            coverage_percentage=total_pii /
            max(1, sum(1 for _ in detected)) * 100,
            summary=" | ".join(summary_parts)
        )

    def mask_value(self, value: Any, pii_type: PIIType) -> str:
        """Mask a value based on PII type."""
        if value is None:
            return "NULL"

        value_str = str(value)
        config = self.patterns.get(pii_type, {})
        masking_rule = config.get('masking_rule', '***')

        # Apply masking rule
        if masking_rule == '***@***' and pii_type == PIIType.EMAIL:
            parts = value_str.split('@')
            if len(parts) == 2:
                return f"{parts[0][0]}***@{parts[1]}"
            return '***@***'

        elif masking_rule == '***-***-****' and pii_type in [PIIType.PHONE, PIIType.SSN]:
            # Keep last 4 digits
            if len(value_str) >= 4:
                return f"***-***-{value_str[-4:]}"
            return '***-***-****'

        elif masking_rule == '****-****-****-****' and pii_type == PIIType.CREDIT_CARD:
            # Keep last 4 digits
            if len(value_str) >= 4:
                return f"****-****-****-{value_str[-4:]}"
            return '****-****-****-****'

        else:
            # Generic masking
            if len(value_str) > 4:
                return f"{masking_rule}{value_str[-4:]}"
            return masking_rule

    def get_masking_rules(self) -> Dict[PIIType, str]:
        """Get all masking rules."""
        return {pii_type: config['masking_rule'] for pii_type, config in self.patterns.items()}

    def get_pii_columns_by_table(self, analysis: PIIAnalysis) -> Dict[str, List[str]]:
        """Get PII columns grouped by table."""
        result = {}
        for item in analysis.detected_items:
            if item.table not in result:
                result[item.table] = []
            result[item.table].append(item.column)
        return result

    def get_summary_report(self, analysis: PIIAnalysis) -> str:
        """Get a human-readable summary report."""
        lines = []
        lines.append("=" * 60)
        lines.append("PII DETECTION SUMMARY")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Total PII Columns: {analysis.total_pii_columns}")
        lines.append(f"Tables with PII: {len(analysis.pii_by_table)}")
        lines.append("")
        lines.append("By Type:")
        for pii_type, count in analysis.pii_by_type.items():
            lines.append(f"  - {pii_type.value}: {count}")
        lines.append("")
        lines.append("By Severity:")
        lines.append(f"  - HIGH/CRITICAL: {analysis.high_severity_count}")
        lines.append(f"  - MEDIUM: {analysis.medium_severity_count}")
        lines.append(f"  - LOW: {analysis.low_severity_count}")
        lines.append("")
        lines.append("Detailed Items:")
        for item in analysis.detected_items:
            lines.append(
                f"  - {item.table}.{item.column} -> {item.type.value} (confidence: {item.confidence:.0%})")
        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)
