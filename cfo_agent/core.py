import os
import json
import logging
from typing import Dict, Any, Optional, List, Union
from google.cloud import secretmanager
from google.cloud import storage
from datetime import datetime

# Configure logging
logger = logging.getLogger("cfo-agent-core")

class CloudEnvironment:
    """Handles cloud-specific functionality for the CFO Agent."""
    
    def __init__(self):
        self.project_id = os.environ.get('PROJECT_ID', 'ledger-457022')
        self.environment = os.environ.get('ENVIRONMENT', 'production')
        self.secrets_cache = {}
        
    def get_secret(self, secret_name: str) -> str:
        """
        Retrieves a secret from Google Secret Manager.
        Caches the secret to avoid repeated API calls.
        
        Args:
            secret_name: Name of the secret to retrieve
            
        Returns:
            The secret value as a string
        """
        # Return from cache if available
        if secret_name in self.secrets_cache:
            return self.secrets_cache[secret_name]
            
        try:
            # Initialize the Secret Manager client
            client = secretmanager.SecretManagerServiceClient()
            
            # Build the resource name of the secret version
            name = f"projects/{self.project_id}/secrets/{secret_name}/versions/latest"
            
            # Access the secret version
            response = client.access_secret_version(request={"name": name})
            
            # Parse the secret payload
            secret_value = response.payload.data.decode("UTF-8")
            
            # Cache the result
            self.secrets_cache[secret_name] = secret_value
            
            return secret_value
            
        except Exception as e:
            logger.error(f"Error retrieving secret {secret_name}: {str(e)}")
            # Return empty string on error to avoid breaking consumers
            return ""

    def store_data_to_gcs(self, 
                         bucket_name: str, 
                         object_name: str, 
                         data: Union[Dict, List, str]) -> bool:
        """
        Stores data to Google Cloud Storage.
        
        Args:
            bucket_name: Name of the GCS bucket
            object_name: Name of the object to store
            data: Data to store (dict, list, or string)
            
        Returns:
            True if storage was successful, False otherwise
        """
        try:
            # Initialize the storage client
            storage_client = storage.Client(project=self.project_id)
            
            # Get the bucket
            bucket = storage_client.bucket(bucket_name)
            
            # Create a new blob
            blob = bucket.blob(object_name)
            
            # Prepare the data for storage
            if isinstance(data, (dict, list)):
                content = json.dumps(data, indent=2)
                content_type = 'application/json'
            else:
                content = str(data)
                content_type = 'text/plain'
            
            # Upload the data
            blob.upload_from_string(content, content_type=content_type)
            
            logger.info(f"Successfully stored data to gs://{bucket_name}/{object_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing data to GCS: {str(e)}")
            return False

    def retrieve_data_from_gcs(self, 
                              bucket_name: str, 
                              object_name: str,
                              as_json: bool = True) -> Optional[Union[Dict, List, str]]:
        """
        Retrieves data from Google Cloud Storage.
        
        Args:
            bucket_name: Name of the GCS bucket
            object_name: Name of the object to retrieve
            as_json: Whether to parse the data as JSON
            
        Returns:
            The retrieved data, or None if retrieval failed
        """
        try:
            # Initialize the storage client
            storage_client = storage.Client(project=self.project_id)
            
            # Get the bucket
            bucket = storage_client.bucket(bucket_name)
            
            # Get the blob
            blob = bucket.blob(object_name)
            
            # Download the data
            content = blob.download_as_string()
            
            # Parse as JSON if requested
            if as_json:
                return json.loads(content)
            else:
                return content.decode('utf-8')
                
        except Exception as e:
            logger.error(f"Error retrieving data from GCS: {str(e)}")
            return None

def get_environment_variables() -> Dict[str, str]:
    """
    Retrieves all environment variables relevant to the CFO Agent.
    
    Returns:
        Dictionary of environment variables
    """
    relevant_vars = {
        'PROJECT_ID': os.environ.get('PROJECT_ID', 'ledger-457022'),
        'ENVIRONMENT': os.environ.get('ENVIRONMENT', 'production'),
        'PORT': os.environ.get('PORT', '8080'),
        'CONFIG_DOC_PATH': os.environ.get('CONFIG_DOC_PATH', ''),
        # Add more relevant environment variables here
    }
    
    # Add any QUICKBOOKS_ prefixed environment variables
    for key, value in os.environ.items():
        if key.startswith('QUICKBOOKS_') or key.startswith('EMAIL_'):
            relevant_vars[key] = value
    
    return relevant_vars

def get_timestamp() -> str:
    """Returns the current timestamp in ISO format."""
    return datetime.utcnow().isoformat() 