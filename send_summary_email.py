import smtplib
from email.message import EmailMessage

# --- Email Configuration ---
# TODO: Replace with actual sender retrieval (e.g., from config or get_secret)
SENDER_EMAIL = "agent@example.com" # Placeholder
RECIPIENT_EMAIL = "hello@757handy.com"
SMTP_SERVER = "localhost" # Assuming local SMTP server for sending
SUBJECT = "Phase 3 Development Summary - Ledger CFO Agent"

# --- Email Body ---
BODY = """
Subject: Phase 3 Development Summary - Ledger CFO Agent

Phase 3 development for the Ledger CFO agent is complete. Here's a summary of the key accomplishments:

1.  **Confirmation State Migration:** The confirmation workflow no longer uses an in-memory dictionary. Pending actions are now stored in the PostgreSQL database (`pending_actions` table) with expiry times. Expired actions are automatically pruned.

2.  **Expense Recording:**
    *   Implemented `RECORD_EXPENSE` intent.
    *   Added QBO function `create_purchase` to record expenses.
    *   Integrated database caching for Vendors (`VendorCache`) and Chart of Accounts (`AccountCache`) to minimize API calls.
    *   Enhanced NLU to extract vendor names, amounts, categories, and descriptions for expenses.
    *   This action requires user confirmation via email reply.

3.  **P&L Report Generation:**
    *   Implemented `GET_REPORT_PNL` intent.
    *   Added QBO function `generate_pnl_report`.
    *   Enhanced NLU to parse date ranges (e.g., "last month", "this year", "YYYY-MM-DD to YYYY-MM-DD").
    *   Formatted report results for clear email replies.
    *   This action does *not* require confirmation.

4.  **Improved User Feedback:** Refined email replies for successes, failures, confirmations, and unknown intents, providing more specific details.

5.  **Dockerfile:** Created a `Dockerfile` to enable containerized deployment using Gunicorn, suitable for Google Cloud Run.

6.  **Initial Unit Tests:** Added basic unit tests for the NLU components (`extract_intent_entities`, `check_for_confirmation`) using `pytest`.

7.  **Documentation:** Updated `README.md` to reflect the new features and setup instructions.

The codebase is now more robust and feature-rich.
"""

# --- Sending Logic --- 
# Note: This assumes a local SMTP server is running and accessible.
# For production, use the actual gmail_api.send_email function.
try:
    msg = EmailMessage()
    msg.set_content(BODY)
    msg['Subject'] = SUBJECT
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL

    print(f"Attempting to send email summary to {RECIPIENT_EMAIL} from {SENDER_EMAIL} via {SMTP_SERVER}...")
    # Example using smtplib (replace with gmail_api.send_email if available and configured)
    with smtplib.SMTP(SMTP_SERVER) as s:
        s.send_message(msg)
    print("Email sent successfully (using smtplib example).")

except Exception as e:
    print(f"Error sending email using smtplib: {e}")
    print("--- Email Content ---")
    print(BODY)
    print("--- End Email Content ---") 