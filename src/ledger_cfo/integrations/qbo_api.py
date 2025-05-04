import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
import datetime
import time

from quickbooks.objects.customer import Customer
from quickbooks.objects.invoice import Invoice
from quickbooks.objects.detailline import SalesItemLine, SalesItemLineDetail, AccountBasedExpenseLine, AccountBasedExpenseLineDetail
from quickbooks.objects.item import Item
from quickbooks.objects.account import Account
from quickbooks.objects.term import Term
from quickbooks.objects.purchase import Purchase
from quickbooks.objects.vendor import Vendor
from quickbooks.objects.reports import ProfitAndLossReport, ReportService

from quickbooks.auth import AuthClient
from quickbooks.client import QuickBooks

# Assuming get_secret is correctly defined in core.config
from ..core.config import get_secret
from ..core import crud # Import CRUD operations
from ..models.customer import CustomerCache # Import the model for type hinting
from ..models.vendor_cache import VendorCache # Added
from ..models.account_cache import AccountCache # Added

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_qbo_client() -> Optional[QuickBooks]:
    """Initializes and returns an authenticated QuickBooks client.

    Fetches necessary credentials from Google Secret Manager dynamically.

    Returns:
        An initialized QuickBooks client object, or None if authentication fails.
    """
    try:
        # Fetch credentials from Secret Manager inside the function
        client_id = get_secret("qbo_client_id")
        client_secret = get_secret("qbo_client_secret")
        refresh_token = get_secret("qbo_refresh_token")
        realm_id = get_secret("qbo_realm_id")
        environment = get_secret("qbo_environment") # 'sandbox' or 'production'

        if not all([client_id, client_secret, refresh_token, realm_id, environment]):
            logging.error("Missing one or more QBO credentials from Secret Manager.")
            return None

        if environment.lower() not in ['sandbox', 'production']:
            logging.error(f"Invalid QBO environment specified in secret: {environment}. Must be 'sandbox' or 'production'.")
            return None

        logging.info(f"Initializing QBO client for environment: {environment}, Realm ID: {realm_id}")

        auth_client = AuthClient(
            client_id=client_id,
            client_secret=client_secret,
            environment=environment,
            redirect_uri="https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl", # Standard redirect URI for non-web apps
        )

        # Set refresh token directly
        auth_client.refresh_token = refresh_token
        auth_client.realm_id = realm_id

        # Attempt to refresh the token to ensure validity
        try:
            auth_client.refresh()
            logging.info("QBO access token refreshed successfully.")
        except Exception as refresh_error:
            logging.error(f"Failed to refresh QBO access token: {refresh_error}")
            # Depending on the error, might need specific handling or raising
            return None # Cannot proceed without a valid token

        # Create the QuickBooks client
        qbo_client = QuickBooks(
            auth_client=auth_client,
            refresh_token=auth_client.refresh_token, # Pass the potentially refreshed token
            company_id=realm_id,
            minorversion=65 # Specify the minor version you are developing against
        )

        logging.info("QuickBooks client initialized successfully.")
        return qbo_client

    except ValueError as ve:
        # Catch errors from get_secret if GCP_PROJECT_ID is missing
        logging.error(f"Configuration error during QBO client initialization: {ve}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during QBO client initialization: {e}")
        return None

# --- QBO operations with Cache Integration --- #

