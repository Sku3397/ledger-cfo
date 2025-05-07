import os
import logging
from google.cloud import secretmanager
from google.api_core.exceptions import NotFound, PermissionDenied
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# Use root logger configured elsewhere if available, otherwise basicConfig
logger = logging.getLogger(__name__) # Use specific logger if preferred

# Initialize the Secret Manager client (can be done globally or within the function)
# Ensure PROJECT_ID is available (e.g., from env var or hardcoded if necessary, though env var is better)
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", None) # Or load from .env if preferred for local
secret_manager_client = None
if GCP_PROJECT_ID:
    try:
        # --- BEGIN NEW DIAGNOSTIC CODE ---
        print(f"DEBUG: Attempting Secret Manager client init for project {GCP_PROJECT_ID}")
        # Check common ADC environment variables right before client init
        adc_env_var = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        gcloud_config_dir = os.environ.get("CLOUDSDK_CONFIG")
        print(f"DEBUG: GOOGLE_APPLICATION_CREDENTIALS env var: {adc_env_var}")
        print(f"DEBUG: CLOUDSDK_CONFIG env var: {gcloud_config_dir}")
        # You could even try importing google.auth here to see if IT fails first
        try:
            import google.auth
            creds, project = google.auth.default()
            print(f"DEBUG: google.auth.default() found credentials for project: {project}")
            if hasattr(creds, 'service_account_email'):
                 print(f"DEBUG: Credentials type: Service Account ({creds.service_account_email})")
            elif hasattr(creds, 'quota_project_id'): # User credentials often have this
                 print(f"DEBUG: Credentials type: User (ADC)")
            else:
                 print(f"DEBUG: Credentials type: Unknown")

        except Exception as auth_ex:
            print(f"!!! DEBUG: google.auth.default() FAILED: {type(auth_ex).__name__}: {auth_ex}")
        # --- END NEW DIAGNOSTIC CODE ---

        print(f"Attempting to initialize SecretManagerServiceClient...")
        secret_manager_client = secretmanager.SecretManagerServiceClient() # The actual call
        logging.info("Secret Manager client initialized successfully.")
        print("Secret Manager client initialized successfully.")

    except Exception as e:
        logging.error(f"!!! FAILED to initialize Secret Manager client: {type(e).__name__}: {e}", exc_info=True)
        print(f"!!! FAILED to initialize Secret Manager client: {type(e).__name__}: {e}")
        secret_manager_client = None
else:
    # Use standard logging level for warning
    logging.warning("GCP_PROJECT_ID environment variable not set. Cannot initialize Secret Manager client.")


# --- Environment Variable Management ---
# Consider centralizing env var loading if not already done

def get_env_variable(var_name: str, default: str | None = None) -> str | None:
    """
    Retrieves an environment variable. Logs a warning if not found and no default is provided.
    """
    value = os.environ.get(var_name)
    if value is None:
        if default is not None:
            # logging.debug(f"Environment variable {var_name} not found, using default.")
            return default
        else:
            # Log potentially sensitive info like missing keys only at DEBUG or specific conditions
            # logging.warning(f"Environment variable {var_name} not found and no default specified.")
            pass # Keep logs cleaner, handle missing vars where needed
    return value

def get_qbo_config() -> dict:
    """Loads QBO configuration safely from environment variables."""
    return {
        "client_id": get_secret("ledger-cfo-qbo-client-id"),
        "client_secret": get_secret("ledger-cfo-qbo-client-secret"),
        "environment": get_env_variable("QBO_ENVIRONMENT", "sandbox"),
        "redirect_uri": get_env_variable("QBO_REDIRECT_URI"),
        "refresh_token": get_secret("ledger-cfo-qbo-refresh-token"),
        "realm_id": get_secret("ledger-cfo-qbo-realm-id"),
    }

