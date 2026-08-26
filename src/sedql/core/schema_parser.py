"""Advanced schema parser for database analysis and introspection."""

from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import re
from datetime import datetime

from ..connectors import BaseConnector
from ..utils.logger import logger


@dataclass
class ParsedColumn:
    """Detailed parsed column information."""
    name: str
    data_type: str
    nullable: bool
    is_primary: bool = False
    is_foreign: bool = False
    is_auto_increment: bool = False
    is_computed: bool = False
    default_value: Optional[str] = None
    max_length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    comment: str = ""
    constraints: List[str] = field(default_factory=list)
    indexes: List[str] = field(default_factory=list)

    # Data pattern analysis
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    null_count: int = 0
    distinct_count: int = 0
    most_common_values: List[Any] = field(default_factory=list)
    pattern: Optional[str] = None  # For strings (email, phone, etc.)

    # Business analysis
    is_identifier: bool = False
    is_timestamp: bool = False
    is_boolean: bool = False
    is_enum: bool = False
    possible_values: List[Any] = field(default_factory=list)
    business_meaning: str = ""


@dataclass
class ParsedTable:
    """Detailed parsed table information."""
    name: str
    schema: str = ""
    comment: str = ""
    row_count: int = 0
    columns: List[ParsedColumn] = field(default_factory=list)
    primary_keys: List[str] = field(default_factory=list)
    foreign_keys: Dict[str, Dict[str, str]] = field(default_factory=dict)
    indexes: List[str] = field(default_factory=list)
    unique_constraints: List[str] = field(default_factory=list)

    # Analysis
    table_type: str = "base"  # base, view, junction, audit, log
    estimated_rows: Optional[int] = None
    columns_count: int = 0
    data_size: Optional[str] = None
    last_updated: Optional[str] = None

    # Patterns
    naming_pattern: str = ""
    business_domain: str = ""
    importance_score: float = 0.5  # 0-1 scale


@dataclass
class ParsedSchema:
    """Complete parsed database schema."""
    database_name: str = ""
    database_type: str = ""
    version: str = ""
    tables: List[ParsedTable] = field(default_factory=list)
    views: List[str] = field(default_factory=list)
    relationships: List[Dict[str, str]] = field(default_factory=list)

    # Analysis
    total_tables: int = 0
    total_columns: int = 0
    domain: str = "general"
    schema_complexity: float = 0.0
    data_quality_score: float = 0.0

    # Summary
    table_types: Dict[str, int] = field(default_factory=dict)
    column_types: Dict[str, int] = field(default_factory=dict)
    pii_columns: List[str] = field(default_factory=list)
    timestamp_columns: List[str] = field(default_factory=list)


