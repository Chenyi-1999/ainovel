"""Small, transactional schema upgrades, shared by API and worker startup.

The PostgreSQL advisory lock covers inspection, DDL and version recording. No
model-generated data is trusted as a migration and old chapter text is untouched.
"""
from sqlalchemy import inspect, text

from .db import Base

SCHEMA_VERSION = 1


def migrate(engine):
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(18110, 1)"))
        elif connection.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations "
                                "(version INTEGER PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
        versions = set(connection.scalars(text("SELECT version FROM schema_migrations")))
        if versions and max(versions) > SCHEMA_VERSION:
            raise RuntimeError("Database schema is newer than this application")
        existing = inspect(connection).get_table_names()
        additions = {
            "novels": {"context_revision": "INTEGER NOT NULL DEFAULT 1"},
            "memories": {
                "source_revision": "INTEGER",
                "evidence_quote": "TEXT NOT NULL DEFAULT ''",
                "provenance": "VARCHAR(20) NOT NULL DEFAULT 'legacy'",
                "visibility": "VARCHAR(20) NOT NULL DEFAULT 'unknown'",
                "known_by_entity_ids": "JSON NOT NULL DEFAULT '[]'",
                "revision": "INTEGER NOT NULL DEFAULT 1",
                "history": "JSON NOT NULL DEFAULT '[]'",
            },
            "jobs": {
                "idempotency_key": "VARCHAR(160)",
                "request_fingerprint": "VARCHAR(64)",
            },
        }
        for table, fields in additions.items():
            if table not in existing:
                continue
            columns = {column["name"] for column in inspect(connection).get_columns(table)}
            for name, definition in fields.items():
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
        Base.metadata.create_all(connection)
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_job_idempotency "
                                "ON jobs (novel_id, idempotency_key)"))
        if SCHEMA_VERSION not in versions:
            connection.execute(text("INSERT INTO schema_migrations(version) VALUES (:version)"),
                               {"version": SCHEMA_VERSION})


def check_schema(engine):
    """Startup never alters an existing installation. Deployment migrates offline."""
    with engine.connect() as connection:
        names = inspect(connection).get_table_names()
        if not names:
            empty = True
        else:
            empty = False
            if "schema_migrations" not in names or connection.scalar(text("SELECT MAX(version) FROM schema_migrations")) != SCHEMA_VERSION:
                raise RuntimeError("Schema upgrade required: stop API/worker and run python -m app.migrations --apply")
    if empty:
        migrate(engine)


if __name__ == "__main__":
    import argparse
    from .db import engine
    parser = argparse.ArgumentParser(description="Offline transactional schema upgrade; stop API/worker first")
    parser.add_argument("--apply", action="store_true", required=True)
    parser.parse_args()
    migrate(engine)
    print(f"Schema version {SCHEMA_VERSION} applied")
