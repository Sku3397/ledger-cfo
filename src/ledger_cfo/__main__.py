import os
import logging
import asyncio # Add asyncio
from datetime import datetime # Add datetime import
from flask import Flask, request, jsonify
import json
import subprocess
import time
from typing import Dict, List, Any, Optional, Tuple
import inspect

# Import core and integration modules
from .core.config import get_secret
from .core.constants import Intent
from .core.database import get_db_session, get_engine
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
from .processing.tasks import dispatch_task, execute_confirmed_action # Remove PENDING_CONFIRMATIONS import
from .processing import llm_orchestrator # Import the LLM orchestrator
from .integrations import qbo_api # Import the full module for tool access
from tenacity import retry, stop_after_attempt, wait_exponential # For ask_claude retry

# Configure logging using the new module
configure_logging()
logger = logging.getLogger(__name__) # Get logger after configuration

# --- Global Constants ---
REACT_MAX_STEPS = 10 # Maximum steps for the ReAct loop

# Create Flask app
app = Flask(__name__)

# --- Initialize Database --- #
# try:
#     logger.info("Initializing Database Engine...")
#     db_engine = init_db_engine()
#     logger.info("Creating Database Tables (if they don't exist)...")
#     # Ensure all models are imported before calling create_all
#     from .models import PendingAction, CustomerCache, ConversationHistory # Make sure models are loaded
#     from .core.database import Base
#     Base.metadata.create_all(bind=db_engine) # Changed to use Base directly
#     logger.info("Database initialization complete.")
# except Exception as e:
#     logger.critical(f"FATAL: Database initialization failed: {e}", exc_info=True)
#     db_engine = None

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

    # Load critical config/secrets - fail fast if unavailable
    # TODO: Add more robust config loading/validation
    allowed_sender = get_secret("ledger-cfo-allowed-sender")
    app_sender_email = get_secret("ledger-cfo-sender-email")

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
                    # --- Handle Confirmation Replies (Existing Logic) ---
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
                            logger.info(f"Confirmed action execution result: {exec_result}", extra=log_context)
                            final_status = exec_result.get('status', 'FAILED')
                            # Update DB status
                            crud.update_pending_action_status(db_session, pending_uuid, 'CONFIRMED')
                            db_session.commit() # Commit status update and execution changes

                        elif decision == 'CANCEL':
                            logger.info(f"Action {pending_uuid} cancelled by user.", extra=log_context)
                            final_status = 'CANCELLED'
                            # Update DB status
                            crud.update_pending_action_status(db_session, pending_uuid, 'CANCELLED')
                            db_session.commit() # Commit status update
                        else:
                             logger.error(f"Invalid decision '{decision}' found for {pending_uuid}", extra=log_context)
                             final_status = 'INVALID_DECISION'

                        # Send final status email
                        intent_val = pending_action.action_details.get('intent', 'Unknown Action')
                        final_subject = f"Action {final_status.capitalize()}: {intent_val} ({pending_uuid[:8]})"
                        if final_status == 'CONFIRMED' or final_status == 'EXECUTED': # Use EXECUTED if returned by task
                           final_body = f"The requested action '{intent_val}' with ID {pending_uuid} was confirmed and processed.\\n\\n{format_result_for_email(exec_result)}"
                        elif final_status == 'CANCELLED':
                           final_body = f"The requested action '{intent_val}' with ID {pending_uuid} was cancelled as requested."
                        elif final_status == 'FAILED': # Handle failure during execution
                            final_body = f"The requested action '{intent_val}' with ID {pending_uuid} was confirmed but failed during execution.\\n\\n{format_result_for_email(exec_result)}"
                        else:
                            final_body = f"There was an issue processing your confirmation decision ('{decision}') for action ID {pending_uuid}. Status: {final_status}"

                        try:
                            await send_email(gmail_service, allowed_sender, app_sender_email, final_subject, final_body)
                            logger.info(f"Sent final status email for action {pending_uuid}", extra=log_context)
                        except Exception as mail_err:
                            logger.error(f"Failed to send final status email for {pending_uuid}: {mail_err}", exc_info=True)
                            # Don't rollback DB changes if mail fails, action is complete/cancelled.

                        # Mark original confirmation email as read
                        mark_email_as_read(gmail_service, msg_id)
                        confirmation_handled_count += 1

                    elif pending_action and pending_action.status != 'PENDING':
                         logger.warning(f"Confirmation received for already processed action {pending_uuid} (Status: {pending_action.status}). Ignoring.", extra=log_context)
                         mark_email_as_read(gmail_service, msg_id)
                         skipped_count += 1
                    elif pending_action and pending_action.expires_at <= datetime.utcnow():
                        logger.warning(f"Confirmation received for expired action {pending_uuid}. Ignoring.", extra=log_context)
                        mark_email_as_read(gmail_service, msg_id)
                        skipped_count += 1
                    else: # No matching pending_uuid
                         logger.warning(f"Confirmation reply received, but no matching pending action found for UUID {pending_uuid}. Maybe expired/pruned or invalid.", extra=log_context)
                         mark_email_as_read(gmail_service, msg_id)
                         skipped_count += 1

                else:
                    # --- Handle New Requests via ReAct Loop ---
                    logger.info("New request detected. Initiating ReAct loop.", extra=log_context)
                    initial_request = f"Subject: {email_subject}\nBody: {email_body}"

                    # Create a unique ID for this conversation/task run
                    # Ensure ID is filesystem/URL safe if used elsewhere
                    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f') # Added microseconds
                    # Truncate msg_id if too long or contains weird chars?
                    safe_msg_id = msg_id.replace('<', '').replace('>', '') # Basic safety
                    conversation_id = f"{timestamp}-{safe_msg_id}"
                    log_context['conversation_id'] = conversation_id
                    logger.info(f"Starting ReAct loop for conversation {conversation_id}.", extra=log_context)

                    # === Call the ReAct Loop ===
                    react_result = await execute_react_loop(
                        initial_request=initial_request,
                        conversation_id=conversation_id,
                        qbo_client=qbo_client,
                        gmail_service=gmail_service,
                        db_session=db_session,
                        allowed_sender=allowed_sender, # Pass sender for final email
                        app_sender_email=app_sender_email # Pass sender for final email
                    )
                    # =========================

                    logger.info(f"ReAct loop finished for conversation {conversation_id}. Result status: {react_result.get('status')}", extra=log_context)

                    # Final result email is now handled within execute_react_loop itself.

                    # Mark original request email as read
                    try:
                        mark_email_as_read(gmail_service, msg_id)
                        # Increment counts based on ReAct loop result
                        if react_result.get('status', '').startswith("COMPLETED"):
                             processed_count += 1
                        else:
                             error_count += 1 # Count FAILED or MAX_STEPS as errors for summary
                    except Exception as mark_err:
                        logger.error(f"Failed to mark processed email {msg_id} as read: {mark_err}", exc_info=True)
                        error_count += 1 # Count as error if marking fails, regardless of react result

        except Exception as e:
            logger.error(f"Unhandled exception during processing of email {msg_id}: {e}", exc_info=True, extra=log_context)
            error_count += 1
            # Try to mark as read even on error to avoid loop, but log failure
            try:
                mark_email_as_read(gmail_service, msg_id)
            except Exception as mark_err:
                logger.error(f"Failed to mark errored email {msg_id} as read: {mark_err}", exc_info=True)
            # Send an error notification email (if possible)
            try:
                error_subject = f"FATAL Error Processing Email (ID: {msg_id})"
                error_body = f"An unexpected FATAL error occurred while processing email ID {msg_id}.\\n\\nThe ReAct loop may not have been initiated or completed cleanly.\\n\\nEmail Subject: {email_subject}\\n\\nError Details:\\n{e}\\n\\nPlease review the application logs for more information."
                # Use asyncio.to_thread if send_email is sync
                await send_email(gmail_service, allowed_sender, app_sender_email, error_subject, error_body)
                logger.info("Sent FATAL error notification email to director.")
            except Exception as mail_err:
                logger.error(f"Failed to send FATAL error notification email: {mail_err}", exc_info=True)

    # End of email processing loop
    total_processed = processed_count + confirmation_handled_count
    result_summary = f"Email processing cycle finished. Total Processed: {total_processed}, Skipped: {skipped_count}, Errors: {error_count}."
    logger.info(result_summary)
    return result_summary, 200

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
# Removing duplicate definition below
# @app.route("/", methods=["POST"])
# def root_post():
#     logger.info("Received POST request on root path. Assuming Pub/Sub trigger.")
#     # Potentially decode Pub/Sub message if needed
#     # data = request.get_json()
#     # print(f"Received Pub/Sub message: {data}")
#     # Trigger processing
#     summary, status_code = process_emails()
#     return summary, status_code

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

