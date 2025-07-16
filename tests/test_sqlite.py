# test_sqlite.py
import unittest
import sqlite3
import os

# Assuming your database file is in 'instance/'
DB_PATH = 'instance/peoples_coin.db'

class TestSQLiteConnection(unittest.TestCase):
    def setUp(self):
        # Ensure a clean database for each test
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        self.conn = sqlite3.connect(DB_PATH)
        self.cursor = self.conn.cursor()

    def tearDown(self):
        self.conn.close()
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)

    def test_connection(self):
        self.assertIsNotNone(self.conn, "Failed to connect to SQLite database.")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY, name TEXT)")
        self.conn.commit()
        self.cursor.execute("INSERT INTO test (name) VALUES (?)", ("test_entry",))
        self.conn.commit()
        self.cursor.execute("SELECT name FROM test WHERE id=1")
        result = self.cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "test_entry")

if __name__ == '__main__':
    unittest.main()

