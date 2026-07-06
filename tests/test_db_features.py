import os
import pytest
import sqlalchemy
from app.db.manager import DatabaseManager, _engines_cache

def test_mysql_url_translation():
    # Verify that mysql:// is automatically translated to mysql+pymysql://
    db = DatabaseManager("mysql://testuser:testpass@localhost:3306/testdb")
    assert db.db_url == "mysql+pymysql://testuser:testpass@localhost:3306/testdb"

def test_engine_caching():
    # Verify that creating multiple manager instances with the same path uses the same engine
    db_file = "test_cache_db.db"
    
    db1 = DatabaseManager(db_file)
    db2 = DatabaseManager(db_file)
    
    assert db1.engine is db2.engine
    
    # Verify a different path creates a new engine
    db_diff = DatabaseManager("test_cache_db_diff.db")
    assert db_diff.engine is not db1.engine
    
    # Cleanup and dispose of engines
    db1.close()
    db2.close()
    db_diff.close()
    
    if os.path.exists(db_file):
        os.remove(db_file)
    if os.path.exists("test_cache_db_diff.db"):
        os.remove("test_cache_db_diff.db")

def test_sqlite_pragmas():
    # Verify that SQLite connection pragmas are applied correctly under test mode
    db_file = "test_pragmas.db"
    db = DatabaseManager(db_file)
    db.initialize()
    
    # Query current SQLite pragmas via the active session
    journal_mode = db.session.execute(sqlalchemy.text("PRAGMA journal_mode")).scalar()
    synchronous = db.session.execute(sqlalchemy.text("PRAGMA synchronous")).scalar()
    foreign_keys = db.session.execute(sqlalchemy.text("PRAGMA foreign_keys")).scalar()
    
    # Under pytest, it should be memory journal mode and synchronous = OFF (0)
    assert journal_mode.lower() == "memory"
    assert synchronous == 0
    assert foreign_keys == 1
    
    db.close()
    if os.path.exists(db_file):
        os.remove(db_file)
