"""Main CLI entry point for SEDQL."""

import sys
import click
from pathlib import Path

from .commands import CommandHandler


@click.group()
@click.version_option(version="0.1.0", prog_name="sedql")
def cli():
    """SEDQL - Semantic Entity Query Layer

    Automatically converts your database into an AI-ready semantic layer.
    """
    pass


@cli.command()
@click.option('--db', '-d', required=True, help='Database connection URL')
@click.option('--output', '-o', default='semantic_layer.json', help='Output file')
def init(db: str, output: str):
    """Initialize SEDQL with a database.

    Example:
        sedql init --db "sqlite:///test.db"
        sedql init --db "postgresql://user:pass@localhost/mydb"
    """
    handler = CommandHandler()
    try:
        handler.init(db, output)
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def status():
    """Show current SEDQL status."""
    handler = CommandHandler()
    handler.status()


@cli.command()
@click.option('--format', '-f', default='table', help='Output format (table, json)')
def list_entities(format: str):
    """List all business entities."""
    handler = CommandHandler()
    handler.list_entities(format)


@cli.command()
@click.argument('entity_name')
def show_entity(entity_name: str):
    """Show details of a specific entity.

    Example:
        sedql show-entity Customer
        sedql show-Entity users
    """
    handler = CommandHandler()
    handler.show_entity(entity_name)


@cli.command()
@click.option('--entity', '-e', help='Filter rules by entity')
def list_rules(entity: str):
    """List all business rules."""
    handler = CommandHandler()
    handler.list_rules(entity)


@cli.command()
@click.argument('query_text')
@click.option('--db', '-d', help='Database connection URL (uses config if not provided)')
def query(query_text: str, db: str):
    """Query the database using natural language.

    Example:
        sedql query "show me all customers"
        sedql query "count orders from last month"
        sedql query "top 10 products by revenue"
    """
    handler = CommandHandler()
    handler.query(query_text, db)


@cli.command()
@click.option('--output', '-o', default='exported_semantic.json', help='Output file')
def export(output: str):
    """Export semantic layer to a file."""
    handler = CommandHandler()
    handler.export(output)


@cli.command()
def show():
    """Show the full semantic layer as JSON."""
    handler = CommandHandler()
    handler.show()


if __name__ == "__main__":
    cli()
