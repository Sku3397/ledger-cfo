import os
from gmail_auth import GmailAuthenticator
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from logger import cfo_logger

def main():
    """Test Gmail API authentication and connection."""
    # Initialize the Gmail authenticator
    print("Initializing Gmail authenticator...")
    gmail_auth = GmailAuthenticator(
        credentials_file="credentials.json",
        token_file="token.pickle"
    )
    
    try:
        # Authenticate
        print("Authenticating with Gmail API...")
        creds = gmail_auth.authenticate()
        
        # Build service
        print("Building Gmail service...")
        service = gmail_auth.build_service(creds)
        
        if not service:
            print("❌ Failed to build Gmail service")
            return
        
        # Test connection with a simple request
        print("Testing connection...")
        result = service.users().getProfile(userId='me').execute()
        
        if 'emailAddress' in result:
            print(f"✅ Authentication successful! Connected as: {result['emailAddress']}")
            
            # Get labels to verify read access
            labels = service.users().labels().list(userId='me').execute()
            print(f"✅ Retrieved {len(labels.get('labels', []))} labels")
            
            # Print a few label names
            for label in labels.get('labels', [])[:5]:
                print(f"  - {label['name']}")
        else:
            print("❌ Failed to verify connection")
    except HttpError as error:
        print(f"❌ Gmail API error: {error}")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    main() 