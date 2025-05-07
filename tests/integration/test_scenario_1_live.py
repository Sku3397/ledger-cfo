import pytest
import logging
import os
from datetime import datetime, timezone
from dotenv import load_dotenv, find_dotenv
import asyncio # Added for async fixture/cleanup
import pytest_asyncio
from unittest.mock import AsyncMock, patch
import http.client as http_client # Added for debugging

# Adjust imports based on actual project structure
# Assumes the package is installed or src is in PYTHONPATH
from ledger_cfo.integrations.qbo_api import (
    get_qbo_client,
    find_customers_by_details,
    get_invoice_details, # Assuming this function exists or adapt to get details
    void_invoice,
    QBOError,
    NotFoundError,
    InvalidDataError
)
# Import the main orchestrator/logic function (adjust if needed)
from ledger_cfo.__main__ import execute_react_loop # Or the relevant entry point

# Corrected DB imports
from ledger_cfo.core.database import get_db_session
from ledger_cfo.processing import llm_orchestrator # Import the orchestrator
from ledger_cfo.integrations import qbo_api # Import the module for tool access

# Configure logging for the test
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Test Configuration ---
# Use environment variables or a config file for sensitive data in a real scenario
# For this example, we assume credentials are handled by get_qbo_client via secrets
LIVE_CUSTOMER_NAME = "Mr. Test" # Target customer for the live test

# Define the callback type hint for clarity (optional)
from typing import Callable, Tuple, Optional
from quickbooks.objects.invoice import Invoice
from quickbooks.client import QuickBooks # For type hinting qbo_client

SetInvoiceIdCallback = Callable[[str], None]
QBOFixtureReturnType = Tuple[Optional[QuickBooks], SetInvoiceIdCallback]

