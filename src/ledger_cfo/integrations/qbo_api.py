import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
import datetime
import time
from cachetools import TTLCache
import asyncio # Added for async/sync execution
import os

from quickbooks.objects.customer import Customer
from quickbooks.objects.invoice import Invoice
from quickbooks.objects.estimate import Estimate # Added
from quickbooks.objects.payment import Payment # Added
from quickbooks.objects import salesreceipt # Added - Revised import
from quickbooks.objects.detailline import SalesItemLine, SalesItemLineDetail, AccountBasedExpenseLine, AccountBasedExpenseLineDetail
from quickbooks.objects.item import Item
from quickbooks.objects.account import Account
from quickbooks.objects.term import Term
from quickbooks.objects.purchase import Purchase
from quickbooks.objects.vendor import Vendor
from quickbooks.objects.company_info import CompanyInfo # Import CompanyInfo
from quickbooks.exceptions import QuickbooksException, AuthorizationException, ValidationException

# from quickbooks.auth import AuthClient # Reverted - Assuming this path is correct if library installed properly
# from quickbooks import AuthClient # Revised?
from quickbooks.client import QuickBooks # Import the main client
from intuitlib.client import AuthClient # Import the correct AuthClient

# Assuming get_secret is correctly defined in core.config
from ..core.config import get_secret
from ..core import crud # Import CRUD operations
# Removed unused model imports (handled by crud)
# from ..models.customer import CustomerCache
# from ..models.vendor_cache import VendorCache
# from ..models.account_cache import AccountCache

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Custom Exception Hierarchy ---
class QBOError(Exception):
    """Base exception for Ledger CFO QBO integration errors."""
    def __init__(self, message, original_exception=None):
        super().__init__(message)
        self.original_exception = original_exception

class AuthenticationError(QBOError): pass
class NotFoundError(QBOError): pass
class InvalidDataError(QBOError): pass
class RateLimitError(QBOError): pass

# --- Caching ---
# Evaluate cache TTLs. Customer/Vendor/Account data might be stable longer.
# Transactional data (invoices, estimates, searches) should have shorter TTLs.
customer_cache = TTLCache(maxsize=100, ttl=3600)  # 1 hour
vendor_cache = TTLCache(maxsize=100, ttl=3600) # 1 hour
account_cache = TTLCache(maxsize=1, ttl=3600) # Cache the whole CoA for 1 hour (use force_refresh)
estimate_cache = TTLCache(maxsize=200, ttl=600)   # 10 minutes
transaction_cache = TTLCache(maxsize=500, ttl=300) # 5 minutes
details_cache = TTLCache(maxsize=200, ttl=600) # Cache individual txn details for 10 mins
search_cache = TTLCache(maxsize=100, ttl=120) # Cache search results for 2 minutes

logger = logging.getLogger(__name__)

# --- Helper Functions ---

def _handle_qbo_sdk_error(e, context="QBO API call"):
    """Maps specific python-quickbooks exceptions to custom exceptions."""
    error_message = f"Error during {context}: {e}"
    logger.error(error_message, exc_info=True)

    # Check for specific QBO exceptions first
    if isinstance(e, AuthorizationException):
        raise AuthenticationError(f"QBO authentication/authorization failed: {e}", original_exception=e) from e
    # elif isinstance(e, NotFoundException): # Handled below by error code check
    #     raise NotFoundError(f"QBO object not found or inactive: {e}", original_exception=e) from e
    elif isinstance(e, ValidationException):
        raise InvalidDataError(f"QBO data validation failed: {e}", original_exception=e) from e
    # elif isinstance(e, RateLimitExceededException): # Handled below by error code check
    #    raise RateLimitError(f"QBO rate limit exceeded: {e}", original_exception=e) from e
    elif isinstance(e, QuickbooksException):
        # Check for specific error codes within the base QuickbooksException
        error_code = getattr(e, 'error_code', None)
        # Safely get detail, handling if it's a string or missing
        detail_attr = getattr(e, 'detail', None)
        if isinstance(detail_attr, dict):
            http_status_code = detail_attr.get('status', None)
        else:
            # If detail is not a dict (e.g., string, None), status code is unknown from detail
            http_status_code = None

        # Log the raw detail if it wasn't a dict, for debugging
        if not isinstance(detail_attr, dict) and detail_attr is not None:
            logger.warning(f"QBO Exception detail was not a dictionary: {detail_attr}")

        if error_code and 600 <= int(error_code) < 700:
            # Treat QBO 6xx error codes as NotFound
            raise NotFoundError(f"QBO object not found or inactive (Error code: {error_code}): {e}", original_exception=e) from e
        elif http_status_code == 429 or (error_code and error_code == '8012'): # Check HTTP 429 or QBO specific code
            # Treat as RateLimitError
            raise RateLimitError(f"QBO rate limit exceeded (HTTP Status: {http_status_code}, Error code: {error_code}): {e}", original_exception=e) from e
        else:
            # Catch-all for other QBO-specific errors
            raise QBOError(f"A QBO specific error occurred (Error code: {error_code}): {e}", original_exception=e) from e
    else:
        # For non-QBO exceptions (network errors, etc.)
        raise QBOError(f"An unexpected error occurred: {e}", original_exception=e) from e

def _generate_cache_key(*args, **kwargs):
    """Generates a cache key from function arguments."""
    # Consider sorting kwargs for consistency if order might change
    return str(args) + str(sorted(kwargs.items()))

def _sync_qbo_call(func, *args, **kwargs):
    """Helper to run synchronous QBO calls in a thread."""
    # Ensure qb client is passed correctly, often as 'qb' keyword arg in SDK
    return asyncio.to_thread(func, *args, **kwargs)

# Global client instance (reinstated)
qbo_client_instance: Optional[QuickBooks] = None

