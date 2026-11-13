"""Regression checks for non-destructive SQLite initialization and transactions."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from storage import Database
from storage.migrations import SCHEMA_VERSION
from voyage_store import VoyageStore


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "nested" / "voyages.sqlite3"

    def test_new_schema_and_repeated_initialization(self) -> None:
        store = VoyageStore(self.path)
        VoyageStore(self.path)
        with store.database.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(tables, {"voyages", "demo_runs", "users", "sessions", "login_attempts", "audit_events", "resource_owners", "weather_datasets"})

    def test_legacy_json_is_preserved_exactly(self) -> None:
        database = Database(self.path)
        original = '{ "text": "Астрахань", "value": 1.00 }'
        with database.transaction() as connection:
            connection.execute("CREATE TABLE voyages (id TEXT PRIMARY KEY, request TEXT NOT NULL, baseline TEXT NOT NULL, current TEXT NOT NULL, conditions TEXT NOT NULL, revision INTEGER NOT NULL)")
            connection.execute("CREATE TABLE demo_runs (id TEXT PRIMARY KEY, result TEXT NOT NULL)")
            connection.execute("INSERT INTO voyages VALUES (?,?,?,?,?,?)", ("legacy", original, original, original, original, 4))
            connection.execute("INSERT INTO demo_runs VALUES (?,?)", ("demo", original))
        VoyageStore(self.path)
        VoyageStore(self.path)
        with database.connect() as connection:
            self.assertEqual(connection.execute("SELECT * FROM voyages").fetchone(), ("legacy", original, original, original, original, 4))
            self.assertEqual(connection.execute("SELECT * FROM demo_runs").fetchone(), ("demo", original))

    def test_future_schema_rejected_without_changes(self) -> None:
        database = Database(self.path)
        with database.transaction() as connection:
            connection.execute("PRAGMA user_version=999")
            connection.execute("CREATE TABLE retained (value TEXT)")
            connection.execute("INSERT INTO retained VALUES ('untouched')")
        with self.assertRaisesRegex(RuntimeError, "newer than supported"):
            VoyageStore(self.path)
        with database.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 999)
            self.assertEqual(connection.execute("SELECT value FROM retained").fetchone()[0], "untouched")

    def test_transaction_rolls_back_rows_and_schema(self) -> None:
        database = Database(self.path)
        database.migrate()
        with self.assertRaisesRegex(ValueError, "failure"):
            with database.transaction() as connection:
                connection.execute("INSERT INTO demo_runs VALUES ('rollback', '{}')")
                connection.execute("CREATE TABLE rolled_back (id INTEGER)")
                raise ValueError("failure")
        with database.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM demo_runs").fetchone()[0], 0)
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='rolled_back'").fetchone())

    def test_connection_pragmas_and_foreign_keys(self) -> None:
        database = Database(self.path, busy_timeout_ms=321)
        with database.transaction() as connection:
            connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
            connection.execute("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))")
        for _ in range(2):
            with database.connect() as connection:
                self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 321)
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("INSERT INTO child VALUES (999)")

    def test_migration_failure_rolls_back_version_and_tables(self) -> None:
        database = Database(self.path)
        with database.transaction() as connection:
            connection.execute("CREATE VIEW demo_runs AS SELECT 1")
        with self.assertRaisesRegex(RuntimeError, "Incompatible schema"):
            database.migrate()
        with database.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='voyages'").fetchone())

    def test_current_version_with_malformed_tables_is_rejected(self) -> None:
        database = Database(self.path)
        with database.transaction() as connection:
            connection.execute("PRAGMA user_version=1")
            connection.execute("CREATE TABLE voyages (id TEXT PRIMARY KEY)")
        with self.assertRaisesRegex(RuntimeError, "Incompatible schema"):
            database.migrate()


if __name__ == "__main__":
    unittest.main()
