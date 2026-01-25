# test_turso.py
import asyncio
import os
import libsql

def main():
    # Use a local file path (will be created if it doesn't exist)
    local_db_path = "intraq_test.db"  # Local file for embedded replica (created automatically)

    # Your Turso credentials
    turso_url = "libsql://intraq-dataops-kinyodan.aws-eu-west-1.turso.io"
    turso_token = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NjkwMDY1MzMsImlkIjoiZmI4NTUxYTctNDQ2Yy00Mzk0LTg2ZTYtOGQyNjZmOWIzZDAwIiwicmlkIjoiMTBmNGM3OTgtM2U0Mi00OGJmLThjNDktZmIzODZlZjI2NTkwIn0.ewIx1HVaW_gvI45d3sG3jdb5XWDkQx5LbHv3rsS7F63a54uOqqav-ypQtMD7OhGuPYZhbXOnVFLirdIy9fWxCA"  # from ~/.turso/tursodb db tokens create ...

    conn = libsql.connect(
        local_db_path,
        sync_url=turso_url,
        auth_token=turso_token
    )

    # Sync local replica with remote Turso (important!)
    conn.sync()  # Pulls schema/data; call on startup or periodically

    # Test query (sync, no await)
    cursor = conn.execute("SELECT sqlite_version();")
    version = cursor.fetchone()[0]
    print(f"SQLite version via Turso: {version}")

    # More tests
    conn.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO test (name) VALUES (?)", ("Daniel from Nairobi",))
    cursor = conn.execute("SELECT * FROM test")
    rows = cursor.fetchall()
    print("Rows in test table:", rows)

    conn.commit()  # Commit changes to local DB
    conn.sync()    # Push changes back to remote Turso

    conn.close()

if __name__ == "__main__":
    main()