# --- Pytest Fixture for QBO Client and Cleanup ---
@pytest_asyncio.fixture(scope="function")
async def live_qbo_client_and_cleanup():
    """
    Provides an authenticated QBO client for live integration tests
    and ensures cleanup (deleting created entities) afterwards.
    Loads credentials from .env file.
    """
    load_dotenv()  # Ensure environment variables are loaded

    # Verify credentials are set in environment, but don't pass them directly
    client_id = os.getenv("QBO_CLIENT_ID")
    client_secret = os.getenv("QBO_CLIENT_SECRET")
    refresh_token = os.getenv("QBO_REFRESH_TOKEN")
    realm_id = os.getenv("QBO_REALM_ID")
    environment = os.getenv("QBO_ENVIRONMENT", "production") # Check environment variable

    if not all([client_id, client_secret, refresh_token, realm_id]):
        pytest.fail(
            "Missing one or more QBO credentials in .env file for live tests: "
            "QBO_CLIENT_ID, QBO_CLIENT_SECRET, QBO_REFRESH_TOKEN, QBO_REALM_ID"
        )

    if environment.lower() != 'production':
         pytest.skip("Skipping live test: QBO_ENVIRONMENT is not set to 'production'")


    qbo_client = None
    created_customer_id = None
    created_invoice_id = None

    # --- BEGIN HTTP DEBUG LOGGING ---
    print("\n--- Enabling HTTP Debug Logging ---")
    http_client.HTTPConnection.debuglevel = 1 # Print request/response lines
    logging.basicConfig(level=logging.DEBUG) # Ensure basicConfig is called with level
    logging.getLogger().setLevel(logging.DEBUG) # Ensure root logger captures debug
    requests_log = logging.getLogger("requests.packages.urllib3")
    # Also log httplib2 if it's used by intuitlib under the hood
    httplib2_log = logging.getLogger("httplib2")
    httplib2_log.setLevel(logging.DEBUG)
    httplib2_log.propagate = True
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True
    print("DEBUG: Enabled HTTPConnection debuglevel and requests/httplib2 logging.")
    # --- END HTTP DEBUG LOGGING ---

    try:
        # Initialize the client (this is where the refresh might happen)
        # get_qbo_client should read env vars itself now
        print("\n--- Initializing QBO Client (expecting it to read env vars) ---")
        qbo_client = get_qbo_client() # Call without arguments
        print("--- QBO Client Initialization Attempt Finished ---")

        if qbo_client is None:
             pytest.fail("get_qbo_client() returned None. Initialization failed. Check logs for details (e.g., missing secrets).")

        # Check if authentication succeeded (e.g., refresh token worked)
        # The QuickBooks client might perform initial auth/refresh upon first API call,
        # or potentially during init depending on the library version.
        # We add an explicit check or a test call if necessary.
        # Let's assume for now init implies readiness, but add a check:
        # try:
        #     # A lightweight call to check authentication
        #     company_info = await _sync_qbo_call(CompanyInfo.get, qbo_client.company_id, qb=qbo_client)
        #     logger.info(f"QBO Connection successful. Company Name: {company_info.CompanyName}")
        #     print(f"--- QBO Client Initialized and Authenticated (Company: {company_info.CompanyName}) ---")
        # except Exception as auth_check_err:
        #     logger.error(f"QBO client authentication check failed: {auth_check_err}", exc_info=True)
        #     # This is where the original 401 might appear if refresh fails!
        #     # We expect the HTTP debug logs to show the request just before this potential failure.
        #     pytest.fail(f"QBO client initialized but failed authentication check: {auth_check_err}")

        # Simplified check (assuming python-quickbooks handles auth state)
        # This might not be sufficient if refresh happens lazily.
        # if not qbo_client.is_authenticated(): # is_authenticated might not exist or work this way
        #     pytest.fail("QBO client initialized but is not authenticated. Refresh likely failed.")

        print("--- QBO Client Initialized (Authentication status may depend on first API call) ---")

        # Yield the client and a dictionary to store created IDs
        created_ids = {"customer_id": None, "invoice_id": None}
        yield qbo_client, created_ids
        created_customer_id = created_ids.get("customer_id")
        created_invoice_id = created_ids.get("invoice_id")

    except Exception as e:
        print(f"\n--- Exception during QBO client setup or test execution: {e} ---")
        # Log the exception details, including the type and message
        logging.exception("Error during QBO client setup or test execution:")
        pytest.fail(f"QBO client setup or test failed: {e}")

    finally:
        # --- BEGIN HTTP DEBUG LOGGING DISABLE (Optional but good practice) ---
        print("\n--- Disabling HTTP Debug Logging ---")
        http_client.HTTPConnection.debuglevel = 0
        logging.getLogger().setLevel(logging.WARNING) # Reset logger level
        requests_log.setLevel(logging.WARNING)
        httplib2_log.setLevel(logging.WARNING)
        print("DEBUG: Disabled HTTPConnection debuglevel and requests/httplib2 logging.")
        # --- END HTTP DEBUG LOGGING DISABLE ---

        print("\n--- Starting Cleanup ---")
        # Remove .is_authenticated() check, just ensure client exists
        if qbo_client:
            # Cleanup phase: Delete created entities in reverse order (invoice then customer)
            if created_invoice_id:
                print(f"Attempting to delete Invoice ID: {created_invoice_id}")
                try:
                    invoice_to_delete = await qbo_client.get_invoice(created_invoice_id)
                    if invoice_to_delete:
                        delete_payload = {
                            "Id": created_invoice_id,
                            "SyncToken": invoice_to_delete.get("SyncToken", "0"), # Required for deletion
                        }
                        # Use delete_invoice for invoices
                        success = await qbo_client.delete_invoice(delete_payload)
                        if success:
                             print(f"Successfully deleted Invoice ID: {created_invoice_id}")
                        else:
                             print(f"Failed to delete Invoice ID: {created_invoice_id} (delete_invoice returned False)")
                    else:
                        print(f"Invoice ID {created_invoice_id} not found for deletion.")

                except QBOMethodNotAllowedError as e:
                     print(f"Skipping invoice deletion due to QBOMethodNotAllowedError: {e}")
                     # This might happen if the entity type doesn't support standard delete,
                     # or if there's a configuration issue. For invoices, it should work.
                except Exception as e:
                    print(f"Error deleting Invoice ID {created_invoice_id}: {e}")
                    logging.exception(f"Error during Invoice cleanup for ID {created_invoice_id}:")


            if created_customer_id:
                print(f"Attempting to delete Customer ID: {created_customer_id}")
                try:
                    customer_to_delete = await qbo_client.get_customer(created_customer_id)
                    if customer_to_delete:
                        # Customers are made inactive, not deleted via API usually
                        update_payload = {
                            "Id": created_customer_id,
                            "SyncToken": customer_to_delete.get("SyncToken", "0"),
                            "Active": False,
                        }
                        updated_customer = await qbo_client.update_customer(update_payload)
                        if updated_customer and not updated_customer.get("Active"):
                            print(f"Successfully deactivated Customer ID: {created_customer_id}")
                        else:
                            print(f"Failed to deactivate Customer ID: {created_customer_id}")
                    else:
                         print(f"Customer ID {created_customer_id} not found for deactivation.")

                except QBOMethodNotAllowedError as e:
                     print(f"Skipping customer deactivation due to QBOMethodNotAllowedError: {e}")
                     # This might happen if the entity type doesn't support standard delete/update,
                     # or if there's a configuration issue.
                except Exception as e:
                    print(f"Error deactivating Customer ID {created_customer_id}: {e}")
                    logging.exception(f"Error during Customer cleanup for ID {created_customer_id}:")
        else:
             print("Skipping cleanup: QBO client not available or not authenticated.")
        print("--- Cleanup Finished ---")

