"""
Instant Email Checker - Continuously monitors Gmail for new messages.

This module provides a way to check for new emails in Gmail with minimal delay,
using a background thread that checks frequently rather than long polling.
"""

import threading
import time
from datetime import datetime
from typing import Callable, Dict, Any, Set, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError
from logger import cfo_logger
from email_storage import EmailStorage
import re

class InstantEmailChecker:
    """Gmail checker that continuously polls in the background with minimal delay."""
    
    def __init__(self, 
                 gmail_auth, 
                 check_frequency: float = 2.0,  # Check every 2 seconds
                 storage: Optional[EmailStorage] = None):
        """Initialize the instant email checker.
        
        Args:
            gmail_auth: Gmail authenticator object
            check_frequency: How often to check for new emails (in seconds)
            storage: Optional EmailStorage for persistent tracking
        """
        self.gmail_auth = gmail_auth
        self.gmail_service = None
        self.check_frequency = check_frequency
        self.is_running = False
        self.check_thread = None
        self.callback = None
        self.storage = storage or EmailStorage(max_age_days=30)
        
        # In-memory set for very recent emails to prevent duplicates
        # between checks (in case the storage write hasn't completed)
        self.recent_ids = set()
        self.max_recent_size = 100
    
    def authenticate_gmail(self) -> bool:
        """Authenticate with Gmail API."""
        try:
            if not self.gmail_service:
                # Make multiple attempts with backoff
                max_attempts = 3
                for attempt in range(1, max_attempts + 1):
                    try:
                        cfo_logger.info(f"Attempting Gmail authentication (attempt {attempt}/{max_attempts})")
                        creds = self.gmail_auth.authenticate()
                        self.gmail_service = self.gmail_auth.build_service(creds)
                        if self.gmail_service:
                            cfo_logger.info("Gmail authentication successful")
                            return True
                    except Exception as e:
                        cfo_logger.error(f"Gmail authentication attempt {attempt} failed: {str(e)}")
                        if attempt < max_attempts:
                            time.sleep(2 * attempt)  # Exponential backoff
                        else:
                            raise
                
                cfo_logger.error("All Gmail authentication attempts failed")
                return False
            return True
        except Exception as e:
            cfo_logger.error(f"Gmail authentication failed: {str(e)}")
            return False
    
    def start_checking(self, callback: Callable[[Dict], None]) -> bool:
        """Start the continuous email checking.
        
        Args:
            callback: Function to call for each new email found
            
        Returns:
            bool: True if started successfully
        """
        if self.is_running:
            cfo_logger.warning("Email checker is already running")
            return True
        
        if not self.authenticate_gmail():
            cfo_logger.error("Failed to authenticate with Gmail API")
            return False
        
        self.callback = callback
        self.is_running = True
        
        # Start the checking thread
        self.check_thread = threading.Thread(
            target=self._check_loop,
            daemon=True
        )
        self.check_thread.start()
        
        cfo_logger.info(f"Instant email checking started (every {self.check_frequency}s)")
        return True
    
    def stop_checking(self) -> None:
        """Stop the continuous email checking."""
        if not self.is_running:
            return
            
        self.is_running = False
        
        if self.check_thread and self.check_thread.is_alive():
            self.check_thread.join(timeout=self.check_frequency * 2)
            
        cfo_logger.info("Instant email checking stopped")
    
    def _check_loop(self) -> None:
        """Continuous loop to check for new emails."""
        retry_count = 0
        max_retries = 5
        auth_timeout = 0  # Timeout counter for authentication
        
        while self.is_running:
            # Check if we're in a timeout period for authentication
            if auth_timeout > 0:
                auth_timeout -= 1
                time.sleep(self.check_frequency)
                continue
                
            try:
                # Check for new emails
                self._check_for_emails()
                
                # Reset retry counter on success
                retry_count = 0
                
                # Sleep briefly before next check
                time.sleep(self.check_frequency)
                
            except RefreshError:
                retry_count += 1
                cfo_logger.error(f"Gmail token refresh error (retry {retry_count})")
                
                if retry_count <= max_retries:
                    # Try to re-authenticate
                    try:
                        cfo_logger.info("Revoking credentials and attempting to reauthenticate")
                        self.gmail_auth.revoke_credentials()
                        self.gmail_service = None
                        if not self.authenticate_gmail():
                            # If authentication fails, set a timeout period
                            auth_timeout = 30  # Skip 30 check cycles (approx. 1 minute with 2s frequency)
                            cfo_logger.warning(f"Setting authentication timeout for {auth_timeout * self.check_frequency} seconds")
                    except Exception as auth_error:
                        cfo_logger.error(f"Failed to reauthenticate: {str(auth_error)}")
                        auth_timeout = 60  # Longer timeout after authentication failure
                
                time.sleep(self.check_frequency)
                
            except HttpError as e:
                retry_count += 1
                error_str = str(e)
                cfo_logger.error(f"Gmail API HTTP error: {error_str}")
                
                # Check for specific error types
                if "401" in error_str:  # Unauthorized
                    cfo_logger.warning("401 Unauthorized error - trying to reauthenticate")
                    self.gmail_auth.revoke_credentials()
                    self.gmail_service = None
                    if not self.authenticate_gmail():
                        auth_timeout = 30
                elif "429" in error_str:  # Too Many Requests
                    cfo_logger.warning("Rate limit hit (429) - backing off")
                    time.sleep(min(30, retry_count * 5))  # Longer backoff for rate limits
                elif retry_count > max_retries:
                    cfo_logger.error("Too many consecutive errors, pausing for 60 seconds")
                    time.sleep(60)  # Longer pause after multiple failures
                    retry_count = 0
                else:
                    time.sleep(self.check_frequency * retry_count)  # Progressive backoff
                    
            except Exception as e:
                cfo_logger.error(f"Error in email check loop: {str(e)}")
                time.sleep(self.check_frequency * (retry_count + 1))  # Progressive backoff
                retry_count += 1
    
    def _check_for_emails(self) -> None:
        """Check for new unread emails."""
        try:
            # Verify service is available
            if not self.gmail_service:
                if not self.authenticate_gmail():
                    return
            
            # Query for unread messages
            results = self.gmail_service.users().messages().list(
                userId='me',
                q='is:unread',
                maxResults=10  # Small batch size for rapid processing
            ).execute()
            
            messages = results.get('messages', [])
            if not messages:
                return  # No unread messages
                
            # Process each message
            for message in messages:
                try:
                    msg_id = message['id']
                    
                    # Skip if already processed
                    if msg_id in self.recent_ids or (self.storage and self.storage.contains(msg_id)):
                        continue
                    
                    # Add to tracking sets
                    self.recent_ids.add(msg_id)
                    if len(self.recent_ids) > self.max_recent_size:
                        # Remove oldest entries (implementation is simplified)
                        self.recent_ids = set(list(self.recent_ids)[-self.max_recent_size:])
                    
                    # Get full message details
                    try:
                        full_msg = self.gmail_service.users().messages().get(
                            userId='me', 
                            id=msg_id,
                            format='full'
                        ).execute()
                    except Exception as e:
                        cfo_logger.error(f"Error getting full message {msg_id}: {str(e)}")
                        continue
                        
                    # Mark as read
                    try:
                        self.gmail_service.users().messages().modify(
                            userId='me',
                            id=msg_id,
                            body={'removeLabelIds': ['UNREAD']}
                        ).execute()
                    except Exception as e:
                        cfo_logger.error(f"Error marking message {msg_id} as read: {str(e)}")
                        # Continue anyway - we can still process the message
                    
                    # Add to storage if available
                    if self.storage:
                        self.storage.add(msg_id)
                    
                    # Process message - build data structure similar to EmailMonitor
                    try:
                        headers = {}
                        for header in full_msg['payload']['headers']:
                            headers[header['name'].lower()] = header['value']
                        
                        from_header = headers.get('from', '')
                        subject = headers.get('subject', 'No Subject')
                        body = self._extract_body(full_msg)
                        
                        # Extract clean email address (needs the helper function)
                        # Assuming _extract_email_address is available (e.g., imported or duplicated)
                        # We might need to adjust this if the helper isn't directly accessible
                        # For now, let's try calling it assuming it exists on self (might need adjustment)
                        try:
                            # Temporarily duplicate extraction logic if needed
                            sender_email = None
                            match_angle = re.search(r'<([^>]+)>', from_header)
                            if match_angle:
                                sender_email = match_angle.group(1).lower()
                            elif '@' in from_header:
                                match_email = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}', from_header)
                                if match_email:
                                    sender_email = match_email.group(0).lower()
                                else: 
                                     sender_email = from_header.strip().lower() # Fallback
                        except Exception as extract_err:
                            cfo_logger.warning(f"Could not extract email from '{from_header}' in instant checker: {extract_err}")
                            sender_email = None

                        # Create email data - MIRROR the structure from EmailMonitor._parse_gmail_message
                        email_data = {
                            'message_id': msg_id,
                            'subject': subject,
                            'body': body,
                            'sender': from_header,       # Raw sender header
                            'from': from_header,         # Raw from header (redundant but matches)
                            'from_email': sender_email, # Extracted clean email
                            'date': headers.get('date', ''),
                            'received': datetime.now(), # Use datetime object
                            'has_attachments': any( # Check for attachments
                                'attachmentId' in part.get('body', {})
                                for part in full_msg['payload'].get('parts', [])
                                if 'body' in part
                            ),
                            'instant_checker': True # Flag source
                        }
                        
                        # Call the callback safely in a new thread
                        if self.callback and self.is_running:
                            # Pass the new, complete email_data dictionary
                            threading.Thread(
                                target=self._safe_callback,
                                args=(email_data,), # Pass the corrected dict
                                daemon=True
                            ).start()
                            cfo_logger.info(f"Instant processing of email: '{subject}' from {from_header}")
                        
                    except Exception as e:
                        cfo_logger.error(f"Error constructing/parsing email data for {msg_id}: {str(e)}", exc_info=True)
                        
                except Exception as message_error:
                    cfo_logger.error(f"Error processing message in batch: {str(message_error)}")
                    # Continue with the next message
                
        except Exception as e:
            cfo_logger.error(f"Error checking for emails: {str(e)}")
            raise  # Let the outer handler deal with it
    
    def _safe_callback(self, email_data: Dict) -> None:
        """Safely call the callback function with error handling.
        
        Args:
            email_data: Email data to pass to the callback
        """
        try:
            if self.callback and self.is_running:
                # Create a copy of the data to avoid thread safety issues
                data_copy = dict(email_data)
                
                # Add a key to indicate this is coming from the instant checker
                data_copy['instant_checker'] = True
                
                # Call the callback
                self.callback(data_copy)
        except Exception as e:
            cfo_logger.error(f"Error in callback for email {email_data.get('subject', 'Unknown')}: {str(e)}")
    
    def _extract_body(self, message) -> str:
        """Extract the message body from a Gmail API message object."""
        try:
            if 'payload' not in message:
                return ""
                
            payload = message['payload']
            
            # For simple messages
            if 'body' in payload and 'data' in payload['body']:
                import base64
                data = payload['body']['data']
                return base64.urlsafe_b64decode(data).decode('utf-8')
                
            # For multipart messages, find the text part
            if 'parts' in payload:
                for part in payload['parts']:
                    if part.get('mimeType') == 'text/plain' and 'data' in part.get('body', {}):
                        import base64
                        data = part['body']['data']
                        return base64.urlsafe_b64decode(data).decode('utf-8')
                    
                # No plain text found, try HTML
                for part in payload['parts']:
                    if part.get('mimeType') == 'text/html' and 'data' in part.get('body', {}):
                        import base64
                        import re
                        data = part['body']['data']
                        html = base64.urlsafe_b64decode(data).decode('utf-8')
                        # Simple HTML to text
                        text = re.sub(r'<[^>]+>', ' ', html)
                        return re.sub(r'\s+', ' ', text)
                        
            return "Unable to extract message body"
            
        except Exception as e:
            cfo_logger.error(f"Error extracting message body: {str(e)}")
            return "Error extracting message body" 