import os
import pytest
from unittest.mock import MagicMock, patch
from gmail_auth import GmailAuthenticator

@pytest.fixture
def gmail_auth():
    return GmailAuthenticator(
        credentials_file="test_credentials.json",
        token_file="test_token.pickle"
    )

def test_init():
    auth = GmailAuthenticator(
        credentials_file="test_credentials.json",
        token_file="test_token.pickle"
    )
    assert auth.credentials_file == "test_credentials.json"
    assert auth.token_file == "test_token.pickle"
    assert auth.SCOPES == [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.modify',
        'https://www.googleapis.com/auth/gmail.labels'
    ]

@patch('gmail_auth.Credentials')
@patch('gmail_auth.pickle')
@patch('gmail_auth.InstalledAppFlow')
def test_authenticate_new_credentials(mock_flow, mock_pickle, mock_creds, gmail_auth):
    # Mock flow for new credentials
    mock_flow_instance = MagicMock()
    mock_flow.from_client_secrets_file.return_value = mock_flow_instance
    mock_flow_instance.run_local_server.return_value = "new_creds"
    
    # Mock pickle operations
    mock_pickle.load.side_effect = FileNotFoundError
    
    # Test authentication
    result = gmail_auth.authenticate()
    
    assert result == "new_creds"
    mock_flow.from_client_secrets_file.assert_called_once_with(
        gmail_auth.credentials_file,
        gmail_auth.SCOPES
    )
    mock_flow_instance.run_local_server.assert_called_once_with(port=0)

@patch('gmail_auth.Credentials')
@patch('gmail_auth.pickle')
def test_authenticate_existing_valid_credentials(mock_pickle, mock_creds, gmail_auth):
    # Mock existing valid credentials
    mock_creds_instance = MagicMock()
    mock_pickle.load.return_value = mock_creds_instance
    mock_creds_instance.valid = True
    
    # Test authentication
    result = gmail_auth.authenticate()
    
    assert result == mock_creds_instance
    mock_pickle.load.assert_called_once()

@patch('os.path')
@patch('os.remove')
def test_revoke_credentials(mock_remove, mock_path, gmail_auth):
    # Mock file existence check
    mock_path.exists.return_value = True
    
    # Test revocation
    gmail_auth.revoke_credentials()
    
    mock_path.exists.assert_called_once_with(gmail_auth.token_file)
    mock_remove.assert_called_once_with(gmail_auth.token_file)

@patch('gmail_auth.Credentials')
@patch('gmail_auth.pickle')
def test_authenticate_expired_credentials(mock_pickle, mock_creds, gmail_auth):
    # Mock expired credentials that need refresh
    mock_creds_instance = MagicMock()
    mock_pickle.load.return_value = mock_creds_instance
    mock_creds_instance.valid = False
    mock_creds_instance.expired = True
    mock_creds_instance.refresh_token = "refresh_token"
    mock_creds_instance.refresh.return_value = None
    
    # Test authentication with refresh
    result = gmail_auth.authenticate()
    
    assert result == mock_creds_instance
    mock_creds_instance.refresh.assert_called_once()
    mock_pickle.dump.assert_called_once()

@patch('gmail_auth.InstalledAppFlow')
def test_authenticate_invalid_credentials_file(mock_flow, gmail_auth):
    # Mock invalid credentials file
    mock_flow.from_client_secrets_file.side_effect = FileNotFoundError
    
    with pytest.raises(FileNotFoundError):
        gmail_auth.authenticate()

@patch('gmail_auth.InstalledAppFlow')
def test_authenticate_failed_auth(mock_flow, gmail_auth):
    # Mock authentication failure
    mock_flow_instance = MagicMock()
    mock_flow.from_client_secrets_file.return_value = mock_flow_instance
    mock_flow_instance.run_local_server.side_effect = Exception("Authentication failed")
    
    with pytest.raises(Exception) as exc_info:
        gmail_auth.authenticate()
    assert str(exc_info.value) == "Authentication failed"

@patch('gmail_auth.Credentials')
@patch('gmail_auth.pickle')
def test_authenticate_refresh_token_failure(mock_pickle, mock_creds, gmail_auth):
    # Mock credentials that fail to refresh
    mock_creds_instance = MagicMock()
    mock_pickle.load.return_value = mock_creds_instance
    mock_creds_instance.valid = False
    mock_creds_instance.expired = True
    mock_creds_instance.refresh_token = "refresh_token"
    mock_creds_instance.refresh.side_effect = Exception("Token refresh failed")
    
    with pytest.raises(Exception) as exc_info:
        gmail_auth.authenticate()
    assert str(exc_info.value) == "Token refresh failed" 