class SchemaParser:
    """Advanced parser for analyzing database schemas."""

    # Regex patterns for data type detection
    PATTERNS = {
        'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
        'phone': r'^[+]?[0-9]{10,15}$',
        'uuid': r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        'date_iso': r'^\d{4}-\d{2}-\d{2}$',
        'datetime_iso': r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}',
        'url': r'^https?://[^\s]+$',
        'postal_code': r'^\d{5}(-\d{4})?$',
        'price': r'^\d+(\.\d{2})?$',
    }

    # PII column name patterns
    PII_PATTERNS = {
        'email': ['email', 'e-mail', 'mail'],
        'phone': ['phone', 'mobile', 'cell', 'telephone'],
        'ssn': ['ssn', 'social', 'social_security'],
        'address': ['address', 'street', 'location'],
        'password': ['password', 'passwd', 'pwd'],
        'credit_card': ['credit', 'card', 'cc_number', 'card_number'],
        'dob': ['dob', 'birth', 'date_of_birth', 'birth_date'],
        'name': ['name', 'full_name', 'first_name', 'last_name'],
    }

    def __init__(self, connector: BaseConnector, analyze_data: bool = True):
        """
        Initialize schema parser.

        Args:
            connector: Database connector
            analyze_data: Whether to analyze sample data for patterns
        """
        self.connector = connector
        self.analyze_data = analyze_data
        self.connector.connect()

    def parse_schema(self) -> ParsedSchema:
        """Parse the entire database schema."""
        logger.info("Parsing database schema...")

        schema_info = self.connector.get_schema_info()

        parsed_schema = ParsedSchema(
            database_name=str(
                self.connector.engine.url.database) if self.connector.engine else "",
            database_type=schema_info.database_type,
            version=schema_info.version or "unknown"
        )

        # Parse each table
        for table in schema_info.tables:
            parsed_table = self._parse_table(table)
            parsed_schema.tables.append(parsed_table)

        # Analyze the schema
        self._analyze_schema(parsed_schema)

        # Find relationships
        parsed_schema.relationships = self._find_all_relationships()

        # Calculate metrics
        parsed_schema.total_tables = len(parsed_schema.tables)
        parsed_schema.total_columns = sum(
            len(t.columns) for t in parsed_schema.tables)
        parsed_schema.table_types = self._count_table_types(parsed_schema)
        parsed_schema.column_types = self._count_column_types(parsed_schema)
        parsed_schema.pii_columns = self._find_pii_columns(parsed_schema)
        parsed_schema.timestamp_columns = self._find_timestamp_columns(
            parsed_schema)
        parsed_schema.schema_complexity = self._calculate_complexity(
            parsed_schema)
        parsed_schema.data_quality_score = self._calculate_data_quality(
            parsed_schema)

        logger.info(
            f"Parsed {parsed_schema.total_tables} tables with {parsed_schema.total_columns} columns")

        return parsed_schema

    def _parse_table(self, table_info: Any) -> ParsedTable:
        """Parse a single table."""
        table = ParsedTable(
            name=table_info.name,
            row_count=table_info.row_count or 0,
            columns_count=len(table_info.columns)
        )

        # Parse columns
        for col in table_info.columns:
            parsed_col = self._parse_column(col, table_info.name)
            table.columns.append(parsed_col)

            # Track primary keys
            if parsed_col.is_primary:
                table.primary_keys.append(parsed_col.name)

            # Track foreign keys
            if parsed_col.is_foreign and parsed_col.name in table_info.foreign_keys:
                # Find the FK info
                for fk in table_info.foreign_keys:
                    if parsed_col.name in fk.get('columns', []):
                        table.foreign_keys[parsed_col.name] = {
                            'referenced_table': fk.get('referred_table', ''),
                            'referenced_column': fk.get('referred_columns', [''])[0] if fk.get('referred_columns') else ''
                        }
                        break

        # Analyze table structure
        self._analyze_table_structure(table)

        # Determine table type
        table.table_type = self._determine_table_type(table)

        # Calculate importance score
        table.importance_score = self._calculate_table_importance(table)

        return table

    def _parse_column(self, column_info: Any, table_name: str) -> ParsedColumn:
        """Parse a single column with detailed analysis."""
        col_name = column_info.name
        col_type = str(column_info.type)

        parsed = ParsedColumn(
            name=col_name,
            data_type=col_type,
            nullable=column_info.nullable,
            is_primary=column_info.is_primary_key,
            is_foreign=column_info.is_foreign_key,
            comment=column_info.comment if hasattr(
                column_info, 'comment') else "",
            constraints=self._extract_constraints(column_info)
        )

        # Parse data type details
        self._parse_data_type_details(parsed)

        # Detect data patterns
        if self.analyze_data:
            self._analyze_column_data(parsed, table_name)

        # Detect business meaning
        parsed.business_meaning = self._detect_business_meaning(parsed)
        parsed.is_identifier = self._is_identifier(parsed)
        parsed.is_timestamp = self._is_timestamp(parsed)
        parsed.is_boolean = self._is_boolean(parsed)
        parsed.is_enum = self._is_enum(parsed)

        # Detect if this is PII
        if self._is_pii(parsed):
            parsed.is_pii = True

        return parsed

    def _parse_data_type_details(self, column: ParsedColumn) -> None:
        """Parse data type details like length, precision, etc."""
        dtype = column.data_type.lower()

        # Extract length/precision
        if 'varchar' in dtype or 'char' in dtype:
            match = re.search(r'\((\d+)\)', dtype)
            if match:
                column.max_length = int(match.group(1))

        if 'decimal' in dtype or 'numeric' in dtype:
            match = re.search(r'\((\d+),\s*(\d+)\)', dtype)
            if match:
                column.precision = int(match.group(1))
                column.scale = int(match.group(2))

        # Check for auto-increment
        if 'auto_increment' in dtype or 'serial' in dtype:
            column.is_auto_increment = True

        # Check for computed
        if 'generated' in dtype or 'computed' in dtype:
            column.is_computed = True

        # Simple type categorization
        if any(t in dtype for t in ['int', 'integer']):
            column.is_identifier = True

    def _analyze_column_data(self, column: ParsedColumn, table_name: str) -> None:
        """Analyze sample data from a column to detect patterns."""
        try:
            # Get sample data
            query = f"""
                SELECT 
                    {column.name},
                    COUNT(*) as total_count,
                    COUNT(DISTINCT {column.name}) as distinct_count,
                    SUM(CASE WHEN {column.name} IS NULL THEN 1 ELSE 0 END) as null_count
                FROM {table_name}
                WHERE {column.name} IS NOT NULL
                GROUP BY {column.name}
                ORDER BY total_count DESC
                LIMIT 10
            """
            results = self.connector.execute_query(query)

            if results:
                # Get most common values
                column.most_common_values = [
                    r.get(column.name) for r in results[:5]]
                column.distinct_count = len(results)

                # Get null count from first row
                if results:
                    column.null_count = results[0].get('null_count', 0)

                # Try to detect pattern for string columns
                if 'varchar' in column.data_type.lower() or 'text' in column.data_type.lower():
                    sample_values = [str(r.get(column.name))
                                     for r in results[:5] if r.get(column.name)]
                    if sample_values:
                        column.pattern = self._detect_pattern(sample_values)

                # For numeric columns
                if any(t in column.data_type.lower() for t in ['int', 'decimal', 'float', 'real']):
                    try:
                        # Get min/max
                        query = f"""
                            SELECT 
                                MIN({column.name}) as min_val,
                                MAX({column.name}) as max_val
                            FROM {table_name}
                            WHERE {column.name} IS NOT NULL
                        """
                        result = self.connector.execute_query(query)
                        if result:
                            column.min_value = result[0].get('min_val')
                            column.max_value = result[0].get('max_val')
                    except:
                        pass

        except Exception as e:
            logger.debug(
                f"Could not analyze data for {table_name}.{column.name}: {e}")

    def _detect_pattern(self, values: List[str]) -> Optional[str]:
        """Detect pattern in string values."""
        if not values:
            return None

        # Check each pattern
        for pattern_name, pattern_regex in self.PATTERNS.items():
            if all(re.match(pattern_regex, str(v)) for v in values if v):
                return pattern_name

        return None

    def _extract_constraints(self, column: Any) -> List[str]:
        """Extract constraints from column."""
        constraints = []
        if not column.nullable:
            constraints.append("NOT NULL")
        if column.is_primary_key:
            constraints.append("PRIMARY KEY")
        if column.is_foreign_key:
            constraints.append("FOREIGN KEY")
        if column.default_value:
            constraints.append(f"DEFAULT {column.default_value}")
        return constraints

    def _detect_business_meaning(self, column: ParsedColumn) -> str:
        """Detect business meaning from column name."""
        name_lower = column.name.lower()

        # Common business meanings
        meanings = {
            'id': 'Unique identifier',
            'name': 'Name',
            'first_name': 'First name',
            'last_name': 'Last name',
            'email': 'Email address',
            'phone': 'Phone number',
            'address': 'Physical address',
            'city': 'City name',
            'state': 'State or province',
            'country': 'Country name',
            'zip': 'Postal code',
            'created_at': 'Creation timestamp',
            'updated_at': 'Last update timestamp',
            'deleted_at': 'Deletion timestamp',
            'status': 'Current status',
            'active': 'Active flag',
            'total': 'Total amount',
            'subtotal': 'Subtotal amount',
            'tax': 'Tax amount',
            'discount': 'Discount amount',
            'quantity': 'Quantity',
            'price': 'Unit price',
            'description': 'Description text',
            'notes': 'Notes or comments',
            'type': 'Type classification',
            'category': 'Category',
            'priority': 'Priority level',
            'score': 'Score or rating',
            'count': 'Count',
            'percentage': 'Percentage',
            'rate': 'Rate',
            'fee': 'Fee amount',
        }

        for key, meaning in meanings.items():
            if key in name_lower:
                return meaning

        return "General field"

    def _is_identifier(self, column: ParsedColumn) -> bool:
        """Check if column is an identifier."""
        name_lower = column.name.lower()
        return 'id' in name_lower or name_lower.endswith('_id')

    def _is_timestamp(self, column: ParsedColumn) -> bool:
        """Check if column is a timestamp."""
        name_lower = column.name.lower()
        type_lower = column.data_type.lower()

        return (any(t in name_lower for t in ['created', 'updated', 'deleted', 'at']) and
                ('timestamp' in type_lower or 'datetime' in type_lower))

    def _is_boolean(self, column: ParsedColumn) -> bool:
        """Check if column is a boolean."""
        name_lower = column.name.lower()
        return (any(t in name_lower for t in ['is_', 'has_', 'active', 'enabled']) and
                ('bool' in column.data_type.lower() or 'tinyint' in column.data_type.lower()))

    def _is_enum(self, column: ParsedColumn) -> bool:
        """Check if column is an enum (few distinct values)."""
        if not self.analyze_data:
            return False

        name_lower = column.name.lower()
        status_keywords = ['status', 'state', 'type', 'category', 'priority']

        # Check if it's a status-like column
        if any(k in name_lower for k in status_keywords):
            return True

        # Check distinct count
        if column.distinct_count and 2 <= column.distinct_count <= 20:
            return True

        return False

    def _is_pii(self, column: ParsedColumn) -> bool:
        """Check if column contains PII data."""
        name_lower = column.name.lower()

        for pii_type, patterns in self.PII_PATTERNS.items():
            for pattern in patterns:
                if pattern in name_lower:
                    return True

        return False

    def _analyze_table_structure(self, table: ParsedTable) -> None:
        """Analyze table structure for patterns."""
        # Check naming pattern
        if table.name.startswith('tbl_'):
            table.naming_pattern = 'prefix'
        elif table.name.endswith('_tbl'):
            table.naming_pattern = 'suffix'
        elif '_' in table.name:
            table.naming_pattern = 'underscore'
        else:
            table.naming_pattern = 'camel'

        # Check if it's a junction table (2+ FKs, no primary key)
        if len(table.foreign_keys) >= 2 and not table.primary_keys:
            table.table_type = 'junction'

        # Check if it's a log/audit table
        if 'log' in table.name.lower() or 'audit' in table.name.lower():
            table.table_type = 'log'

    def _determine_table_type(self, table: ParsedTable) -> str:
        """Determine the type of table."""
        name_lower = table.name.lower()

        if 'log' in name_lower or 'audit' in name_lower:
            return 'log'
        elif len(table.foreign_keys) >= 2 and not table.primary_keys:
            return 'junction'
        elif 'view' in name_lower:
            return 'view'
        elif len(table.columns) <= 3:
            return 'reference'
        else:
            return 'base'

    def _calculate_table_importance(self, table: ParsedTable) -> float:
        """Calculate the importance score of a table."""
        score = 0.5

        # More columns = more important
        if len(table.columns) > 10:
            score += 0.2
        elif len(table.columns) > 5:
            score += 0.1

        # Primary key = important
        if table.primary_keys:
            score += 0.1

        # Foreign keys = important
        if table.foreign_keys:
            score += 0.1

        # Many rows = important
        if table.row_count and table.row_count > 10000:
            score += 0.1

        return min(score, 1.0)

    def _count_table_types(self, schema: ParsedSchema) -> Dict[str, int]:
        """Count tables by type."""
        types = {}
        for table in schema.tables:
            types[table.table_type] = types.get(table.table_type, 0) + 1
        return types

    def _count_column_types(self, schema: ParsedSchema) -> Dict[str, int]:
        """Count columns by data type."""
        types = {}
        for table in schema.tables:
            for column in table.columns:
                dtype = column.data_type.lower()
                # Simplify type
                if 'int' in dtype:
                    dtype = 'integer'
                elif 'varchar' in dtype or 'text' in dtype or 'char' in dtype:
                    dtype = 'string'
                elif 'date' in dtype or 'time' in dtype:
                    dtype = 'datetime'
                elif 'bool' in dtype:
                    dtype = 'boolean'
                elif 'decimal' in dtype or 'numeric' in dtype or 'float' in dtype or 'real' in dtype:
                    dtype = 'decimal'

                types[dtype] = types.get(dtype, 0) + 1
        return types

    def _find_pii_columns(self, schema: ParsedSchema) -> List[str]:
        """Find all PII columns."""
        pii = []
        for table in schema.tables:
            for column in table.columns:
                if column.is_pii:
                    pii.append(f"{table.name}.{column.name}")
        return pii

    def _find_timestamp_columns(self, schema: ParsedSchema) -> List[str]:
        """Find all timestamp columns."""
        timestamps = []
        for table in schema.tables:
            for column in table.columns:
                if column.is_timestamp:
                    timestamps.append(f"{table.name}.{column.name}")
        return timestamps

    def _analyze_schema(self, schema: ParsedSchema) -> None:
        """Analyze the entire schema."""
        # Detect domain
        domain_scores = {
            'ecommerce': 0,
            'saas': 0,
            'fintech': 0,
            'healthcare': 0,
            'logistics': 0
        }

        for table in schema.tables:
            name_lower = table.name.lower()

            # Domain detection
            if any(t in name_lower for t in ['order', 'product', 'customer']):
                domain_scores['ecommerce'] += 1
            if any(t in name_lower for t in ['subscription', 'plan', 'user']):
                domain_scores['saas'] += 1
            if any(t in name_lower for t in ['transaction', 'account', 'wallet']):
                domain_scores['fintech'] += 1
            if any(t in name_lower for t in ['patient', 'doctor', 'appointment']):
                domain_scores['healthcare'] += 1
            if any(t in name_lower for t in ['shipment', 'delivery', 'warehouse']):
                domain_scores['logistics'] += 1

        if domain_scores:
            schema.domain = max(domain_scores, key=domain_scores.get)
            if max(domain_scores.values()) == 0:
                schema.domain = "general"

    def _find_all_relationships(self) -> List[Dict[str, str]]:
        """Find all relationships in the database."""
        relationships = []
        table_names = self.connector.get_table_names()

        for table in table_names:
            fks = self.connector.get_foreign_keys(table)
            for fk in fks:
                relationships.append({
                    'from_table': table,
                    'from_column': fk.get('constrained_columns', [''])[0],
                    'to_table': fk.get('referred_table', ''),
                    'to_column': fk.get('referred_columns', [''])[0] if fk.get('referred_columns') else '',
                    'constraint_name': fk.get('name', '')
                })

        return relationships

    def _calculate_complexity(self, schema: ParsedSchema) -> float:
        """Calculate schema complexity score (0-1)."""
        score = 0.0

        # Number of tables
        if schema.total_tables > 20:
            score += 0.3
        elif schema.total_tables > 10:
            score += 0.2
        elif schema.total_tables > 5:
            score += 0.1

        # Number of relationships
        if len(schema.relationships) > 20:
            score += 0.3
        elif len(schema.relationships) > 10:
            score += 0.2
        elif len(schema.relationships) > 5:
            score += 0.1

        # Variety of column types
        if len(schema.column_types) > 5:
            score += 0.2
        elif len(schema.column_types) > 3:
            score += 0.1

        return min(score, 1.0)

    def _calculate_data_quality(self, schema: ParsedSchema) -> float:
        """Calculate data quality score (0-1)."""
        total_score = 0.0
        checks_performed = 0

        for table in schema.tables:
            # Check for primary key (important)
            if table.primary_keys:
                total_score += 1.0
            checks_performed += 1

            # Check for foreign keys (data integrity)
            if table.foreign_keys:
                total_score += 0.5
            checks_performed += 0.5

            # Check for row count (has data)
            if table.row_count and table.row_count > 0:
                total_score += 0.5
            checks_performed += 0.5

        if checks_performed == 0:
            return 0.0

        return min(total_score / checks_performed, 1.0)

    def get_summary(self, schema: ParsedSchema) -> Dict[str, Any]:
        """Get a summary of the parsed schema."""
        return {
            "database": schema.database_name,
            "type": schema.database_type,
            "version": schema.version,
            "domain": schema.domain,
            "tables": {
                "total": schema.total_tables,
                "by_type": schema.table_types
            },
            "columns": {
                "total": schema.total_columns,
                "by_type": schema.column_types
            },
            "relationships": len(schema.relationships),
            "pii_columns": len(schema.pii_columns),
            "timestamp_columns": len(schema.timestamp_columns),
            "complexity_score": schema.schema_complexity,
            "data_quality_score": schema.data_quality_score,
            "views": len(schema.views)
        }
