import sqlite3
from datetime import datetime

def insert_test_data():
    conn = sqlite3.connect('instance/peoples_coin.db')
    cursor = conn.cursor()

    test_entries = [
        "Hello AILEE 🚀",
    ] + [f"Test entry #{i}" for i in range(1, 11)]

    for entry in test_entries:
        cursor.execute("""
            INSERT INTO data_entries (value, processed, created_at, updated_at)
            VALUES (?, 0, ?, ?)
        """, (entry, datetime.now(), datetime.now()))

    conn.commit()
    conn.close()
    print("✅ Inserted test entries with processed=0!")

if __name__ == "__main__":
    insert_test_data()

