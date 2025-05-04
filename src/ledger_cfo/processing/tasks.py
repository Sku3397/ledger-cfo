import logging
import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from quickbooks.objects.invoice import Invoice
from quickbooks.objects.purchase import Purchase

from ..core.constants import Intent
from ..integrations import qbo_api, gmail_api
from ..core.config import get_secret
from ..core import crud # Import crud module

logger = logging.getLogger(__name__)

# --- Helper Functions ---

def _format_confirmation_email_body(action_details: dict, pending_id: str) -> str:
    """Formats the body of the confirmation email."""
    intent_value = action_details.get('intent') # Intent might be stored as string now
    entities = action_details.get('entities', {})
    body = f"Please confirm the following action:\n\n"
    body += f"Action: {intent_value}\n"
    body += f"Details:\n"
    for key, value in entities.items():
        body += f"  - {key.replace('_', ' ').title()}: {value}\n"
    body += f"\nTo proceed, reply to this email with:\nCONFIRM {pending_id}\n"
    body += f"\nTo cancel, reply with:\nCANCEL {pending_id}"
    return body

# --- Task Execution Functions (Placeholders/Dispatch Logic) ---

def execute_create_invoice(entities: dict, qbo_client, db_session: Session) -> dict:
    """Placeholder or actual call to create an invoice in QBO."""
    logger.info(f"Attempting to execute CREATE_INVOICE with entities: {entities}")
    customer_name = entities.get('customer_name')
    amount = entities.get('amount')
    item_desc = entities.get('item_description', 'Service') # Default item description

    if not customer_name or not amount:
        logger.error("Missing customer name or amount for creating invoice.")
        return {'status': 'FAILED', 'error': 'Missing required details: customer_name, amount'}

    try:
        # 1. Find or create customer (uses cache)
        customer = qbo_api.find_or_create_customer(customer_name, db_session, qbo_client)
        if not customer:
            return {'status': 'FAILED', 'error': f'Could not find or create customer: {customer_name}'}

        # 2. Create Invoice object (using placeholder values for item/account refs)
        # TODO: Need proper Item and Account references from QBO or config
        line_detail = {
            "Amount": float(amount),
            "DetailType": "SalesItemLineDetail",
            "SalesItemLineDetail": {
                "ItemRef": {"value": "1"} # Placeholder - Fetch/config real item ID
            },
            "Description": item_desc
        }
        invoice = Invoice()
        invoice.CustomerRef = customer['qbo_customer_ref'] # Assuming find_or_create_customer returns this
        invoice.Line = [line_detail]
        # Add due date if present
        # if entities.get('due_date'): ... parse and add ...

        created_invoice = qbo_api.create_invoice(invoice, qbo_client)
        logger.info(f"Successfully created invoice ID: {created_invoice.Id}")
        # Include customer email if found for potential follow-up
        customer_email = customer.get('email_address')
        result_detail = {
            'invoice_id': created_invoice.Id,
            'qbo_link': created_invoice.get_link(),
            'customer_name': customer.get('display_name'),
            'customer_email': customer_email,
            'amount': float(amount)
        }
        return {'status': 'EXECUTED', 'result': result_detail}

    except Exception as e:
        logger.error(f"Failed to execute CREATE_INVOICE: {e}", exc_info=True)
        return {'status': 'FAILED', 'error': str(e)}

