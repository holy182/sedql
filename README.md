# SeDQL - Semantic Database Query Layer

<p align="center">
  <img src="https://img.shields.io/badge/version-0.2.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/license-AGPL--3.0-green.svg" alt="License">
</p>

<p align="center">
  <strong>Turn your database schema into LLM-ready context. One command, zero config, 100% local.</strong>
</p>

---

## What is SeDQL?

SeDQL reads your database schema and exports a clean, structured JSON semantic layer — business names, relationships, PII flags, and rules — that you can drop straight into a prompt, a RAG pipeline, or an agent's context window.

It also ships a small template-based query CLI as a convenience for quick lookups without writing SQL, but the export is the point. If you're building anything that hands database context to an LLM (a coding agent, a support bot, a RAG system), SeDQL is the fastest way to generate that context without hand-writing a schema description yourself.

**It is not an LLM. It is not a data warehouse. It is a thin, local wrapper around your database that makes it legible — to you and to AI.**

---

## What SeDQL Actually Does

| Claim (Marketing) | Reality (What It Does) |
|-------------------|----------------------|
| "LLM-ready context" | JSON export with column mappings, business names, relationships, and rule templates — designed to be pasted or piped into a prompt |
| "Auto-detects PII" | Regex pattern matching on column names (email, phone, ssn, etc.), flagged in the export so an LLM knows what to mask |
| "Business rules engine" | Pre-defined rule templates with severity levels and conditions, included in the export as context |
| "Natural language query" | A secondary CLI convenience: pattern matching against a template list. Predictable, auditable, no hallucinations — but not the main feature |
| "Works offline, no API keys" | Yes, actually. No external calls. You can run it on an air-gapped machine |

---

## Who Is This For?

This tool is for developers who want to:

- Generate structured schema context for an LLM, coding agent, RAG pipeline, or support bot — without hand-writing a schema description
- Understand what tables/columns mean in business terms
- Flag PII and business rules automatically so they're visible to both humans and AI
- Get a quick answer to a simple question without writing SQL, as a bonus
- Avoid setting up dbt, Cube, or WrenAI just to generate schema context

**This is not for enterprise-scale data warehousing, and it's not a text-to-SQL engine.** If you need free-form natural language querying at scale, use an LLM-backed tool like WrenAI or Vanna. If you have hundreds of tables and complex metrics, use dbt Semantic Layer or Cube.

---

## The Honest Tradeoff

| SeDQL | LLM-Powered Alternatives (WrenAI, Vanna) |
|-------|------------------------------------------|
| No API keys required to generate the export | Requires LLM API key to generate context or answer queries |
| 100% local processing | Sends data/schema to cloud (usually) |
| Works offline | Requires internet |
| You bring your own LLM for querying — SeDQL just prepares the context | Query answering is built in, end to end |
| Predictable, template-based query responses (bonus feature) | Flexible free-form querying, but can hallucinate |
| 5-100 table sweet spot | Scales to thousands of tables |
| No external services to configure | Requires connecting an LLM provider and, often, a vector store |

SeDQL isn't trying to be the thing that answers your question. It's trying to be the thing that hands an LLM everything it needs to answer your question correctly, without you writing that context by hand every time your schema changes.

---

## Quick Start

```bash
# Install
pip install sedql

# Initialize with your database
sedql init --db "sqlite:///mydb.db"

# Query using templates
sedql query "show me all customers"
sedql query "top 10 products by revenue"

# Export semantic JSON
sedql export --output semantic.json
```

---

## Installation

```bash
pip install sedql
```

With database support:

```bash
pip install "sedql[postgres]"   # PostgreSQL
pip install "sedql[mysql]"      # MySQL
pip install "sedql[all]"        # All
```

---

## Usage

### CLI Commands