def get_qbo_client() -> Optional[QuickBooks]:
    """
    Initializes and returns a QuickBooks client instance.
    Handles fetching credentials and environment settings.
    Returns None if initialization fails.
    """
    global qbo_client_instance
    # Consider if re-initialization is needed based on token expiry or other factors
    # For simplicity, this basic version initializes once.
    if qbo_client_instance:
        # TODO: Add logic here to check if the token needs refreshing
        # If token is expired or close to expiry, refresh it
        # try:
        #     qbo_client_instance.auth_client.refresh()
        #     logger.info("QBO token refreshed successfully.")
        # except Exception as refresh_err:
        #     logger.error(f"Failed to refresh QBO token: {refresh_err}", exc_info=True)
        #     # Decide how to handle refresh failure - maybe force re-init or raise error
        #     qbo_client_instance = None # Force re-init on next call
        #     return None # Or raise AuthenticationError("Token refresh failed")
        logger.debug("Returning existing QBO client instance.")
        return qbo_client_instance

    logger.info("Attempting to initialize new QBO client instance...")
    try:
        # Fetch credentials from Secret Manager using the core config module
        client_id = get_secret("ledger-cfo-qbo-client-id")
        client_secret = get_secret("ledger-cfo-qbo-client-secret")
        refresh_token = get_secret("ledger-cfo-qbo-refresh-token")
        realm_id = get_secret("ledger-cfo-qbo-realm-id")
        environment = os.getenv('QBO_ENVIRONMENT', 'sandbox').lower()

        # Strip whitespace/newlines from credentials, especially realm_id
        if client_id: client_id = client_id.strip()
        if client_secret: client_secret = client_secret.strip()
        if refresh_token: refresh_token = refresh_token.strip()
        if realm_id: realm_id = realm_id.strip()

        if not all([client_id, client_secret, refresh_token, realm_id]):
            missing = [k for k, v in locals().items() if k in ['client_id', 'client_secret', 'refresh_token', 'realm_id'] and not v]
            logger.error(f"QBO client initialization failed: Missing required credentials: {missing}")
            raise ValueError(f"Missing QBO credentials: {missing}")

        # --- BEGIN NEW DIAGNOSTIC PRINTS (Moved and Enhanced) ---
        # WARNING: Avoid logging secrets in production environments long-term.
        # print(f"\nDEBUG QBO PRE-INIT: Using Client ID: {client_id}")
        # print(f"DEBUG QBO PRE-INIT: Using Client Secret: {client_secret}") # Be careful with full secret in logs
        # print(f"DEBUG QBO PRE-INIT: Using Refresh Token: {refresh_token}") # Be careful with full token in logs
        # print(f"DEBUG QBO PRE-INIT: Using Realm ID: {realm_id}")
        # print(f"DEBUG QBO PRE-INIT: Using Environment: {environment}\n")
        # --- END NEW DIAGNOSTIC PRINTS ---

        if environment not in ['sandbox', 'production']:
            logger.error(f"Invalid QBO_ENVIRONMENT: '{environment}'. Must be 'sandbox' or 'production'.")
            raise ValueError("Invalid QBO environment setting.")

        logger.info(f"Initializing QBO AuthClient for environment: {environment}, Realm ID: {realm_id}")

        # --- TEMPORARY DEBUG: Log exact credentials before passing to AuthClient ---
        # WARNING: REMOVE THIS AFTER DEBUGGING - LOGS SECRETS!
        # try:
        #     print(f"DEBUG QBO AUTH: Passing client_id: {repr(client_id)}")
        #     print(f"DEBUG QBO AUTH: Passing client_secret: {repr(client_secret)}")
        # except Exception as log_err:
        #     print(f"DEBUG QBO AUTH: Error logging credentials: {log_err}")
        # --- END TEMPORARY DEBUG ---

        # Step 1: Initialize AuthClient from intuitlib
        auth_client_instance = AuthClient(
            client_id=client_id,
            client_secret=client_secret,
            environment=environment,
            redirect_uri='https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl', # Placeholder for non-web apps
            # access_token=... # Access token is usually managed via refresh token flow
        )
        logger.info("AuthClient initialized.")

        # Step 2: Initialize the main QuickBooks client, passing the auth_client and refresh token
        # THIS IS WHERE THE FAILING REFRESH LIKELY OCCURS INTERNALLY
        # print("DEBUG QBO PRE-INIT: About to initialize QuickBooks client which will trigger token refresh...")
        qbo_client_instance = QuickBooks(
            auth_client=auth_client_instance,
            refresh_token=refresh_token,
            company_id=realm_id,
            # minorversion=... # Specify if needed, e.g., minorversion=70
        )
        logger.info("QuickBooks client initialized successfully.")

        # Explicitly try to refresh the token immediately after initialization
        # to ensure authentication is valid before returning the client.
        try:
            logger.info("Attempting initial token refresh...")
            # NOTE: The refresh() method itself might not exist directly on QuickBooks,
            # it's usually on the AuthClient instance. Access it via qbo_client_instance.auth_client
            if hasattr(qbo_client_instance, 'auth_client') and hasattr(qbo_client_instance.auth_client, 'refresh'):
                qbo_client_instance.auth_client.refresh() # Correct way to call refresh
                logger.info("Initial token refresh successful.")
                print("--- QBO Token Refresh Successful ---")
            else:
                logger.warning("Could not find refresh method on auth_client. Skipping explicit refresh.")
        except AuthorizationException as refresh_ae:
            logger.error(f"QBO initial token refresh failed with AuthorizationException: {refresh_ae}", exc_info=True)
            # Log the HTTP debug output here if possible, though it might be complex
            # to capture it specifically from this point. The global logging should catch it.
            print(f"--- QBO Token Refresh FAILED: {refresh_ae} ---")
            # Fail fast if refresh doesn't work
            raise AuthenticationError(f"Initial token refresh failed: {refresh_ae}") from refresh_ae
        except Exception as refresh_err:
            logger.error(f"QBO initial token refresh failed with unexpected error: {refresh_err}", exc_info=True)
            print(f"--- QBO Token Refresh FAILED Unexpectedly: {refresh_err} ---")
            # Also fail fast on other refresh errors
            raise QBOError(f"Initial token refresh failed unexpectedly: {refresh_err}") from refresh_err

        # Optional: Perform a test call to verify connection/token (Now redundant if refresh succeeded)
        # --- Temporarily commented out --- #
        # try:
        #     logger.info("Verifying QBO connection by fetching company info...")
        #     # Corrected: Use CompanyInfo object to get details
        #     # Need to run this synchronously if get_qbo_client is sync
        #     company_info = CompanyInfo.get(realm_id, qb=qbo_client_instance)
        #     logger.info(f"QBO Connection successful. Company Name: {company_info.CompanyName}")
        # except Exception as test_call_err:
        #      logger.error(f"QBO post-initialization test call failed: {test_call_err}. Check credentials and API status.", exc_info=True)
        #      # Decide if this should prevent returning the client
        #      # For now, log the error but return the client optimistically
        #      # raise AuthenticationError(f"Failed QBO test call: {test_call_err}")
        #      # DO NOT return None here, just log the error

        return qbo_client_instance

    except ValueError as ve:
        # Raised for missing credentials or invalid environment
        logger.error(f"Configuration error during QBO client initialization: {ve}")
        return None # Return None on config errors
    except AuthorizationException as ae:
         logger.error(f"QBO Authorization error during initialization (check refresh token/realm ID?): {ae}", exc_info=True)
         # raise AuthenticationError(f"QBO Auth Error: {ae}") # Or return None
         return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during QBO client initialization: {e}", exc_info=True)
        # Log the specific error and potentially raise a custom exception or return None
        return None

# --- Core QBO Functions Placeholders (Task 1 Target) ---

async def get_customer_details(qbo_client: QuickBooks, customer_id: str) -> Dict[str, Any]:
    """Fetches full details for a specific customer."""
    logger.info(f"Placeholder: Fetching details for customer ID: {customer_id}")
    # TODO: Implement using _sync_qbo_call(Customer.get, ...)
    raise NotImplementedError

