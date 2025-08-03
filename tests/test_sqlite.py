import sqlite3
import os
import tempfile

# Get a temporary file path for the database
temp_db_path = os.path.join(tempfile.gettempdir(), 'direct_test_db.sqlite')

print(f"Attempting to create database at: {temp_db_path}")

conn = None # Initialize conn to None
try:
    # Connect to the database (creates it if it doesn't exist)
    conn = sqlite3.connect(temp_db_path)
    cursor = conn.cursor()

    # Create a simple table
    cursor.execute("CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()

    print(f"Successfully created database and table at {temp_db_path}")
    print("You can check if the file exists now.")

except sqlite3.OperationalError as e:
    print(f"ERROR: sqlite3.OperationalError: {e}")
    print("This means the database file could not be created or opened.")
    print("Possible causes: permissions, file lock, antivirus/security software.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
finally:
    if conn:
        conn.close()
        print("Database connection closed.")
        # Optional: Try to delete the file after testing
        try:
            os.remove(temp_db_path)
            print(f"Successfully removed temporary database: {temp_db_path}")
        except OSError as e:
            print(f"Could not remove temporary database: {e}")
            print(f"Please manually check and delete: {temp_db_path}")