def find_or_create_customer(name: str, db: Session, qbo: QuickBooks, create_if_not_found: bool = True) -> Dict[str, Any] | None:
    """
    Finds a customer by name, checking the cache first, then QBO.
    Optionally creates the customer in QBO if not found and updates the cache.

    Args:
        name: The display name of the customer.
        db: SQLAlchemy Session object.
        qbo: Initialized QuickBooks client.
        create_if_not_found: If True, create the customer in QBO if they don't exist.

    Returns:
        A dictionary with customer details (from cache or QBO) or None.
        The dictionary includes 'qbo_customer_id', 'display_name', 'email_address',
        and potentially 'qbo_customer_ref' if fetched/created in QBO.
    """
    logger.info(f"Finding/Creating customer: '{name}'")

    # 1. Check cache first (case-insensitive)
    cached_customer = crud.get_customer_by_name(db, name)
    if cached_customer:
        logger.info(f"Found customer '{name}' in cache (ID: {cached_customer.qbo_customer_id}).")
        # Return data in a consistent dictionary format
        return {
            "qbo_customer_id": cached_customer.qbo_customer_id,
            "display_name": cached_customer.display_name,
            "email_address": cached_customer.email_address,
            "source": "cache"
            # qbo_customer_ref is not stored in cache, might need to fetch if required later
        }

    logger.info(f"Customer '{name}' not found in cache. Querying QBO.")
    # 2. If not in cache, query QBO
    try:
        # Ensure exact match for QBO query if possible
        query = f"SELECT * FROM Customer WHERE DisplayName = '{name.replace("'", "\\'")}' MAXRESULTS 1"
        qbo_customers = Customer.query(query, qb=qbo)

        if qbo_customers:
            qbo_customer = qbo_customers[0]
            logger.info(f"Found customer '{name}' in QBO (ID: {qbo_customer.Id}). Updating cache.")
            customer_data = {
                "qbo_customer_id": qbo_customer.Id,
                "display_name": qbo_customer.DisplayName,
                "email_address": qbo_customer.PrimaryEmailAddr.Address if qbo_customer.PrimaryEmailAddr else None
            }
            # Update cache
            crud.update_or_create_customer_cache(db, customer_data)
            customer_data['source'] = 'qbo'
            customer_data['qbo_customer_ref'] = qbo_customer.to_ref() # Include ref for immediate use
            return customer_data
        else:
            logger.info(f"Customer '{name}' not found in QBO.")
            if create_if_not_found:
                logger.info(f"Creating customer '{name}' in QBO.")
                new_customer = Customer()
                new_customer.DisplayName = name
                # Add other fields if necessary (e.g., email from original request?)
                new_customer.save(qb=qbo)
                logger.info(f"Created new customer '{name}' in QBO (ID: {new_customer.Id}). Updating cache.")
                customer_data = {
                    "qbo_customer_id": new_customer.Id,
                    "display_name": new_customer.DisplayName,
                    "email_address": new_customer.PrimaryEmailAddr.Address if new_customer.PrimaryEmailAddr else None
                }
                # Update cache
                crud.update_or_create_customer_cache(db, customer_data)
                customer_data['source'] = 'qbo_created'
                customer_data['qbo_customer_ref'] = new_customer.to_ref()
                return customer_data
            else:
                return None # Not found and not creating

    except Exception as e:
        logger.error(f"Error finding or creating customer '{name}' in QBO: {e}", exc_info=True)
        return None # Propagate error indication

# --- Placeholder functions (existing/added) --- #

def find_item(qbo: QuickBooks, name: str) -> Optional[Item]:
    # (Existing function - kept for now, might need cache later)
    logging.info(f"Searching for item: {name}")
    try:
        # Basic item search - might need refinement based on item types (Service, Inventory)
        query = f"SELECT * FROM Item WHERE Name = '{name.replace("'", "\\'")}' MAXRESULTS 1"
        items = Item.query(query, qb=qbo)
        if items:
            logging.info(f"Found item: {name}")
            return items[0]
        else:
            logging.warning(f"Item '{name}' not found. Ensure it exists in QBO.")
            return None
    except Exception as e:
        logging.error(f"Error finding item '{name}': {e}", exc_info=True)
        return None

def create_invoice(invoice_obj: Invoice, qbo: QuickBooks) -> Invoice:
    """Creates an invoice in QuickBooks from an Invoice object."""
    # Refactored to accept pre-built Invoice object
    logging.info(f"Creating invoice in QBO for Customer ID: {invoice_obj.CustomerRef.value}")
    try:
        invoice_obj.save(qb=qbo)
        logging.info(f"Successfully created invoice ID: {invoice_obj.Id}")
        return invoice_obj
    except Exception as e:
        logger.error(f"Error creating invoice: {e}", exc_info=True)
        raise # Re-raise exception to be caught by caller

