# test_import.py
import unittest

# Assuming your main app is in 'run.py' and imports other modules
# You might need to adjust this import based on your actual app's structure
# from your_app_name import db, systems # Example if you define a main package

class TestImports(unittest.TestCase):
    def test_can_import_modules(self):
        # Basic test to ensure modules can be imported without errors
        try:
            import db.models
            import systems.nervous_system
            # Add other critical imports here
        except ImportError as e:
            self.fail(f"Could not import a module: {e}")

if __name__ == '__main__':
    unittest.main()