# --- Tool Execution Functions --- #

async def execute_qbo_tool(action_name: str, params: dict, qbo_client, db_session) -> Any:
    """Executes a specified QBO API tool/function."""
    # Map action_name (e.g., 'QBO_CREATE_INVOICE') to the actual qbo_api function
    # Add more mappings as needed
    func_mapping = {
        "QBO_FIND_CUSTOMERS_BY_DETAILS": qbo_api.find_customers_by_details,
        "QBO_GET_CUSTOMER_TRANSACTIONS": qbo_api.get_customer_transactions,
        "QBO_FIND_ESTIMATES": qbo_api.find_estimates,
        "QBO_GET_ESTIMATE_DETAILS": qbo_api.get_estimate_details,
        "QBO_CREATE_INVOICE": qbo_api.create_invoice,
        "QBO_SEND_INVOICE": qbo_api.send_invoice,
        "QBO_VOID_INVOICE": qbo_api.void_invoice,
        "QBO_FIND_ITEM": qbo_api.find_item,
        "QBO_CREATE_PURCHASE": qbo_api.create_purchase,
        # Add generate_pnl_report if re-enabled later
        # "QBO_GENERATE_PNL": qbo_api.generate_pnl_report,
    }

    target_func = func_mapping.get(action_name)
    if not target_func:
        logger.error(f"Unknown QBO tool action requested: {action_name}")
        return f"Error: Unknown QBO tool action '{action_name}'."

    # Prepare arguments, including the client and session where needed
    func_sig = inspect.signature(target_func)
    pass_params = {}
    if 'qbo_client' in func_sig.parameters or 'qbo' in func_sig.parameters:
        pass_params['qbo_client' if 'qbo_client' in func_sig.parameters else 'qbo'] = qbo_client
    if 'db_session' in func_sig.parameters or 'db' in func_sig.parameters:
        pass_params['db_session' if 'db_session' in func_sig.parameters else 'db'] = db_session

    # Add parameters from the LLM call
    pass_params.update(params)

    # Remove extra params not expected by the function
    final_params = {k: v for k, v in pass_params.items() if k in func_sig.parameters}

    logger.info(f"Executing QBO tool '{action_name}' with params: {final_params.keys()}")

    try:
        result = await target_func(**final_params)
        # Convert result to a JSON-serializable format if needed (e.g., for complex objects)
        # For now, assume functions return serializable dicts/lists/primitives
        logger.info(f"QBO tool '{action_name}' executed successfully.")
        return result
    except qbo_api.NotFoundError as nfe:
        logger.warning(f"QBO tool '{action_name}' failed: Object not found. Params: {params}. Error: {nfe}", exc_info=True)
        error_type = "ObjectNotFoundError"
        # Map specific function calls to Scenario 1 error categories
        if action_name == "QBO_FIND_CUSTOMERS_BY_DETAILS": error_type = "CustomerLookupError"
        elif action_name == "QBO_FIND_ESTIMATES": error_type = "EstimateLookupError"
        # Add other mappings if needed
        return f"Error: Tool {action_name} failed. Error Type: {error_type}. Details: {nfe}"
    except qbo_api.InvalidDataError as ide:
        logger.error(f"QBO tool '{action_name}' failed: Invalid data. Params: {params}. Error: {ide}", exc_info=True)
        error_type = "InvalidDataError"
        if action_name == "QBO_CREATE_INVOICE": error_type = "InvoiceCreationError"
        elif action_name == "QBO_SEND_INVOICE": error_type = "InvoiceSendError"
        # Add other mappings if needed
        return f"Error: Tool {action_name} failed. Error Type: {error_type}. Details: {ide}"
    except qbo_api.AuthenticationError as ae:
         logger.error(f"QBO tool '{action_name}' failed: Authentication error. Error: {ae}", exc_info=True)
         return f"Error: Tool {action_name} failed. Error Type: QBOApiError (Auth). Details: Authentication failed. Check credentials/connection."
    except qbo_api.RateLimitError as rle:
         logger.warning(f"QBO tool '{action_name}' failed: Rate limit exceeded. Error: {rle}", exc_info=True)
         return f"Error: Tool {action_name} failed. Error Type: QBOApiError (RateLimit). Details: Rate limit exceeded. Try again later."
    except qbo_api.QBOError as qe:
        logger.error(f"QBO tool '{action_name}' failed: General QBO error. Params: {params}. Error: {qe}", exc_info=True)
        # Generic QBO error, potentially map based on action if needed
        return f"Error: Tool {action_name} failed. Error Type: QBOApiError. Details: {qe}"
    except Exception as e:
        # Catch-all for unexpected errors during tool execution
        logger.error(f"Unexpected error executing tool '{action_name}'. Params: {params}. Error: {e}", exc_info=True)
        return f"Error: Tool {action_name} failed. Error Type: UnexpectedError. Details: {e}"

