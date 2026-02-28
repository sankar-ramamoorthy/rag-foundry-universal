# tests/test_migrations.py
import subprocess

def test_alembic_upgrade_applies_cleanly():
    """Verify Alembic migrations run on a fresh DB."""
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, result.stderr
