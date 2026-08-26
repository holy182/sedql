"""Complete semantic layer generator with business mapping and rules."""

from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
import json
import re
from pathlib import Path

from ..connectors import BaseConnector
from ..utils.logger import logger


@dataclass
class BusinessField:
    """Business representation of a database field."""
    name: str
    business_name: str
    description: str
    data_type: str
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_nullable: bool = True
    is_pii: bool = False
    pii_type: Optional[str] = None
    is_metric: bool = False
    is_date: bool = False
    is_status: bool = False
    allowed_values: List[str] = field(default_factory=list)
    default_value: Optional[str] = None
    sample_values: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    business_rules: List[str] = field(default_factory=list)


@dataclass
class BusinessEntity:
    """Business representation of a database table."""
    name: str
    business_name: str
    description: str
    domain: str = "general"
    fields: List[BusinessField] = field(default_factory=list)
    relationships: List[Dict[str, str]] = field(default_factory=list)
    primary_key: Optional[str] = None
    row_count: int = 0
    sample_data: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BusinessRelationship:
    """Business representation of a database relationship."""
    from_entity: str
    from_business: str
    from_field: str
    to_entity: str
    to_business: str
    to_field: str
    relationship_type: str
    business_description: str
    business_context: str
    cardinality: str
    is_mandatory: bool = False


@dataclass
class BusinessMetric:
    """Business metric definition."""
    name: str
    business_name: str
    description: str
    formula: str
    entity: str
    field: str
    aggregation_type: str
    filters: List[str] = field(default_factory=list)
    unit: Optional[str] = None
    category: str = "financial"


