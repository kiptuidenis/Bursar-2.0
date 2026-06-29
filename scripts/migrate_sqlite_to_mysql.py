"""
Data Migration Script: SQLite to Amazon RDS MySQL
Usage:
    python scripts/migrate_sqlite_to_mysql.py --sqlite-path bursar.db --mysql-url "mysql+pymysql://bursar_admin:password@rds-endpoint:3306/bursardb"
"""

import argparse
import sqlite3
import pymysql
import os
import sys
import traceback
from urllib.parse import urlparse

def parse_mysql_url(url: str):
    if url.startswith("mysql+pymysql://"):
        url = url.replace("mysql+pymysql://", "mysql://")
    parsed = urlparse(url)
    return {
        'host': parsed.hostname,
        'port': parsed.port or 3306,
        'user': parsed.username,
        'password': parsed.password,
        'database': parsed.path.lstrip('/')
    }

MYSQL_SCHEMA_QUERIES = [
    "SET FOREIGN_KEY_CHECKS = 0;",
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        phone_number VARCHAR(191) UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        first_name VARCHAR(255) DEFAULT '',
        last_name VARCHAR(255) DEFAULT '',
        email VARCHAR(255) DEFAULT '',
        avatar_url TEXT,
        bio TEXT,
        theme VARCHAR(50) DEFAULT 'dark',
        notifications_enabled INT DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        user_id INT PRIMARY KEY,
        balance DOUBLE DEFAULT 0.0,
        daily_budget DOUBLE DEFAULT 0.0,
        phone_number VARCHAR(255) DEFAULT '',
        payout_time VARCHAR(50) DEFAULT '08:00',
        mode VARCHAR(50) DEFAULT 'sandbox',
        mpesa_consumer_key TEXT,
        mpesa_consumer_secret TEXT,
        mpesa_shortcode VARCHAR(100) DEFAULT '',
        mpesa_initiator_name VARCHAR(100) DEFAULT '',
        mpesa_initiator_password TEXT,
        mpesa_b2c_result_url TEXT,
        mpesa_b2c_timeout_url TEXT,
        budget_locked_until VARCHAR(100) DEFAULT '',
        deposit_locked_until VARCHAR(100) DEFAULT '',
        start_date VARCHAR(100) DEFAULT '',
        end_date VARCHAR(100) DEFAULT '',
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS payouts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        payout_date VARCHAR(50) NOT NULL,
        amount DOUBLE NOT NULL,
        phone_number VARCHAR(100) NOT NULL,
        status VARCHAR(50) NOT NULL,
        conversation_id VARCHAR(255) DEFAULT '',
        originator_conversation_id VARCHAR(255) DEFAULT '',
        transaction_id VARCHAR(255) DEFAULT '',
        error_message TEXT,
        completed_at VARCHAR(100) DEFAULT '',
        failed_at VARCHAR(100) DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE KEY uq_user_payout (user_id, payout_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS logs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        level VARCHAR(50) NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS budget_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        category VARCHAR(191) NOT NULL,
        amount DOUBLE NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE KEY uq_user_category (user_id, category)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS deposits (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        checkout_request_id VARCHAR(191) UNIQUE NOT NULL,
        amount DOUBLE NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
        mpesa_receipt VARCHAR(255) DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        session_token VARCHAR(191) UNIQUE NOT NULL,
        user_agent TEXT,
        ip_address VARCHAR(100) DEFAULT '',
        expires_at BIGINT NOT NULL,
        last_activity BIGINT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    "SET FOREIGN_KEY_CHECKS = 1;"
]

def migrate(sqlite_path: str, mysql_url: str):
    if not os.path.exists(sqlite_path):
        # Try finding in src directory or current directory
        candidates = [sqlite_path, os.path.join("src", sqlite_path), os.path.join("src", "app", sqlite_path)]
        found = False
        for c in candidates:
            if os.path.exists(c):
                sqlite_path = c
                found = True
                break
        if not found:
            print(f"[ERROR] SQLite database file not found at '{sqlite_path}'. Please check path.")
            return

    print(f"[*] Connecting to SQLite database at: {sqlite_path}")
    try:
        sq_conn = sqlite3.connect(sqlite_path)
        sq_conn.row_factory = sqlite3.Row
        sq_cursor = sq_conn.cursor()
    except Exception as e:
        print(f"[ERROR] Failed to open SQLite database: {e}")
        traceback.print_exc()
        return

    config = parse_mysql_url(mysql_url)
    print(f"[*] Connecting to Amazon RDS MySQL database at: {config['host']}:{config['port']}/{config['database']}")
    
    try:
        my_conn = pymysql.connect(
            host=config['host'],
            port=config['port'],
            user=config['user'],
            password=config['password'],
            database=config['database'],
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False
        )
        my_cursor = my_conn.cursor()
    except Exception as e:
        print(f"[ERROR] Failed to connect to MySQL on RDS: {e}")
        traceback.print_exc()
        return

    print("[*] Initializing schema tables on Amazon RDS MySQL...")
    try:
        for q in MYSQL_SCHEMA_QUERIES:
            my_cursor.execute(q)
        my_conn.commit()
        print("[+] MySQL schema initialized successfully.")
    except Exception as e:
        print(f"[ERROR] Failed initializing MySQL tables: {e}")
        traceback.print_exc()
        my_conn.rollback()

    tables = ['users', 'settings', 'payouts', 'logs', 'budget_items', 'deposits', 'sessions']

    for table in tables:
        try:
            print(f"[*] Extracting table from SQLite: {table}...")
            sq_cursor.execute(f"SELECT * FROM {table}")
            rows = sq_cursor.fetchall()
            if not rows:
                print(f"[!] No rows found in SQLite table '{table}'.")
                continue

            columns = list(rows[0].keys())
            cols_str = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            sql = f"REPLACE INTO {table} ({cols_str}) VALUES ({placeholders})"

            data_to_insert = [tuple(row[col] for col in columns) for row in rows]
            
            my_cursor.executemany(sql, data_to_insert)
            my_conn.commit()
            print(f"[+] Successfully migrated {len(data_to_insert)} records to MySQL table '{table}'.")
        except Exception as e:
            print(f"[WARNING] Could not migrate table '{table}': {e}")
            traceback.print_exc()
            my_conn.rollback()

    sq_conn.close()
    my_conn.close()
    print("\n[SUCCESS] Migration workflow complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Bursar SQLite database to Amazon RDS MySQL.")
    parser.add_argument("--sqlite-path", default="bursar.db", help="Path to SQLite db file")
    parser.add_argument("--mysql-url", required=True, help="MySQL connection string")
    args = parser.parse_args()

    migrate(args.sqlite_path, args.mysql_url)