def execute_send_invoice(entities: dict, qbo_client, gmail_service, db_session: Session) -> dict:
    """Placeholder or actual call to send an invoice."""
    logger.info(f"Attempting to execute SEND_INVOICE with entities: {entities}")
    invoice_id = entities.get('invoice_id')
    customer_email = entities.get('customer_email')

    if not invoice_id:
        # Attempt to create first if no ID provided (linking CREATE and SEND)
        logger.warning("No invoice_id provided for SEND_INVOICE, attempting to create first.")
        create_result = execute_create_invoice(entities, qbo_client, db_session)
        if create_result['status'] != 'EXECUTED':
            return create_result # Propagate failure
        invoice_id = create_result['result']['invoice_id']
        customer_email = create_result['result']['customer_email']
        logger.info(f"Created invoice {invoice_id} before sending.")

    if not customer_email:
        # Try to fetch email from customer cache if not passed/created
        try:
            inv = qbo_api.get_invoice(invoice_id, qbo_client)
            if inv and inv.CustomerRef:
                cust_ref_id = inv.CustomerRef.value
                cust_cache = crud.get_customer_by_qbo_id(db_session, cust_ref_id)
                if cust_cache:
                    customer_email = cust_cache.email_address
                    logger.info(f"Fetched customer email {customer_email} from cache for invoice {invoice_id}")
        except Exception as e:
            logger.warning(f"Could not fetch customer email for invoice {invoice_id}: {e}", exc_info=True)

    if not customer_email:
        logger.error(f"No customer email address found or provided for sending invoice {invoice_id}.")
        return {'status': 'FAILED', 'error': f'Missing customer email to send invoice {invoice_id}'}

    try:
        # Using QBO send
        success = qbo_api.send_invoice(invoice_id, qbo_client, customer_email)
        if success:
             logger.info(f"Successfully sent invoice ID: {invoice_id} via QBO to {customer_email}")
             return {'status': 'EXECUTED', 'result': {'invoice_id': invoice_id, 'sent_to': customer_email, 'sent': True}}
        else:
             logger.warning(f"QBO API indicated send failed for invoice ID: {invoice_id}")
             return {'status': 'FAILED', 'error': f'QBO failed to send invoice {invoice_id}'}

    except Exception as e:
        logger.error(f"Failed to execute SEND_INVOICE for ID {invoice_id}: {e}", exc_info=True)
        return {'status': 'FAILED', 'error': str(e)}

def execute_find_customer(entities: dict, qbo_client, db_session: Session) -> dict:
    """Executes finding a customer, leveraging the cache."""
    logger.info(f"Attempting to execute FIND_CUSTOMER with entities: {entities}")
    customer_name = entities.get('customer_name')
    if not customer_name:
        return {'status': 'FAILED', 'error': 'Missing required entity: customer_name'}

    try:
        customer_info = qbo_api.find_or_create_customer(customer_name, db_session, qbo_client, create_if_not_found=False)
        if customer_info:
            logger.info(f"Found customer: {customer_info}")
            # Format result slightly for clarity
            result_detail = {
                'qbo_customer_id': customer_info.get('qbo_customer_id'),
                'display_name': customer_info.get('display_name'),
                'email_address': customer_info.get('email_address'),
                'last_synced': customer_info.get('last_synced_at').isoformat() if customer_info.get('last_synced_at') else None
            }
            return {'status': 'EXECUTED', 'result': result_detail}
        else:
            logger.info(f"Customer not found: {customer_name}")
            return {'status': 'EXECUTED', 'result': {'message': f'Customer "{customer_name}" not found.'}}
    except Exception as e:
        logger.error(f"Failed to execute FIND_CUSTOMER: {e}", exc_info=True)
        return {'status': 'FAILED', 'error': str(e)}

def execute_record_expense(entities: dict, qbo_client, db_session: Session) -> dict:
    """Executes recording an expense (Purchase) in QBO using qbo_api.create_purchase."""
    logger.info(f"Attempting to execute RECORD_EXPENSE with entities: {entities}")
    vendor_name = entities.get('vendor_name')
    amount = entities.get('amount') # Should be Decimal from NLU
    category = entities.get('category')
    description = entities.get('description')
    # payment_account_name could be added to NLU or defaulted here
    payment_account_name = entities.get('payment_account', "Checking") # Default

    if not vendor_name:
        return {'status': 'FAILED', 'error': 'Missing required entity: vendor_name'}
    if not amount or not isinstance(amount, Decimal) or amount <= 0:
        return {'status': 'FAILED', 'error': 'Missing or invalid required entity: amount (must be positive number)'}

    try:
        # Call the qbo_api function which handles vendor/account lookup and creation
        result_dict = qbo_api.create_purchase(
            qbo=qbo_client,
            db=db_session,
            vendor_name=vendor_name,
            amount=float(amount), # QBO API might expect float
            category_name=category,
            description=description,
            payment_account_name=payment_account_name
        )
        # The result_dict from create_purchase already contains status and result/error
        return result_dict

    except Exception as e:
        logger.error(f"Unexpected error in execute_record_expense task: {e}", exc_info=True)
        return {'status': 'FAILED', 'error': f'Unexpected error recording expense: {str(e)}'}

