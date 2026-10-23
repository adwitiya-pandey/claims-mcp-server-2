"""Tests for the read-only database layer (SPEC S1, TASKS T4).

Verifies:
- INSERT, UPDATE, DELETE, DROP, CREATE, ATTACH, writable PRAGMA all fail
- SELECT, JOIN, GROUP BY, and aggregate functions succeed
- A missing path raises DatabaseError and leaves no file behind
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from claims_mcp.db import DatabaseError, open_readonly
from tests.fixtures import build_fixture_db


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Build the fixture DB and return its path."""
    p = tmp_path / "test.db"
    build_fixture_db(p)
    return p


class TestReadOnlyConnection:
    """Connection opened by open_readonly blocks all writes."""

    def test_select_works(self, db_path: Path) -> None:
        conn = open_readonly(db_path)
        try:
            rows = conn.execute("SELECT COUNT(*) FROM claims").fetchone()
            assert rows[0] == 8  # fixture has 8 claims
        finally:
            conn.close()

    def test_join_works(self, db_path: Path) -> None:
        conn = open_readonly(db_path)
        try:
            row = conn.execute(
                "SELECT c.claim_id, p.network_status "
                "FROM claims c JOIN providers p ON c.provider_id = p.provider_id "
                "WHERE c.claim_id = ?",
                ("CLM00000001",),
            ).fetchone()
            assert row is not None
            assert row["claim_id"] == "CLM00000001"
        finally:
            conn.close()

    def test_group_by_works(self, db_path: Path) -> None:
        conn = open_readonly(db_path)
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM claims GROUP BY status"
            ).fetchall()
            assert len(rows) > 0
        finally:
            conn.close()

    def test_aggregate_functions(self, db_path: Path) -> None:
        conn = open_readonly(db_path)
        try:
            row = conn.execute(
                "SELECT SUM(billed_amount), AVG(billed_amount), "
                "MIN(billed_amount), MAX(billed_amount) FROM claims"
            ).fetchone()
            assert row[0] is not None  # SUM
        finally:
            conn.close()

    def test_insert_denied(self, db_path: Path) -> None:
        conn = open_readonly(db_path)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute("INSERT INTO plans VALUES ('PLN999','Evil',0,0,0)")
        finally:
            conn.close()

    def test_update_denied(self, db_path: Path) -> None:
        conn = open_readonly(db_path)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute(
                    "UPDATE plans SET plan_name='Hacked' WHERE plan_id='PLN001'"
                )
        finally:
            conn.close()

    def test_delete_denied(self, db_path: Path) -> None:
        conn = open_readonly(db_path)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute("DELETE FROM plans WHERE plan_id='PLN001'")
        finally:
            conn.close()

    def test_drop_denied(self, db_path: Path) -> None:
        conn = open_readonly(db_path)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute("DROP TABLE plans")
        finally:
            conn.close()

    def test_create_denied(self, db_path: Path) -> None:
        conn = open_readonly(db_path)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute("CREATE TABLE evil (id TEXT)")
        finally:
            conn.close()

    def test_attach_denied(self, db_path: Path) -> None:
        conn = open_readonly(db_path)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute(f"ATTACH DATABASE '{db_path}' AS evil")
        finally:
            conn.close()

    def test_writable_pragma_denied(self, db_path: Path) -> None:
        conn = open_readonly(db_path)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute("PRAGMA journal_mode = WAL")
        finally:
            conn.close()

    def test_pragma_query_only_denied(self, db_path: Path) -> None:
        """Cannot turn off query_only once the authorizer is installed."""
        conn = open_readonly(db_path)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute("PRAGMA query_only = OFF")
        finally:
            conn.close()


class TestMissingFile:
    def test_missing_path_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.db"
        with pytest.raises(DatabaseError, match="not found"):
            open_readonly(missing)

    def test_missing_path_creates_nothing(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.db"
        with pytest.raises(DatabaseError):
            open_readonly(missing)
        assert not missing.exists()

    def test_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(DatabaseError):
            open_readonly(tmp_path)


class TestRowFactory:
    def test_row_factory_is_row(self, db_path: Path) -> None:
        conn = open_readonly(db_path)
        try:
            row = conn.execute(
                "SELECT plan_id, plan_name FROM plans WHERE plan_id='PLN001'"
            ).fetchone()
            assert row["plan_id"] == "PLN001"
            assert row["plan_name"] == "Meridian Gold"
        finally:
            conn.close()
