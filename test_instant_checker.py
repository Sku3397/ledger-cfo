"""
Test script for the instant email checker.

Run this file directly with 'python test_instant_checker.py' to start
the instant email checker and see emails as they arrive.
"""

import time
from datetime import datetime
from gmail_auth import GmailAuthenticator
from instant_email_checker import InstantEmailChecker
from logger import cfo_logger

def email_callback(email_data):
    """Callback function when new emails are received."""
    print("\n=== NEW EMAIL DETECTED ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"From: {email_data.get('from', 'Unknown')}")
    print(f"Subject: {email_data.get('subject', 'No Subject')}")
    print("=========================\n")
    
    # Print email body preview
    body = email_data.get('body', '')
    if body:
        preview = body[:100] + '...' if len(body) > 100 else body
        print(f"Preview: {preview}")
    
    print("\nFull email data:")
    for key, value in email_data.items():
        if key != 'body':  # Skip printing the full body
            print(f"  {key}: {value}")
    print("=========================\n")

def main():
    """Main function to test the instant email checker."""
    print("Starting instant email checker test...")
    
    # Initialize Gmail authenticator (uses credentials.json and token.pickle)
    try:
        gmail_auth = GmailAuthenticator()
        
        # Create and start the instant email checker
        checker = InstantEmailChecker(
            gmail_auth=gmail_auth,
            check_frequency=2.0  # Check every 2 seconds
        )
        
        # Start checking
        started = checker.start_checking(email_callback)
        
        if started:
            print("Instant email checker started successfully")
            print("Checking for new emails every 2 seconds...")
            print("Send an email to the configured Gmail account to test")
            print("Press Ctrl+C to stop")
            
            try:
                # Keep the main thread alive
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nStopping instant email checker...")
                checker.stop_checking()
                print("Instant email checker stopped")
        else:
            print("Failed to start instant email checker")
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main() 