def execute_calculate_tool(expression: str) -> Any:
    """Executes simple arithmetic expressions using a safer method."""
    logger.info(f"Executing Calculate tool with expression: {expression}")
    try:
        # Use ast.literal_eval for safer evaluation of simple expressions
        # Allows numbers, strings, tuples, lists, dicts, booleans, None.
        # Does NOT allow arithmetic operations directly. Need a math parser.
        # Let's implement a very basic parser for +, -, *, /
        import operator
        import re

        # Basic validation
        allowed_chars = r'^[\d\.\s\+\-\*\/\(\)]+$'
        if not re.match(allowed_chars, expression):
            raise ValueError("Invalid characters in expression")

        # VERY basic and unsafe eval. Replace with a proper math expression parser library!
        # Example: asteval, numexpr, or implement shunting-yard algorithm
        # For now, sticking with eval but logging a major warning.
        logger.critical("SECURITY WARNING: Using eval() for calculation. Replace with a safe parser.")
        result = eval(expression, {"__builtins__": {}}, {}) # Slightly safer eval

        logger.info(f"Calculate tool result: {result}")
        return {"result": result}
    except Exception as e:
        logger.error(f"Calculate tool error evaluating '{expression}': {e}", exc_info=True)
        return {"error": f"Failed to evaluate expression '{expression}'. Details: {e}"}

async def execute_send_director_email(subject: str, body: str, email_client, allowed_sender, app_sender_email) -> Dict[str, Any]:
    """Sends an email to the configured director/allowed sender asynchronously."""
    logger.info(f"Executing Send Director Email tool. Subject: {subject}")
    try:
        # send_email is now async, so await it directly.
        sent_message_info = await send_email( # MODIFIED: Removed asyncio.to_thread, direct await
            email_client,      # This is the Gmail service instance (AsyncMock in test)
            allowed_sender,    # Send TO the director
            app_sender_email,  # Send FROM the app's email
            subject,
            body
        )
        
        if sent_message_info and sent_message_info.get('id'):
            logger.info(f"Send Director Email tool executed successfully. Message ID: {sent_message_info.get('id')}")
            return {"status": "Email sent successfully.", "message_id": sent_message_info.get('id')}
        else:
            logger.error(f"Send Director Email tool underlying send_email function reported failure. Subject: {subject}")
            return {"status": "Email send failed.", "error": "Internal email function failed to send or confirm sending."}

    except Exception as e:
        logger.error(f"Send Director Email tool error: {e}", exc_info=True)
        return {"status": "Email send failed.", "error": f"Failed to send email. Details: {str(e)}"}

