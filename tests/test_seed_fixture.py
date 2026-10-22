"""Tests for seed_db.py and fixtures.py."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures import build_fixture_db

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def seed_db(tmp_path: Path) -> Path:
    """Run the seed script and return the database path."""
    db_path = tmp_path / "claims.db"
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "seed_db.py"),
            "--out",
            str(db_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"seed_db.py failed: {result.stderr}"
    return db_path


@pytest.fixture()
def fixture_db(tmp_path: Path) -> Path:
    """Build the fixture database and return the path."""
    db_path = tmp_path / "fixture.db"
    build_fixture_db(db_path)
    return db_path


class TestSeedDb:
    """Tests for the seed script."""

    def test_seed_creates_db(self, seed_db: Path) -> None:
        assert seed_db.exists()

    def test_seed_row_counts(self, seed_db: Path) -> None:
        conn = sqlite3.connect(str(seed_db))
        counts = {}
        for table in [
            "plans",
            "members",
            "providers",
            "coverage_rules",
            "claims",
            "claim_notes",
        ]:
            counts[table] = conn.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608
            ).fetchone()[0]
        conn.close()

        assert counts["plans"] == 3
        assert counts["members"] == 200
        assert counts["providers"] == 25
        assert counts["coverage_rules"] == 36  # 3 plans * 12 procedures
        assert counts["claims"] == 1500
        assert counts["claim_notes"] == 400

    def test_seed_deterministic(self, tmp_path: Path) -> None:
        """Running seed twice produces identical row counts."""
        db1 = tmp_path / "run1.db"
        db2 = tmp_path / "run2.db"

        for db_path in [db1, db2]:
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts" / "seed_db.py"),
                    "--out",
                    str(db_path),
                ],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0

        conn1 = sqlite3.connect(str(db1))
        conn2 = sqlite3.connect(str(db2))

        for table in [
            "plans",
            "members",
            "providers",
            "coverage_rules",
            "claims",
            "claim_notes",
        ]:
            c1 = conn1.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608
            ).fetchone()[0]
            c2 = conn2.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608
            ).fetchone()[0]
            assert c1 == c2, f"{table}: {c1} != {c2}"

        conn1.close()
        conn2.close()

    def test_seed_check_constraints(self, seed_db: Path) -> None:
        """All data satisfies CHECK constraints (loading doesn't raise)."""
        conn = sqlite3.connect(str(seed_db))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA integrity_check")
        # Verify each table can be read
        for table in [
            "plans",
            "members",
            "providers",
            "coverage_rules",
            "claims",
            "claim_notes",
        ]:
            rows = conn.execute(
                f"SELECT * FROM {table}"  # noqa: S608
            ).fetchall()
            assert len(rows) > 0
        conn.close()

    def test_seed_adversarial_notes_file(self, seed_db: Path) -> None:
        """Adversarial note IDs file exists and has at least 15 entries."""
        adversarial_path = PROJECT_ROOT / "data" / "adversarial_note_ids.txt"
        # The seed script creates this at PROJECT_ROOT, but for this test
        # we check the file written by the seed
        # Since seed_db fixture runs the script, the file should be at
        # PROJECT_ROOT/data/adversarial_note_ids.txt
        assert adversarial_path.exists()
        ids = [
            line.strip()
            for line in adversarial_path.read_text().splitlines()
            if line.strip()
        ]
        assert len(ids) >= 15

    def test_seed_procedure_codes(self, seed_db: Path) -> None:
        """Exactly 12 procedure codes in coverage_rules."""
        conn = sqlite3.connect(str(seed_db))
        codes = conn.execute(
            "SELECT DISTINCT procedure_code FROM coverage_rules ORDER BY procedure_code"
        ).fetchall()
        conn.close()
        assert len(codes) == 12
        assert codes[0][0] == "PX0001"
        assert codes[-1][0] == "PX0012"


class TestFixtureDb:
    """Tests for the fixture database."""

    def test_fixture_creates_db(self, fixture_db: Path) -> None:
        assert fixture_db.exists()

    def test_fixture_row_counts(self, fixture_db: Path) -> None:
        conn = sqlite3.connect(str(fixture_db))
        assert conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM members").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM coverage_rules").fetchone()[0] == 6
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 8
        assert conn.execute("SELECT COUNT(*) FROM claim_notes").fetchone()[0] == 4
        conn.close()

    def test_fixture_integrity(self, fixture_db: Path) -> None:
        conn = sqlite3.connect(str(fixture_db))
        conn.execute("PRAGMA foreign_keys = ON")
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        assert result == "ok"
        conn.close()

    def test_fixture_has_adversarial_note(self, fixture_db: Path) -> None:
        conn = sqlite3.connect(str(fixture_db))
        note = conn.execute(
            "SELECT note_text FROM claim_notes WHERE note_id = 4"
        ).fetchone()
        conn.close()
        assert note is not None
        assert "IGNORE PREVIOUS INSTRUCTIONS" in note[0]
