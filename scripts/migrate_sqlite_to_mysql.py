"""
Data Migration Script: SQLite to Amazon RDS MySQL
Usage:
    python scripts/migrate_sqlite_to_mysql.py --sqlite-path bursar.db --mysql-url "mysql+pymysql://bursar_admin:password@rds-endpoint:3306/bursardb"
"""

import argparse
import sqlite3
import pymysql
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

def migrate(sqlite_path: str, mysql_url: str):
    print(f"[*] Connecting to SQLite database at: {sqlite_path}")
    sq_conn = sqlite3.connect(sqlite_path)
    sq_conn.row_factory = sqlite3.Row
    sq_cursor = sq_conn.cursor()

    config = parse_mysql_url(mysql_url)
    print(f"[*] Connecting to Amazon RDS MySQL database at: {config['host']}:{config['port']}/{config['database']}")
    
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

    tables = ['users', 'settings', 'payouts', 'logs', 'budget_items', 'deposits', 'sessions']

    try:
        for table in tables:
            sq_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            if not sq_cursor.fetchone():
                print(f"[-] Table {table} does not exist in SQLite, skipping...")
                continue

            print(f"[*] Migrating table: {table}...")
            sq_cursor.execute(f"SELECT * FROM {table}")
            rows = sq_cursor.fetchall()
            if not rows:
                print(f"[!] No rows in {table}.")
                continue

            columns = rows[0].keys()
            cols_str = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            sql = f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})"

            data_to_insert = [tuple(row[col] for col in columns) for row in rows]
            
            my_cursor.executemany(sql, data_to_insert)
            print(f"[+] Migrated {len(data_to_insert)} records to {table}.")

        my_conn.commit()
        print("\n[SUCCESS] Migration completed successfully!")

    except Exception as e:
        my_conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
    finally:
        sq_conn.close()
        my_conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Bursar SQLite database to Amazon RDS MySQL.")
    parser.add_argument("--sqlite-path", default="bursar.db", help="Path to SQLite db file")
    parser.add_argument("--mysql-url", required=True, help="MySQL connection string")
    args = parser.parse_args()

    migrate(args.sqlite_path, args.mysql_url)