# --- Ask Claude Helper --- #

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def run_ask_claude_sync(query: str, attempt: int) -> Optional[str]:
    """Synchronously runs the node ask_claude.cjs script with exponential backoff."""
    logger.info(f"Consulting Claude (Attempt {attempt}) for query: {query[:100]}...")
    # Use the correct path separator for Windows
    script_path = os.path.join(os.path.dirname(__file__), '..', '..', 'ask_claude.cjs') # Assuming script is at workspace root
    # Check if script exists
    if not os.path.exists(script_path):
        logger.critical(f"FATAL: 'ask_claude.cjs' script not found at expected path: {script_path}")
        raise FileNotFoundError(f"ask_claude.cjs not found at {script_path}")

    command = ["node", script_path, query] # Pass query as argument
    logger.info(f"Executing command: {' '.join(command)}")
    try:
        # Set appropriate cwd? Assuming workspace root is desired.
        workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False, # Don't raise exception on non-zero exit code, check manually
            timeout=120, # Add a timeout (2 minutes)
            cwd=workspace_root, # Run from workspace root
            shell=False # Avoid shell=True if possible
        )

        exit_code = process.returncode
        stdout = process.stdout.strip() if process.stdout else ""
        stderr = process.stderr.strip() if process.stderr else ""

        log_extra = {'exit_code': exit_code, 'stdout': stdout, 'stderr': stderr}

        if exit_code != 0:
            logger.error(f"ask_claude.cjs failed.", extra=log_extra)
            # Raise an exception to trigger tenacity retry
            raise Exception(f"ask_claude.cjs script failed (Code: {exit_code}): {stderr or stdout}")

        if not stdout:
             logger.warning("ask_claude.cjs returned empty stdout.", extra=log_extra)
             # Consider this a failure for retry?
             raise Exception("ask_claude.cjs returned empty output.")

        logger.info("Claude responded successfully.", extra=log_extra)
        # Look for the specific start marker if ask_claude.cjs adds one
        marker = "Claude Response:"
        if marker in stdout:
            return stdout.split(marker, 1)[1].strip()
        else:
            # Return the whole output if marker is not present
            logger.warning(f"Marker '{marker}' not found in Claude response. Returning full stdout.")
            return stdout

    except FileNotFoundError as fnf_err:
        # Specific check for Node.js might be needed
        logger.critical(f"FATAL: 'node' command not found or script missing. Error: {fnf_err}")
        raise # Stop retrying if the command cannot be run at all
    except subprocess.TimeoutExpired:
         logger.error("ask_claude.cjs script timed out after 120 seconds.")
         raise # Trigger retry
    except Exception as e:
        logger.error(f"Error running ask_claude.cjs: {e}", exc_info=True)
        raise # Re-raise to trigger retry

# --- ReAct Execution Loop --- #