@dataclass
class BusinessRule:
    """Business rule definition."""
    id: str
    name: str
    business_name: str
    description: str
    category: str
    severity: str
    entity: str
    field: Optional[str] = None
    condition: str = ""
    action: str = ""
    is_enabled: bool = True
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class SemanticLayerGenerator:
    """Generates comprehensive semantic layer from database schema."""

    def __init__(self, connector: BaseConnector):
        self.connector = connector
        self.connector.connect()

        # Load configuration
        self._load_config()

        # Results
        self.entities: List[BusinessEntity] = []
        self.relationships: List[BusinessRelationship] = []
        self.metrics: List[BusinessMetric] = []
        self.rules: List[BusinessRule] = []

    def _load_config(self) -> None:
        """Load configuration from business_logic_config.json."""
        config_dir = Path(__file__).parent.parent.parent / "config"
        config_path = config_dir / "business_logic_config.json"

        if config_path.exists():
            try:
                with open(config_path) as f:
                    self.full_config = json.load(f)

                # Extract sections
                naming = self.full_config.get("naming_rules", {})
                self.name_mappings = naming.get("table_mappings", {})
                self.field_mappings = naming.get("field_mappings", {})

                pii = self.full_config.get("pii_detection", {})
                self.pii_patterns = pii.get("patterns", {})

                # Status values
                statuses = self.full_config.get("status_values", {})
                self.status_patterns = statuses.get("common_statuses", {})

                # Metrics
                metrics = self.full_config.get("metrics", {})
                self.metric_definitions = metrics.get("definitions", {})

                logger.info(f"Loaded config from {config_path}")

            except Exception as e:
                logger.warning(f"Failed to load config: {e}")
                self._load_default_config()
        else:
            logger.warning(
                f"Config not found at {config_path}, using defaults")
            self._load_default_config()

    def _load_default_config(self) -> None:
        """Load default configuration."""
        self.name_mappings = {
            'user': 'Customer', 'users': 'Customer', 'customer': 'Customer',
            'order': 'Order', 'orders': 'Order', 'product': 'Product',
            'payment': 'Payment', 'address': 'Address', 'invoice': 'Invoice'
        }
        self.field_mappings = {
            'id': 'ID', 'name': 'Name', 'email': 'Email Address',
            'phone': 'Phone Number', 'address': 'Physical Address',
            'created_at': 'Created Date', 'updated_at': 'Updated Date'
        }
        self.pii_patterns = {
            'email': {'pattern': 'email', 'masking': '***@***', 'severity': 'HIGH'},
            'phone': {'pattern': 'phone', 'masking': '***-***-****', 'severity': 'HIGH'}
        }
        self.status_patterns = {}
        self.metric_definitions = {}

    def generate(self) -> Dict[str, Any]:
        """Generate complete semantic layer."""
        logger.info("Generating semantic layer...")

        # Get schema
        schema = self.connector.get_schema_info()

        # Detect domain
        detected_domain = self._detect_domain(schema)
        logger.info(f"Detected domain: {detected_domain}")

        # Process each table
        for table in schema.tables:
            entity = self._create_entity(table, detected_domain)
            self.entities.append(entity)

            # Generate rules for this entity
            self._generate_rules(entity)

            # Generate metrics
            self._generate_metrics(entity)

        # Find relationships
        self._find_relationships(schema)

        # Build result
        result = {
            "version": self.full_config.get("version", "2.0"),
            "generated_at": datetime.now().isoformat(),
            "domain": detected_domain,
            "database": {
                "type": schema.database_type,
                "version": schema.version,
                "tables": len(schema.tables)
            },
            "entities": self._serialize_entities(),
            "relationships": self._serialize_relationships(),
            "metrics": self._serialize_metrics(),
            "rules": self._serialize_rules(),
            "summary": self._generate_summary()
        }

        return result

    def _detect_domain(self, schema: Any) -> str:
        """Detect business domain from schema."""
        table_names = [t.name.lower() for t in schema.tables]
        column_names = []
        for t in schema.tables:
            column_names.extend([c.name.lower() for c in t.columns])

        domain_config = self.full_config.get("domain_detection", {})
        domains = domain_config.get("domains", {})

        scores = {}
        for domain, config in domains.items():
            score = 0
            patterns = config.get("patterns", {})
            weight = config.get("weight", 1)

            # Check table patterns
            for pattern in patterns.get("tables", []):
                if any(pattern in name for name in table_names):
                    score += weight

            # Check column patterns
            for pattern in patterns.get("columns", []):
                if any(pattern in name for name in column_names):
                    score += weight / 2

            scores[domain] = score

        if not scores:
            return "general"

        max_score = max(scores.values())
        if max_score == 0:
            return "general"

        return max(scores, key=scores.get)

    def _create_entity(self, table: Any, domain: str) -> BusinessEntity:
        """Create a business entity from a database table."""
        table_name = table.name
        business_name = self._get_business_name(table_name)
        description = self._generate_entity_description(
            table_name, business_name, domain)

        fields = []
        for col in table.columns:
            field = self._create_field(col, table_name)
            fields.append(field)

        # Find primary key
        primary_key = None
        for field in fields:
            if field.is_primary_key:
                primary_key = field.name
                break

        return BusinessEntity(
            name=table_name,
            business_name=business_name,
            description=description,
            domain=domain,
            fields=fields,
            primary_key=primary_key,
            row_count=getattr(table, 'row_count', 0),
            sample_data=getattr(table, 'sample_data', [])
        )

    def _create_field(self, column: Any, table_name: str) -> BusinessField:
        """Create a business field from a database column."""
        col_name = column.name
        business_name = self.field_mappings.get(
            col_name, col_name.replace('_', ' ').title())

        # Check PII
        is_pii = False
        pii_type = None
        for pii_key, pii_config in self.pii_patterns.items():
            pattern = pii_config.get("pattern", "")
            if pattern in col_name.lower():
                is_pii = True
                pii_type = pii_key
                break

        # Check status
        is_status = False
        allowed_values = []
        for status_key, status_list in self.status_patterns.items():
            if status_key.lower() in col_name.lower():
                is_status = True
                allowed_values = status_list
                break

        # Check metric
        is_metric = any(m in col_name.lower()
                        for m in ['total', 'amount', 'price', 'cost'])
        is_date = 'date' in column.type.lower() or 'time' in column.type.lower()

        # Generate description
        description = self._generate_field_description(
            col_name, business_name, is_pii)

        # Get sample values
        sample_values = []
        try:
            query = f"SELECT DISTINCT {col_name} FROM {table_name} LIMIT 5"
            results = self.connector.execute_query(query)
            sample_values = [str(row.get(col_name))
                             for row in results if row.get(col_name)]
        except:
            pass

        return BusinessField(
            name=col_name,
            business_name=business_name,
            description=description,
            data_type=column.type,
            is_primary_key=column.is_primary_key,
            is_foreign_key=column.is_foreign_key,
            is_nullable=column.nullable,
            is_pii=is_pii,
            pii_type=pii_type,
            is_metric=is_metric,
            is_date=is_date,
            is_status=is_status,
            allowed_values=allowed_values if allowed_values else sample_values,
            sample_values=sample_values,
            constraints=self._get_constraints(column)
        )

    def _generate_rules(self, entity: BusinessEntity) -> None:
        """Generate business rules for an entity."""
        # PII protection rules
        for field in entity.fields:
            if field.is_pii:
                pii_config = self.pii_patterns.get(field.pii_type, {})
                severity = pii_config.get("severity", "HIGH")
                masking = pii_config.get("masking", "***")

                self.rules.append(BusinessRule(
                    id=f"pii_{entity.name}_{field.name}",
                    name=f"PII Protection for {field.business_name}",
                    business_name=f"Mask {field.business_name}",
                    description=f"{field.business_name} contains PII and must be masked in queries",
                    category="security",
                    severity=severity,
                    entity=entity.name,
                    field=field.name,
                    condition=f"{field.name} IS NOT NULL",
                    action="MASK_DATA",
                    priority=1,
                    metadata={
                        "masking_pattern": masking,
                        "pii_type": field.pii_type
                    }
                ))

        # Required fields
        for field in entity.fields:
            if not field.is_nullable and not field.is_primary_key:
                self.rules.append(BusinessRule(
                    id=f"required_{entity.name}_{field.name}",
                    name=f"Required Field: {field.business_name}",
                    business_name=f"{field.business_name} is required",
                    description=f"{field.business_name} must have a value",
                    category="validation",
                    severity="MEDIUM",
                    entity=entity.name,
                    field=field.name,
                    condition=f"{field.name} IS NOT NULL",
                    action="REJECT_QUERY",
                    priority=2
                ))

        # Status validation
        for field in entity.fields:
            if field.is_status and field.allowed_values:
                allowed_values_str = ', '.join(
                    [repr(v) for v in field.allowed_values[:5]])
                if len(field.allowed_values) > 5:
                    allowed_values_str += ', ...'

                self.rules.append(BusinessRule(
                    id=f"status_{entity.name}_{field.name}",
                    name=f"Status Values for {field.business_name}",
                    business_name=f"Validate {field.business_name}",
                    description=f"{field.business_name} must be one of: {allowed_values_str}",
                    category="validation",
                    severity="MEDIUM",
                    entity=entity.name,
                    field=field.name,
                    condition=f"{field.name} IN ({', '.join([repr(v) for v in field.allowed_values])})",
                    action="REJECT_QUERY",
                    priority=3,
                    metadata={"allowed_values": field.allowed_values}
                ))

    def _generate_metrics(self, entity: BusinessEntity) -> None:
        """Generate business metrics from entity."""
        # Count metric
        self.metrics.append(BusinessMetric(
            name=f"count_{entity.name}",
            business_name=f"Number of {entity.business_name}s",
            description=f"Total count of {entity.business_name}s",
            formula=f"COUNT({entity.name}.{entity.primary_key or 'id'})",
            entity=entity.name,
            field=entity.primary_key or 'id',
            aggregation_type="count",
            category="operational"
        ))

        # Metric fields
        for field in entity.fields:
            if field.is_metric and 'int' in field.data_type.lower() or 'real' in field.data_type.lower():
                # Sum
                self.metrics.append(BusinessMetric(
                    name=f"sum_{entity.name}_{field.name}",
                    business_name=f"Total {field.business_name}",
                    description=f"Sum of all {field.business_name} values",
                    formula=f"SUM({entity.name}.{field.name})",
                    entity=entity.name,
                    field=field.name,
                    aggregation_type="sum",
                    category="financial"
                ))

                # Average
                self.metrics.append(BusinessMetric(
                    name=f"avg_{entity.name}_{field.name}",
                    business_name=f"Average {field.business_name}",
                    description=f"Average of {field.business_name} values",
                    formula=f"AVG({entity.name}.{field.name})",
                    entity=entity.name,
                    field=field.name,
                    aggregation_type="avg",
                    category="financial"
                ))

    def _get_business_name(self, table_name: str) -> str:
        """Get business name for a table."""
        # Try exact match
        if table_name in self.name_mappings:
            return self.name_mappings[table_name]

        # Try singular form
        singular = table_name[:-1] if table_name.endswith('s') else table_name
        if singular in self.name_mappings:
            return self.name_mappings[singular]

        # Default: title case
        return table_name.replace('_', ' ').title()

    def _generate_entity_description(self, table_name: str, business_name: str, domain: str) -> str:
        """Generate description for an entity."""
        descriptions = {
            'Customer': 'People who buy our products or services',
            'Order': 'Customer purchases and transactions',
            'Product': 'Items offered for sale',
            'Payment': 'Financial transactions from customers',
            'Address': 'Physical location information',
            'Invoice': 'Billing documents for customers'
        }
        return descriptions.get(business_name, f"Table containing {business_name.lower()} data")

    def _generate_field_description(self, field_name: str, business_name: str, is_pii: bool) -> str:
        """Generate description for a field."""
        if is_pii:
            return f"{business_name} (PII - must be protected)"
        elif 'id' in field_name.lower():
            return "Unique identifier for this record"
        elif 'created' in field_name.lower():
            return "When this record was created"
        elif 'updated' in field_name.lower():
            return "When this record was last updated"
        else:
            return f"{business_name} field"

    def _get_constraints(self, column: Any) -> List[str]:
        """Get constraints for a column."""
        constraints = []
        if not column.nullable:
            constraints.append("NOT NULL")
        if column.is_primary_key:
            constraints.append("PRIMARY KEY")
        if column.is_foreign_key:
            constraints.append("FOREIGN KEY")
        return constraints

    def _find_relationships(self, schema: Any) -> None:
        """Find relationships between entities."""
        for entity in self.entities:
            fks = self.connector.get_foreign_keys(entity.name)

            for fk in fks:
                from_cols = fk.get('constrained_columns', [])
                to_cols = fk.get('referred_columns', [])
                to_table = fk.get('referred_table', '')

                if from_cols and to_table:
                    to_entity = None
                    for e in self.entities:
                        if e.name == to_table:
                            to_entity = e
                            break

                    if not to_entity:
                        continue

                    relationship_type = "one_to_many"
                    cardinality = "1:N"

                    self.relationships.append(BusinessRelationship(
                        from_entity=entity.name,
                        from_business=entity.business_name,
                        from_field=from_cols[0],
                        to_entity=to_table,
                        to_business=to_entity.business_name,
                        to_field=to_cols[0] if to_cols else 'id',
                        relationship_type=relationship_type,
                        business_description=f"{entity.business_name} belongs to {to_entity.business_name}",
                        business_context=f"{entity.business_name} is linked to {to_entity.business_name}",
                        cardinality=cardinality
                    ))

    def _serialize_entities(self) -> List[Dict]:
        """Serialize entities to dict."""
        return [{
            "name": e.name,
            "business_name": e.business_name,
            "description": e.description,
            "domain": e.domain,
            "primary_key": e.primary_key,
            "row_count": e.row_count,
            "fields": [{
                "name": f.name,
                "business_name": f.business_name,
                "description": f.description,
                "data_type": f.data_type,
                "is_primary_key": f.is_primary_key,
                "is_foreign_key": f.is_foreign_key,
                "is_nullable": f.is_nullable,
                "is_pii": f.is_pii,
                "pii_type": f.pii_type,
                "is_metric": f.is_metric,
                "is_date": f.is_date,
                "is_status": f.is_status,
                "allowed_values": f.allowed_values,
                "sample_values": f.sample_values,
                "constraints": f.constraints
            } for f in e.fields]
        } for e in self.entities]

    def _serialize_relationships(self) -> List[Dict]:
        """Serialize relationships to dict."""
        return [{
            "from_entity": r.from_entity,
            "from_business": r.from_business,
            "from_field": r.from_field,
            "to_entity": r.to_entity,
            "to_business": r.to_business,
            "to_field": r.to_field,
            "relationship_type": r.relationship_type,
            "cardinality": r.cardinality,
            "business_description": r.business_description,
            "business_context": r.business_context
        } for r in self.relationships]

    def _serialize_metrics(self) -> List[Dict]:
        """Serialize metrics to dict."""
        return [{
            "name": m.name,
            "business_name": m.business_name,
            "description": m.description,
            "formula": m.formula,
            "entity": m.entity,
            "field": m.field,
            "aggregation_type": m.aggregation_type,
            "category": m.category
        } for m in self.metrics]

    def _serialize_rules(self) -> List[Dict]:
        """Serialize rules to dict."""
        return [{
            "id": r.id,
            "name": r.name,
            "business_name": r.business_name,
            "description": r.description,
            "category": r.category,
            "severity": r.severity,
            "entity": r.entity,
            "field": r.field,
            "condition": r.condition,
            "action": r.action,
            "is_enabled": r.is_enabled,
            "priority": r.priority,
            "metadata": r.metadata
        } for r in self.rules]

    def _generate_summary(self) -> Dict[str, int]:
        """Generate summary statistics."""
        return {
            "entities": len(self.entities),
            "fields": sum(len(e.fields) for e in self.entities),
            "relationships": len(self.relationships),
            "metrics": len(self.metrics),
            "rules": len(self.rules),
            "pii_rules": len([r for r in self.rules if r.category == "security"]),
            "validation_rules": len([r for r in self.rules if r.category == "validation"])
        }