def send_invoice(invoice_id: str, qbo: QuickBooks) -> bool:
    """Sends an existing invoice using QBO's send functionality."""
    logging.info(f"Attempting to send invoice ID: {invoice_id} via QBO.")
    try:
        invoice = Invoice.get(invoice_id, qb=qbo)
        if not invoice:
            logger.error(f"Cannot send invoice: Invoice ID {invoice_id} not found.")
            return False

        # QBO API v3 doesn't have a direct high-level 'send' like v2.
        # Sending is often triggered by setting EmailStatus or using the send() method.
        # The python-quickbooks library might handle this implicitly or require specific calls.
        # Checking the library's Invoice object methods...
        # It seems '.send()' is the method.
        invoice.send(qb=qbo)
        # Note: The send method might take optional send_to address.
        # If not provided, it usually goes to the customer's PrimaryEmailAddr.
        # response = invoice.send(qb=qbo, send_to='override@example.com') # Example override

        # We might need to check the invoice status afterwards if the send call is async
        # or doesn't return immediate success/failure boolean.
        logging.info(f"QBO send() method called for invoice ID: {invoice_id}. Check QBO UI for status.")
        # Assuming success if no exception is raised by .send()
        return True
    except Exception as e:
        logger.error(f"Error sending invoice ID {invoice_id}: {e}", exc_info=True)
        return False

def create_purchase(purchase_obj: Purchase, qbo: QuickBooks) -> Purchase:
    """Creates a purchase (expense) in QuickBooks from a Purchase object."""
    logging.info(f"Creating purchase/expense in QBO.")
    try:
        purchase_obj.save(qb=qbo)
        logging.info(f"Successfully created purchase ID: {purchase_obj.Id}")
        return purchase_obj
    except Exception as e:
        logger.error(f"Error creating purchase: {e}", exc_info=True)
        raise