async def get_customer_transactions(qbo_client: QuickBooks, customer_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches Invoices, Payments, Estimates, Sales Receipts for a specific customer."""
    cache_key = _generate_cache_key('get_customer_transactions', customer_id=customer_id, start_date=start_date, end_date=end_date)
    if cache_key in transaction_cache:
        logger.debug(f"Cache hit for transactions, customer ID: {customer_id}, Dates: {start_date}-{end_date}")
        return transaction_cache[cache_key]

    logger.info(f"Fetching transactions for customer ID: {customer_id} from QBO (Start: {start_date}, End: {end_date})")
    all_transactions = []
    # Define entity types and the fields to extract for consistency
    entity_map = {
        Invoice: ["Id", "TxnDate", "TotalAmt", "Balance", "DueDate", "DocNumber"],
        Payment: ["Id", "TxnDate", "TotalAmt", "UnappliedAmt"],
        Estimate: ["Id", "TxnDate", "TotalAmt", "TxnStatus", "ExpirationDate", "DocNumber"],
        salesreceipt.SalesReceipt: ["Id", "TxnDate", "TotalAmt", "DocNumber"] # Revised usage
    }

    try:
        # Optional: Verify customer exists first? Could prevent unnecessary queries if customer ID is invalid.
        # await get_customer_details(qbo_client, customer_id) # This would raise NotFoundError early

        for EntityClass, fields_to_extract in entity_map.items():
            entity_name = EntityClass.__name__
            logger.debug(f"Querying for {entity_name} for customer {customer_id}")
            # Build QBQL WHERE clause
            filters = [f"CustomerRef = '{customer_id}'"]
            if start_date:
                filters.append(f"TxnDate >= '{start_date}'")
            if end_date:
                filters.append(f"TxnDate <= '{end_date}'")
            query_filter = " AND ".join(filters)

            # python-quickbooks' .where handles pagination up to 1000 results
            try:
                entities = await _sync_qbo_call(EntityClass.where, query_filter, qb=qbo_client)
                logger.debug(f"Found {len(entities)} {entity_name}(s) for customer {customer_id}")

                for entity in entities:
                    txn_data = {"type": entity_name} # Add type identifier
                    for field in fields_to_extract:
                        # Handle nested attributes like CustomerRef if needed, though filter covers it
                        # For simplicity, getattr handles basic fields
                        txn_data[field] = getattr(entity, field, None)
                    # Add customer ref ID for context
                    txn_data["CustomerRefValue"] = entity.CustomerRef.value if entity.CustomerRef else None
                    all_transactions.append(txn_data)

            except QuickbooksException as query_e:
                # Log other query errors but continue processing other types
                # Check if it behaves like a NotFound error (e.g., specific error code)
                # Example: QBO error codes for not found are often in the 6xx range (e.g., 610, 620)
                error_code = getattr(query_e, 'error_code', None)
                if error_code and 600 <= int(error_code) < 700:
                     logger.debug(f"No {entity_name} found for customer {customer_id} matching criteria (Caught via QuickbooksException code {error_code}).")
                     continue # Treat as NotFound
                else:
                    logger.error(f"Error querying {entity_name} for customer {customer_id}: {query_e}", exc_info=True)
                    # Depending on policy, could raise here or collect errors

        logger.info(f"Successfully fetched {len(all_transactions)} total transactions for customer ID: {customer_id}")
        transaction_cache[cache_key] = all_transactions # Update cache
        return all_transactions

    except Exception as e:
        # Catch errors not handled in the inner loop (like potential get_customer_details error)
        _handle_qbo_sdk_error(e, context=f"get customer transactions for ID {customer_id}")
        # Error handler raises, no return needed

async def get_estimate_details(qbo_client: QuickBooks, estimate_id: str) -> Dict[str, Any]:
    """Fetches full details for a specific estimate, including line items."""
    cache_key = _generate_cache_key('get_estimate_details', estimate_id=estimate_id)
    if cache_key in details_cache:
        logger.debug(f"Cache hit for estimate details ID: {estimate_id}")
        return details_cache[cache_key]

    logger.info(f"Fetching details for estimate ID: {estimate_id} from QBO")
    try:
        estimate = await _sync_qbo_call(Estimate.get, estimate_id, qb=qbo_client)
        # Convert the full SDK object to a dictionary
        details = estimate.to_dict()
        logger.info(f"Successfully fetched details for estimate ID: {estimate_id}")
        details_cache[cache_key] = details # Cache the result
        return details
    except Exception as e:
        _handle_qbo_sdk_error(e, context=f"get estimate details for ID {estimate_id}")

async def get_invoice_details(qbo_client: QuickBooks, invoice_id: str) -> Dict[str, Any]:
    """Fetches full details for a specific invoice, including line items."""
    cache_key = _generate_cache_key('get_invoice_details', invoice_id=invoice_id)
    if cache_key in details_cache:
        logger.debug(f"Cache hit for invoice details ID: {invoice_id}")
        return details_cache[cache_key]

    logger.info(f"Fetching details for invoice ID: {invoice_id} from QBO")
    try:
        # Use the Invoice object's get method via the sync helper
        invoice = await _sync_qbo_call(Invoice.get, invoice_id, qb=qbo_client)
        # Convert the full SDK object to a dictionary for easier handling
        details = invoice.to_dict()
        logger.info(f"Successfully fetched details for invoice ID: {invoice_id}")
        details_cache[cache_key] = details # Cache the result
        return details
    except QuickbooksException as qbe:
        # Check error code for NotFound equivalent
        error_code = getattr(qbe, 'error_code', None)
        if error_code and 600 <= int(error_code) < 700:
             logger.warning(f"Invoice ID {invoice_id} not found in QBO (Caught via QuickbooksException code {error_code}).")
             # Raise our internal NotFoundError for consistency
             raise NotFoundError(f"Invoice ID {invoice_id} not found.", original_exception=qbe) from qbe
        else:
             # Let the generic handler deal with other QBO errors
             _handle_qbo_sdk_error(qbe, context=f"get invoice details for ID {invoice_id}")
    except Exception as e:
        # Use the generic error handler for other QBO/network errors
        _handle_qbo_sdk_error(e, context=f"get invoice details for ID {invoice_id}")
        # _handle_qbo_sdk_error raises the appropriate QBOError subtype, so no return needed here

async def find_estimates(qbo_client: QuickBooks, customer_id: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Finds estimates, filterable by customer and status."""
    cache_key = _generate_cache_key('find_estimates', customer_id=customer_id, status=status)
    if cache_key in search_cache:
        logger.debug(f"Cache hit for find_estimates: Cust={customer_id}, Stat={status}")
        return search_cache[cache_key]

    logger.info(f"Finding estimates from QBO (Customer: {customer_id}, Status: {status})")
    filters = []
    if customer_id:
        filters.append(f"CustomerRef = '{customer_id}'")
    if status:
        # Ensure status matches QBO valid statuses
        # QBO statuses: Accepted, Pending, Closed, Rejected
        valid_statuses = ['Accepted', 'Pending', 'Closed', 'Rejected']
        if status not in valid_statuses:
            logger.warning(f"Invalid status '{status}' requested for find_estimates. Ignoring status filter.")
        else:
            filters.append(f"TxnStatus = '{status}'")

    query = " AND ".join(filters) if filters else "" # Empty query string for .all
    max_results = 1000 # Default limit for queries

    try:
        if query:
            # Use .where for filtering
            estimates_sdk = await _sync_qbo_call(Estimate.where, query, max_results=max_results, qb=qbo_client)
        else:
            # Use .all if no specific filters are provided
            estimates_sdk = await _sync_qbo_call(Estimate.all, max_results=max_results, qb=qbo_client)

        # Convert results to dictionaries for consistent output
        estimates_list = [est.to_dict() for est in estimates_sdk]
        logger.info(f"Found {len(estimates_list)} estimates matching criteria.")
        search_cache[cache_key] = estimates_list # Cache the results
        return estimates_list
    except Exception as e:
        _handle_qbo_sdk_error(e, context=f"finding estimates (Cust={customer_id}, Status={status})")
        # Error handler raises

async def find_customers_by_details(query: str, qbo_client: QuickBooks) -> List[Dict[str, Any]]:
    """
    Finds customers by matching the query string against DisplayName, CompanyName,
    Email, or Phone.
    Returns a list of customer dictionaries with essential details if found,
    otherwise an empty list.
    """
    logger.info(f"Searching for customers matching details: '{query}'")
    # Escape single quotes in the query for the QBO query string
    escaped_query = query.replace("'", "\\\\'")

    # Construct a more robust query. QBO's query language is SQL-like but has limitations.
    # We'll try to match against common fields.
    # Note: QBO query service does not support OR across different fields directly in a simple way like SQL.
    # We might need to perform multiple queries or use a more general search if available and then filter.
    # For now, let's try DisplayName and PrimaryEmailAddr.Address as common search fields.
    # A more robust solution might involve multiple targeted queries if one field fails.
    
    # Attempting a query that searches multiple fields (syntax might vary or not be fully supported for complex ORs)
    # QBO's query language is not full SQL. It's often better to query one specific field or use more generic text search if the API supports it.
    # For this iteration, we will prioritize DisplayName and then try Email if no results.
    # A simpler, more reliable initial query:
    
    # Query 1: Try DisplayName
    full_query_display_name = f"SELECT * FROM Customer WHERE DisplayName LIKE '%{escaped_query}%' MAXRESULTS 10"
    logger.info(f"Constructed QBO query (DisplayName): {full_query_display_name}")
    
    customers_found = []
    try:
        customers_sdk_display_name = await _sync_qbo_call(Customer.query, full_query_display_name, qb=qbo_client)
        if customers_sdk_display_name:
            for cust_sdk in customers_sdk_display_name:
                customers_found.append(sdk_customer_to_dict(cust_sdk))
        logger.info(f"Found {len(customers_found)} customer(s) matching DisplayName query: '{query}'")

    except Exception as e:
        # Log the error but don't let it stop other query attempts if DisplayName query itself fails syntactically
        logger.error(f"Error during QBO Customer query by DisplayName for '{query}': {e}", exc_info=True)
        # Do not re-raise here, allow fallback to other field queries. _handle_qbo_sdk_error might be called by _sync_qbo_call

    # Query 2: Try PrimaryEmailAddr if no results from DisplayName and query looks like an email
    if not customers_found and '@' in query: # Rudimentary check for email-like query
        full_query_email = f"SELECT * FROM Customer WHERE PrimaryEmailAddr.Address LIKE '%{escaped_query}%' MAXRESULTS 10"
        logger.info(f"Constructed QBO query (Email): {full_query_email}")
        try:
            customers_sdk_email = await _sync_qbo_call(Customer.query, full_query_email, qb=qbo_client)
            if customers_sdk_email:
                for cust_sdk in customers_sdk_email:
                    # Avoid duplicates if a customer somehow matched both
                    if not any(c['Id'] == cust_sdk.Id for c in customers_found):
                         customers_found.append(sdk_customer_to_dict(cust_sdk))
            logger.info(f"Found {len(customers_found) - len([c for c in customers_found if c.get('matched_by_displayname')])} additional customer(s) matching Email query: '{query}'") # Adjust log
        except Exception as e:
            logger.error(f"Error during QBO Customer query by Email for '{query}': {e}", exc_info=True)


    # TODO: Add searches for CompanyName and Phone if necessary, being mindful of QBO query limitations.
    # It's often better to let the LLM decide to query specific fields if an initial broader search fails.
    # However, the QBO query language is limited.

    if not customers_found:
        logger.warning(f"No customers found matching query: '{query}' after trying DisplayName and Email.")
        # Raising NotFoundError here makes sense if NO customers are found by any means.
        # The LLM should then handle this.
        # raise NotFoundError(f"No customers found matching details: {query}") # Let's not raise here, let LLM decide next step based on empty list.

    return customers_found

def sdk_customer_to_dict(customer_sdk_object: Customer) -> Dict[str, Any]:
    """Converts a QBO SDK Customer object to a dictionary for broader use."""
    # Ensure all relevant fields are extracted. Add more as needed.
    data = {
        "Id": customer_sdk_object.Id,
        "DisplayName": customer_sdk_object.DisplayName,
        "CompanyName": customer_sdk_object.CompanyName,
        "GivenName": customer_sdk_object.GivenName,
        "FamilyName": customer_sdk_object.FamilyName,
        "PrimaryEmailAddr": customer_sdk_object.PrimaryEmailAddr.Address if customer_sdk_object.PrimaryEmailAddr else None,
        "PrimaryPhone": customer_sdk_object.PrimaryPhone.FreeFormNumber if customer_sdk_object.PrimaryPhone else None,
        "BillAddr": {
            "Line1": customer_sdk_object.BillAddr.Line1,
            "City": customer_sdk_object.BillAddr.City,
            "CountrySubDivisionCode": customer_sdk_object.BillAddr.CountrySubDivisionCode, # State
            "PostalCode": customer_sdk_object.BillAddr.PostalCode,
        } if customer_sdk_object.BillAddr else None,
        "Balance": customer_sdk_object.Balance,
        "SyncToken": customer_sdk_object.SyncToken,
        # Add any other fields you want to expose
    }
    return data

async def get_recent_transactions_with_customer_data(qbo_client: QuickBooks, days: int = 30) -> List[Dict[str, Any]]:
    """Fetches recent transactions (all types) and includes associated customer details."""
    cache_key = _generate_cache_key('get_recent_transactions_with_customer_data', days=days)
    if cache_key in transaction_cache:
        logger.debug(f"Cache hit for recent transactions w/ customer data (last {days} days)")
        return transaction_cache[cache_key]

    logger.info(f"Fetching transactions from the last {days} days with customer data from QBO.")
    end_date = datetime.date.today().strftime('%Y-%m-%d')
    start_date = (datetime.date.today() - datetime.timedelta(days=days)).strftime('%Y-%m-%d')

    all_enriched_transactions = []
    # Cache customer details fetched during this specific call to avoid redundant gets
    customer_details_internal_cache = {}

    # Define entity types and key fields (include CustomerRef)
    entity_map = {
        Invoice: ["Id", "TxnDate", "TotalAmt", "Balance", "DueDate", "DocNumber", "CustomerRef"],
        Payment: ["Id", "TxnDate", "TotalAmt", "UnappliedAmt", "CustomerRef"],
        Estimate: ["Id", "TxnDate", "TotalAmt", "TxnStatus", "ExpirationDate", "DocNumber", "CustomerRef"],
        salesreceipt.SalesReceipt: ["Id", "TxnDate", "TotalAmt", "DocNumber", "CustomerRef"] # Revised usage
        # Add Purchase, Bill, etc. if needed
    }
    max_results_per_page = 100 # Keep page size reasonable for enrichment loops

    try:
        for EntityClass, fields_to_extract in entity_map.items():
            entity_name = EntityClass.__name__
            logger.debug(f"Querying recent {entity_name} (last {days} days)")
            query = f"TxnDate >= '{start_date}' AND TxnDate <= '{end_date}'"

            # Handle pagination explicitly
            start_position = 1
            fetch_more = True
            while fetch_more:
                try:
                    entities = await _sync_qbo_call(EntityClass.where, query, start_position=start_position, max_results=max_results_per_page, qb=qbo_client)
                    logger.debug(f"Fetched page of {len(entities)} {entity_name}(s)")

                    if not entities:
                        fetch_more = False
                        continue # No more entities of this type/page

                    # Process and enrich the fetched entities
                    for entity in entities:
                        txn_data = {"type": entity_name}
                        customer_id = None
                        customer_ref_value = None

                        # Extract fields and find CustomerRef ID
                        for field in fields_to_extract:
                            value = getattr(entity, field, None)
                            if field == "CustomerRef" and value:
                                customer_id = value.value
                                customer_ref_value = {"value": customer_id, "name": value.name} # Store ref dict
                                txn_data[field] = customer_ref_value
                            else:
                                txn_data[field] = value

                        # Fetch and add customer details if ID found
                        if customer_id:
                            if customer_id not in customer_details_internal_cache:
                                try:
                                    # Use the dedicated function (which has its own cache)
                                    cust_details = await get_customer_details(qbo_client, customer_id)
                                    customer_details_internal_cache[customer_id] = cust_details
                                except QBOError as cust_err:
                                    # Log but store error state in cache to avoid retries within this call
                                    logger.warning(f"Failed to fetch customer {customer_id} for enrichment: {cust_err}")
                                    customer_details_internal_cache[customer_id] = {"error": str(cust_err), "original_exception": cust_err}

                            txn_data["CustomerDetails"] = customer_details_internal_cache.get(customer_id)
                        else:
                            txn_data["CustomerDetails"] = None

                        all_enriched_transactions.append(txn_data)

                    # Pagination logic
                    if len(entities) < max_results_per_page:
                        fetch_more = False # Last page for this entity type
                    else:
                        start_position += max_results_per_page

                except QuickbooksException as page_qbe:
                    error_code = getattr(page_qbe, 'error_code', None)
                    if error_code and 600 <= int(error_code) < 700:
                         logger.debug(f"No more {entity_name} found for the period (Caught via QuickbooksException code {error_code}).")
                         fetch_more = False # Treat as NotFound for pagination
                    else:
                         # Log other query errors but continue overall process
                         logger.error(f"Error querying page for {entity_name}: {page_qbe}", exc_info=True)
                         fetch_more = False # Stop pagination on error for this type
                except Exception as page_e:
                    # Log error for this page/type but continue overall process
                    logger.error(f"Error querying page for {entity_name}: {page_e}", exc_info=True)
                    fetch_more = False # Stop pagination on error for this type

        logger.info(f"Successfully fetched and enriched {len(all_enriched_transactions)} transactions from the last {days} days.")
        transaction_cache[cache_key] = all_enriched_transactions # Update main transaction cache
        return all_enriched_transactions
    except Exception as e:
        # Catch broad errors during the process
        _handle_qbo_sdk_error(e, context=f"getting recent transactions (last {days} days)")
        # Error handler raises

async def create_invoice(qbo_client: QuickBooks, customer_id: str, line_items: List[Dict[str, Any]], invoice_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Creates an invoice in QBO using python-quickbooks."""
    logger.info(f"Attempting to create invoice in QBO for customer ID: {customer_id}")
    invoice_obj = Invoice()
    invoice_obj.CustomerRef = {"value": customer_id}

    # Apply top-level invoice data like DueDate, Terms, etc.
    if invoice_data:
        for key, value in invoice_data.items():
            if hasattr(invoice_obj, key):
                # Handle nested refs if needed (e.g., Terms)
                if key == "ClassRef" and isinstance(value, dict):
                    invoice_obj.ClassRef = type('obj', (object,), value)()
                elif key == "SalesTermRef" and isinstance(value, dict):
                     invoice_obj.SalesTermRef = type('obj', (object,), value)()
                elif key == "BillEmail" and isinstance(value, dict): # Handle email structure
                    invoice_obj.BillEmail = type('obj', (object,), value)()
                else:
                    setattr(invoice_obj, key, value)
            else:
                 logger.warning(f"Invoice data contains unknown field '{key}' while creating invoice. Ignoring.")

    # Build Line items using SDK objects
    sdk_lines = []
    if not line_items:
         raise InvalidDataError("Invoice must have at least one line item.")

    for idx, item_dict in enumerate(line_items):
        line = SalesItemLine()
        line.LineNum = idx + 1 # Line numbers are optional but good practice

        if 'Amount' not in item_dict:
            raise InvalidDataError(f"Line item {idx+1} is missing 'Amount'.")
        line.Amount = item_dict['Amount']
        line.Description = item_dict.get('Description')

        # DetailType determines the type of line (Item-based, Account-based, etc.)
        # Defaulting to SalesItemLineDetail, assuming lines refer to Products/Services
        line.DetailType = 'SalesItemLineDetail'
        sild = SalesItemLineDetail()

        # Check if ItemRef is provided for linking to a Product/Service in QBO
        item_ref_data = item_dict.get('SalesItemLineDetail', {}).get('ItemRef')
        if isinstance(item_ref_data, dict) and item_ref_data.get('value'):
            sild.ItemRef = item_ref_data
            # Optionally set Qty and UnitPrice if provided and using ItemRef
            if 'Qty' in item_dict: sild.Qty = item_dict['Qty']
            if 'UnitPrice' in item_dict: sild.UnitPrice = item_dict['UnitPrice']
        elif 'Qty' in item_dict or 'UnitPrice' in item_dict:
             logger.warning(f"Line item {idx+1} has Qty/UnitPrice but no ItemRef. These might be ignored by QBO.")
        # If no ItemRef, QBO treats it as a generic line item based on Description/Amount

        # Add TaxCodeRef if provided
        tax_code_ref = item_dict.get('SalesItemLineDetail', {}).get('TaxCodeRef')
        if isinstance(tax_code_ref, dict) and tax_code_ref.get('value'):
            sild.TaxCodeRef = tax_code_ref

        line.SalesItemLineDetail = sild
        sdk_lines.append(line)

    invoice_obj.Line = sdk_lines

    try:
        # Save the populated invoice object
        created_invoice_sdk = await _sync_qbo_call(invoice_obj.save, qb=qbo_client)
        logger.info(f"Successfully created invoice ID: {created_invoice_sdk.Id} Doc #: {created_invoice_sdk.DocNumber}")
        # Return the created invoice data as a dictionary
        return created_invoice_sdk.to_dict()
    except Exception as e:
        _handle_qbo_sdk_error(e, context=f"creating invoice for customer {customer_id}")
        # Error handler raises

async def create_estimate(qbo_client: QuickBooks, customer_id: str, line_items: List[Dict[str, Any]], estimate_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Creates an estimate in QBO using python-quickbooks."""
    logger.info(f"Attempting to create estimate in QBO for customer ID: {customer_id}")
    estimate_obj = Estimate()
    estimate_obj.CustomerRef = {"value": customer_id}

    # Apply top-level estimate data
    if estimate_data:
        for key, value in estimate_data.items():
            if hasattr(estimate_obj, key):
                # Handle nested refs if needed (e.g., ClassRef)
                if key == "ClassRef" and isinstance(value, dict):
                    estimate_obj.ClassRef = type('obj', (object,), value)()
                else:
                    setattr(estimate_obj, key, value)
            else:
                 logger.warning(f"Estimate data contains unknown field '{key}' while creating estimate. Ignoring.")

    # Build Line items
    sdk_lines = []
    if not line_items:
        raise InvalidDataError("Estimate must have at least one line item.")

    for idx, item_dict in enumerate(line_items):
        line = SalesItemLine()
        line.LineNum = idx + 1

        if 'Amount' not in item_dict:
            raise InvalidDataError(f"Estimate Line item {idx+1} missing 'Amount'.")
        line.Amount = item_dict['Amount']
        line.Description = item_dict.get('Description')
        line.DetailType = 'SalesItemLineDetail'

        sild = SalesItemLineDetail()
        item_ref_data = item_dict.get('SalesItemLineDetail', {}).get('ItemRef')
        if isinstance(item_ref_data, dict) and item_ref_data.get('value'):
            sild.ItemRef = item_ref_data
            if 'Qty' in item_dict: sild.Qty = item_dict['Qty']
            if 'UnitPrice' in item_dict: sild.UnitPrice = item_dict['UnitPrice']
        # Add TaxCodeRef if provided
        tax_code_ref = item_dict.get('SalesItemLineDetail', {}).get('TaxCodeRef')
        if isinstance(tax_code_ref, dict) and tax_code_ref.get('value'):
            sild.TaxCodeRef = tax_code_ref

        line.SalesItemLineDetail = sild
        sdk_lines.append(line)

    estimate_obj.Line = sdk_lines

    try:
        # Save the estimate object
        created_estimate_sdk = await _sync_qbo_call(estimate_obj.save, qb=qbo_client)
        logger.info(f"Successfully created estimate ID: {created_estimate_sdk.Id} Doc #: {created_estimate_sdk.DocNumber}")
        return created_estimate_sdk.to_dict()
    except Exception as e:
        _handle_qbo_sdk_error(e, context=f"creating estimate for customer {customer_id}")

async def record_payment(qbo_client: QuickBooks, customer_id: str, invoice_id: str, amount: float, payment_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Records a payment against an invoice in QBO."""
    logger.info(f"Attempting to record payment of {amount} for invoice ID: {invoice_id} from customer {customer_id}")
    payment_obj = Payment()
    payment_obj.CustomerRef = {"value": customer_id}
    payment_obj.TotalAmt = amount # Total amount of the payment itself

    # Apply other payment header data if provided
    if payment_data:
        for key, value in payment_data.items():
             if hasattr(payment_obj, key):
                 # Handle nested refs explicitly if they come as dicts
                 if key in ["DepositToAccountRef", "PaymentMethodRef", "ARAccountRef"] and isinstance(value, dict):
                     # Dynamically create a simple object for the ref
                     setattr(payment_obj, key, type('obj', (object,), value)())
                 else:
                    setattr(payment_obj, key, value)
             else:
                 logger.warning(f"Payment data contains unknown field '{key}'. Ignoring.")

    # Link payment line to the specific invoice being paid
    # The Line amount should match the amount being applied to this invoice
    payment_obj.Line = [{
        "Amount": amount, # Amount applied to this linked transaction
        "LinkedTxn": [{
            "TxnId": invoice_id,
            "TxnType": "Invoice"
        }]
    }]
    # If handling multiple invoices or under/over payments, Line logic would be more complex.

    try:
        # Save the payment object
        created_payment_sdk = await _sync_qbo_call(payment_obj.save, qb=qbo_client)
        logger.info(f"Successfully recorded payment ID: {created_payment_sdk.Id}")
        return created_payment_sdk.to_dict()
    except Exception as e:
        _handle_qbo_sdk_error(e, context=f"recording payment for invoice {invoice_id}")

async def send_invoice(qbo_client: QuickBooks, invoice_id: str) -> bool:
    """Triggers QBO to send the specified invoice via email."""
    logger.info(f"Attempting to trigger QBO send for invoice ID: {invoice_id}")
    try:
        # Fetch the invoice first to ensure it exists
        invoice = await _sync_qbo_call(Invoice.get, invoice_id, qb=qbo_client)

        # Use the SDK's send() method on the invoice object
        # This typically sends to the customer's BillEmail or PrimaryEmailAddr
        await _sync_qbo_call(invoice.send, qb=qbo_client)

        logger.info(f"Successfully called send method for invoice ID: {invoice_id}. QBO handles actual email delivery.")
        # Clear cache for this specific invoice details if needed
        details_cache.pop(_generate_cache_key('get_invoice_details', invoice_id=invoice_id), None)
        # Potentially clear broader transaction caches if status change is critical
        transaction_cache.clear()
        return True
    except ValidationException as ve:
        # Handle specific errors like missing email address
        if "Email Address is missing" in str(ve) or "email address does not appear" in str(ve):
             logger.error(f"Cannot send invoice {invoice_id}: Customer email missing or invalid. Error: {ve}")
             raise InvalidDataError(f"Cannot send invoice {invoice_id}: Customer email missing or invalid.", ve) from ve
        else:
             _handle_qbo_sdk_error(ve, context=f"sending invoice ID {invoice_id} (Validation)")
             return False # Should be handled by raising exception
    except Exception as e:
        # Handle other errors (NotFound, Auth, etc.)
        _handle_qbo_sdk_error(e, context=f"sending invoice ID {invoice_id}")
        return False # Indicate failure on error (though error handler should raise)

async def void_invoice(qbo_client: QuickBooks, invoice_id: str) -> bool:
    """Voids a specific invoice in QBO."""
    logger.warning(f"Attempting to VOID invoice ID: {invoice_id} in QBO")
    try:
        # 1. Fetch the invoice to get the current state and SyncToken
        invoice = await _sync_qbo_call(Invoice.get, invoice_id, qb=qbo_client)

        # Ensure we have SyncToken needed for updates/voids
        if not invoice.SyncToken:
             raise QBOError(f"Cannot void invoice {invoice_id}: Missing SyncToken.")

        # 2. Use the .save() method with the 'operation=void' parameter
        # The SDK should handle constructing the correct sparse update request.
        # The object passed to save (invoice) contains the ID and SyncToken.
        voided_invoice_response = await _sync_qbo_call(
            invoice.save, # Call save on the fetched object itself
            qb=qbo_client,
            params={'operation': 'void'} # Crucial parameter for void action
        )

        # 3. Verify response
        # A successful void usually returns the object with updated state (e.g., status, zeroed amounts)
        if voided_invoice_response and voided_invoice_response.Id == invoice_id:
            logger.info(f"Successfully voided invoice ID: {invoice_id}")
            # Clear relevant caches as the transaction state has significantly changed
            details_cache.pop(_generate_cache_key('get_invoice_details', invoice_id=invoice_id), None)
            transaction_cache.clear() # Clear broader caches that might list this invoice
            return True
        else:
            # This case might indicate an unexpected response from the SDK/API after a 2xx status
            logger.error(f"Void operation for invoice ID {invoice_id} completed but SDK response was unexpected: {voided_invoice_response}")
            return False

    except ValidationException as ve:
         # Handle cases where QBO explicitly forbids voiding
         # E.g., "You can only void transactions that have not been paid"
         if "may be voided only if it has a zero balance" in str(ve) or "paid" in str(ve):
              logger.error(f"Cannot void invoice {invoice_id}: {ve} (Likely already paid or has non-zero balance)." )
              raise InvalidDataError(f"Invoice {invoice_id} cannot be voided (likely paid or has balance).", ve) from ve
         else:
              _handle_qbo_sdk_error(ve, context=f"voiding invoice ID {invoice_id} (Validation)")
              return False # Error handler will raise
    except Exception as e:
        # Handle other errors like NotFound, Auth, etc.
        _handle_qbo_sdk_error(e, context=f"voiding invoice ID {invoice_id}")
        return False # Error handler will raise

# --- Existing Functions (Now Implemented with Async) ---

async def find_or_create_customer(name: str, db: Session, qbo: QuickBooks, create_if_not_found: bool = True) -> Dict[str, Any] | None:
    """Finds or creates a customer, checking DB cache first. Uses async SDK calls."""
    logger.info(f"Async Finding/Creating customer: '{name}'")
    # 1. Check DB cache (synchronous - ok within async func)
    cached_customer = crud.get_customer_by_name(db, name)
    if cached_customer:
        logger.info(f"Found customer '{name}' in DB cache (ID: {cached_customer.qbo_customer_id}).")
        # Return structure includes ID for referencing
        return {
            "qbo_customer_id": cached_customer.qbo_customer_id,
            "display_name": cached_customer.display_name,
            "email_address": cached_customer.email_address,
            "source": "db_cache",
            "qbo_customer_ref_id": cached_customer.qbo_customer_id # Added for consistency
        }

    logger.info(f"Customer '{name}' not found in DB cache. Querying QBO.")
    # 2. Query QBO (asynchronously)
    try:
        sanitized_name = name.replace("'", "\\\'")
        query = f"SELECT * FROM Customer WHERE DisplayName = '{sanitized_name}' MAXRESULTS 1"
        qbo_customers = await _sync_qbo_call(Customer.query, query, qb=qbo)

        customer_data_for_cache = None
        return_data = None

        if qbo_customers:
            qbo_customer = qbo_customers[0]
            logger.info(f"Found customer '{name}' in QBO (ID: {qbo_customer.Id}). Updating DB cache.")
            customer_data_for_cache = {
                "qbo_customer_id": qbo_customer.Id,
                "display_name": qbo_customer.DisplayName,
                "email_address": qbo_customer.PrimaryEmailAddr.Address if qbo_customer.PrimaryEmailAddr else None
            }
            return_data = {**customer_data_for_cache, "source": "qbo", "qbo_customer_ref_id": qbo_customer.Id}

        elif create_if_not_found:
            logger.info(f"Creating customer '{name}' in QBO.")
            new_customer_obj = Customer()
            new_customer_obj.DisplayName = name
            # TODO: Consider adding email/phone if available from original request context?
            created_customer = await _sync_qbo_call(new_customer_obj.save, qb=qbo)
            logger.info(f"Created new customer '{name}' in QBO (ID: {created_customer.Id}). Updating DB cache.")
            customer_data_for_cache = {
                "qbo_customer_id": created_customer.Id,
                "display_name": created_customer.DisplayName,
                "email_address": created_customer.PrimaryEmailAddr.Address if created_customer.PrimaryEmailAddr else None
            }
            return_data = {**customer_data_for_cache, "source": "qbo_created", "qbo_customer_ref_id": created_customer.Id}

        else: # Not found and not creating
            logger.info(f"Customer '{name}' not found in QBO and creation disabled.")
            return None

        # Update DB cache if customer was found or created
        if customer_data_for_cache:
             crud.update_or_create_customer_cache(db, customer_data_for_cache)
             # db.commit() should be handled by the caller/session manager

        return return_data

    except Exception as e:
        _handle_qbo_sdk_error(e, context=f"find/create customer '{name}'")
        # Error handler raises

async def find_item(qbo: QuickBooks, name: str) -> Optional[Dict[str, Any]]:
     """Finds an item by name. Returns dict with key details or None."""
     logger.info(f"Async Searching for item: {name}")
     try:
         sanitized_name = name.replace("'", "\\\'")
         query = f"SELECT * FROM Item WHERE Name = '{sanitized_name}' MAXRESULTS 1"
         items_sdk = await _sync_qbo_call(Item.query, query, qb=qbo)

         if items_sdk:
             item = items_sdk[0]
             logger.info(f"Found item: {name} (ID: {item.Id}, Type: {item.Type})")
             # Return key details as a dictionary
             return {
                 "Id": item.Id,
                 "Name": item.Name,
                 "Description": item.Description,
                 "Type": item.Type,
                 "UnitPrice": item.UnitPrice,
                 "IncomeAccountRef": item.IncomeAccountRef.value if item.IncomeAccountRef else None,
                 "ExpenseAccountRef": item.ExpenseAccountRef.value if item.ExpenseAccountRef else None,
                 "Active": item.Active
             }
         else:
             logger.warning(f"Item '{name}' not found in QBO.")
             return None
     except Exception as e:
         _handle_qbo_sdk_error(e, context=f"find item '{name}'")
         # Return None on error after handling/logging
         return None

async def get_qbo_accounts(qbo: QuickBooks, db: Session, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Fetches all accounts from QBO, uses/updates DB cache and in-memory cache."""
    cache_key = 'all_accounts' # Use a fixed key for the full list
    now = time.time()

    # Check in-memory cache first
    cached_data = account_cache.get(cache_key)
    if not force_refresh and cached_data is not None:
         # Use get_timestamp if available, otherwise assume standard TTLCache behavior if needed
         # Simple check if data exists is often enough if TTL is handled internally
         logger.info("Using in-memory cache for QBO accounts.")
         return cached_data

    logger.info(f"Fetching accounts from QBO (force_refresh={force_refresh}). Updating caches.")
    try:
        accounts_sdk = await _sync_qbo_call(Account.all, qb=qbo)
        accounts_data = []
        for acc in accounts_sdk:
            accounts_data.append({
                'qbo_account_id': acc.Id,
                'name': acc.Name,
                'account_type': acc.AccountType,
                'account_sub_type': acc.AccountSubType,
                'classification': acc.Classification,
                'active': acc.Active,
                'current_balance': acc.CurrentBalance,
            })

        # Update DB cache (synchronous)
        try:
            crud.bulk_update_or_create_account_cache(db, accounts_data)
            logger.info(f"Updated DB cache with {len(accounts_data)} accounts.")
            # db.commit() # Assume commit happens higher up
        except Exception as db_err:
             logger.error(f"Failed to update account DB cache: {db_err}", exc_info=True)
             # Continue with in-memory cache update even if DB fails

        # Update in-memory cache
        account_cache[cache_key] = accounts_data
        logger.info(f"Fetched and cached {len(accounts_data)} accounts from QBO.")
        return accounts_data

    except Exception as e:
        _handle_qbo_sdk_error(e, context="fetching QBO accounts")
        # Attempt to return stale in-memory cache if available on error
        stale_data = account_cache.get(cache_key)
        if stale_data is not None:
             logger.warning("Returning stale account cache due to fetch error.")
             return stale_data
        else:
             # If fetch fails and no cache exists, reraise the original error
             logger.error("Failed to fetch accounts and no cache available.")
             raise

# find_account_in_cache remains synchronous

async def find_or_create_vendor(name: str, db: Session, qbo: QuickBooks, create_if_not_found: bool = True) -> Dict[str, Any] | None:
    """Finds or creates a vendor, checking DB cache first. Uses async SDK calls."""
    logger.info(f"Async Finding/Creating vendor: '{name}'")
    # 1. Check DB cache
    cached_vendor = crud.get_vendor_by_name(db, name)
    if cached_vendor:
        logger.info(f"Found vendor '{name}' in DB cache (ID: {cached_vendor.qbo_vendor_id}).")
        return {
            "qbo_vendor_id": cached_vendor.qbo_vendor_id,
            "display_name": cached_vendor.display_name,
            "source": "db_cache",
            "qbo_vendor_ref_id": cached_vendor.qbo_vendor_id # Added for consistency
        }

    logger.info(f"Vendor '{name}' not found in DB cache. Querying QBO.")
    # 2. Query QBO
    try:
        sanitized_name = name.replace("'", "\\\'")
        query = f"SELECT * FROM Vendor WHERE DisplayName = '{sanitized_name}' MAXRESULTS 1"
        qbo_vendors = await _sync_qbo_call(Vendor.query, query, qb=qbo)

        vendor_data_for_cache = None
        return_data = None

        if qbo_vendors:
            qbo_vendor = qbo_vendors[0]
            logger.info(f"Found vendor '{name}' in QBO (ID: {qbo_vendor.Id}). Updating DB cache.")
            vendor_data_for_cache = {
                "qbo_vendor_id": qbo_vendor.Id,
                "display_name": qbo_vendor.DisplayName
                # Add other fields like email/phone if needed from qbo_vendor object
            }
            return_data = {**vendor_data_for_cache, "source": "qbo", "qbo_vendor_ref_id": qbo_vendor.Id}

        elif create_if_not_found:
            logger.info(f"Creating vendor '{name}' in QBO.")
            new_vendor_obj = Vendor()
            new_vendor_obj.DisplayName = name
            created_vendor = await _sync_qbo_call(new_vendor_obj.save, qb=qbo)
            logger.info(f"Created new vendor '{name}' in QBO (ID: {created_vendor.Id}). Updating DB cache.")
            vendor_data_for_cache = {
                "qbo_vendor_id": created_vendor.Id,
                "display_name": created_vendor.DisplayName
            }
            return_data = {**vendor_data_for_cache, "source": "qbo_created", "qbo_vendor_ref_id": created_vendor.Id}
        else:
            logger.info(f"Vendor '{name}' not found in QBO and creation disabled.")
            return None

        if vendor_data_for_cache:
            crud.update_or_create_vendor_cache(db, vendor_data_for_cache)
            # db.commit()

        return return_data

    except Exception as e:
        _handle_qbo_sdk_error(e, context=f"find/create vendor '{name}'")


async def create_purchase(qbo: QuickBooks, db: Session, vendor_name: str, amount: float, category_name: str = None, description: str = None, payment_account_name: str = "Checking") -> dict:
    """Records an expense (Purchase) in QBO using async helpers."""
    logger.info(f"Async creating purchase for Vendor: '{vendor_name}', Amount: {amount}, Category: {category_name}")
    try:
        # 1. Find/Create Vendor (async)
        vendor_info = await find_or_create_vendor(vendor_name, db, qbo, create_if_not_found=True)
        if not vendor_info or not vendor_info.get('qbo_vendor_id'):
            # find_or_create_vendor should raise error if it fails
             raise QBOError(f"Failed to find or create vendor '{vendor_name}' before purchase creation.")
        vendor_ref_id = vendor_info['qbo_vendor_id']

        # 2. Fetch/Cache Accounts (async)
        all_accounts = await get_qbo_accounts(qbo, db)
        if not all_accounts:
             # get_qbo_accounts should raise if it fails and has no cache
             raise QBOError("Failed to get QBO Chart of Accounts before purchase creation.")

        # 3. Find Expense Account (sync using cached list)
        expense_category_name = category_name or "Miscellaneous Expense"
        expense_account = find_account_in_cache(expense_category_name, account_type='Expense', accounts_list=all_accounts)
        if not expense_account:
             # Try fallbacks
             logger.warning(f"Expense category '{expense_category_name}' not found. Trying fallbacks...")
             fallbacks = ["Miscellaneous Expense", "Other Miscellaneous Expense", "Uncategorized Expense"]
             for fb_name in fallbacks:
                 expense_account = find_account_in_cache(fb_name, account_type='Expense', accounts_list=all_accounts)
                 if expense_account: break
             if not expense_account:
                 err_msg = f"Could not find suitable expense account category ('{category_name}' or fallbacks)."
                 raise InvalidDataError(err_msg)

        expense_account_ref = {"value": expense_account['qbo_account_id']}
        logger.info(f"Using expense account: {expense_account['name']} (ID: {expense_account['qbo_account_id']})")

        # 4. Find Payment Account (sync using cached list)
        payment_account = find_account_in_cache(payment_account_name, account_type='Bank', accounts_list=all_accounts)
        if not payment_account:
             payment_account = find_account_in_cache(payment_account_name, account_type='Credit Card', accounts_list=all_accounts)
             if not payment_account:
                 err_msg = f"Payment account '{payment_account_name}' not found as Bank or Credit Card type."
                 raise InvalidDataError(err_msg)

        payment_account_ref = {"value": payment_account['qbo_account_id']}
        logger.info(f"Using payment account: {payment_account['name']} (ID: {payment_account['qbo_account_id']})")

        # 5. Create Purchase object
        purchase_obj = Purchase()
        purchase_obj.AccountRef = payment_account_ref # Account the money came FROM
        purchase_obj.PaymentType = "Check" # Default, make configurable?
        # Use EntityRef for payee in Purchase transactions
        purchase_obj.EntityRef = {"value": vendor_ref_id, "type": "Vendor"}

        line = AccountBasedExpenseLine()
        line.Amount = float(amount)
        line.DetailType = "AccountBasedExpenseLineDetail"
        detail = AccountBasedExpenseLineDetail()
        detail.AccountRef = expense_account_ref # The expense category account
        line.AccountBasedExpenseLineDetail = detail
        if description:
            line.Description = description
        purchase_obj.Line = [line]

        # 6. Save Purchase (async)
        created_purchase = await _sync_qbo_call(purchase_obj.save, qb=qbo)
        logger.info(f"Successfully created Purchase ID: {created_purchase.Id}")

        # 7. Return success details as dictionary
        return created_purchase.to_dict()

    except Exception as e:
        # Let _handle_qbo_sdk_error map and raise
        _handle_qbo_sdk_error(e, context=f"creating purchase for vendor '{vendor_name}'")