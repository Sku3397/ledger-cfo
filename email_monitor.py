import os
import time
import re
import threading
import email
from email.header import decode_header
from typing import Optional, Callable, Dict, List
from datetime import datetime, timedelta
from email_validator import validate_email, EmailNotValidError
from logger import cfo_logger
from config import config
import base64
import pickle
import os.path

# Import Gmail API modules
from gmail_auth import GmailAuthenticator
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from email_storage import EmailStorage
from instant_email_checker import InstantEmailChecker

class EmailMonitor:
    """Module for monitoring a Gmail inbox for invoice requests using the Gmail API.
    
    This class handles OAuth authentication, email retrieval, and validation
    of authorized senders. It continuously checks for new emails and
    processes them if they meet the authorization criteria.
    """
    
    def __init__(self, config):
        """Initialize the email monitoring service with configuration settings."""
        self.config = config
        self.authorized_senders = config.AUTHORIZED_EMAIL_SENDERS
        self.check_interval = config.EMAIL_CHECK_INTERVAL
        self.is_monitoring = False
        self.monitor_thread = None
        self.last_checked_time = None
        self.max_retries = 3
        self.retry_delay = 5  # seconds between retries
        self.callback = None
        
        # Initialize Gmail authenticator
        try:
            cfo_logger.info("Initializing Gmail authenticator")
            credentials_file = getattr(config, 'GMAIL_CREDENTIALS_FILE', 'credentials.json')
            token_file = getattr(config, 'GMAIL_TOKEN_FILE', 'token.pickle')
            self.gmail_auth = GmailAuthenticator(
                credentials_file=credentials_file,
                token_file=token_file
            )
            self.gmail_service = None
        except Exception as e:
            cfo_logger.error(f"Failed to initialize Gmail authenticator: {str(e)}")
            self.gmail_auth = None
            self.gmail_service = None
        
        # Initialize persistent storage with 30-day retention
        try:
            self.email_storage = EmailStorage(max_age_days=30)
        except Exception as e:
            cfo_logger.error(f"Failed to initialize email storage: {str(e)}")
            self.email_storage = None
        
        # Initialize instant email checker for real-time monitoring
        try:
            self.instant_checker = InstantEmailChecker(
                gmail_auth=self.gmail_auth,
                check_frequency=2.0,  # Check every 2 seconds
                storage=self.email_storage
            )
            cfo_logger.info("Email monitor initialized with instant checking capabilities")
        except Exception as e:
            cfo_logger.error(f"Failed to initialize instant email checker: {str(e)}")
            self.instant_checker = None
    
    def _decode_email_header(self, header: str) -> str:
        """Decode email header properly handling encoded strings.
        
        Args:
            header: The email header string to decode
            
        Returns:
            The decoded header string
        """
        try:
            decoded_header = decode_header(header)
            parts = []
            for content, charset in decoded_header:
                if isinstance(content, bytes):
                    if charset:
                        parts.append(content.decode(charset or 'utf-8', errors='replace'))
                    else:
                        parts.append(content.decode('utf-8', errors='replace'))
                else:
                    parts.append(str(content))
            return ''.join(parts)
        except Exception as e:
            cfo_logger.error(f"Error decoding email header: {str(e)}")
            return header  # Return original if decoding fails
    
    def _extract_email_address(self, sender: str) -> Optional[str]:
        """Extract the email address from a sender string.
        
        Args:
            sender: The sender string (may include name and email)
            
        Returns:
            The extracted email address or None if not found
        """
        try:
            if not sender:
                return None
                
            # Common format: "Name <email@example.com>"
            match = re.search(r'<([^>]+)>', sender)
            if match:
                return match.group(1).lower()
                
            # Simple format: email@example.com
            if '@' in sender:
                # Look for anything that looks like an email address
                match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', sender)
                if match:
                    return match.group(0).lower()
                    
                # If that fails, just return the whole string (it might be just an email)
                return sender.strip().lower()
                
            return None
        except Exception as e:
            cfo_logger.error(f"Error extracting email address: {str(e)}")
            return None
    
    def validate_sender(self, sender: str) -> bool:
        """Validate if the email is from an authorized sender.
        
        Args:
            sender: The sender's email address
            
        Returns:
            True if the sender is authorized, False otherwise
        """
        try:
            # Clean and normalize the sender address
            sender_email = self._extract_email_address(sender)
            if not sender_email:
                return False
                
            # Validate email format
            valid = validate_email(sender_email)
            
            # Check if it matches our authorized senders
            return valid.email.lower() in self.authorized_senders
        except EmailNotValidError:
            return False
        except Exception as e:
            cfo_logger.error(f"Error validating sender: {str(e)}")
            return False
    
    def _get_message_body(self, message):
        """Extract the message body from a Gmail API message object.
        
        Args:
            message: The Gmail API message object
            
        Returns:
            The message body as text
        """
        if 'payload' not in message:
            return ""
            
        payload = message['payload']
        
        # Handle multipart messages
        if 'parts' in payload:
            for part in payload['parts']:
                mime_type = part.get('mimeType', '')
                if mime_type == 'text/plain':
                    body_data = part.get('body', {}).get('data', '')
                    if body_data:
                        return base64.urlsafe_b64decode(body_data).decode('utf-8')
            
            # If no plain text found, try to get HTML and convert it
            for part in payload['parts']:
                mime_type = part.get('mimeType', '')
                if mime_type == 'text/html':
                    body_data = part.get('body', {}).get('data', '')
                    if body_data:
                        html_body = base64.urlsafe_b64decode(body_data).decode('utf-8')
                        # Simple HTML to text conversion
                        # For production, consider using html2text or BeautifulSoup
                        text_body = re.sub(r'<[^>]+>', ' ', html_body)
                        text_body = re.sub(r'\s+', ' ', text_body)
                        return text_body
        
        # Handle single part messages
        elif 'body' in payload and 'data' in payload['body']:
            body_data = payload['body']['data']
            return base64.urlsafe_b64decode(body_data).decode('utf-8')
        
        return ""
    
    def _parse_gmail_message(self, msg_id, msg_data) -> Dict:
        """Parse a Gmail API message into a structured format.
        
        Args:
            msg_id: The message ID
            msg_data: The full message data from Gmail API
            
        Returns:
            A dictionary with email details
        """
        try:
            headers = {}
            for header in msg_data['payload']['headers']:
                headers[header['name'].lower()] = header['value']
            
            subject = headers.get('subject', 'No Subject')
            from_header = headers.get('from', '')
            
            # Extract the message body
            body = self._get_message_body(msg_data)
            
            # Create structured email data
            email_data = {
                'message_id': msg_id,
                'subject': subject,
                'body': body,
                'sender': from_header,
                'from': from_header,
                'date': headers.get('date', ''),
                'received': datetime.now(),
                'has_attachments': any(
                    'attachmentId' in part.get('body', {})
                    for part in msg_data['payload'].get('parts', [])
                    if 'body' in part
                )
            }
            
            return email_data
        except Exception as e:
            cfo_logger.error(f"Error parsing Gmail message: {str(e)}")
            # Ensure sender key is present even on error
            return {
                'message_id': msg_id,
                'error': str(e),
                'from': 'unknown', 
                'sender': 'unknown', # Add sender key here too
                'from_email': None, # Indicate extraction failed
                'subject': 'Parse Error',
                'body': f'Error parsing message body: {e}',
                'received': datetime.now()
            }
    
    def check_for_new_emails(self) -> List[Dict]:
        """Check for new emails from authorized senders using Gmail API.
        
        Returns:
            A list of parsed email messages from authorized senders
        """
        new_emails = []
        retry_count = 0
        
        while retry_count < self.max_retries:
            try:
                cfo_logger.debug(f"Checking for new emails (attempt {retry_count + 1})")
                
                # Get Gmail service
                if not self.gmail_service:
                    creds = self.gmail_auth.authenticate()
                    self.gmail_service = self.gmail_auth.build_service(creds)
                
                # Check for new messages
                results = self.gmail_service.users().messages().list(
                    userId='me',
                    q='is:unread',
                    maxResults=20
                ).execute()
                
                messages = results.get('messages', [])
                
                for message in messages:
                    msg_id = message['id']
                    
                    # Skip already processed messages using persistent storage
                    if self.email_storage.contains(msg_id):
                        continue
                    
                    # Get full message details
                    full_msg = self.gmail_service.users().messages().get(
                        userId='me', 
                        id=msg_id,
                        format='full'
                    ).execute()
                    
                    # Mark the message as read
                    self.gmail_service.users().messages().modify(
                        userId='me',
                        id=msg_id,
                        body={'removeLabelIds': ['UNREAD']}
                    ).execute()
                    
                    # Add to persistent storage
                    self.email_storage.add(msg_id)
                    
                    # Parse message data
                    email_data = self._parse_gmail_message(msg_id, full_msg)
                    
                    # Extract sender
                    sender = email_data.get('from', '')
                    sender_email = self._extract_email_address(sender)
                    email_data['from_email'] = sender_email
                    
                    # Check if sender is authorized
                    if self.validate_sender(sender):
                        cfo_logger.info(f"Processing new email from {sender} with subject: {email_data.get('subject', 'No Subject')}")
                        new_emails.append(email_data)
                    else:
                        cfo_logger.warning(f"Skipped email from unauthorized sender: {sender}")
                
                # Update last checked time
                self.last_checked_time = datetime.now()
                
                # Return new emails
                return new_emails
                
            except RefreshError as e:
                cfo_logger.error(f"OAuth token refresh error: {str(e)}")
                # Attempt to reauthenticate
                try:
                    self.gmail_auth.revoke_credentials()
                    creds = self.gmail_auth.authenticate()
                    self.gmail_service = self.gmail_auth.build_service(creds)
                    retry_count += 1
                except Exception as auth_error:
                    cfo_logger.error(f"Failed to reauthenticate: {str(auth_error)}")
                    retry_count = self.max_retries
            except HttpError as e:
                retry_count += 1
                cfo_logger.error(f"Gmail API HTTP error (attempt {retry_count}): {str(e)}")
                if retry_count < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    cfo_logger.error(f"Failed to check emails after {self.max_retries} attempts")
            except Exception as e:
                retry_count += 1
                cfo_logger.error(f"Email check failed (attempt {retry_count}): {str(e)}")
                if retry_count < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    cfo_logger.error(f"Failed to check emails after {self.max_retries} attempts")
                    
        # Return any emails collected before error
        return new_emails
    
    def _monitor_loop(self, callback: Callable[[Dict], None]):
        """Continuous monitoring loop for new emails.
        
        Args:
            callback: Function to call for each new authorized email
        """
        cfo_logger.info("Starting email monitoring loop")
        
        while self.is_monitoring:
            try:
                # Check for new emails
                new_emails = self.check_for_new_emails()
                
                # Process each new email
                for email_data in new_emails:
                    try:
                        callback(email_data)
                    except Exception as e:
                        cfo_logger.error(f"Error in email callback processing: {str(e)}")
                
                # Sleep between checks
                time.sleep(self.check_interval)
                
            except Exception as e:
                cfo_logger.error(f"Error in email monitoring loop: {str(e)}")
                time.sleep(self.check_interval)  # Continue checking even after error
    
    def start_monitoring(self, callback: Callable[[Dict], None]):
        """Start monitoring for new emails.
        
        Args:
            callback: Function to call for each new authorized email
        """
        if self.is_monitoring:
            cfo_logger.warning("Email monitoring already active")
            return
            
        if not self.validate_connection():
            cfo_logger.error("Failed to validate Gmail API connection")
            return
        
        self.callback = callback
        self.is_monitoring = True
        
        # Define a wrapper to validate sender before passing to callback
        def validated_callback(email_data):
            try:
                # Extract sender email
                sender = email_data.get('from', '')
                sender_email = self._extract_email_address(sender)
                email_data['from_email'] = sender_email
                
                # Validate the sender more carefully
                is_valid = False
                if sender_email:
                    # First try direct match with the email address
                    if sender_email.lower() in [s.lower() for s in self.authorized_senders]:
                        is_valid = True
                    # Then check if the full sender string contains any authorized email
                    elif any(auth_email.lower() in sender.lower() for auth_email in self.authorized_senders):
                        is_valid = True
                    
                if is_valid:
                    cfo_logger.info(f"Processing email from {sender} with subject: {email_data.get('subject', 'No Subject')}")
                    
                    # Use the main thread's callback to avoid thread context issues in Streamlit
                    # We'll queue it for the main thread to process
                    import queue
                    from main import update_queue
                    
                    # Put an email status update in the queue
                    try:
                        update_data = {
                            'type': 'email_status',
                            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'sender': sender,
                            'subject': email_data.get('subject', 'No Subject'),
                            'status': 'Processing',
                            'message_id': email_data.get('message_id')
                        }
                        update_queue.put(update_data)
                        # Let the main thread handle the actual processing
                        callback(email_data)
                    except Exception as e:
                        cfo_logger.error(f"Error queueing email update: {str(e)}")
                        # Fall back to direct callback if queueing fails
                        callback(email_data)
                else:
                    cfo_logger.warning(f"Skipped email from unauthorized sender: {sender} ({sender_email})")
            except Exception as e:
                cfo_logger.error(f"Error in validated_callback: {str(e)}")
        
        # Start real-time checking if available
        if self.instant_checker:
            started = self.instant_checker.start_checking(validated_callback)
            if started:
                cfo_logger.info("Instant email checking started successfully")
                return
            else:
                cfo_logger.warning("Failed to start instant email checking, falling back to polling")
        
        # Fall back to traditional polling if instant checking fails or not available
        cfo_logger.info("Starting polling-based email monitoring")
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(callback,),
            daemon=True
        )
        self.monitor_thread.start()
        cfo_logger.info("Email polling started in background thread")
    
    def stop_monitoring(self):
        """Stop the email monitoring service."""
        self.is_monitoring = False
        
        # Stop instant checking if active
        if self.instant_checker:
            self.instant_checker.stop_checking()
            cfo_logger.info("Instant email checking stopped")
        
        # Stop polling thread if active
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=10)
            cfo_logger.info("Email polling stopped")
            
        cfo_logger.info("Email monitoring stopped completely")

    def validate_connection(self):
        """Validate Gmail API connection and credentials."""
        try:
            if not self.gmail_auth:
                cfo_logger.error("Gmail authenticator not initialized")
                return False
                
            creds = self.gmail_auth.authenticate()
            self.gmail_service = self.gmail_auth.build_service(creds)
            
            if not self.gmail_service:
                cfo_logger.error("Failed to build Gmail service")
                return False
                
            # Test connection with a simple request
            result = self.gmail_service.users().getProfile(userId='me').execute()
            if 'emailAddress' in result:
                cfo_logger.info(f"Gmail API connection validated successfully for {result['emailAddress']}")
                return True
            else:
                cfo_logger.error("Gmail API connection validation failed: Could not get user profile")
                return False
        except Exception as e:
            cfo_logger.error(f"Gmail API connection validation failed: {str(e)}")
            return False

    def simulate_email(self, subject, body, from_email="hello@757handy.com"):
        """Simulate receiving an email and process it using the current callback.
        
        Args:
            subject (str): The subject of the simulated email.
            body (str): The body content of the simulated email.
            from_email (str): The sender email address (defaults to authorized sender).
        """
        # Check if callback is assigned (it should be if monitor started or simulation used)
        if not self.callback:
            cfo_logger.error("Cannot simulate email: Callback function not set.")
            return False
            
        cfo_logger.info(f"Simulating email from {from_email} with subject: {subject}")
        
        # Construct simulated email data mimicking Gmail API structure (simplified)
        simulated_email_data = {
            'message_id': f"simulated_{int(time.time())}", # Unique ID for simulation
            'sender': f"Simulated User <{from_email}>",
            'from': f"Simulated User <{from_email}>", # Add 'from' for consistency
            'from_email': from_email, # Add extracted email
            'subject': subject,
            'body': body,
            'date': datetime.now().isoformat(), # Use ISO format string
            'received': datetime.now(), # Keep as datetime obj? Or use string?
            'simulated': True # Flag as simulated
        }
        
        try:
            # Directly call the assigned callback function (e.g., handle_llm_email_processing)
            cfo_logger.debug(f"Calling callback function: {self.callback.__name__}")
            self.callback(simulated_email_data)
            cfo_logger.info("Simulated email passed to callback successfully.")
            return True
        except Exception as e:
            cfo_logger.error(f"Error executing callback for simulated email: {e}", exc_info=True)
            return False 