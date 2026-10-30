"""Additive, data-preserving database upgrades for existing SQLite files."""

from __future__ import annotations

from sqlalchemy import Engine, inspect


SQLITE_ADDITIONS = {
    "reference_version": "VARCHAR(80)",
    "batch_description": "VARCHAR(255)",
    "methodology": "JSON",
    "report_metadata": "JSON",
    "feature_results": "JSON",
}


def upgrade_sqlite_schema(engine: Engine) -> None:
    """Add nullable drift-report fields without rebuilding or deleting rows.

    The migration is idempotent. ``BEGIN IMMEDIATE`` serializes concurrent
    SQLite startup upgrades, and every added field is nullable so legacy
    MonitoringReport rows remain valid and unchanged.
    """
    if engine.dialect.name != "sqlite":
        return

    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            inspector = inspect(connection)
            if not inspector.has_table("monitoring_reports"):
                connection.commit()
                return
            existing = {
                column["name"]
                for column in inspector.get_columns("monitoring_reports")
            }
            for name, sql_type in SQLITE_ADDITIONS.items():
                if name not in existing:
                    connection.exec_driver_sql(
                        f'ALTER TABLE monitoring_reports ADD COLUMN "{name}" {sql_type}'
                    )
            indexes = {
                index["name"]
                for index in inspect(connection).get_indexes("monitoring_reports")
            }
            if "ix_monitoring_reports_model_created" not in indexes:
                connection.exec_driver_sql(
                    "CREATE INDEX ix_monitoring_reports_model_created "
                    "ON monitoring_reports (model_version, created_at)"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
