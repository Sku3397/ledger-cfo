import os
import sys
from datetime import datetime
from mock_quickbooks_api import MockQuickBooksAPI

# Print current environment settings
print("\n=== CURRENT ENVIRONMENT STATUS ===\n")
print(f"Current demo_mode setting in .env: {os.getenv('DEMO_MODE', 'Not set')}")
print(f"Current OS environment demo_mode: {os.environ.get('DEMO_MODE', 'Not set')}")

# Force disable demo mode
os.environ["DEMO_MODE"] = "false"
print("\nForced DEMO_MODE to 'false' in environment")

# Check if we're loading the real QuickBooks API
from config import config
from quickbooks_api import QuickBooksAPI
import importlib
importlib.reload(config)  # Reload config to pick up the new environment variable

# Check demo mode status
print(f"\nConfig demo_mode: {config.demo_mode}")

# Create a new instance of the accounting engine with a specific QuickBooks API
print("\n=== TESTING API INITIALIZATION ===\n")

def test_api_initialization():
    """Test API initialization to see which implementation is being used."""
    try:
        # Initialize the API directly
        qb_api = QuickBooksAPI()
        
        # Check if this is a mock or real instance
        is_mock = isinstance(qb_api, MockQuickBooksAPI)
        
        print(f"API Instance Type: {'MockQuickBooksAPI' if is_mock else 'Real QuickBooksAPI'}")
        print(f"API Environment: {qb_api.environment}")
        print(f"API Base URL: {qb_api.base_url}")
        
        if is_mock:
            print("\n⚠️ STILL USING MOCK API despite demo_mode=false!")
            print("The issue is in the quickbooks_api.py implementation.")
        else:
            print("\n✓ Successfully initialized REAL QuickBooks API")
    except Exception as e:
        print(f"Error initializing API: {str(e)}")

test_api_initialization()

# Look for any substitution in quickbooks_api.py that might be causing this
print("\n=== CHECKING QUICKBOOKS_API IMPLEMENTATION ===\n")

# Print the first few lines of QuickBooksAPI.__init__ method
import inspect
qb_init = inspect.getsource(QuickBooksAPI.__init__)
print("QuickBooksAPI.__init__ method:")
for i, line in enumerate(qb_init.split('\n')):
    if i < 15:  # Print first 15 lines
        print(f"{i+1}: {line}")

print("\nMost likely issue: The system is still using the mock API instead of the real one.")
print("To fix this, we need to modify the accounting_engine.py file to explicitly use the real API.") 