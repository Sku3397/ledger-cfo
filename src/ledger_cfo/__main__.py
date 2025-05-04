import os
import logging
import asyncio # Add asyncio
from datetime import datetime # Add datetime import
from flask import Flask, request, jsonify

# Import core and integration modules
from .core.config import get_secret
from .core.constants import Intent
from .core.database import init_db_engine, create_db_tables, get_db_session
from .core import crud # Import crud
from .core.logging_config import configure_logging # <-- Import new config function
from .integrations.gmail_api import (
    get_gmail_service,
    get_unread_emails,
    mark_email_as_read,
    send_email
)
from .integrations.qbo_api import (
    get_qbo_client,
    find_or_create_customer,
    find_item,
    create_invoice
)
from .processing.nlu import check_for_confirmation # Keep confirmation check
from .processing.llm_nlu import extract_intent_entities_llm # Import LLM NLU
from .processing.tasks import dispatch_task, execute_confirmed_action # Remove PENDING_CONFIRMATIONS import

# Configure logging using the new module
configure_logging()
logger = logging.getLogger(__name__) # Get logger after configuration

# Create Flask app
app = Flask(__name__)

# --- Initialize Database --- #
try:
    logger.info("Initializing Database Engine...")
    db_engine = init_db_engine()
    logger.info("Creating Database Tables (if they don't exist)...")
    # Ensure all models are imported before calling create_all
    from .models import PendingAction, CustomerCache # Make sure models are loaded
    from .core.database import Base
    Base.metadata.create_all(bind=db_engine) # Changed to use Base directly
    logger.info("Database initialization complete.")
except Exception as e:
    logger.critical(f"FATAL: Database initialization failed: {e}", exc_info=True)
    db_engine = None

# --- Helper: Format Result for Email ---
def format_result_for_email(result_dict: dict) -> str:
    """Formats the result dictionary into a readable string for email bodies."""
    if not result_dict:
        return "No details available."

    status = result_dict.get('status', 'Unknown')
    details = result_dict.get('result', {})
    error = result_dict.get('error')

    if status == 'EXECUTED':
        # Check for specific known result types
        if 'report_summary' in details:
            start = details.get('start_date', '')
            end = details.get('end_date', '')
            summary = details.get('report_summary', 'No summary available.')
            return f"Status: Success\nPeriod: {start} to {end}\n\n{summary}"
        elif 'purchase_id' in details: # Expense recorded
             formatted_details = "\n".join([f"  - {k.replace('_', ' ').title()}: {v}" for k, v in details.items()])
             return f"Status: Success\nDetails:\n{formatted_details}"
        elif 'invoice_id' in details: # Invoice created/sent
             formatted_details = "\n".join([f"  - {k.replace('_', ' ').title()}: {v}" for k, v in details.items()])
             return f"Status: Success\nDetails:\n{formatted_details}"
        # Generic success message
        elif isinstance(details, dict):
            formatted_details = "\n".join([f"  - {k.replace('_', ' ').title()}: {v}" for k, v in details.items()])
            return f"Status: Success\nDetails:\n{formatted_details}"
        else:
            return f"Status: Success\nDetails: {details}"
    elif status == 'FAILED':
        return f"Status: Failed\nError: {error or 'Unknown error'}"
    elif status == 'CONFIRMATION_SENT':
         pending_id = result_dict.get('pending_id', '')
         return f"Status: Action requires confirmation.\nPlease check your email for a message with ID ending in {pending_id[:8]}."
    else:
        # Catch-all for other statuses
        return f"Status: {status}\nDetails: {details or error or 'N/A'}"

# --- Health Check Endpoint --- #
@app.route("/health", methods=["GET"])
def health_check():
    """Basic health check endpoint for Cloud Run"""
    # Could add DB check later if needed
    return "OK", 200