def execute_get_report_pnl(entities: dict, qbo_client) -> dict:
    """Executes fetching a PNL report from QBO using parsed dates."""
    logger.info(f"Attempting to execute GET_REPORT_PNL with entities: {entities}")
    start_date = entities.get('start_date')
    end_date = entities.get('end_date')
    raw_date_range = entities.get('date_range_raw', 'Unknown Range') # Get raw string for logging

    if not start_date or not end_date:
        logger.error(f"Missing parsed start_date or end_date for raw range: '{raw_date_range}'.")
        return {'status': 'FAILED', 'error': f'Could not understand date range: \'{raw_date_range}\'. Try "last month", "this year", or "YYYY-MM-DD to YYYY-MM-DD".'}

    try:
        report_summary = qbo_api.generate_pnl_report(qbo_client, start_date, end_date)
        logger.info(f"Successfully fetched P&L report for range: {start_date} to {end_date}")
        return {
            'status': 'EXECUTED',
            'result': {
                 'report_summary': report_summary,
                 'start_date': start_date,
                 'end_date': end_date
             }
        }
    except Exception as e:
        logger.error(f"Failed to execute GET_REPORT_PNL for {start_date} to {end_date}: {e}", exc_info=True)
        return {'status': 'FAILED', 'error': f'Error generating P&L report: {str(e)}'}

# --- Main Dispatch Function ---

def dispatch_task(nlu_result: dict, qbo_client, gmail_service, db_session: Session, original_email_id: str) -> dict:
    """
    Routes the NLU result to the appropriate execution function or triggers confirmation
    by storing details in the PendingAction database table.
    """
    intent = nlu_result.get('intent', Intent.UNKNOWN)
    entities = nlu_result.get('entities', {})

    logger.info(f"Dispatching task for intent: {intent.value}")

    # Actions requiring confirmation
    confirmation_required_intents = [
        Intent.CREATE_INVOICE,
        Intent.SEND_INVOICE,
        Intent.RECORD_EXPENSE
    ]

    if intent in confirmation_required_intents:
        pending_id = str(uuid.uuid4())
        action_details_to_store = {
            'intent': intent.value, # Store enum value (string)
            'entities': entities,
            'original_email_id': original_email_id
        }
        try:
            # Store in database
            crud.create_pending_action(db=db_session, action_id=pending_id, details=action_details_to_store, email_id=original_email_id)
            db_session.commit() # Commit the pending action creation
            logger.info(f"Stored pending action {pending_id} in DB for intent {intent.value}.")

            # Send confirmation email
            confirmation_body = _format_confirmation_email_body(action_details_to_store, pending_id)
            sender_email = get_secret("SENDER_EMAIL")
            recipient_email = get_secret("ALLOWED_SENDER_EMAIL")
            subject = f"Confirmation Required: {intent.value} Request ({pending_id[:8]})"

            gmail_api.send_email(
                service=gmail_service,
                to=recipient_email,
                sender=sender_email,
                subject=subject,
                body_text=confirmation_body
            )
            logger.info(f"Sent confirmation email for pending action {pending_id} to {recipient_email}")
            return {'status': 'CONFIRMATION_SENT', 'pending_id': pending_id}
        except Exception as e:
            logger.error(f"Failed during confirmation process for {intent.value}: {e}", exc_info=True)
            db_session.rollback() # Rollback DB changes if email fails
            # Attempt to clean up DB entry if it was partially created?
            # crud.delete_pending_action(db_session, pending_id) might be needed if flush occurred before error
            # For simplicity, rely on prune_expired_actions later.
            return {'status': 'FAILED', 'error': f'Failed to create pending action or send confirmation: {str(e)}'}

    elif intent == Intent.FIND_CUSTOMER:
        # Execute directly (no confirmation)
        result = execute_find_customer(entities, qbo_client, db_session)
        db_session.commit() # Commit any potential cache updates within the function
        return result
    elif intent == Intent.GET_REPORT_PNL:
        # Execute directly (no confirmation)
        result = execute_get_report_pnl(entities, qbo_client)
        # No DB changes expected here, so no commit needed
        return result
    elif intent == Intent.UNKNOWN:
        logger.warning("Intent UNKNOWN, cannot dispatch task.")
        return {'status': 'FAILED', 'error': 'Could not understand the request.'}
    else:
        logger.error(f"Unhandled intent: {intent.value}")
        return {'status': 'FAILED', 'error': f'Action {intent.value} is not implemented yet.'}

