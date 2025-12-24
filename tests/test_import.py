# /Users/donfeeney/peoples_coin/test_import.py
import sys
from pathlib import Path

# Ensure the project root is at the beginning of sys.path for running from outside
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    # Attempt to import the main run.py from the inner peoples_coin package
    from peoples_coin import run
    print("Successfully imported peoples_coin.peoples_coin.run!")
except ImportError as e:
    print(f"ImportError encountered: {e}")
    print("Please ensure your PYTHONPATH is not interfering and module caches are clear.")
    print("\nSys path:")
    for p in sys.path:
        print(p)
except Exception as e:
    print(f"An unexpected error occurred: {e}")
