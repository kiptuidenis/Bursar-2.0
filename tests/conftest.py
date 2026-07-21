"""
conftest.py — Shared pytest fixtures and session-scoped test database initialization.

Ensures the shared integration test SQLite database is deleted and re-created fresh
before any test runs, preventing both "no such table" errors (CI fresh environments)
and "database disk image is malformed" errors (corrupt leftover DB files from prior runs).
"""
import os
import pytest
from app.db.manager import DatabaseManager

# Shared test DB file — must match the value used in test_main.py and test_budget_deposit_validation.py
SHARED_TEST_DB = "test_api_multitenant.db"


@pytest.fixture(scope="session", autouse=True)
def initialize_shared_test_db():
    """
    Session-scoped fixture that runs once before any test.
    Deletes any corrupt or stale test DB file, then creates a clean schema.
    """
    # Remove any existing (potentially corrupt) DB file before re-initializing
    for db_file in (SHARED_TEST_DB, SHARED_TEST_DB + "-shm", SHARED_TEST_DB + "-wal"):
        try:
            if os.path.exists(db_file):
                os.remove(db_file)
        except OSError:
            pass

    # Create fresh schema
    db = DatabaseManager(SHARED_TEST_DB)
    db.initialize()
    db.close()

    yield

    # Clean up after the full test session completes
    for db_file in (SHARED_TEST_DB, SHARED_TEST_DB + "-shm", SHARED_TEST_DB + "-wal"):
        try:
            if os.path.exists(db_file):
                os.remove(db_file)
        except OSError:
            pass