@pytest.fixture(scope="function")
async def mock_gmail_service():
    """Provides a mock Gmail service for tests that don't need live Gmail interaction."""
    mock_service = AsyncMock()
    logger.info("Provided mock_gmail_service.")
    return mock_service

@pytest_asyncio.fixture(scope="function")
async def mock_get_db_session_in_react_loop():
    """Mocks get_db_session specifically for the react loop to control DB interactions."""
    mock_session = AsyncMock()

    async def mock_session_context_manager(*args, **kwargs):
        logger.info("mock_get_db_session_in_react_loop: __aenter__ called")
        return mock_session

    async def mock_exit_session_context_manager(*args, **kwargs):
        logger.info("mock_get_db_session_in_react_loop: __aexit__ called")
        pass

    mock_db_session_manager = AsyncMock()
    mock_db_session_manager.__aenter__ = AsyncMock(side_effect=mock_session_context_manager)
    mock_db_session_manager.__aexit__ = AsyncMock(side_effect=mock_exit_session_context_manager)
    
    # Patch where get_db_session is DEFINED and would be imported from.
    # This is ledger_cfo.core.database.get_db_session
    # Modules like __main__.py or crud.py (if they were to call it directly, which they don't for the loop) would import it from there.
    # The test calls execute_react_loop, which itself is called from within the sync_react_wrapper
    # which uses a `with get_db_session()` call. This get_db_session is imported in __main__.py from .core.database.
    # So, patching it at its source (ledger_cfo.core.database.get_db_session) is the most robust way.

    # The test setup calls execute_react_loop. The execute_react_loop itself
    # is wrapped by sync_react_wrapper which calls `with get_db_session() as db_session:`
    # This `get_db_session` is imported in `__main__.py` from `.core.database`.
    # Thus, we need to patch `ledger_cfo.__main__.get_db_session` if the test structure directly calls
    # a function in `__main__` that uses its local import of `get_db_session`.
    # Or, more broadly, patch `ledger_cfo.core.database.get_db_session` as that's the source.
    # Let's try patching the source first, and then specific import locations if needed.

    # Patching the source should cover all usages.
    with patch("ledger_cfo.core.database.get_db_session", return_value=mock_db_session_manager) as mock_db_getter:
        logger.info("mock_get_db_session_in_react_loop activated. ledger_cfo.core.database.get_db_session is patched.")
        yield mock_db_getter # The test itself doesn't use this yielded value directly.
    
    logger.info("mock_get_db_session_in_react_loop deactivated.")

