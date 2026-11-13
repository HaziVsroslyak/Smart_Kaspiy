"""Numbered, transactional schema upgrades; existing JSON remains untouched."""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 3


def migrate(connection: sqlite3.Connection) -> None:
    """Apply upgrades inside the caller's transaction, including version changes."""
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema {version} is newer than supported schema {SCHEMA_VERSION}."
        )
    if version == 0:
        # Legacy databases have these tables but no user_version. Adopt without
        # rewriting their rows or immutable baseline JSON.
        connection.execute(
            "CREATE TABLE IF NOT EXISTS voyages (id TEXT PRIMARY KEY, request TEXT NOT NULL, "
            "baseline TEXT NOT NULL, current TEXT NOT NULL, conditions TEXT NOT NULL, "
            "revision INTEGER NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS demo_runs (id TEXT PRIMARY KEY, result TEXT NOT NULL)"
        )
        connection.execute("PRAGMA user_version=1")
    for table, expected in (
        ("voyages", ("id", "request", "baseline", "current", "conditions", "revision")),
        ("demo_runs", ("id", "result")),
    ):
        kind = connection.execute(
            "SELECT type FROM sqlite_master WHERE name=?", (table,),
        ).fetchone()
        columns = tuple(row[1] for row in connection.execute(f"PRAGMA table_info({table})"))
        if kind != ("table",) or columns != expected:
            raise RuntimeError(f"Incompatible schema for {table}.")
    if version < 2:
        for statement in SECURITY_SCHEMA:
            connection.execute(statement)
        connection.execute("INSERT OR IGNORE INTO resource_owners(resource_type,resource_id) SELECT 'voyage',id FROM voyages")
        connection.execute("INSERT OR IGNORE INTO resource_owners(resource_type,resource_id) SELECT 'demo',id FROM demo_runs")
        connection.execute('PRAGMA user_version=2')
    for table in ('users','sessions','login_attempts','audit_events','resource_owners'):
        actual=connection.execute('SELECT sql FROM sqlite_master WHERE type=\'table\' AND name=?',(table,)).fetchone()
        if actual is None:
            raise RuntimeError(f'Incompatible security schema: missing {table}.')
        expected=next(statement for statement in SECURITY_SCHEMA if statement.startswith(f'CREATE TABLE {table}('))
        normalized=lambda value: ''.join(value.casefold().split()).replace('"','')
        if normalized(actual[0])!=normalized(expected):
            raise RuntimeError(f'Incompatible security schema for {table}.')
    if version < 3:
        connection.execute('CREATE TABLE weather_datasets(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,payload TEXT NOT NULL)')
        connection.execute('PRAGMA user_version=3')
    columns=tuple(row[1] for row in connection.execute('PRAGMA table_info(weather_datasets)'))
    if columns!=('id','owner_id','payload'):raise RuntimeError('Incompatible weather dataset schema.')
    foreign_keys=connection.execute('PRAGMA foreign_key_list(weather_datasets)').fetchall()
    if not any(row[2]=='users' and row[3]=='owner_id' and row[4]=='id' and row[6]=='RESTRICT' for row in foreign_keys):
        raise RuntimeError('Incompatible weather dataset ownership constraint.')

SECURITY_SCHEMA = (
    "CREATE TABLE users(id TEXT PRIMARY KEY,login TEXT NOT NULL,email TEXT NOT NULL,login_normalized TEXT UNIQUE NOT NULL,email_normalized TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('logistician','admin','root')),status TEXT NOT NULL CHECK(status IN ('active','frozen')),must_change_password INTEGER NOT NULL,created_at REAL NOT NULL)",
    'CREATE TABLE sessions(token_digest TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,csrf_digest TEXT NOT NULL,created_at REAL NOT NULL,last_seen_at REAL NOT NULL,expires_at REAL NOT NULL,pre_auth INTEGER NOT NULL,revoked_at REAL)',
    'CREATE INDEX sessions_user ON sessions(user_id)',
    'CREATE TABLE login_attempts(bucket TEXT PRIMARY KEY,window_start REAL NOT NULL,failures INTEGER NOT NULL)',
    'CREATE TABLE audit_events(id TEXT PRIMARY KEY,at_utc REAL NOT NULL,actor_ref TEXT NOT NULL,action TEXT NOT NULL,subject_ref TEXT NOT NULL,detail_json TEXT NOT NULL)',
    "CREATE TABLE resource_owners(resource_type TEXT NOT NULL CHECK(resource_type IN ('voyage','demo')),resource_id TEXT NOT NULL,owner_id TEXT REFERENCES users(id) ON DELETE RESTRICT,ownership_revision INTEGER NOT NULL DEFAULT 0,parent_voyage_id TEXT REFERENCES voyages(id) ON DELETE RESTRICT,PRIMARY KEY(resource_type,resource_id))",
)