| Command | Description |
|---------|-------------|
| `sedql init --db URL` | Initialize with database |
| `sedql status` | Show current status |
| `sedql list-entities` | List business entities |
| `sedql show-entity NAME` | Show entity details |
| `sedql list-rules` | List business rules |
| `sedql query "..."` | Query using templates |
| `sedql export` | Export semantic layer |
| `sedql show` | Show full semantic layer |

### Supported Query Templates (Bonus Feature)

The `query` command is a convenience for quick lookups without writing SQL — not SeDQL's main feature. It matches natural language questions against a template list:

| You Ask | SeDQL Translates To |
|---------|-------------------|
| "show me all [entity]" | `SELECT * FROM [table] LIMIT 10` |
| "show me [entity] where [field] is [value]" | `SELECT * FROM [table] WHERE [field] = [value]` |
| "count [entity]" | `SELECT COUNT(*) FROM [table]` |
| "top N [entity] by [field]" | `SELECT * FROM [table] ORDER BY [field] DESC LIMIT N` |
| "sum [field] from [entity]" | `SELECT SUM([field]) FROM [table]` |

If your question doesn't match a template, SeDQL will tell you what patterns it does support.

---

## Configuration

### Environment Variables

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/mydb
SeDQL_CONFIG_PATH=./sedql.config.json
SeDQL_LOG_LEVEL=INFO
```

### Config File

Create `sedql.config.json`:

```json
{
  "database": {
    "url": "postgresql://user:pass@localhost:5432/mydb"
  },
  "semantic": {
    "output_path": "./semantic_layer.json",
    "include_pii": true
  },
  "rules": {
    "enabled": true,
    "pii_protection": true
  },
  "security": {
    "mask_pii": true
  }
}
```

---

## What the Semantic Layer Contains

The exported JSON includes:

| Component | Description |
|-----------|-------------|
| **Entities** | Tables mapped to business names (e.g., `users` → `Customer`) |
| **Fields** | Columns mapped to business names with PII flags |
| **Relationships** | Foreign keys mapped to business descriptions |
| **Rules** | Validation, security, and business logic rules |
| **Metrics** | Pre-defined business metrics (count, sum, avg) |

### Example Output

```json
{
  "entities": [
    {
      "name": "users",
      "business_name": "Customer",
      "fields": [
        {
          "name": "email",
          "business_name": "Email Address",
          "is_pii": true
        }
      ]
    }
  ],
  "relationships": [
    {
      "from": "Customer",
      "to": "Order",
      "description": "Customer places Orders"
    }
  ],
  "rules": [
    {
      "name": "email_pii_protection",
      "type": "security",
      "description": "Email is PII - mask in queries"
    }
  ]
}
```

---

## Architecture

```mermaid
flowchart TB
    DB[("Your Database<br/>PostgreSQL · MySQL · SQLite")]

    subgraph CORE["SeDQL Core"]
        direction TB
        CONN["Connectors<br/><sub>pooling, retry, health checks</sub>"]
        PARSE["Schema Parser<br/><sub>tables, columns, relationships</sub>"]
        GEN["Semantic Layer Generator<br/><sub>entities, fields, PII flags</sub>"]
        RULES["Rules Engine<br/><sub>validation, security</sub>"]
        TMPL["Query Templates<br/><sub>pattern matching — bonus feature</sub>"]
        EXEC["Query Executor<br/><sub>caching, pagination</sub>"]

        CONN --> PARSE --> GEN --> RULES
        RULES --> TMPL --> EXEC
    end

    OUT1["Semantic Layer JSON<br/><sub>LLM / RAG context</sub>"]
    OUT2["Business Rules & Metrics"]
    OUT3["SQL Query Results"]

    DB --> CONN
    RULES -.export.-> OUT1
    RULES -.export.-> OUT2
    EXEC --> OUT3
