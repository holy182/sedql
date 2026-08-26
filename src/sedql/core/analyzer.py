"""Database analyzer with production-ready features."""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json
import time
from pathlib import Path

from ..connectors import BaseConnector
from ..connectors import ConnectionConfig
from ..utils.logger import logger
from .schema_parser import SchemaParser, ParsedSchema
from .semantic_layer_generator import SemanticLayerGenerator


@dataclass
class AnalysisResult:
    """Result of a database analysis."""
    success: bool
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    database_type: str
    database_version: Optional[str]
    schema: Optional[ParsedSchema] = None
    semantic_layer: Optional[Dict[str, Any]] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "database_type": self.database_type,
            "database_version": self.database_version,
            "summary": self.summary,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)


class Analyzer:
    """
    Database analyzer with comprehensive analysis capabilities.

    Features:
    - Schema discovery and parsing
    - Business domain detection
    - Semantic layer generation
    - Data quality assessment
    - Performance monitoring
    - Incremental analysis
    """

    def __init__(
        self,
        connector: BaseConnector,
        config_path: Optional[Path] = None,
        analyze_data: bool = True,
        deep_analysis: bool = True
    ):
        """
        Initialize analyzer.

        Args:
            connector: Database connector
            config_path: Path to configuration file
            analyze_data: Whether to analyze sample data
            deep_analysis: Whether to perform deep analysis
        """
        self.connector = connector
        self.config_path = config_path
        self.analyze_data = analyze_data
        self.deep_analysis = deep_analysis

        # Ensure connection
        self.connector.connect()

        # Results cache
        self._cached_schema: Optional[ParsedSchema] = None
        self._cached_semantic: Optional[Dict[str, Any]] = None
        self._analysis_timestamp: Optional[datetime] = None

    def analyze(self, force_refresh: bool = False) -> AnalysisResult:
        """
        Perform complete database analysis.

        Args:
            force_refresh: Force refresh of cached results

        Returns:
            AnalysisResult object
        """
        logger.info("Starting database analysis...")
        start_time = datetime.now()

        result = AnalysisResult(
            success=False,
            start_time=start_time,
            end_time=start_time,
            duration_seconds=0.0,
            database_type=self.connector.get_database_type(),
            database_version=self.connector.get_version()
        )

        try:
            # Step 1: Parse schema
            logger.info("Step 1: Parsing schema...")
            schema = self._parse_schema()
            result.schema = schema
            result.summary['schema'] = self._get_schema_summary(schema)

            # Step 2: Generate semantic layer
            logger.info("Step 2: Generating semantic layer...")
            semantic = self._generate_semantic_layer(schema)
            result.semantic_layer = semantic
            result.summary['semantic'] = semantic.get('summary', {})

            # Step 3: Analyze data quality
            if self.analyze_data:
                logger.info("Step 3: Analyzing data quality...")
                quality = self._analyze_data_quality(schema)
                result.summary['data_quality'] = quality

            # Step 4: Detect domain
            logger.info("Step 4: Detecting business domain...")
            domain = self._detect_domain(schema)
            result.summary['domain'] = domain
            result.metadata['domain'] = domain

            # Step 5: Identify patterns
            if self.deep_analysis:
                logger.info("Step 5: Identifying patterns...")
                patterns = self._identify_patterns(schema)
                result.metadata['patterns'] = patterns

            # Step 6: Generate recommendations
            logger.info("Step 6: Generating recommendations...")
            recommendations = self._generate_recommendations(schema)
            result.metadata['recommendations'] = recommendations

            result.success = True

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            result.errors.append(str(e))
            result.success = False

        # Calculate duration
        end_time = datetime.now()
        result.end_time = end_time
        result.duration_seconds = (end_time - start_time).total_seconds()

        # Add final metadata
        result.metadata['analyze_data'] = self.analyze_data
        result.metadata['deep_analysis'] = self.deep_analysis
        result.metadata['timestamp'] = start_time.isoformat()

        # Update cache
        self._analysis_timestamp = start_time

        logger.info(f"Analysis complete in {result.duration_seconds:.2f}s")

        return result

    def _parse_schema(self) -> ParsedSchema:
        """Parse database schema."""
        # Use schema parser
        parser = SchemaParser(self.connector, analyze_data=self.analyze_data)
        schema = parser.parse_schema()

        # Cache for later use
        self._cached_schema = schema

        return schema

    def _generate_semantic_layer(self, schema: ParsedSchema) -> Dict[str, Any]:
        """Generate semantic layer from schema."""
        # Use semantic layer generator
        generator = SemanticLayerGenerator(self.connector)

        # Convert schema to format expected by generator
        # The generator will handle this internally

        # Generate semantic layer
        semantic = generator.generate()

        # Add additional context
        if 'domain' not in semantic:
            semantic['domain'] = self._detect_domain(schema)

        semantic['analyzed_at'] = datetime.now().isoformat()
        semantic['database'] = {
            'type': self.connector.get_database_type(),
            'version': self.connector.get_version(),
            'tables': len(schema.tables)
        }

        self._cached_semantic = semantic

        return semantic

    def _analyze_data_quality(self, schema: ParsedSchema) -> Dict[str, Any]:
        """Analyze data quality metrics."""
        quality = {
            'score': 0.0,
            'metrics': {},
            'issues': []
        }

        total_score = 0.0
        checks = 0

        # Check primary keys
        tables_with_pk = 0
        for table in schema.tables:
            if table.primary_keys:
                tables_with_pk += 1

        if schema.total_tables > 0:
            pk_ratio = tables_with_pk / schema.total_tables
            total_score += pk_ratio * 10
            checks += 10
            quality['metrics']['primary_key_coverage'] = pk_ratio

            if pk_ratio < 0.8:
                quality['issues'].append(
                    f"Low primary key coverage: {pk_ratio:.0%}")

        # Check column completeness
        total_nulls = 0
        total_columns = 0
        for table in schema.tables:
            for column in table.columns:
                total_columns += 1
                if column.nullable:
                    total_nulls += 1

        if total_columns > 0:
            null_ratio = total_nulls / total_columns
            total_score += (1 - null_ratio) * 10
            checks += 10
            quality['metrics']['null_ratio'] = null_ratio

            if null_ratio > 0.5:
                quality['issues'].append(f"High null ratio: {null_ratio:.0%}")

        # Check relationships
        relationships = len(schema.relationships)
        if schema.total_tables > 0:
            rel_ratio = relationships / schema.total_tables
            total_score += min(rel_ratio, 1.0) * 10
            checks += 10
            quality['metrics']['relationship_density'] = rel_ratio

        # Calculate final score
        quality['score'] = (total_score / checks) * 10 if checks > 0 else 0
        quality['score'] = min(quality['score'], 10.0)

        return quality

    def _detect_domain(self, schema: ParsedSchema) -> str:
        """Detect business domain from schema."""
        domain_scores = {
            'ecommerce': 0,
            'saas': 0,
            'fintech': 0,
            'healthcare': 0,
            'logistics': 0,
            'education': 0,
            'real_estate': 0,
            'gaming': 0,
            'social_media': 0,
            'general': 0
        }

        # Keywords for domain detection
        domain_keywords = {
            'ecommerce': ['order', 'product', 'customer', 'cart', 'payment', 'shipment', 'inventory'],
            'saas': ['user', 'subscription', 'plan', 'feature', 'billing', 'tenant', 'organization'],
            'fintech': ['transaction', 'account', 'wallet', 'balance', 'transfer', 'ledger', 'currency'],
            'healthcare': ['patient', 'doctor', 'appointment', 'prescription', 'diagnosis', 'treatment'],
            'logistics': ['shipment', 'warehouse', 'driver', 'vehicle', 'route', 'delivery', 'tracking'],
            'education': ['student', 'course', 'teacher', 'class', 'enrollment', 'grade', 'assignment'],
            'real_estate': ['property', 'listing', 'agent', 'client', 'offer', 'showing', 'commission'],
            'gaming': ['player', 'game', 'score', 'level', 'achievement', 'match', 'tournament'],
            'social_media': ['post', 'friend', 'like', 'comment', 'share', 'follower', 'profile']
        }

        # Score each table
        for table in schema.tables:
            table_lower = table.name.lower()

            for domain, keywords in domain_keywords.items():
                for keyword in keywords:
                    if keyword in table_lower:
                        domain_scores[domain] += 2
                        break

                    # Check columns too
                    for column in table.columns:
                        if keyword in column.name.lower():
                            domain_scores[domain] += 1
                            break

        # Find max score
        max_domain = max(domain_scores, key=domain_scores.get)
        max_score = domain_scores[max_domain]

        if max_score >= 5:
            return max_domain
        elif max_score >= 2:
            return max_domain
        else:
            return 'general'

    def _identify_patterns(self, schema: ParsedSchema) -> Dict[str, List[str]]:
        """Identify patterns in the schema."""
        patterns = {
            'naming_patterns': [],
            'relationship_patterns': [],
            'column_patterns': []
        }

        # Naming patterns
        for table in schema.tables:
            if table.name.startswith('tbl_'):
                patterns['naming_patterns'].append(
                    f"{table.name}: prefix 'tbl_'")
            elif table.name.startswith('vw_'):
                patterns['naming_patterns'].append(
                    f"{table.name}: view prefix")
            elif '_' in table.name and table.name.islower():
                patterns['naming_patterns'].append(f"{table.name}: snake_case")
            elif table.name[0].isupper() and not '_' in table.name:
                patterns['naming_patterns'].append(f"{table.name}: PascalCase")

        # Relationship patterns
        for relationship in schema.relationships:
            rel_str = f"{relationship['from_table']} -> {relationship['to_table']}"
            if rel_str not in patterns['relationship_patterns']:
                patterns['relationship_patterns'].append(rel_str)

        # Column patterns
        for table in schema.tables:
            for column in table.columns:
                if column.name.endswith('_id'):
                    patterns['column_patterns'].append(
                        f"{table.name}.{column.name}: foreign key pattern")
                elif column.name.startswith('is_') or column.name.startswith('has_'):
                    patterns['column_patterns'].append(
                        f"{table.name}.{column.name}: boolean flag")
                elif 'created' in column.name or 'updated' in column.name:
                    patterns['column_patterns'].append(
                        f"{table.name}.{column.name}: timestamp pattern")

        return patterns

    def _generate_recommendations(self, schema: ParsedSchema) -> List[str]:
        """Generate recommendations based on analysis."""
        recommendations = []

        # Check primary keys
        tables_without_pk = []
        for table in schema.tables:
            if not table.primary_keys:
                tables_without_pk.append(table.name)

        if tables_without_pk:
            recommendations.append(
                f"Add primary keys to: {', '.join(tables_without_pk[:5])}")

        # Check table count
        if schema.total_tables > 50:
            recommendations.append(
                "Consider normalizing or partitioning large schema")

        # Check columns count
        for table in schema.tables:
            if len(table.columns) > 30:
                recommendations.append(
                    f"Consider splitting {table.name} (has {len(table.columns)} columns)")

        # Check no FK relationships
        if not schema.relationships:
            recommendations.append(
                "No foreign key relationships detected. Consider adding relationships.")

        # Check naming
        for table in schema.tables:
            if not table.name.islower() and '_' not in table.name:
                if table.name not in [r.split(':')[0].strip() for r in recommendations]:
                    recommendations.append(
                        f"Consider using snake_case for {table.name}")

        return recommendations[:10]  # Limit to 10 recommendations

    def _get_schema_summary(self, schema: ParsedSchema) -> Dict[str, Any]:
        """Get schema summary."""
        return {
            'tables': schema.total_tables,
            'columns': schema.total_columns,
            'relationships': len(schema.relationships),
            'views': len(schema.views),
            'pii_columns': len(schema.pii_columns),
            'timestamp_columns': len(schema.timestamp_columns),
            'domain': schema.domain,
            'complexity_score': schema.schema_complexity,
            'data_quality_score': schema.data_quality_score
        }

    def get_cached_schema(self) -> Optional[ParsedSchema]:
        """Get cached schema."""
        return self._cached_schema

    def get_cached_semantic(self) -> Optional[Dict[str, Any]]:
        """Get cached semantic layer."""
        return self._cached_semantic

    def get_analysis_timestamp(self) -> Optional[datetime]:
        """Get timestamp of last analysis."""
        return self._analysis_timestamp

    def get_summary(self) -> Dict[str, Any]:
        """Get quick summary without full analysis."""
        if self._cached_schema:
            return self._get_schema_summary(self._cached_schema)

        # Quick analysis
        try:
            tables = self.connector.get_table_names()
            return {
                'tables': len(tables),
                'database_type': self.connector.get_database_type(),
                'version': self.connector.get_version(),
                'status': 'ready'
            }
        except:
            return {
                'status': 'error',
                'message': 'Could not connect to database'
            }

    def export_results(self, result: AnalysisResult, output_path: Path) -> None:
        """Export analysis results to file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2, default=str)

        logger.info(f"Analysis results exported to: {output_path}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        # No cleanup needed, connector handles its own cleanup
        pass


def quick_analyze(
    connection_url: str,
    config_path: Optional[Path] = None,
    output_path: Optional[Path] = None
) -> AnalysisResult:
    """
    Quick helper function for database analysis.

    Args:
        connection_url: Database connection URL
        config_path: Path to configuration file
        output_path: Path to export results

    Returns:
        AnalysisResult object
    """
    from ..connectors import get_connector

    # Create connector
    connector = get_connector(connection_url)

    # Create analyzer
    analyzer = Analyzer(connector, config_path)

    # Run analysis
    result = analyzer.analyze()

    # Export if requested
    if output_path and result.success:
        analyzer.export_results(result, output_path)

    return result


# For backward compatibility
def analyze_database(connection_url: str, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Legacy function for database analysis.

    Args:
        connection_url: Database connection URL
        config_path: Path to configuration file

    Returns:
        Dictionary with analysis results
    """
    result = quick_analyze(connection_url, config_path)

    if result.success and result.semantic_layer:
        return result.semantic_layer
    else:
        return {
            'error': 'Analysis failed',
            'errors': result.errors
        }
