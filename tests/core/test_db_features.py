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

def test_mysql_url_special_characters():
    # Verify that URLs with special characters in the password are correctly sanitized and encoded
    from app.db.manager import sanitize_db_url
    
    # 1. URL with '@' in the password
    url1 = "mysql://db_user:my@password@rds-instance.amazonaws.com:3306/db_name"
    sanitized1 = sanitize_db_url(url1)
    assert sanitized1 == "mysql+pymysql://db_user:my%40password@rds-instance.amazonaws.com:3306/db_name"
    
    # 2. URL with ':' and '@' in the password
    url2 = "mysql+pymysql://db_user:my:pass@word@rds-instance.amazonaws.com/db_name"
    sanitized2 = sanitize_db_url(url2)
    assert sanitized2 == "mysql+pymysql://db_user:my%3Apass%40word@rds-instance.amazonaws.com/db_name"
    
    # 3. URL already encoded
    url3 = "mysql://db_user:my%40password@rds-instance.amazonaws.com:3306/db_name"
    sanitized3 = sanitize_db_url(url3)
    assert sanitized3 == "mysql+pymysql://db_user:my%40password@rds-instance.amazonaws.com:3306/db_name"

def test_load_dotenv_relative_path(tmp_path):
    import os
    from app.core.config import load_dotenv
    
    # Define an environment variable key that is not set
    env_key = "TEST_TEMPORARY_ENV_VAR_X"
    if env_key in os.environ:
        del os.environ[env_key]
        
    # Find project root
    import app.core.config as config_mod
    root_dir = os.path.abspath(os.path.join(os.path.dirname(config_mod.__file__), "..", "..", ".."))
    
    # Create a temporary file at the project root
    temp_env_path = os.path.join(root_dir, "temp_test_dotenv.env")
    with open(temp_env_path, "w") as f:
        f.write(f"{env_key}=loaded_value_successfully\n")
        
    # Change working directory to a completely different path (tmp_path)
    old_cwd = os.getcwd()
    os.chdir(str(tmp_path))
    
    try:
        # Load using a relative path, from a different working directory
        load_dotenv("temp_test_dotenv.env")
        
        # Verify it was loaded successfully by finding it at the project root
        assert os.environ.get(env_key) == "loaded_value_successfully"
    finally:
        os.chdir(old_cwd)
        if os.path.exists(temp_env_path):
            os.remove(temp_env_path)
        if env_key in os.environ:
            del os.environ[env_key]
