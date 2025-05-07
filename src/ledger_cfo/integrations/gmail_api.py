import logging
import base64
import re
from email import message_from_bytes
from email.header import decode_header
from typing import Optional, List, Dict, Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2 import service_account

# Assuming get_secret is correctly defined in core.config
from ..core.config import get_secret

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service() -> Optional[Any]:
    """Initializes and returns an authorized Gmail API service object.

    Fetches credentials (client ID, client secret, refresh token) from
    Google Secret Manager and uses them to create credentials.
    Removes reliance on token.pickle and local credentials.json.

    Returns:
        An authorized Gmail API service object, or None if authentication fails.
    """
    creds = None
    try:
        # Fetch credentials from Secret Manager
        client_id = get_secret("ledger-cfo-gmail-client-id")
        client_secret = get_secret("ledger-cfo-gmail-client-secret")
        refresh_token = get_secret("ledger-cfo-gmail-refresh-token")

        if not all([client_id, client_secret, refresh_token]):
            logging.error("Missing one or more Gmail credentials from Secret Manager.")
            return None

        logging.info("Attempting to build Gmail credentials using refresh token from Secret Manager.")
        # Create credentials object directly from fetched secrets
        creds = Credentials.from_authorized_user_info(
            info={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "token_uri": "https://oauth2.googleapis.com/token", # Standard token URI
            },
            scopes=SCOPES
        )

        # Note: The Credentials object handles token refreshing automatically if needed.
        # No need to manually check expiry or call refresh() unless explicitly required.
        # We trust that the library will raise errors if the refresh token is invalid/expired.

        service = build('gmail', 'v1', credentials=creds)
        logging.info("Gmail API service object created successfully.")
        return service

    except ValueError as ve:
        # Catch errors from get_secret if GCP_PROJECT_ID is missing
        logging.error(f"Configuration error during Gmail service initialization: {ve}")
        return None
    except Exception as e:
        # This could catch errors from Credentials creation or build()
        # For example, if the refresh token is invalid or revoked.
        logging.error(f"Failed to create Gmail service: {e}")
        # Consider logging specific details about the credential state if possible/needed
        # logging.error(f"Credential details: valid={creds.valid if creds else 'N/A'}, expired={creds.expired if creds else 'N/A'}")
        return None

def extract_email_address(from_header: str) -> str:
    """Extracts the email address from a 'From' header string."""
    match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', from_header)
    return match.group(0).lower() if match else ""

def decode_mime_header(header: str) -> str:
    """Decodes MIME encoded email headers."""
    decoded_parts = decode_header(header)
    header_parts = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            header_parts.append(part.decode(encoding or 'utf-8', errors='replace'))
        else:
            header_parts.append(part)
    return "".join(header_parts)

def get_unread_emails(service: Any, user_id='me', query='is:unread') -> List[Dict[str, Any]]:
    """Fetches unread emails based on a query."""
    unread_emails_data = []
    try:
        logging.info(f"Fetching unread emails with query: '{query}'")
        results = service.users().messages().list(userId=user_id, q=query).execute()
        messages = results.get('messages', [])

        if not messages:
            logging.info("No unread messages found matching the query.")
            return []

        logging.info(f"Found {len(messages)} potentially unread messages. Fetching details...")
        for msg_ref in messages:
            msg = service.users().messages().get(userId=user_id, id=msg_ref['id'], format='full').execute()
            email_data = parse_email_message(msg)
            if email_data:
                unread_emails_data.append(email_data)

    except HttpError as error:
        logging.error(f'An HTTP error occurred while fetching emails: {error}')
    except Exception as e:
        logging.error(f'An unexpected error occurred while fetching emails: {e}')

    logging.info(f"Returning {len(unread_emails_data)} processed unread emails.")
    return unread_emails_data

def parse_email_message(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parses the relevant information from a Gmail message object."""
    try:
        email_data = {"id": message['id']}
        headers = message['payload']['headers']
        for header in headers:
            name = header['name'].lower()
            if name == 'from':
                email_data['from'] = extract_email_address(decode_mime_header(header['value']))
                email_data['from_full'] = decode_mime_header(header['value'])
            elif name == 'subject':
                email_data['subject'] = decode_mime_header(header['value'])
            elif name == 'date':
                email_data['date'] = header['value']

        # Find the email body (handle multipart messages)
        body = ""
        if 'parts' in message['payload']:
            parts = message['payload']['parts']
            # Look for text/plain first
            plain_part = next((p for p in parts if p.get('mimeType') == 'text/plain'), None)
            if plain_part and 'data' in plain_part['body']:
                body = base64.urlsafe_b64decode(plain_part['body']['data']).decode('utf-8')
            else:
                # Fallback: look for text/html or the first part with data
                html_part = next((p for p in parts if p.get('mimeType') == 'text/html'), None)
                if html_part and 'data' in html_part['body']:
                    body = base64.urlsafe_b64decode(html_part['body']['data']).decode('utf-8')
                    # Potentially strip HTML tags here if needed
                else:
                     # Try getting the first part if specific types aren't found
                     first_part_with_data = next((p for p in parts if 'data' in p.get('body', {})), None)
                     if first_part_with_data:
                         body = base64.urlsafe_b64decode(first_part_with_data['body']['data']).decode('utf-8')
        elif 'body' in message['payload'] and 'data' in message['payload']['body']:
            # Handle non-multipart messages
            body = base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8')

        email_data['body'] = body.strip()

        # Ensure essential fields are present
        if not all(k in email_data for k in ('from', 'subject', 'body')):
            logging.warning(f"Skipping email ID {email_data['id']}: missing essential header or body.")
            return None

        return email_data

    except Exception as e:
        logging.error(f"Error parsing email message ID {message.get('id', 'N/A')}: {e}")
        return None

def mark_email_as_read(service: Any, msg_id: str, user_id='me') -> None:
    """Marks a specific email as read by removing the UNREAD label."""
    try:
        logging.info(f"Marking email ID {msg_id} as read.")
        service.users().messages().modify(
            userId=user_id,
            id=msg_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()
    except HttpError as error:
        logging.error(f'An HTTP error occurred while marking email {msg_id} as read: {error}')
    except Exception as e:
        logging.error(f'An unexpected error occurred marking email {msg_id} as read: {e}')

# Add other Gmail functions as needed (e.g., sending emails, managing labels)

from email.mime.text import MIMEText

async def send_email(service: Any, to: str, sender: str, subject: str, body: str, user_id='me') -> Optional[Dict]:
    """Creates and sends an email message asynchronously."""
    try:
        message = MIMEText(body)
        message['to'] = to
        message['from'] = sender
        message['subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}

        # Properly await each step in the AsyncMock chain
        users_service = await service.users()
        messages_service = await users_service.messages()
        # The send() method on the real API client typically returns a request object,
        # which then has an execute() method. Or send() might directly execute.
        # Assuming send() returns the request that needs execute():
        send_request = await messages_service.send(userId=user_id, body=create_message)
        send_message_result = await send_request.execute()
        
        logger.info(f"Sent email successfully. Message ID: {send_message_result.get('id')}")
        return send_message_result
    except HttpError as error:
        logger.error(f'An HTTP error occurred while sending email: {error}')
        return None
    except Exception as e:
        logger.error(f'An unexpected error occurred while sending email: {e}', exc_info=True)
        return None 