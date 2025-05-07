import pytest
import os
import logging
from google.cloud import secretmanager
from dotenv import load_dotenv, find_dotenv

# --- Explicit .env Loading ---
# Construct absolute path to .env in project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
dotenv_path = os.path.join(project_root, '.env')
print(f"DEBUG: Explicitly loading .env from: {dotenv_path}")
loaded = load_dotenv(dotenv_path=dotenv_path, override=True)
if not loaded:
    print(f"WARNING: .env file not found at {dotenv_path}")
else:
    print(".env file loaded successfully.")
# --- End Explicit Loading ---

logger = logging.getLogger(__name__)

def test_gsm_client_initialization():
    """
    Tests ONLY the initialization of the Secret Manager client.
    """
    print("--- Starting Secret Manager Client Init Test ---")
    gcp_project_id = os.environ.get("GCP_PROJECT_ID", None)
    print(f"GCP_PROJECT_ID found: {gcp_project_id}")
    assert gcp_project_id is not None, "GCP_PROJECT_ID environment variable must be set in .env"

    client = None
    initialization_error = None
    try:
        print("Attempting: client = secretmanager.SecretManagerServiceClient()")
        client = secretmanager.SecretManagerServiceClient()
        print("SUCCESS: SecretManagerServiceClient() initialized.")
        # Optional: Try a simple, non-destructive call if init succeeds
        # try:
        #     print("Attempting: client.list_secrets() call...")
        #     # Requires resourcemanager.projects.get permission usually
        #     response = client.list_secrets(parent=f"projects/{gcp_project_id}")
        #     print(f"SUCCESS: list_secrets call returned (iterator: {response})")
        # except Exception as list_e:
        #     print(f"ERROR during list_secrets call: {type(list_e).__name__}: {list_e}")
        #     # Don't fail the test for list error, just log it
        #     initialization_error = list_e # Record list error if it happens

    except Exception as e:
        print(f"!!! FAILED to initialize SecretManagerServiceClient: {type(e).__name__}: {e}")
        logging.critical(f"SecretManagerServiceClient init failed", exc_info=True)
        initialization_error = e # Store the error

    print("--- Finished Secret Manager Client Init Test --- ")
    # Assert that the client object was created, even if subsequent calls failed
    assert client is not None, f"SecretManagerServiceClient object is None after initialization attempt. Error: {initialization_error}"
    # Optionally, assert that no initialization error occurred if list_secrets wasn't tested or expected to work
    # assert initialization_error is None, f"An error occurred during or after initialization: {initialization_error}" 