# --- Core Email Processing Logic --- #
async def process_emails():
    """
    Main async function to fetch and process unread emails.
    Triggered by the Flask endpoint.
    Handles authorization, NLU (LLM), dispatching, confirmation flow, and DB caching.
    """
    logger.info("Starting async email processing cycle.")

    if not db_engine:
        logger.error("Database not initialized. Aborting email processing.")
        return "Error: Database connection failed.", 500

    # Get authorized sender from secrets
    try:
        allowed_sender = get_secret("ALLOWED_SENDER_EMAIL")
        app_sender_email = get_secret("SENDER_EMAIL")
    except Exception as e:
        logger.error(f"Configuration error fetching sender emails: {e}", exc_info=True)
        return "Error: Sender emails not configured.", 500

    if not allowed_sender or not app_sender_email:
        logger.error("Configuration error: Allowed sender or app sender email not found in Secret Manager.")
        return "Error: Sender emails not configured.", 500
    allowed_sender = allowed_sender.lower()
    logger.info(f"Authorized sender configured: {allowed_sender}")

    # Initialize Gmail Service
    gmail_service = get_gmail_service()
    if not gmail_service:
        logger.error("Failed to initialize Gmail service.")
        return "Error: Gmail service initialization failed.", 500

    # Fetch unread emails
    unread_messages = get_unread_emails(gmail_service, query='is:unread')

    if not unread_messages:
        logger.info("No new unread emails to process.")
        return "No new emails to process.", 200

    # Initialize QBO Client
    qbo_client = get_qbo_client()
    if not qbo_client:
        logger.error("Failed to initialize QBO client.")
        return "Error: QBO client initialization failed.", 500

    processed_count = 0
    skipped_count = 0
    error_count = 0
    confirmation_handled_count = 0

    # --- Prune Expired Actions Once Per Run --- #
    try:
        with get_db_session() as db:
            crud.prune_expired_actions(db)
            db.commit()
            logger.info("Pruned expired pending actions.")
    except Exception as prune_err:
        logger.error(f"Failed to prune expired actions: {prune_err}", exc_info=True)
        # Continue processing emails even if pruning fails

    for email_data in unread_messages:
        msg_id = email_data['id']
        sender_email = email_data.get('from', '').lower()
        email_subject = email_data.get('subject', '')
        email_body = email_data.get('body', '')

        # --- Sender Authorization Check --- #
        if sender_email != allowed_sender:
            logger.warning(f"Unauthorized email from {sender_email} (ID: {msg_id}). Skipping.")
            # Mark as read even if unauthorized to prevent reprocessing
            try:
                mark_email_as_read(gmail_service, msg_id)
            except Exception as mark_err:
                 logger.error(f"Failed to mark unauthorized email {msg_id} as read: {mark_err}")
            skipped_count += 1
            continue

        logger.info(f"Processing email ID {msg_id} from authorized sender.")

        # Add context for logging within this email's scope
        log_context = {'email_id': msg_id}

        # --- Database Session Scope --- #
        try:
            with get_db_session() as db_session:
                # --- Confirmation Check --- #
                confirmation_check_text = f"{email_subject} {email_body}"
                # Add context before NLU/Confirmation checks
                logger.info("Checking for confirmation reply.", extra=log_context)
                confirmation_result = check_for_confirmation(confirmation_check_text)

                if confirmation_result:
                    log_context['intent'] = confirmation_result.get('intent') # Add intent context
                    logger.info(f"Handling confirmation reply.", extra=log_context)
                    decision = confirmation_result['entities']['decision']
                    pending_uuid = confirmation_result['entities']['uuid']
                    log_context['task_id'] = pending_uuid # Add task/pending id context

                    # Look up pending action in DB
                    pending_action = crud.get_pending_action(db_session, pending_uuid)

                    if pending_action and pending_action.status == 'PENDING' and pending_action.expires_at > datetime.utcnow():
                        logger.info(f"Found valid pending action. Decision: {decision}", extra=log_context)
                        final_status = 'UNKNOWN'
                        exec_result = None

                        if decision == 'CONFIRM':
                            # Execute the confirmed action
                            logger.info("Executing confirmed action.", extra=log_context)
                            exec_result = execute_confirmed_action(
                                action_details=pending_action.action_details,
                                qbo_client=qbo_client,
                                gmail_service=gmail_service,
                                db_session=db_session # Session passed for potential updates
                            )
                            logger.info(f"Confirmed action execution result: {exec_result}")
                            final_status = exec_result.get('status', 'FAILED')
                            # Update DB status
                            crud.update_pending_action_status(db_session, pending_uuid, 'CONFIRMED')
                            db_session.commit() # Commit status update and execution changes

                        elif decision == 'CANCEL':
                            logger.info(f"Action {pending_uuid} cancelled by user.")
                            final_status = 'CANCELLED'
                            # Update DB status
                            crud.update_pending_action_status(db_session, pending_uuid, 'CANCELLED')
                            db_session.commit() # Commit status update
                        else:
                             logger.error(f"Invalid decision '{decision}' found for {pending_uuid}")
                             final_status = 'INVALID_DECISION'

                        # Send final status email
                        intent_val = pending_action.action_details.get('intent', 'Unknown Action')
                        final_subject = f"Action {final_status.capitalize()}: {intent_val} ({pending_uuid[:8]})"
                        if final_status == 'CONFIRMED' or final_status == 'EXECUTED': # Use EXECUTED if returned by task
                           final_body = f"The requested action '{intent_val}' with ID {pending_uuid} was confirmed and processed.\n\n{format_result_for_email(exec_result)}"
                        elif final_status == 'CANCELLED':
                           final_body = f"The requested action '{intent_val}' with ID {pending_uuid} was cancelled as requested."
                        elif final_status == 'FAILED': # Handle failure during execution
                            final_body = f"The requested action '{intent_val}' with ID {pending_uuid} was confirmed but failed during execution.\n\n{format_result_for_email(exec_result)}"
                        else:
                            final_body = f"There was an issue processing your confirmation decision ('{decision}') for action ID {pending_uuid}. Status: {final_status}"

                        try:
                            send_email(gmail_service, allowed_sender, app_sender_email, final_subject, final_body)
                            logger.info(f"Sent final status email for action {pending_uuid}")
                        except Exception as mail_err:
                            logger.error(f"Failed to send final status email for {pending_uuid}: {mail_err}", exc_info=True)
                            # Don't rollback DB changes if mail fails, action is complete/cancelled.

                        mark_email_as_read(gmail_service, msg_id)
                        confirmation_handled_count += 1
                        continue # Skip normal NLU/dispatch

                    else:
                        # Handle invalid/expired confirmation
                        logger.warning(f"Invalid or expired confirmation attempt for {pending_uuid}.", extra=log_context)
                        send_email(
                            gmail_service,
                            to=sender_email,
                            sender=app_sender_email,
                            subject=f"Re: {email_subject}",
                            body="Sorry, the confirmation link/ID seems invalid or has expired."
                        )
                        # Still update status if found but invalid
                        if pending_action:
                             crud.update_pending_action_status(db_session, pending_uuid, 'EXPIRED') # Or 'INVALID'
                             db_session.commit()
                        # error_count += 1 # Don't count as processing error, maybe confirmation error?
                        confirmation_handled_count += 1 # Count as handled
                        # Fall through to mark email as read

                else:
                    # --- Standard Intent Processing --- #
                    logger.info("No confirmation found, processing as new request.", extra=log_context)
                    # Extract intent and entities using LLM NLU
                    nlu_result = await extract_intent_entities_llm(email_body)

                    # Handle potential errors from LLM call itself
                    if 'error' in nlu_result:
                         logger.error(f"LLM NLU failed for email {msg_id}: {nlu_result['error']}", extra=log_context)
                         # Send specific error message back?
                         feedback_subject = f"Re: {email_subject}"
                         feedback_body = f"Sorry, I couldn't understand your request due to an internal issue analysing the email content (Error: {nlu_result['error']}). Please try rephrasing or contact support."
                         send_email(gmail_service, to=sender_email, sender=app_sender_email, subject=feedback_subject, body=feedback_body)
                         # Mark as read and continue to next email
                         mark_email_as_read(gmail_service, msg_id)
                         error_count += 1
                         continue # Skip further processing for this email

                    # Get intent and entities from LLM result
                    intent_str = nlu_result.get('intent', Intent.UNKNOWN.value) # LLM returns string
                    entities = nlu_result.get('entities', {})
                    log_context['intent'] = intent_str # Add intent context
                    logger.info(f"LLM NLU Result: Intent={intent_str}, Entities={entities}", extra=log_context)

                    # Convert intent string back to Enum if tasks.py expects it, otherwise pass string
                    try:
                        intent_enum = Intent(intent_str)
                    except ValueError:
                        logger.warning(f"LLM returned an intent string '{intent_str}' not in the Intent Enum. Defaulting to UNKNOWN.")
                        intent_enum = Intent.UNKNOWN

                    # Dispatch task based on intent
                    task_result = dispatch_task(
                        db_session=db_session,
                        intent=intent_enum, # Pass Enum member
                        entities=entities,
                        qbo_client=qbo_client,
                        gmail_service=gmail_service,
                        sender_email=sender_email, # Pass sender for confirmation replies
                        email_subject=email_subject, # Pass subject for replies
                        msg_id=msg_id # Pass msg_id for context
                    )

                    log_context['task_id'] = task_result.get('pending_id') or task_result.get('task_id') # Add ID context
                    logger.info(f"Task dispatch result: {task_result.get('status', 'UNKNOWN')}", extra=log_context)

                    # Send feedback/result email
                    feedback_subject = f"Re: {email_subject}"
                    feedback_body = format_result_for_email(task_result)
                    logger.info(f"Sending feedback email to {sender_email}", extra=log_context)
                    send_email(
                        gmail_service,
                        to=sender_email,
                        sender=app_sender_email,
                        subject=feedback_subject,
                        body=feedback_body
                    )

                # --- Mark Email as Read (after processing) --- #
                logger.info(f"Marking email {msg_id} as read.", extra=log_context)
                mark_email_as_read(gmail_service, msg_id)
                processed_count += 1
                if confirmation_result: confirmation_handled_count += 1

        except Exception as e:
            logger.error(f"Error processing email {msg_id}: {e}", exc_info=True, extra=log_context)
            error_count += 1
            # Optional: Try to mark as read even if error occurred
            try:
                mark_email_as_read(gmail_service, msg_id)
            except Exception as mark_err:
                logger.error(f"Failed to mark errored email {msg_id} as read: {mark_err}", extra=log_context)
            # Optional: Send an error notification email
            try:
                send_email(
                    gmail_service,
                    to=sender_email, # Send to user who sent it
                    sender=app_sender_email,
                    subject=f"Error Processing Your Request (Re: {email_subject})",
                    body=f"Sorry, there was an internal error processing your request from email ID {msg_id}. The technical team has been notified."
                )
            except Exception as notify_err:
                logger.error(f"Failed to send error notification email for {msg_id}: {notify_err}", extra=log_context)

    # --- Cycle Summary --- #
    summary = (
        f"Email processing cycle finished. "
        f"Processed: {processed_count}, Confirmations Handled: {confirmation_handled_count}, "
        f"Skipped: {skipped_count}, Errors: {error_count}."
    )
    logger.info(summary)
    return summary, 200