```

Everything runs locally in one process — no external services, no network calls beyond your own database connection.

---

## Using the Export with an LLM

The whole point of the export is that you don't have to explain your schema by hand. A typical flow:

```bash
sedql init --db "sqlite:///mydb.db"
sedql export --output semantic.json
```

Then drop `semantic.json` into:

- A system prompt or context window for a coding agent working on your app
- A RAG pipeline as grounding context before generating SQL
- A support bot that needs to know which fields are PII and must be masked
- Your own text-to-SQL prompt, so the LLM gets business names and rules instead of raw `col_7` column names

Because the export already resolves table names to business entities and flags PII and rules, the LLM spends fewer tokens (and fewer guesses) figuring out what your schema means.

---

## Who's Using SeDQL?

Ideal for:

- Developers wiring database context into an LLM, agent, or RAG pipeline
- Indie developers building side projects with <50 tables
- Small teams who find dbt/Cube overbuilt for their needs
- Developers building local-first apps with SQLite
- Privacy-conscious devs who don't want to send schema to cloud
- Anyone who wants a simple semantic layer without a 15-tool data stack

Not ideal for:

- Teams that need a built-in, end-to-end natural language query engine (use WrenAI or Vanna)
- Enterprise data warehouses with hundreds of tables
- Teams requiring SOC2 or procurement documentation
- Large-scale BI with complex metric definitions

---

## What's Next

SeDQL is v0.2.0 — early, and shaped by whoever shows up to build it. Here's the direction, roughly in priority order:

- **First-class SQLite / embeddable mode** — use SeDQL as a Python library inside a local-first or desktop app, not just a CLI. Generate context at runtime instead of exporting a file.
- **More query templates** — the pattern list is intentionally small right now. Contributions of new templates (with tests) are one of the easiest ways to add value.
- **Richer relationship inference** — better detection of implicit foreign keys and many-to-many join tables beyond declared constraints.
- **Pluggable PII detectors** — swap the regex-based detector for something smarter (custom rules, allow/deny lists, or an optional local NER model) without touching core.
- **Semantic layer validators** — a `sedql lint` command to catch missing descriptions, orphaned rules, or entities with no business name before you export.
- **More database backends** — DuckDB and MSSQL are the next likely additions after the current three.

None of this is committed on a timeline — it's a list of what would make SeDQL more useful, not a promise. If one of these matters to you, open an issue or just start on it.

---

## Contributing

SeDQL only gets better with more schemas, more edge cases, and more hands on it. This isn't a solo project by design — the goal is for it to become a genuinely useful, community-run open-source semantic layer, and that only happens with contributors.

Good places to start:

- **Add a query template** — small, self-contained, easy first PR
- **Improve PII detection** — add patterns for fields the regex misses (addresses, national IDs, etc. — see [What's Next](#whats-next))
- **Add a database backend** — DuckDB support is a good next target
- **Write docs or examples** — a real-world schema walkthrough helps more people trust the tool
- **Report inaccurate output** — if the export mislabels an entity or misses a relationship, that's a bug worth filing even without a fix attached

No contribution is too small. Fixing a typo in the docs is as welcome as a new backend.

### Development Setup

```bash
git clone https://github.com/holy182/sedql.git
cd sedql
pip install -e ".[dev]"
```

### Running Tests

```bash
pytest tests/
pytest tests/ --cov=src/sedql --cov-report=html
```

### How to Contribute

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

If you're not sure where to start, open a Discussion — don't feel like you need a fully-formed PR to say hello.

---

## License

AGPL-3.0

> **Note:** AGPL-3.0 means anyone who runs a modified version of SeDQL as a network service must release their source changes too — not just people who redistribute the binary. If you're targeting indie devs and small teams embedding SeDQL inside proprietary products, double-check this is the license you actually want; MIT or Apache-2.0 is more common for that audience unless blocking closed-source SaaS wrappers is a deliberate goal.

---

## Support

- Issues: [GitHub Issues](https://github.com/holy182/sedql/issues)
- Discussions: [GitHub Discussions](https://github.com/holy182/sedql/discussions)

---

**Made for developers who want simple, local semantic querying**