# --- Live Integration Test ---
# Use pytest.mark to potentially skip live tests by default
@pytest.mark.live # Add a custom marker for live tests
@pytest.mark.asyncio # Mark test as async
async def test_final_invoice_live_mr_test(
    live_qbo_client_and_cleanup, 
    mock_gmail_service,
    mock_get_db_session_in_react_loop
):
    qbo_client, cleanup_ids = live_qbo_client_and_cleanup
    assert qbo_client is not None, "QBO Client fixture failed to initialize."

    # --- Get Customer ID (Live) ---
    LIVE_CUSTOMER_NAME = "Mr. Test" # Consistent with .env expectations for live test data
    customers = []
    try:
        logger.info(f"Attempting to find customer: {LIVE_CUSTOMER_NAME} in live QBO...")
        # Call with keyword arguments to avoid ambiguity and match the refactored function
        customers = await find_customers_by_details(query=LIVE_CUSTOMER_NAME, qbo_client=qbo_client)

        if not customers or not isinstance(customers, list) or len(customers) == 0:
            pytest.fail(f"Customer '{LIVE_CUSTOMER_NAME}' not found in QBO live environment. Please ensure this customer exists.")
        if len(customers) > 1:
            logger.warning(f"Multiple customers found for '{LIVE_CUSTOMER_NAME}'. Using the first one: {customers[0]}")
        
        live_customer_id = customers[0]["Id"]
        cleanup_ids["customer_id_found"] = live_customer_id # For potential later inspection if needed
        logger.info(f"Found customer '{LIVE_CUSTOMER_NAME}' with ID: {live_customer_id}")

    except Exception as e:
        logger.error(f"Unexpected error finding customer '{LIVE_CUSTOMER_NAME}': {e}", exc_info=True)
        pytest.fail(f"Unexpected error finding customer: {e}")

    # 2. Construct the initial request simulating an email/user input
    initial_request_text = f"Please prepare the final invoice for {LIVE_CUSTOMER_NAME}. They have completed their project."
    # Use timezone-aware UTC now
    conversation_id = f"live_test_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    logger.info(f"Executing core logic (ReAct loop) for conversation ID: {conversation_id}")

    # --- Prepare for ReAct Loop ---
    allowed_sender = "test@example.com"
    app_sender_email = "app@example.com"
    final_result = None

    # 3. Execute the core ReAct loop logic
    try:
         def sync_react_wrapper():
             with get_db_session() as db_session:
                try:
                    return asyncio.run(execute_react_loop(
                        initial_request=initial_request_text,
                        conversation_id=conversation_id,
                        qbo_client=qbo_client,
                        gmail_service=mock_gmail_service,
                        db_session=db_session,
                        allowed_sender=allowed_sender,
                        app_sender_email=app_sender_email
                    ))
                except RuntimeError as e:
                    if "cannot be called from a running event loop" in str(e):
                        # Handle case where asyncio.run cannot be used because loop is running
                        # This is complex. A different approach might be needed, e.g. refactoring
                        # get_db_session or execute_react_loop structure.
                        logger.error("Cannot run nested asyncio loop. Refactoring needed.", exc_info=True)
                        raise e # Re-raise the error
                    else:
                         raise # Re-raise other RuntimeErrors

         final_result = await asyncio.to_thread(sync_react_wrapper)

         logger.info(f"Core logic execution completed. Final result type: {type(final_result)}, value: {str(final_result)[:200]}...") # Log type and snippet

    except Exception as react_err:
         logger.error(f"Error during core logic (ReAct loop) execution: {react_err}", exc_info=True)
         pytest.fail(f"Core logic (execute_react_loop) failed during execution: {react_err}", pytrace=True)

    # 4. Verification Step (Example: Check if an invoice was created)
    # This part depends heavily on what `execute_react_loop` actually returns or does.
    # Assuming final_result might contain the invoice ID or status.
    assert final_result is not None, "ReAct loop did not return a result."

    # Example: If final_result is expected to be the created invoice ID as a string
    if isinstance(final_result, str) and final_result.startswith("invoice_id:"):
        invoice_id_str = final_result.split(":")[1].strip()
        assert invoice_id_str.isdigit(), f"Expected numeric invoice ID, got: {invoice_id_str}"
        invoice_id = int(invoice_id_str)
        logger.info(f"ReAct loop reported creating invoice ID: {invoice_id}")
        cleanup_ids["invoice_id_found"] = str(invoice_id) # Pass ID to fixture for cleanup
    else:
        # Adapt assertion based on actual expected outcome of execute_react_loop
        pytest.fail(f"ReAct loop did not return the expected invoice ID format. Result: {final_result}")

    # Optional: Fetch the created invoice from QBO and verify details
    if invoice_id:
        logger.info(f"Verifying details of created invoice ID: {invoice_id} in QBO...")
        try:
            # Ensure get_invoice_details is awaited if it's async
            invoice_details = await get_invoice_details(qbo_client, str(invoice_id))
            assert invoice_details is not None, f"Invoice {invoice_id} not found in QBO after creation."
            logger.info(f"Successfully fetched invoice {invoice_id} for verification.")
            # Add more specific assertions based on expected invoice content
            assert str(invoice_details.get('CustomerRef', {}).get('value')) == str(live_customer_id), f"Invoice customer ID mismatch."
            # Example: Check total amount (adjust based on expected value)
            # assert invoice_details.get('TotalAmt') == EXPECTED_AMOUNT, "Invoice total amount mismatch."
        except Exception as verify_err:
             logger.error(f"Error verifying invoice {invoice_id} in QBO: {verify_err}", exc_info=True)
             pytest.fail(f"Failed to verify created invoice {invoice_id} in QBO: {verify_err}")

    logger.info("Test execution part completed successfully.") 