# --- Confirmed Action Executor ---
def execute_confirmed_action(action_details: dict, qbo_client, gmail_service, db_session: Session) -> dict:
    """Executes an action that was previously confirmed via email reply."""
    intent_str = action_details.get('intent')
    entities = action_details.get('entities', {})
    logger.info(f"Executing confirmed action: Intent={intent_str}, Entities={entities}")

    # Default result
    execution_result = {'status': 'FAILED', 'error': 'Confirmed intent not mapped to execution'}
    intent = None

    # Validate intent string
    try:
        intent = Intent(intent_str)
    except ValueError:
        logger.error(f"Invalid intent '{intent_str}' found in confirmed action details.")
        execution_result['error'] = f'Invalid intent \'{intent_str}\' in confirmed action'
        return execution_result # Return early if intent is invalid

    # Execute based on valid intent
    try:
        if intent == Intent.CREATE_INVOICE:
            execution_result = execute_create_invoice(entities, qbo_client, db_session)
        elif intent == Intent.SEND_INVOICE:
            execution_result = execute_send_invoice(entities, qbo_client, gmail_service, db_session)
        elif intent == Intent.FIND_CUSTOMER:
            # FIND_CUSTOMER likely doesn't need confirmation, but handle if it was added
            execution_result = execute_find_customer(entities, qbo_client, db_session)
        elif intent == Intent.RECORD_EXPENSE:
            execution_result = execute_record_expense(entities, qbo_client, db_session)
        elif intent == Intent.GET_REPORT_PNL:
            # GET_REPORT_PNL likely doesn't need confirmation
            execution_result = execute_get_report_pnl(entities, qbo_client)
        elif intent == Intent.CREATE_ESTIMATE: # New
            execution_result = execute_create_estimate(entities, qbo_client, db_session)
        elif intent == Intent.RECORD_PAYMENT: # New
            execution_result = execute_record_payment(entities, qbo_client, db_session)
        else:
            # This case should ideally not be hit if confirmation logic is sound
            logger.error(f"Unhandled confirmed intent: {intent.value}")
            execution_result['error'] = f'Execution logic for confirmed intent {intent.value} not found.'

        # Commit/Rollback considerations (as noted in previous attempt)
        # Relying on sub-functions for transaction management for now.

    except Exception as e:
        logger.error(f"Exception during confirmed action execution for intent {intent_str}: {e}", exc_info=True)
        # Ensure rollback happens if an exception occurs during execution
        try:
            db_session.rollback()
            logger.info(f"Rolled back DB session due to exception in confirmed action {intent_str}")
        except Exception as rb_err:
            logger.error(f"Failed to rollback DB session after exception in confirmed action {intent_str}: {rb_err}")
        execution_result = {'status': 'FAILED', 'error': f'Exception during execution: {str(e)}'}

    logger.info(f"Confirmed action execution result: {execution_result}")
    return execution_result