def parse_date_range(date_range_str: str) -> tuple[str, str]:
    """Parses common date range strings into start/end dates (YYYY-MM-DD)."""
    # TODO: Implement robust date parsing logic
    # Placeholder implementation
    today = datetime.date.today()
    if date_range_str == "last month":
        first_day_current_month = today.replace(day=1)
        last_day_last_month = first_day_current_month - datetime.timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)
        start_date = first_day_last_month.strftime("%Y-%m-%d")
        end_date = last_day_last_month.strftime("%Y-%m-%d")
    elif date_range_str == "this month":
        start_date = today.replace(day=1).strftime("%Y-%m-%d")
        # Find last day of current month
        next_month = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) # Go to next month
        end_date = (next_month - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    # Add more cases: "last quarter", "this year", specific dates "July 2024"
    else: # Default to this month if unrecognized
        logger.warning(f"Unrecognized date range '{date_range_str}'. Defaulting to 'this month'.")
        return parse_date_range("this month")

    logger.info(f"Parsed date range '{date_range_str}' to: {start_date} - {end_date}")
    return start_date, end_date

def get_pnl_report(start_date: str, end_date: str, qbo: QuickBooks) -> dict:
    """Fetches a Profit and Loss report from QBO for the specified date range."""
    logging.info(f"Fetching PNL Report from QBO for {start_date} to {end_date}")
    try:
        # Use the Reports endpoint
        report = ProfitAndLossReport.query(
            f"SELECT * FROM Report WHERE ReportName = 'ProfitAndLoss' STARTDATE '{start_date}' ENDDATE '{end_date}'",
            qb=qbo
        )
        if report and report.Rows:
             # TODO: Process the report structure into a more usable format
             # The structure can be complex (Rows, Columns, Header, Summary)
             # For now, return a simplified summary
             summary = report.Summary.ColData if report.Summary else []
             income = summary[1].value if len(summary) > 1 else "N/A"
             expense = summary[2].value if len(summary) > 2 else "N/A"
             net_income = summary[3].value if len(summary) > 3 else "N/A"
             logger.info(f"Successfully fetched PNL report. Income: {income}, Expense: {expense}, Net: {net_income}")
             return {
                 "start_date": start_date,
                 "end_date": end_date,
                 "total_income": income,
                 "total_expense": expense,
                 "net_income": net_income,
                 # "raw_report": report.to_dict() # Optionally include raw data
             }
        else:
            logger.warning(f"PNL Report query returned no data or unexpected structure.")
            return {"error": "No data found for the specified period."}
    except Exception as e:
        logger.error(f"Error fetching PNL report: {e}", exc_info=True)
        raise

# Add other QBO functions as needed (e.g., find_account, find_vendor etc.) 

# --- Cache Management for Accounts --- #
CACHE_EXPIRY_SECONDS = 3600 # Cache Chart of Accounts for 1 hour
_account_cache = {
    'data': None,
    'timestamp': 0
}

def get_qbo_accounts(qbo: QuickBooks, db: Session, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Fetches all accounts from QBO, uses DB cache and updates it."""
    now = time.time()
    if not force_refresh and _account_cache['data'] and (now - _account_cache['timestamp'] < CACHE_EXPIRY_SECONDS):
        logger.info("Using in-memory cache for QBO accounts.")
        return _account_cache['data']

    logger.info("Fetching accounts from QBO and updating cache.")
    try:
        accounts = Account.all(qb=qbo)
        accounts_data = []
        for acc in accounts:
            accounts_data.append({
                'qbo_account_id': acc.Id,
                'name': acc.Name,
                'account_type': acc.AccountType,
                'account_sub_type': acc.AccountSubType,
                'classification': acc.Classification,
                # Include other relevant fields if needed
            })

        # Bulk update DB cache
        crud.bulk_update_or_create_account_cache(db, accounts_data)
        db.commit()

        # Update in-memory cache
        _account_cache['data'] = accounts_data
        _account_cache['timestamp'] = now
        logger.info(f"Fetched and cached {len(accounts_data)} accounts from QBO.")
        return accounts_data

    except Exception as e:
        logger.error(f"Error fetching accounts from QBO: {e}", exc_info=True)
        db.rollback()
        # Return stale cache if available, otherwise empty list
        return _account_cache['data'] or []

def find_account_in_cache(name: str, account_type: str = None, accounts_list: List[Dict[str, Any]] = None) -> Dict[str, Any] | None:
    """Finds an account by name (case-insensitive) within a list of account data (from cache)."""
    if not accounts_list:
        return None # Should not happen if get_qbo_accounts is called first

    name_lower = name.lower()
    for acc in accounts_list:
        if acc['name'].lower() == name_lower:
            if account_type and acc['account_type'].lower() != account_type.lower():
                continue # Skip if type doesn't match
            return acc
    return None

# --- Vendor Operations (with Cache) --- #
def find_or_create_vendor(name: str, db: Session, qbo: QuickBooks, create_if_not_found: bool = True) -> Dict[str, Any] | None:
    """
    Finds a vendor by name, checking the cache first, then QBO.
    Optionally creates the vendor in QBO if not found and updates the cache.
    Similar structure to find_or_create_customer.
    """
    logger.info(f"Finding/Creating vendor: '{name}'")

    # 1. Check cache
    cached_vendor = crud.get_vendor_by_name(db, name)
    if cached_vendor:
        logger.info(f"Found vendor '{name}' in cache (ID: {cached_vendor.qbo_vendor_id}).")
        return {
            "qbo_vendor_id": cached_vendor.qbo_vendor_id,
            "display_name": cached_vendor.display_name,
            "source": "cache"
        }

    logger.info(f"Vendor '{name}' not found in cache. Querying QBO.")
    # 2. Query QBO
    try:
        query = f"SELECT * FROM Vendor WHERE DisplayName = '{name.replace("'", "\\'")}' MAXRESULTS 1"
        qbo_vendors = Vendor.query(query, qb=qbo)

        if qbo_vendors:
            qbo_vendor = qbo_vendors[0]
            logger.info(f"Found vendor '{name}' in QBO (ID: {qbo_vendor.Id}). Updating cache.")
            vendor_data = {
                "qbo_vendor_id": qbo_vendor.Id,
                "display_name": qbo_vendor.DisplayName
            }
            crud.update_or_create_vendor_cache(db, vendor_data)
            # db.commit()
            vendor_data['source'] = 'qbo'
            vendor_data['qbo_vendor_ref'] = qbo_vendor.to_ref()
            return vendor_data
        else:
            logger.info(f"Vendor '{name}' not found in QBO.")
            if create_if_not_found:
                logger.info(f"Creating vendor '{name}' in QBO.")
                new_vendor = Vendor()
                new_vendor.DisplayName = name
                new_vendor.save(qb=qbo)
                logger.info(f"Created new vendor '{name}' in QBO (ID: {new_vendor.Id}). Updating cache.")
                vendor_data = {
                    "qbo_vendor_id": new_vendor.Id,
                    "display_name": new_vendor.DisplayName
                }
                crud.update_or_create_vendor_cache(db, vendor_data)
                # db.commit()
                vendor_data['source'] = 'qbo_created'
                vendor_data['qbo_vendor_ref'] = new_vendor.to_ref()
                return vendor_data
            else:
                return None

    except Exception as e:
        logger.error(f"Error finding or creating vendor '{name}' in QBO: {e}", exc_info=True)
        return None

# --- Purchase (Expense) Operations --- #
def create_purchase(qbo: QuickBooks, db: Session, vendor_name: str, amount: float, category_name: str = None, description: str = None, payment_account_name: str = "Checking") -> dict:
    """Records an expense (Purchase) in QBO.

    Handles finding/creating vendor and finding expense/payment accounts using cache.
    """
    logger.info(f"Attempting to create purchase for Vendor: '{vendor_name}', Amount: {amount}, Category: {category_name}")

    try:
        # 1. Find/Create Vendor
        vendor = find_or_create_vendor(vendor_name, db, qbo, create_if_not_found=True)
        if not vendor or not vendor.get('qbo_vendor_ref'):
            err_msg = f"Could not find or create vendor '{vendor_name}'."
            logger.error(err_msg)
            return {'status': 'FAILED', 'error': err_msg}
        vendor_ref = vendor['qbo_vendor_ref']

        # 2. Fetch/Cache Accounts
        all_accounts = get_qbo_accounts(qbo, db)
        if not all_accounts:
            err_msg = "Failed to fetch QBO Chart of Accounts."
            logger.error(err_msg)
            return {'status': 'FAILED', 'error': err_msg}

        # 3. Find Expense Account (Category)
        # Default to a standard expense category if none provided or found
        expense_category_name = category_name or "Miscellaneous Expense" # Or "Uncategorized Expense"
        expense_account = find_account_in_cache(expense_category_name, account_type='Expense', accounts_list=all_accounts)

        if not expense_account:
            logger.warning(f"Expense category '{expense_category_name}' not found in cached accounts. Attempting fallback: 'Miscellaneous Expense'")
            expense_account = find_account_in_cache("Miscellaneous Expense", account_type='Expense', accounts_list=all_accounts)
            if not expense_account:
                logger.warning(f"Fallback 'Miscellaneous Expense' not found. Attempting 'Uncategorized Expense'")
                expense_account = find_account_in_cache("Uncategorized Expense", account_type='Expense', accounts_list=all_accounts)
                if not expense_account:
                     err_msg = f"Could not find a suitable expense account category ('{category_name}' or fallbacks). Please check QBO Chart of Accounts."
                     logger.error(err_msg)
                     return {'status': 'FAILED', 'error': err_msg}

        expense_account_ref = {"value": expense_account['qbo_account_id']}
        logger.info(f"Using expense account: {expense_account['name']} (ID: {expense_account['qbo_account_id']})")

        # 4. Find Payment Account (Bank/Credit Card)
        payment_account = find_account_in_cache(payment_account_name, account_type='Bank', accounts_list=all_accounts)
        if not payment_account:
            # Try finding as Credit Card if not found as Bank
             payment_account = find_account_in_cache(payment_account_name, account_type='Credit Card', accounts_list=all_accounts)
             if not payment_account:
                 err_msg = f"Payment account '{payment_account_name}' not found as Bank or Credit Card type. Please check QBO Chart of Accounts."
                 logger.error(err_msg)
                 return {'status': 'FAILED', 'error': err_msg}

        payment_account_ref = {"value": payment_account['qbo_account_id']}
        logger.info(f"Using payment account: {payment_account['name']} (ID: {payment_account['qbo_account_id']})")

        # 5. Create Purchase object
        purchase = Purchase()
        purchase.AccountRef = payment_account_ref # Account the money came FROM
        purchase.PaymentType = "Check" # Default, could be configurable
        # purchase.PayeeType = "Vendor" # Implicit?
        purchase.EntityRef = vendor_ref # Who was paid (Vendor)

        line = AccountBasedExpenseLine()
        line.Amount = float(amount)
        line.DetailType = "AccountBasedExpenseLineDetail"
        detail = AccountBasedExpenseLineDetail()
        detail.AccountRef = expense_account_ref # The expense category account
        line.AccountBasedExpenseLineDetail = detail
        if description:
            line.Description = description
        purchase.Line = [line]

        # 6. Save Purchase
        created_purchase = purchase.save(qb=qbo)
        logger.info(f"Successfully created Purchase ID: {created_purchase.Id}")

        # 7. Return success details
        return {
            'status': 'EXECUTED',
            'result': {
                'purchase_id': created_purchase.Id,
                'vendor_name': vendor['display_name'],
                'amount': float(amount),
                'expense_category': expense_account['name'],
                'payment_account': payment_account['name']
            }
        }

    except Exception as e:
        logger.error(f"Error creating purchase for vendor '{vendor_name}': {e}", exc_info=True)
        # db.rollback() # Rollback handled at higher level
        return {'status': 'FAILED', 'error': str(e)}

# --- Reporting Operations --- #
def generate_pnl_report(qbo: QuickBooks, start_date: str, end_date: str) -> str:
    """Generates a Profit and Loss report summary for the specified date range."""
    logger.info(f"Generating P&L Report from {start_date} to {end_date}")
    try:
        report_service = ReportService()
        report = report_service.execute_report('ProfitAndLoss', qb=qbo, start_date=start_date, end_date=end_date)

        # Format the report into a simple text summary
        if report and report.Columns and report.Rows:
            summary = f"Profit & Loss Report ({report.Header.StartPeriod} to {report.Header.EndPeriod})\n"
            summary += "=" * 40 + "\n"

            # Assuming a simple structure: Category | Amount
            # Header might be more complex, find the main amount column
            amount_col_index = 0
            for i, col in enumerate(report.Columns.Column):
                if "Amount" in col.ColTitle or col.ColType == "Money": # Heuristic
                    amount_col_index = i
                    break

            for row in report.Rows.Row:
                if row.Header and row.Header.ColData:
                    title = row.Header.ColData[0].value.strip()
                    amount = row.Header.ColData[amount_col_index].value if len(row.Header.ColData) > amount_col_index else "N/A"
                    summary += f"{title}: {amount}\n"
                elif row.Rows: # Handle sub-rows/groups
                    for sub_row in row.Rows.Row:
                         if sub_row.ColData:
                             title = sub_row.ColData[0].value.strip()
                             amount = sub_row.ColData[amount_col_index].value if len(sub_row.ColData) > amount_col_index else "N/A"
                             indent = "  " if sub_row.parentId else ""
                             summary += f"{indent}{title}: {amount}\n"
                elif row.Summary and row.Summary.ColData:
                    title = row.Summary.ColData[0].value.strip()
                    amount = row.Summary.ColData[amount_col_index].value if len(row.Summary.ColData) > amount_col_index else "N/A"
                    summary += "-" * 20 + "\n"
                    summary += f"{title}: {amount}\n"
            return summary
        else:
            logger.warning("P&L report structure not as expected or empty.")
            return "Could not generate P&L report summary (empty or unexpected format)."

    except Exception as e:
        logger.error(f"Error generating P&L report: {e}", exc_info=True)
        return f"Error generating P&L report: {str(e)}" 