async def execute_react_loop(initial_request: str, conversation_id: str, qbo_client, gmail_service, db_session, allowed_sender: str, app_sender_email: str):
    """
    Executes the ReAct (Reason + Act) loop for processing a user request.
    Uses an LLM to determine actions, executes them, and feeds back results.
    Includes error handling, Claude consultation, and conversation history management.
    """
    logger.info(f"Starting ReAct loop for Conversation ID: {conversation_id}")
    log_context = {'conversation_id': conversation_id}

    # Define available tools and map to execution functions
    tool_functions = {
        # These keys MUST EXACTLY MATCH the tool names in REACT_SYSTEM_PROMPT
        "QBO_FIND_CUSTOMERS_BY_DETAILS": lambda params: execute_qbo_tool("QBO_FIND_CUSTOMERS_BY_DETAILS", params, qbo_client, db_session),
        "QBO_GET_CUSTOMER_TRANSACTIONS": lambda params: execute_qbo_tool("QBO_GET_CUSTOMER_TRANSACTIONS", params, qbo_client, db_session),
        # "QBO_GET_INVOICE_DETAILS": lambda params: execute_qbo_tool("QBO_GET_INVOICE_DETAILS", params, qbo_client, db_session), # Example if you have it
        "QBO_GET_ESTIMATE_DETAILS": lambda params: execute_qbo_tool("QBO_GET_ESTIMATE_DETAILS", params, qbo_client, db_session),
        "QBO_FIND_ESTIMATES": lambda params: execute_qbo_tool("QBO_FIND_ESTIMATES", params, qbo_client, db_session),
        # "QBO_GET_RECENT_TRANSACTIONS": lambda params: execute_qbo_tool("QBO_GET_RECENT_TRANSACTIONS", params, qbo_client, db_session), # Example if you have it
        "QBO_CREATE_INVOICE": lambda params: execute_qbo_tool("QBO_CREATE_INVOICE", params, qbo_client, db_session),
        "QBO_SEND_INVOICE": lambda params: execute_qbo_tool("QBO_SEND_INVOICE", params, qbo_client, db_session),
        "QBO_VOID_INVOICE": lambda params: execute_qbo_tool("QBO_VOID_INVOICE", params, qbo_client, db_session),
        "QBO_RECORD_PAYMENT": lambda params: execute_qbo_tool("QBO_RECORD_PAYMENT", params, qbo_client, db_session),
        "CALCULATE": lambda params: execute_calculate_tool(**params), # Uses sync helper
        "SEND_DIRECTOR_EMAIL": lambda params: execute_send_director_email(**params, email_client=gmail_service, allowed_sender=allowed_sender, app_sender_email=app_sender_email),
        # Add other QBO tools as defined in REACT_SYSTEM_PROMPT
        # "QBO_GET_CUSTOMER_DETAILS": lambda params: execute_qbo_tool("QBO_GET_CUSTOMER_DETAILS", params, qbo_client, db_session), # Already covered by FIND if ID is known?
        # "QBO_CREATE_ESTIMATE": lambda params: execute_qbo_tool("QBO_CREATE_ESTIMATE", params, qbo_client, db_session),
    }
    available_tools = list(tool_functions.keys()) # This is for internal validation, LLM sees names from system prompt

    # Load conversation history or start new
    history = crud.get_conversation_history(db_session, conversation_id)
    if not history:
        history = [{"role": "user", "content": initial_request}]
        # Persist initial user request immediately
        try:
            crud.save_conversation_turn(db_session, conversation_id, history[0])
            db_session.commit() # Commit this initial turn
            logger.info("Saved initial user request to history.", extra=log_context)
        except Exception as db_err:
            logger.error(f"Failed to save initial user request: {db_err}", exc_info=True, extra=log_context)
            db_session.rollback() # Rollback if initial save fails
            # Don't proceed if we can't save history
            return {"status": "FAILED", "conversation_id": conversation_id, "error": "Database error saving initial request."}
        logger.info("No existing history found. Starting new conversation.", extra=log_context)
    else:
        logger.info(f"Loaded existing history with {len(history)} entries.", extra=log_context)

    # --- Loop Settings --- #
    max_steps = REACT_MAX_STEPS # Use the global constant
    current_step = 0
    prompt_tokens_total = 0
    completion_tokens_total = 0
    claude_consultations = 0
    max_claude_consultations = 10 # As per requirements

    final_answer = None
    error_message = None

    # --- Main ReAct Loop --- #
    for step in range(max_steps):
        logger.info(f"ReAct Step {step + 1}/{max_steps}", extra=log_context)

        try:
            # === Call LLM to determine next action ===
            # determine_next_action_llm now returns a tuple: (thought, action_name, action_params_or_error_dict)
            llm_thought, llm_action_name, llm_action_params_or_error = await llm_orchestrator.determine_next_action_llm(
                history,
            )
            # === End LLM Call ===

            # Construct the llm_response object for saving and processing
            if llm_action_name: # Successful tool call from LLM
                llm_response_to_save = {
                    "role": "assistant", # Or "model" - check consistency
                    "thought": llm_thought,
                    "action": llm_action_name,
                    "params": llm_action_params_or_error # This is action_params here
                }
            elif llm_action_params_or_error and isinstance(llm_action_params_or_error, dict) and "error" in llm_action_params_or_error:
                # This means an error occurred within determine_next_action_llm (e.g., API call failed)
                llm_response_to_save = {
                    "role": "assistant", # Or "system"/"error"
                    "thought": llm_thought if llm_thought else "Error in LLM decision making.",
                    "error_details": llm_action_params_or_error.get("error", "Unknown LLM error"),
                    "content": f"LLM determination failed: {llm_action_params_or_error.get('error', 'Unknown LLM error')}" # For history
                }
                # Set top-level error_message to propagate the failure
                error_message = f"LLM determination failed: {llm_action_params_or_error.get('error', 'Unknown LLM error')}"
            elif llm_thought and not llm_action_name and not llm_action_params_or_error:
                # LLM responded with thought but no action and no error (e.g. just content, might be FINISH without tool_call)
                llm_response_to_save = {
                    "role": "assistant",
                    "thought": llm_thought,
                    "content": llm_thought # Save thought as content if no action
                }
                # Potentially check if llm_thought implies FINISH here if that's a valid path
            else: # Unexpected return from determine_next_action_llm
                llm_response_to_save = {
                    "role": "assistant",
                    "thought": "LLM returned an unexpected response structure.",
                    "error_details": "Malformed response from LLM orchestrator.",
                    "content": "Malformed response from LLM orchestrator."
                }
                error_message = "Malformed response from LLM orchestrator."


            # Log and save the LLM's turn (or error state)
            try:
                # Ensure llm_response_to_save is always a dict here
                crud.save_conversation_turn(db_session, conversation_id, llm_response_to_save)
                db_session.commit()
            except Exception as db_err:
                logger.error(f"Failed to save LLM response/error turn: {db_err}", exc_info=True, extra=log_context)
                db_session.rollback()
                # Overwrite error_message because DB save is critical
                error_message = f"Database error during LLM response save: {db_err}"
                break # Exit loop on DB error

            # If an error was determined from LLM call, break the loop
            if error_message and "LLM determination failed" in error_message:
                 logger.error(f"Breaking ReAct loop due to LLM determination failure: {error_message}")
                 break
            if error_message and "Malformed response from LLM orchestrator" in error_message:
                logger.error(f"Breaking ReAct loop due to malformed LLM response: {error_message}")
                break


            history.append(llm_response_to_save) # Add the (potentially modified) llm_response to history

            # Use the parsed components from determine_next_action_llm
            thought = llm_thought
            action = llm_action_name
            action_params = llm_action_params_or_error if isinstance(llm_action_params_or_error, dict) and not ("error" in llm_action_params_or_error) else {}

            # Check for FINISH action (which now comes from the 'action' variable)
            # The 'response' for FINISH should be part of action_params if provided by LLM.
            llm_final_answer = None
            if action == "FINISH":
                llm_final_answer = action_params.get("response") # Assuming 'response' is a key in params for FINISH

            logger.info(f"LLM Thought: {thought}", extra=log_context)

            # --- Check for Final Answer --- #
            if action == "FINISH" and llm_final_answer:
                logger.info(f"LLM provided Final Answer: {llm_final_answer}", extra=log_context)
                final_answer = llm_final_answer
                break # Exit loop successfully

            # --- Check for Action --- #
            if not action:
                logger.error("LLM did not provide an action or final answer (Step {step + 1}).", extra=log_context)
                # === Claude Consultation for missing action ===
                if claude_consultations < max_claude_consultations:
                    claude_query = f"The assistant is stuck in a ReAct loop for request '{initial_request[:100]}...'. Current history: {json.dumps(history)}. The last LLM response lacked an action or final answer: {json.dumps(llm_response_to_save)}. What should be the next observation or action?"
                    try:
                        logger.info("Consulting Claude for missing action.", extra=log_context)
                        claude_suggestion = await asyncio.to_thread(run_ask_claude_sync, claude_query, claude_consultations + 1)
                        claude_consultations += 1
                        if claude_suggestion:
                            logger.info(f"Claude suggested: {claude_suggestion}", extra=log_context)
                            # Add Claude's suggestion as an observation for the LLM
                            observation = {"role": "tool", "content": f"Observation: Received external guidance suggesting: {claude_suggestion}"}
                            try:
                                crud.save_conversation_turn(db_session, conversation_id, observation)
                                db_session.commit()
                                history.append(observation)
                                logger.info("Added Claude suggestion as observation.", extra=log_context)
                                continue # Go to next loop iteration with Claude's input
                            except Exception as db_err:
                                logger.error(f"Failed to save Claude suggestion turn: {db_err}", exc_info=True, extra=log_context)
                                db_session.rollback()
                                error_message = "Database error saving Claude suggestion."
                                break # Exit loop on DB error
                        else:
                            logger.warning("Claude consultation (missing action) did not yield a suggestion.", extra=log_context)
                            error_message = "LLM failed to decide on a next step, and Claude consultation failed."
                            break # Exit loop if Claude fails
                    except Exception as claude_err:
                        logger.error(f"Error consulting Claude (missing action): {claude_err}", exc_info=True, extra=log_context)
                        error_message = f"LLM failed to decide on a next step. Error consulting Claude: {claude_err}"
                        break # Exit loop if Claude errors out
                else:
                    logger.error(f"Max Claude consultations ({max_claude_consultations}) reached after missing action.", extra=log_context)
                    error_message = "LLM failed to decide on a next step, and max Claude consultations reached."
                    break # Exit loop
                # === End Claude Consultation ===
                # break # Break is handled inside conditional logic now

            if action not in tool_functions:
                logger.error(f"LLM chose an invalid tool: {action}", extra=log_context)
                observation_content = f"Error: Tool '{action}' is not available. Available tools are: {', '.join(available_tools)}"
            else:
                # === Execute the chosen tool ===
                logger.info(f"Executing Tool: {action}, Params: {action_params}", extra=log_context)
                tool_function = tool_functions[action]
                try:
                    # Execute async or sync tool function appropriately
                    # Check if the lambda target is async (which execute_qbo_tool and execute_send_director_email are)
                    # Note: This check on the lambda itself isn't reliable. We know which helpers are async.
                    if action.startswith("QBO_") or action == "SEND_DIRECTOR_EMAIL":
                        tool_result = await tool_function(action_params)
                    elif action == "CALCULATE":
                        # Run synchronous tool functions in a thread pool executor
                        tool_result = await asyncio.to_thread(tool_function, action_params)
                    else:
                        # Fallback for potentially unknown sync tools? Or assume all known tools are handled.
                        logger.warning(f"Executing unknown or potentially synchronous tool {action} directly.")
                        tool_result = tool_function(action_params)

                    logger.info(f"Tool {action} Result (type: {type(tool_result)}): {str(tool_result)[:200]}...", extra=log_context)

                    # === Format Observation based on Tool Result ===
                    if isinstance(tool_result, dict) and tool_result.get("error"):
                        error_detail = tool_result["error"]
                        logger.error(f"Tool {action} execution failed: {error_detail}", extra=log_context)
                        observation_content = f"Error executing tool '{action}': {error_detail}"
                        # === Claude Consultation for tool error ===
                        if claude_consultations < max_claude_consultations:
                            claude_query = f"The assistant encountered an error executing tool '{action}' with params {json.dumps(action_params)} for request '{initial_request[:100]}...'. Error: {error_detail}. Current history: {json.dumps(history[-4:])}. How should the assistant proceed or retry?"
                            try:
                                logger.info("Consulting Claude for tool error.", extra=log_context)
                                claude_suggestion = await asyncio.to_thread(run_ask_claude_sync, claude_query, claude_consultations + 1)
                                claude_consultations += 1
                                if claude_suggestion:
                                    logger.info(f"Claude suggested for tool error: {claude_suggestion}", extra=log_context)
                                    # Append suggestion to the observation for the LLM
                                    observation_content += f"\n\nExternal guidance suggests: {claude_suggestion}"
                                else:
                                    logger.warning("Claude consultation (tool error) did not yield a suggestion.", extra=log_context)
                                    # Proceed with just the error observation
                            except Exception as claude_err:
                                logger.error(f"Error consulting Claude (tool error): {claude_err}", exc_info=True, extra=log_context)
                                # Proceed with just the error observation even if Claude fails
                                observation_content += "\n\n(Failed to get external guidance)"
                        else:
                            logger.error(f"Max Claude consultations ({max_claude_consultations}) reached. Reporting tool error directly.", extra=log_context)
                            observation_content += "\n\n(Max external consultations reached)"
                        # === End Claude Consultation ===
                    else:
                        # Format successful result for the LLM
                        # Ensure result is serializable and reasonably sized for history
                        try:
                            # Handle specific object types if necessary (e.g., QBO SDK objects)
                            # Our execute_qbo_tool should return serializable data, but double-check
                            if isinstance(tool_result, (dict, list)):
                                result_str = json.dumps(tool_result)
                            elif isinstance(tool_result, (str, int, float, bool, type(None))):
                                result_str = str(tool_result) # Simple types as string
                            else:
                                # Attempt to convert other types (like SDK objects if they slip through)
                                logger.warning(f"Tool {action} returned non-standard type: {type(tool_result)}. Converting to string.")
                                result_str = str(tool_result)

                            # Save observation to history
                            observation_to_save = f"Observation: {result_str}"
                            
                            # --- COMMENTING OUT THIS BLOCK ---
                            # MAX_OBSERVATION_LENGTH = 4000  # Max length for observation to avoid overly long history
                            # if len(observation_to_save) > MAX_OBSERVATION_LENGTH:
                            #     logger.warning(f"Truncating long observation from tool {action_name}. Original length: {len(observation_to_save)}")
                            #     observation_to_save = observation_to_save[:MAX_OBSERVATION_LENGTH] + "... (truncated)"
                            # --- END COMMENTED BLOCK ---
                            
                            logger.info(f"Saving Observation: {observation_to_save[:200]}...") # Log a preview
                        except TypeError as serial_err:
                            logger.error(f"Failed to serialize result from tool {action_name}: {serial_err}", exc_info=True)
                            # Ensure observation_content is set for the error case if it's used later
                            observation_content = f"System Error: Failed to serialize result from tool {action_name}. Type was {type(tool_result)}."
                            tool_success = False # Ensure this is set if relying on it

                except Exception as tool_exec_err:
                    logger.error(f"Unexpected exception executing tool {action}: {tool_exec_err}", exc_info=True, extra=log_context)
                    observation_content = f"System Error: Unexpected error during execution of tool '{action}': {tool_exec_err}"
                    # === Claude Consultation for unexpected tool error ===
                    if claude_consultations < max_claude_consultations:
                        claude_query = f"The assistant encountered an unexpected system error while trying to execute tool '{action}' with params {json.dumps(action_params)} for request '{initial_request[:100]}...'. Error: {tool_exec_err}. Current history: {json.dumps(history[-4:])}. How should the assistant proceed?"
                        try:
                            logger.info("Consulting Claude for unexpected tool error.", extra=log_context)
                            claude_suggestion = await asyncio.to_thread(run_ask_claude_sync, claude_query, claude_consultations + 1)
                            claude_consultations += 1
                            if claude_suggestion:
                                logger.info(f"Claude suggested for system error: {claude_suggestion}", extra=log_context)
                                observation_content += f"\n\nExternal guidance suggests: {claude_suggestion}"
                            else:
                                logger.warning("Claude consultation (system error) did not yield a suggestion.", extra=log_context)
                        except Exception as claude_err:
                            logger.error(f"Error consulting Claude (system error): {claude_err}", exc_info=True, extra=log_context)
                            observation_content += "\n\n(Failed to get external guidance)"
                    else:
                        logger.error(f"Max Claude consultations ({max_claude_consultations}) reached after system error.", extra=log_context)
                        observation_content += "\n\n(Max external consultations reached)"
                    # === End Claude Consultation ===
                # === End Tool Execution ===

            # === Save Observation ===
            # Determine role for observation (tool result/error) - use 'assistant' as per prompt guidance? or 'tool'?
            # LangChain uses 'tool'. Let's try 'tool'.
            observation = {"role": "tool", "content": observation_content}
            logger.info(f"Saving Observation: {observation_content[:100]}...", extra=log_context)
            try:
                crud.save_conversation_turn(db_session, conversation_id, observation)
                db_session.commit()
            except Exception as db_err:
                logger.error(f"Failed to save observation turn: {db_err}", exc_info=True, extra=log_context)
                db_session.rollback()
                error_message = "Database error during observation save."
                break # Exit loop on DB error
            history.append(observation)
            # === End Save Observation ===

        except Exception as loop_err:
            logger.error(f"Exception in ReAct loop step {step + 1}: {loop_err}", exc_info=True, extra=log_context)
            # === Claude Consultation for loop error ===
            if claude_consultations < max_claude_consultations:
                claude_query = f"The ReAct loop encountered an unexpected error on step {step+1} for request '{initial_request[:100]}...'. Error: {loop_err}. Current history: {json.dumps(history[-4:])}. How should the assistant proceed or recover?"
                try:
                    logger.info("Consulting Claude for loop error.", extra=log_context)
                    claude_suggestion = await asyncio.to_thread(run_ask_claude_sync, claude_query, claude_consultations + 1)
                    claude_consultations += 1
                    if claude_suggestion:
                        logger.info(f"Claude suggested recovery for loop error: {claude_suggestion}", extra=log_context)
                        # Add Claude's suggestion as an observation to potentially guide the LLM
                        observation = {"role": "tool", "content": f"Observation: Encountered loop error ({loop_err}). External guidance suggests: {claude_suggestion}"}
                        try:
                            crud.save_conversation_turn(db_session, conversation_id, observation)
                            db_session.commit()
                            history.append(observation)
                            logger.info("Added Claude recovery suggestion as observation.", extra=log_context)
                            continue # Try to continue the loop based on Claude's advice
                        except Exception as db_err:
                            logger.error(f"Failed to save Claude recovery suggestion turn: {db_err}", exc_info=True, extra=log_context)
                            db_session.rollback()
                            error_message = f"Loop error occurred ({loop_err}), and failed to save Claude recovery suggestion."
                            break # Exit loop on DB error
                    else:
                        logger.warning("Claude consultation (loop error) did not yield a recovery suggestion.", extra=log_context)
                        error_message = f"An internal error occurred ({loop_err}), and Claude consultation failed."
                        break # Exit loop if Claude fails
                except Exception as claude_err:
                    logger.error(f"Error consulting Claude (loop error): {claude_err}", exc_info=True, extra=log_context)
                    error_message = f"An internal error occurred ({loop_err}). Error consulting Claude: {claude_err}"
                    break # Exit loop if Claude errors out
            else:
                logger.error(f"Max Claude consultations ({max_claude_consultations}) reached after loop error.", extra=log_context)
                error_message = f"An internal error occurred ({loop_err}), and max Claude consultations reached."
                break # Exit loop
            # === End Claude Consultation ===
            # break # Break is handled inside conditional logic now

    # --- Loop End --- #
    final_result = {}
    email_subject_prefix = f"Re: Task {conversation_id[:8]}"

    # Determine final status and send email notification
    if final_answer:
        logger.info(f"ReAct loop completed successfully for {conversation_id}. Final Answer: {final_answer}", extra=log_context)
        final_result = {"status": "COMPLETED", "conversation_id": conversation_id, "result": final_answer}
        email_subject = f"{email_subject_prefix} - Success"
        email_body = f"Task completed successfully.\n\nFinal Answer:\n{final_answer}\n\nFull conversation history stored with ID: {conversation_id}"
    elif error_message:
        logger.error(f"ReAct loop failed for {conversation_id}. Error: {error_message}", extra=log_context)
        final_result = {"status": "FAILED", "conversation_id": conversation_id, "error": error_message}
        email_subject = f"{email_subject_prefix} - Failed"
        email_body = f"The task failed to complete.\n\nError: {error_message}\n\nFull conversation history stored with ID: {conversation_id}. Please review logs."
    else: # Max steps reached
        logger.warning(f"ReAct loop reached max steps ({max_steps}) without a final answer for {conversation_id}.", extra=log_context)
        final_result = {"status": "MAX_STEPS_REACHED", "conversation_id": conversation_id, "error": "Processing timed out (reached maximum steps)."}
        email_subject = f"{email_subject_prefix} - Incomplete (Max Steps)"
        email_body = f"The task did not complete within the maximum allowed steps ({max_steps}).\n\nIt may require adjustment or intervention.\n\nFull conversation history stored with ID: {conversation_id}. Please review logs."

    # Send final status email
    try:
        await execute_send_director_email(
            subject=email_subject,
            body=email_body,
            email_client=gmail_service,
            allowed_sender=allowed_sender,
            app_sender_email=app_sender_email
        )
        logger.info("Sent final status email to director.", extra=log_context)
    except Exception as mail_err:
        logger.error(f"Failed to send final status email: {mail_err}", exc_info=True, extra=log_context)
        # Update status to reflect mail failure if needed
        if final_result.get("status") == "COMPLETED":
            final_result["status"] = "COMPLETED_MAIL_FAILED"
            final_result["error"] = f"Task completed but failed to send final email: {mail_err}"
        elif final_result.get("status") == "FAILED":
             final_result["status"] = "FAILED_MAIL_FAILED"
             final_result["error"] = f"{final_result.get('error', '')}. Additionally, failed to send failure notification email: {mail_err}"
        # else: MAX_STEPS_REACHED, error already logged

    # Final commit attempt (most turns committed individually)
    try:
        db_session.commit()
    except Exception as commit_err:
        logger.error(f"Final database commit failed (changes might be lost if previous commits failed): {commit_err}", exc_info=True, extra=log_context)
        db_session.rollback()

    return final_result

# --- Main Execution ---
if __name__ == "__main__":
    setup_logging() # Apply logging configuration if needed
    logger.info("Ledger CFO Agent Starting...")

    # TODO: Replace with actual trigger mechanism (e.g., email polling, API endpoint)
    # For now, using a hardcoded example request for Scenario 1
    example_request_scenario_1 = """
    Hi Ledger,

    Please send the final invoice to Mr. Test for the job at 123 Test St.
    We sent an initial estimate (Estimate #est_mr_test_1, $25,296.00) which he accepted.
    He already paid the initial deposit invoice (Invoice #inv_mr_test_initial, $7,588.80).
    Calculate the remaining balance and send him a new invoice for that amount. Make sure it references the original estimate if possible.

    Thanks,
    Director
    """

    # Initialize DB (if needed globally or called elsewhere)
    logger.info("Initializing Database...")
    init_db()

    # Run the main loop
    try:
        result = asyncio.run(execute_react_loop(example_request_scenario_1))
        logger.info(f"ReAct Loop Result: {result}")
    except Exception as main_err:
        logger.critical(f"Unhandled exception during main execution: {main_err}", exc_info=True)

    logger.info("Ledger CFO Agent Finished.")
