"""Natural language to SQL translator."""

import re
from typing import Dict, List, Any, Optional, Tuple
from ..utils.logger import logger


class Translator:
    """Translate natural language queries to SQL."""

    def __init__(self, semantic_layer: Dict):
        self.semantic = semantic_layer
        self._build_index()

    def _build_index(self):
        """Build search index from semantic layer."""
        self.entity_map = {}
        self.field_map = {}
        self.field_to_table = {}
        self.pii_fields = set()

        for entity in self.semantic.get("entities", []):
            entity_name = entity.get("name", "").lower()
            business_name = entity.get("business_name", "").lower()

            # Map business names to table names
            self.entity_map[business_name] = entity_name
            self.entity_map[entity_name] = entity_name

            # Also add common variations
            if business_name.endswith('s'):
                self.entity_map[business_name[:-1]] = entity_name
            else:
                self.entity_map[business_name + 's'] = entity_name

            # Map fields
            for field in entity.get("fields", []):
                field_name = field.get("name", "").lower()
                business_field = field.get("business_name", "").lower()

                field_info = {
                    'table': entity_name,
                    'field': field_name,
                    'type': field.get("type", ""),
                    'is_pii': field.get("is_pii", False),
                    'is_primary': field.get("is_primary", False),
                    'is_foreign': field.get("is_foreign", False)
                }

                self.field_map[field_name] = field_info
                self.field_map[business_field] = field_info

                if field_info['is_pii']:
                    self.pii_fields.add(field_name)

                if field_name not in self.field_to_table:
                    self.field_to_table[field_name] = []
                self.field_to_table[field_name].append(entity_name)

    def translate(self, query: str) -> str:
        """Translate natural language query to SQL."""
        query_lower = query.lower().strip()

        # Remove common fillers
        query_lower = re.sub(r'^show me\s+', '', query_lower)
        query_lower = re.sub(r'^get\s+', '', query_lower)
        query_lower = re.sub(r'^i want\s+', '', query_lower)
        query_lower = re.sub(r'^please\s+', '', query_lower)

        # Detect query type
        if self._is_count(query_lower):
            return self._build_count_query(query_lower)
        elif self._is_sum(query_lower):
            return self._build_sum_query(query_lower)
        elif self._is_top(query_lower):
            return self._build_top_query(query_lower)
        elif self._is_aggregate(query_lower):
            return self._build_aggregate_query(query_lower)
        else:
            return self._build_select_query(query_lower)

    def _is_count(self, query: str) -> bool:
        return 'count' in query or 'how many' in query

    def _is_sum(self, query: str) -> bool:
        return 'sum' in query or 'total' in query or 'revenue' in query or 'sales' in query

    def _is_top(self, query: str) -> bool:
        return 'top' in query or 'limit' in query

    def _is_aggregate(self, query: str) -> bool:
        return any(word in query for word in ['average', 'avg', 'max', 'min', 'group by'])

    def _find_entity(self, query: str) -> Optional[str]:
        """Find the primary entity in the query."""
        for entity in sorted(self.entity_map.keys(), key=len, reverse=True):
            if entity in query and len(entity) > 2:
                return self.entity_map[entity]
        return None

    def _find_fields(self, query: str) -> List[Tuple[str, str]]:
        """Find field references in the query."""
        found = []
        for field_name, info in self.field_map.items():
            if field_name in query:
                found.append((field_name, info['table']))
        return found

    def _get_table_fields(self, table: str, include_pii: bool = False) -> List[str]:
        """Get all fields for a table."""
        for entity in self.semantic.get("entities", []):
            if entity.get("name", "").lower() == table.lower():
                fields = []
                for field in entity.get("fields", []):
                    if include_pii or not field.get("is_pii", False):
                        fields.append(field.get("name"))
                return fields
        return ['*']

    def _build_select_query(self, query: str) -> str:
        """Build a SELECT query."""
        entity = self._find_entity(query)
        if not entity:
            return f"-- Could not find entity in: {query}\nSELECT * FROM unknown_table LIMIT 10"

        # Find specific fields
        fields = self._find_fields(query)

        if fields:
            # Use only fields mentioned in query
            select_fields = [f[0] for f in fields if f[1] == entity]
            if not select_fields:
                select_fields = self._get_table_fields(entity)[:3]
        else:
            select_fields = self._get_table_fields(entity)

        # Add conditions if found
        where_clause = self._build_where_clause(query)

        # Build SQL
        sql = f"SELECT {', '.join(select_fields)}\nFROM {entity}"

        if where_clause:
            sql += f"\nWHERE {where_clause}"

        sql += "\nLIMIT 10"

        return sql

    def _build_count_query(self, query: str) -> str:
        """Build a COUNT query."""
        entity = self._find_entity(query)
        if not entity:
            return f"-- Could not find entity in: {query}\nSELECT COUNT(*) FROM unknown_table"

        where_clause = self._build_where_clause(query)

        sql = f"SELECT COUNT(*) as total_count\nFROM {entity}"

        if where_clause:
            sql += f"\nWHERE {where_clause}"

        return sql

    def _build_sum_query(self, query: str) -> str:
        """Build a SUM query."""
        entity = self._find_entity(query)
        if not entity:
            return f"-- Could not find entity in: {query}\nSELECT SUM(amount) FROM unknown_table"

        # Find what to sum
        field_to_sum = None
        for field_name in ['total_amount', 'amount', 'price', 'quantity', 'revenue']:
            if field_name in query or field_name in self.field_map:
                field_to_sum = field_name
                break

        if not field_to_sum:
            # Try to find any numeric field
            for entity_info in self.semantic.get("entities", []):
                if entity_info.get("name", "").lower() == entity.lower():
                    for field in entity_info.get("fields", []):
                        if 'int' in field.get("type", "").lower() or 'real' in field.get("type", "").lower():
                            field_to_sum = field.get("name")
                            break
                if field_to_sum:
                    break

        if not field_to_sum:
            field_to_sum = 'id'

        where_clause = self._build_where_clause(query)

        sql = f"SELECT SUM({field_to_sum}) as total\nFROM {entity}"

        if where_clause:
            sql += f"\nWHERE {where_clause}"

        return sql

    def _build_top_query(self, query: str) -> str:
        """Build a TOP/LIMIT query."""
        entity = self._find_entity(query)
        if not entity:
            return f"-- Could not find entity in: {query}\nSELECT * FROM unknown_table LIMIT 10"

        # Extract number
        numbers = re.findall(r'\d+', query)
        limit = int(numbers[0]) if numbers else 10

        # Find sort field
        sort_field = None
        for word in ['revenue', 'total', 'amount', 'price', 'sales', 'orders']:
            if word in query:
                sort_field = word
                break

        if sort_field:
            # Try to find matching field
            for field_name, info in self.field_map.items():
                if sort_field in field_name:
                    sort_field = info['field']
                    break

        # Build SQL
        fields = self._get_table_fields(entity)
        sql = f"SELECT {', '.join(fields)}\nFROM {entity}"

        if sort_field:
            sql += f"\nORDER BY {sort_field} DESC"

        sql += f"\nLIMIT {limit}"

        return sql

    def _build_aggregate_query(self, query: str) -> str:
        """Build an aggregate query."""
        entity = self._find_entity(query)
        if not entity:
            return f"-- Could not find entity in: {query}\nSELECT AVG(id) FROM unknown_table"

        # Determine aggregate type
        agg_type = 'AVG'
        if 'max' in query:
            agg_type = 'MAX'
        elif 'min' in query:
            agg_type = 'MIN'
        elif 'average' in query or 'avg' in query:
            agg_type = 'AVG'

        # Find field to aggregate
        field_to_agg = None
        for field_name, info in self.field_map.items():
            if field_name in query and info['table'] == entity:
                field_to_agg = info['field']
                break

        if not field_to_agg:
            field_to_agg = 'id'

        sql = f"SELECT {agg_type}({field_to_agg}) as result\nFROM {entity}"
        return sql

    def _build_where_clause(self, query: str) -> str:
        """Extract conditions from query."""
        conditions = []

        # Date conditions
        if 'last month' in query:
            conditions.append("created_at >= date('now', '-1 month')")
        if 'last week' in query:
            conditions.append("created_at >= date('now', '-7 days')")
        if 'today' in query:
            conditions.append("created_at >= date('now')")

        # Status conditions
        if 'completed' in query:
            conditions.append("status = 'completed'")
        if 'pending' in query:
            conditions.append("status = 'pending'")
        if 'cancelled' in query:
            conditions.append("status = 'cancelled'")

        # Active conditions
        if 'active' in query:
            conditions.append("status != 'inactive'")

        return ' AND '.join(conditions) if conditions else ''