# --- Flask Endpoints --- #

# Health check endpoint
@app.route("/", methods=["GET"])
def index():
    return (
        jsonify(
            {
                "status": "healthy",
                "service": "ledger-cfo",
                "version": os.environ.get("K_REVISION", "local"),
            }
        ),
        200,
    )

# Add a POST handler for root path to prevent 405 errors
@app.route("/", methods=["POST"])
def root_post():
    logger.info("Received POST request on root path. Assuming Pub/Sub trigger.")
    # Potentially decode Pub/Sub message if needed
    # data = request.get_json()
    # print(f"Received Pub/Sub message: {data}")
    # Trigger processing
    summary, status_code = process_emails()
    return summary, status_code

# Endpoint for Pub/Sub push notifications (if used)
@app.route("/", methods=["POST"])
def root_post():
    logger.info("Received POST request on root path. Assuming Pub/Sub trigger.")
    # Potentially decode Pub/Sub message if needed
    # data = request.get_json()
    # print(f"Received Pub/Sub message: {data}")
    # Trigger processing
    summary, status_code = process_emails()
    return summary, status_code

# Endpoint to manually trigger email processing (for testing/cron)
@app.route('/tasks/process-emails', methods=['POST'])
async def task_process_emails():
    """Flask endpoint to trigger the async email processing function."""
    logger.info("Received request to process emails.")
    # Run the async function. Consider background task managers (like Celery) for long-running tasks
    # For Cloud Run + Scheduler, a direct await might be acceptable if timeout is sufficient
    try:
        summary, status_code = await process_emails()
        return summary, status_code
    except Exception as e:
        logger.error(f"Unhandled exception in task_process_emails: {e}", exc_info=True)
        return "Internal Server Error during email processing.", 500

# --- Main Execution --- #
if __name__ == "__main__":
    # Use environment variables for host and port (useful for Docker/Cloud Run)
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting Flask server on {host}:{port}")
    # Use debug=False for production/staging
    app.run(host=host, port=port, debug=False)
