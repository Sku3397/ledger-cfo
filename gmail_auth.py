import os
import pickle
import random
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from typing import Optional
from logger import cfo_logger

class GmailAuthenticator:
    """
    Handles Gmail API authentication using OAuth 2.0
    """
    
    def __init__(self, credentials_file: str, token_file: str):
        """
        Initialize the Gmail authenticator.
        
        Args:
            credentials_file (str): Path to the credentials JSON file from Google Cloud Console
            token_file (str): Path where the authentication token will be stored
        """
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.SCOPES = [
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.modify',
            'https://www.googleapis.com/auth/gmail.labels',
            'https://www.googleapis.com/auth/gmail.send'
        ]
    
    def authenticate(self) -> Credentials:
        """
        Authenticate with Gmail API using OAuth 2.0.
        
        Returns:
            Credentials: The OAuth 2.0 credentials
        """
        creds = None
        
        # Try to load existing credentials
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, 'rb') as token:
                    creds = pickle.load(token)
            except Exception as e:
                cfo_logger.error(f"Error loading credentials from token file: {str(e)}")
                creds = None
        
        # If no valid credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    cfo_logger.error(f"Token refresh failed: {str(e)}")
                    # Token refresh failed, need to re-authenticate
                    creds = self._create_new_credentials()
            else:
                creds = self._create_new_credentials()
            
            # Save the credentials for future use
            try:
                with open(self.token_file, 'wb') as token:
                    pickle.dump(creds, token)
                cfo_logger.info("Saved new credentials to token file")
            except Exception as e:
                cfo_logger.error(f"Error saving credentials to token file: {str(e)}")
        
        return creds
    
    def _create_new_credentials(self) -> Credentials:
        """
        Create new credentials through user authentication flow.
        Tries multiple ports if the default port is in use.
        
        Returns:
            Credentials: The new OAuth 2.0 credentials
        """
        # Try a few different ports if the default is in use
        ports = [8080, 8090, 8888, 9000, 9090] + [random.randint(8000, 9999) for _ in range(3)]
        
        for port in ports:
            try:
                cfo_logger.info(f"Attempting OAuth flow on port {port}")
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file,
                    self.SCOPES
                )
                creds = flow.run_local_server(port=port)
                cfo_logger.info(f"Successfully authenticated with Gmail API on port {port}")
                return creds
            except OSError as e:
                if "Only one usage of each socket address" in str(e):
                    cfo_logger.warning(f"Port {port} is in use, trying another port")
                    continue
                else:
                    cfo_logger.error(f"Unexpected error during OAuth flow: {str(e)}")
                    raise
            except Exception as e:
                cfo_logger.error(f"Failed to authenticate with Gmail API: {str(e)}")
                raise
        
        # If we've tried all ports and none worked
        raise RuntimeError("Failed to find an available port for OAuth authentication")
    
    def revoke_credentials(self) -> None:
        """
        Revoke the current credentials by deleting the token file.
        """
        if os.path.exists(self.token_file):
            try:
                os.remove(self.token_file)
                cfo_logger.info("Removed token file to force reauthentication")
            except Exception as e:
                cfo_logger.error(f"Error removing token file: {str(e)}")

    def build_service(self, creds: Credentials) -> Optional[object]:
        """
        Build the Gmail API service using the provided credentials.
        
        Args:
            creds (Credentials): The OAuth 2.0 credentials
        
        Returns:
            Optional[object]: Gmail API service object if authentication successful, None otherwise
        """
        try:
            # Build the Gmail API service
            service = build('gmail', 'v1', credentials=creds)
            
            # Verify the connection by making a simple API call
            profile = service.users().getProfile(userId='me').execute()
            cfo_logger.info(f"Gmail API connection validated successfully for {profile.get('emailAddress', 'unknown')}")
            
            return service
        except Exception as e:
            cfo_logger.error(f"Error building Gmail service: {str(e)}")
            return None 