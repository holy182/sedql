"""CLI command implementations for SEDQL."""

import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from tabulate import tabulate

from ..connectors import get_connector
from ..core.analyzer import Analyzer
from ..core.semantic_layer import SemanticLayer
from ..utils.logger import logger
from ..query.translator import Translator


class CommandHandler:
    """Handles all CLI commands."""

    def __init__(self):
        self.config_path = Path.cwd() / "sedql.config.json"
        self.semantic_path = Path.cwd() / "semantic_layer.json"
        self.connector = None

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if not self.config_path.exists():
            return {}
        with open(self.config_path) as f:
            return json.load(f)

    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to file."""
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)

    def init(self, db_url: str, output: str = "semantic_layer.json") -> Dict[str, Any]:
        """Initialize SEDQL with a database."""
        # Step 1: Connect to database
        print(f"🔍 Connecting to: {db_url}")

        try:
            # Get connector
            self.connector = get_connector(db_url)
            self.connector.connect()
            print("✅ Connected successfully")

            # Step 2: Analyze database
            analyzer = Analyzer(self.connector)
            result = analyzer.analyze()

            # Step 3: Generate semantic layer
            semantic = SemanticLayer(result)
            semantic.save(output)

            # Step 4: Save config
            config = {
                "database_url": db_url,
                "semantic_layer": output,
                "entities": len(result.get("entities", [])),
                "relationships": len(result.get("relationships", [])),
                "rules": len(result.get("rules", []))
            }
            self.save_config(config)

            # Step 5: Show results
            print(f"✅ Semantic layer saved to: {output}")
            print(f"📊 Found {config['entities']} entities")
            print(f"🔗 Found {config['relationships']} relationships")
            print(f"📋 Generated {config['rules']} rules")

            return result

        except Exception as e:
            logger.error(f"Init failed: {e}")
            raise

    def status(self) -> None:
        """Show SEDQL status."""
        config = self.load_config()
        semantic_exists = self.semantic_path.exists()

        print("\n📊 SEDQL Status")
        print("-" * 50)

        # Config status
        if config:
            print(f"✅ Config: {self.config_path}")
            print(f"   Database: {config.get('database_url', 'N/A')}")
            print(f"   Entities: {config.get('entities', 0)}")
            print(f"   Relationships: {config.get('relationships', 0)}")
            print(f"   Rules: {config.get('rules', 0)}")
        else:
            print(f"❌ No config found at: {self.config_path}")

        # Semantic layer status
        if semantic_exists:
            with open(self.semantic_path) as f:
                data = json.load(f)
            print(f"\n✅ Semantic Layer: {self.semantic_path}")
            print(f"   Tables: {len(data.get('entities', []))}")
            print(f"   Relationships: {len(data.get('relationships', []))}")
            print(f"   Rules: {len(data.get('rules', []))}")
        else:
            print(f"\n❌ Semantic layer not found at: {self.semantic_path}")
            print("   Run 'sedql init' to generate one")

    def list_entities(self, format: str = "table") -> None:
        """List all business entities."""
        if not self.semantic_path.exists():
            print("❌ Semantic layer not found. Run 'sedql init' first.")
            return

        with open(self.semantic_path) as f:
            data = json.load(f)

        entities = data.get("entities", [])

        if not entities:
            print("No entities found.")
            return

        if format == "json":
            print(json.dumps(entities, indent=2))
            return

        # Table format
        table = []
        for entity in entities:
            table.append([
                entity.get("business_name", entity.get("name")),
                entity.get("name"),
                len(entity.get("fields", [])),
                entity.get("description", "")
            ])

        print("\n📦 Business Entities")
        print("-" * 80)
        print(tabulate(
            table,
            headers=["Business Name", "Table", "Fields", "Description"],
            tablefmt="grid"
        ))

    def show_entity(self, entity_name: str) -> None:
        """Show details of a specific entity."""
        if not self.semantic_path.exists():
            print("❌ Semantic layer not found. Run 'sedql init' first.")
            return

        with open(self.semantic_path) as f:
            data = json.load(f)

        # Find entity
        entity = None
        for e in data.get("entities", []):
            if e.get("name", "").lower() == entity_name.lower():
                entity = e
                break
            if e.get("business_name", "").lower() == entity_name.lower():
                entity = e
                break

        if not entity:
            print(f"❌ Entity not found: {entity_name}")
            return

        print(
            f"\n📋 Entity: {entity.get('business_name')} (`{entity.get('name')}`)")
        print(f"   {entity.get('description', '')}")
        print("\n   Fields:")
        print("   " + "-" * 60)

        table = []
        for field in entity.get("fields", []):
            pii = "⚠️ Yes" if field.get("is_pii") else ""
            key = "🔑" if field.get("is_primary") else ""
            fk = "🔗" if field.get("is_foreign") else ""
            table.append([
                field.get("name"),
                field.get("business_name", ""),
                field.get("type", ""),
                pii,
                key + fk
            ])

        if table:
            print(tabulate(
                table,
                headers=["Column", "Business Name", "Type", "PII", "Keys"],
                tablefmt="grid"
            ))

    def list_rules(self, entity: Optional[str] = None) -> None:
        """List business rules."""
        if not self.semantic_path.exists():
            print("❌ Semantic layer not found. Run 'sedql init' first.")
            return

        with open(self.semantic_path) as f:
            data = json.load(f)

        rules = data.get("rules", [])

        if entity:
            rules = [r for r in rules if r.get("entity") == entity]

        if not rules:
            print("No rules found.")
            return

        print(f"\n📋 Business Rules ({len(rules)})")
        print("-" * 70)

        table = []
        for rule in rules:
            table.append([
                rule.get("name", ""),
                rule.get("entity", ""),
                rule.get("type", ""),
                rule.get("description", "")
            ])

        print(tabulate(
            table,
            headers=["Rule", "Entity", "Type", "Description"],
            tablefmt="grid"
        ))

    def query(self, query_text: str, db_url: Optional[str] = None) -> None:
        """Execute a natural language query."""
        # Load semantic layer
        if not self.semantic_path.exists():
            print("❌ Semantic layer not found. Run 'sedql init' first.")
            return

        with open(self.semantic_path) as f:
            semantic_data = json.load(f)

        # Translate to SQL
        print(f"🔍 Translating: {query_text}")
        translator = Translator(semantic_data)
        sql = translator.translate(query_text)

        print(f"\n📝 Generated SQL:")
        print("-" * 50)
        print(sql)
        print("-" * 50)

        # Execute if DB provided
        db_to_use = db_url

        if not db_to_use:
            config = self.load_config()
            db_to_use = config.get("database_url")

        if db_to_use:
            try:
                connector = get_connector(db_to_use)
                connector.connect()
                results = connector.execute_query(sql)

                if results:
                    print(f"\n📊 Results ({len(results)} rows)")
                    print("-" * 50)

                    headers = results[0].keys()
                    table = []
                    for row in results:
                        table.append([str(row.get(h, "")) for h in headers])

                    print(tabulate(table, headers=headers, tablefmt="grid"))
                else:
                    print("\n📊 No results found")

            except Exception as e:
                print(f"❌ Execution error: {e}")
        else:
            print(
                "\nℹ️  No database connection provided. Add --db or run 'sedql init' first.")

    def export(self, output: str = "semantic_layer.json") -> None:
        """Export semantic layer to file."""
        if not self.semantic_path.exists():
            print("❌ Semantic layer not found. Run 'sedql init' first.")
            return

        import shutil
        shutil.copy(self.semantic_path, output)
        print(f"✅ Exported semantic layer to: {output}")

    def show(self) -> None:
        """Show the full semantic layer."""
        if not self.semantic_path.exists():
            print("❌ Semantic layer not found. Run 'sedql init' first.")
            return

        with open(self.semantic_path) as f:
            data = json.load(f)

        print(json.dumps(data, indent=2))

    def show_config(self) -> None:
        """Show current configuration."""
        print("\n⚙️  SEDQL Configuration")
        print("-" * 50)

        config = self.load_config()
        if config:
            print(f"Database: {config.get('database_url', 'N/A')}")
            print(f"Entities: {config.get('entities', 0)}")
            print(f"Relationships: {config.get('relationships', 0)}")
            print(f"Rules: {config.get('rules', 0)}")

        # Check if config files exist
            config_dir = Path(__file__).parent.parent.parent / "config"
            name_mappings = config_dir / "name_mappings.json"

            if name_mappings.exists():
                print(f"✅ Custom mappings loaded from: {name_mappings}")
            else:
                print(
                    f"⚠️  Using default mappings. Create {name_mappings} for custom names.")
        else:
            print("No configuration found. Run 'sedql init' first.")
