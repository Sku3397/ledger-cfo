import os
import logging
from google.cloud import secretmanager
from google.api_core.exceptions import GoogleAPICallError, NotFound

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define expected Secret Manager secret IDs
# These should correspond to the names of the secrets created in GCP Secret Manager
# Use the names defined in DEPLOYMENT.md
SECRET_MAPPING = {
    # QBO Secrets
    "QBO_CLIENT_ID": "ledger-cfo-qbo-client-id",
    "QBO_CLIENT_SECRET": "ledger-cfo-qbo-client-secret",
    "QBO_REFRESH_TOKEN": "ledger-cfo-qbo-refresh-token",
    "QBO_REALM_ID": "ledger-cfo-qbo-realm-id",
    "QBO_ENVIRONMENT": "ledger-cfo-qbo-environment", # Example: 'sandbox' or 'production'

    # Gmail Secrets
    "GMAIL_CLIENT_SECRETS_JSON": "ledger-cfo-gmail-client-secrets", # Contains the JSON content
    "GMAIL_REFRESH_TOKEN": "ledger-cfo-gmail-refresh-token",

    # App Config Secrets
    "ALLOWED_SENDER_EMAIL": "ledger-cfo-allowed-sender",
    "SENDER_EMAIL": "ledger-cfo-sender-email", # Email agent sends FROM

    # Database Secrets (Required by init_db_engine)
    "DB_USER": "ledger-cfo-db-user",
    "DB_PASS": "ledger-cfo-db-password",
    "DB_NAME": "ledger-cfo-db-name",
    "DB_INSTANCE_CONNECTION_NAME": "ledger-cfo-db-instance-connection-name", # Pass this via secret

    # LLM Secrets
    "ANTHROPIC_API_KEY": "ledger-cfo-anthropic-api-key",
}

def get_secret(internal_key: str, project_id: str | None = None) -> str | None:
    """
    Retrieves a secret value from Google Cloud Secret Manager using an internal key.

    Args:
        internal_key: The internal key corresponding to the desired secret (e.g., 'QBO_CLIENT_ID').
        project_id: The GCP Project ID. Defaults to the GCP_PROJECT_ID env var or raises error.

    Returns:
        The secret value as a string, or None if an error occurs.
    """
    if project_id is None:
        project_id = os.environ.get("GCP_PROJECT_ID")
        if not project_id:
            logging.error("GCP_PROJECT_ID environment variable not set.")
            raise ValueError("GCP Project ID must be provided either as an argument or via GCP_PROJECT_ID env var.")

    secret_id = SECRET_MAPPING.get(internal_key)
    if not secret_id:
        logging.error(f"Invalid internal secret key provided: {internal_key}")
        raise ValueError(f"Invalid internal secret key: {internal_key}. Available keys: {list(SECRET_MAPPING.keys())}")

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"

    try:
        logging.info(f"Attempting to access secret: {name}")
        response = client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8")
        logging.info(f"Successfully accessed secret: {secret_id}")
        return payload
    except NotFound:
        logging.error(f"Secret not found: {name}. Ensure the secret exists and the service account has permissions.")
        return None
    except GoogleAPICallError as e:
        logging.error(f"Failed to access secret {name}: {e}")
        # Consider more specific error handling based on e.code() if needed
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred while accessing secret {name}: {e}")
        return None

# Example of how other modules will use this (DO NOT uncomment/run here)
# qbo_client_id = get_secret("QBO_CLIENT_ID")
# anthropic_key = get_secret("ANTHROPIC_API_KEY")
# db_user = get_secret("DB_USER") 