# test_connection.py
from db import engine
from sqlalchemy import text  # <-- Add this import

with engine.connect() as conn:

    # cursor = conn.execute("SELECT sqlite_version();")
    # version = cursor.fetchone()[0]
    # print(f"SQLite version via Turso: {version}")
    # DDL: CREATE TABLE (wrapped with text)
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS test (
            id INTEGER PRIMARY KEY,
            name TEXT
        )
    """))

    # DML: INSERT (with parameter binding - safer!)
    conn.execute(
        text("INSERT INTO test (name) VALUES (:name)"),
        {"name": "Daniel from Nairobi"}
    )

    # DML: SELECT
    result = conn.execute(text("SELECT * FROM test"))
    rows = result.fetchall()
    # Print rows (each row is a Row object)
    print("Rows in test table:")
    for row in rows:
        print(row)  # or row._asdict() for dict view

    conn.commit()  # Commit changes to local DB

    conn.close()