def get_secret(internal_key: str, project_id: str | None = None) -> str | None:
    """
    Retrieves a secret value from Google Cloud Secret Manager.

    Args:
        internal_key: The Secret ID in Secret Manager (e.g., 'qbo-client-id', 'DB_USER').
        project_id: The GCP Project ID. Uses GCP_PROJECT_ID env var if not provided.

    Returns:
        The secret value as a string, or None if not found or on error.
    """
    if not secret_manager_client:
        logging.error("Secret Manager client is not available (check GCP_PROJECT_ID and initialization logs). Cannot fetch secret.")
        # Raising an error might be better here to prevent silent failures downstream
        # raise RuntimeError("Secret Manager client not initialized.")
        return None # Returning None for now as per original example design

    target_project_id = project_id or GCP_PROJECT_ID
    if not target_project_id:
        logging.error("GCP Project ID is not configured. Cannot fetch secret.")
        # raise ValueError("GCP Project ID is required but not configured.")
        return None

    secret_id = internal_key # Assuming internal_key directly maps to Secret ID in GSM
    secret_version = "latest" # Always fetch the latest version
    secret_name = f"projects/{target_project_id}/secrets/{secret_id}/versions/{secret_version}"

    try:
        # Use standard logging level
        logging.info(f"Attempting to access secret version: {secret_name}")
        response = secret_manager_client.access_secret_version(name=secret_name)
        payload = response.payload.data.decode("UTF-8")
        logging.info(f"Successfully retrieved secret for key: {internal_key} (ID: {secret_id})")
        return payload
    except NotFound:
        logging.error(f"Secret ID '{secret_id}' (version '{secret_version}') not found in project '{target_project_id}'.")
        return None
    except PermissionDenied:
        # Log less detail here, more in debug if needed, avoid leaking structure info
        logging.error(f"Permission denied accessing secret ID '{secret_id}' in project '{target_project_id}'. Ensure the running identity has the 'Secret Manager Secret Accessor' role.")
        return None
    except Exception as e:
        # Catch broader exceptions but log specifics
        logging.error(f"An unexpected error occurred trying to access secret ID '{secret_id}' in project '{target_project_id}': {e}", exc_info=True)
        return None

# Example usage (optional, for direct testing of this module)
# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO)
#     if not GCP_PROJECT_ID:
#         print("Please set the GCP_PROJECT_ID environment variable.")
#     else:
#         print(f"Testing with Project ID: {GCP_PROJECT_ID}")
#         test_secret_id = "your-test-secret-id" # Replace with a real secret ID for testing
#         secret_value = get_secret(test_secret_id)
#         if secret_value:
#             print(f"Secret '{test_secret_id}' value: [REDACTED]") # Avoid printing secrets
#         else:
#             print(f"Could not retrieve secret '{test_secret_id}'. Check logs and Secret Manager configuration.")

# Optional: Add functions to get other specific configs if needed
# def get_database_config(): ...
# def get_gmail_config(): ...

# Define expected Secret Manager secret IDs (Keep mapping for reference)
# THIS MAPPING IS NOW DEPRECATED as secret IDs are used directly in the code.
# Consider removing this or updating it just for documentation.
# SECRET_MAPPING = {
#     # QBO Secrets
#     "qbo_client_id": "ledger-cfo-qbo-client-id",
#     "qbo_client_secret": "ledger-cfo-qbo-client-secret",
#     "qbo_refresh_token": "ledger-cfo-qbo-refresh-token",
#     "qbo_realm_id": "ledger-cfo-qbo-realm-id",
#     "qbo_environment": "ledger-cfo-qbo-environment", # Example: 'sandbox' or 'production'
#
#     # Gmail Secrets
#     "gmail_client_secrets_json": "ledger-cfo-gmail-client-secrets", # Contains the JSON content
#     "gmail_refresh_token": "ledger-cfo-gmail-refresh-token",
#
#     # App Config Secrets
#     "allowed_sender_email": "ledger-cfo-allowed-sender",
#     "sender_email": "ledger-cfo-sender-email", # Email agent sends FROM
#
#     # Database Secrets (Required by init_db_engine)
#     "db_user": "ledger-cfo-db-user",
#     "db_pass": "ledger-cfo-db-password",
#     "db_name": "ledger-cfo-db-name",
#     "db_instance_connection_name": "ledger-cfo-db-instance-conn", # Pass this via secret
#
#     # LLM Secrets
#     "anthropic_api_key": "ledger-cfo-anthropic-api-key",
#     "openai_api_key": "ledger-cfo-openai-api-key" # Assuming OpenAI key is also needed
# }

# Example of how other modules will use this (DO NOT uncomment/run here)
# qbo_client_id = get_secret("ledger-cfo-qbo-client-id")
# anthropic_key = get_secret("ledger-cfo-anthropic-api-key")
# db_user = get_secret("ledger-cfo-db-user") 