import requests
import json
from datetime import datetime, timedelta
import base64
from urllib.parse import urlencode
import time
import re
from config import config
from logger import cfo_logger
from typing import Optional, Dict

class QuickBooksAPI:
    """QuickBooks API integration for the CFO Agent.
    
    Handles authentication, data retrieval, and updates to QuickBooks Online.
    """
    
    def __init__(self):
        """Initialize the QuickBooks API client."""
        self.client_id = config.quickbooks_client_id
        self.client_secret = config.quickbooks_client_secret
        self.refresh_token = config.quickbooks_refresh_token
        self.realm_id = config.quickbooks_realm_id
        self.environment = config.quickbooks_environment
        
        # Set base URLs based on environment
        if self.environment == "production":
            self.base_url = "https://quickbooks.api.intuit.com"
            self.auth_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
        else:
            self.base_url = "https://sandbox-quickbooks.api.intuit.com"
            self.auth_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
            
        self.access_token = None
        self.token_expires_at = None
        self.max_retries = 3
        self.retry_delay = 2  # seconds
        
    def _refresh_access_token(self):
        """Refresh the OAuth access token."""
        try:
            auth_header = base64.b64encode(
                f"{self.client_id}:{self.client_secret}".encode('utf-8')
            ).decode('utf-8')
            
            headers = {
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token
            }
            
            response = requests.post(
                self.auth_url,
                headers=headers,
                data=urlencode(data)
            )
            
            response.raise_for_status()
            auth_data = response.json()
            
            self.access_token = auth_data["access_token"]
            self.token_expires_at = datetime.now() + timedelta(seconds=auth_data["expires_in"])
            # Store the new refresh token if provided
            if "refresh_token" in auth_data:
                self.refresh_token = auth_data["refresh_token"]
                cfo_logger.info("Received new refresh token")
            
            cfo_logger.info("Successfully refreshed QuickBooks access token")
            
        except Exception as e:
            cfo_logger.error(f"Error refreshing QuickBooks access token: {str(e)}")
            raise
            
    def _ensure_token(self):
        """Ensure a valid access token is available."""
        if not self.access_token or not self.token_expires_at or datetime.now() >= self.token_expires_at:
            self._refresh_access_token()
            
    def _make_api_request(self, endpoint, method="GET", params=None, data=None, retry_count=0):
        """Make a request to the QuickBooks API with retry logic."""
        self._ensure_token()
        
        url = f"{self.base_url}/v3/company/{self.realm_id}/{endpoint}"
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=30)
            elif method == "PUT":
                response = requests.put(url, headers=headers, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Handle rate limiting
            if response.status_code == 429:
                if retry_count < self.max_retries:
                    # Get retry-after header or use default delay
                    retry_after = int(response.headers.get('Retry-After', self.retry_delay))
                    cfo_logger.warning(f"Rate limit hit. Retrying after {retry_after} seconds.")
                    time.sleep(retry_after)
                    return self._make_api_request(endpoint, method, params, data, retry_count + 1)
                else:
                    cfo_logger.error("Max retries reached for rate limiting")
                    response.raise_for_status()
                
            # Handle authorization issues
            if response.status_code == 401:
                if retry_count < self.max_retries:
                    cfo_logger.warning("Authorization error. Refreshing token and retrying.")
                    self._refresh_access_token()
                    return self._make_api_request(endpoint, method, params, data, retry_count + 1)
                else:
                    cfo_logger.error("Max retries reached for authorization")
                    response.raise_for_status()
                
            # Handle other errors
            if response.status_code >= 400:
                error_message = f"QuickBooks API error: {response.status_code}"
                try:
                    error_detail = response.json()
                    error_message += f" - {json.dumps(error_detail)}"
                except:
                    error_message += f" - {response.text}"
                
                cfo_logger.error(error_message)
                response.raise_for_status()
                
            return response.json()
            
        except requests.exceptions.ConnectionError as e:
            # Handle connection errors with retry
            if retry_count < self.max_retries:
                cfo_logger.warning(f"Connection error: {str(e)}. Retrying in {self.retry_delay} seconds.")
                time.sleep(self.retry_delay)
                return self._make_api_request(endpoint, method, params, data, retry_count + 1)
            else:
                cfo_logger.error(f"Max retries reached for connection error: {str(e)}")
                raise
        except requests.exceptions.Timeout as e:
            # Handle timeout errors with retry
            if retry_count < self.max_retries:
                cfo_logger.warning(f"Timeout error: {str(e)}. Retrying in {self.retry_delay} seconds.")
                time.sleep(self.retry_delay)
                return self._make_api_request(endpoint, method, params, data, retry_count + 1)
            else:
                cfo_logger.error(f"Max retries reached for timeout error: {str(e)}")
                raise
        except Exception as e:
            cfo_logger.error(f"QuickBooks API request error: {str(e)}")
            raise
            
    def _validate_date(self, date_str):
        """Validate that a date string is in YYYY-MM-DD format."""
        if not date_str:
            return False
            
        pattern = r'^\d{4}-\d{2}-\d{2}$'
        if not re.match(pattern, date_str):
            return False
            
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False
            
    def get_accounts(self):
        """Get all accounts from QuickBooks."""
        return self._make_api_request("query", params={"query": "SELECT * FROM Account WHERE Active = true ORDER BY Name"})
        
    def get_transactions(self, start_date=None, end_date=None):
        """Get transactions from QuickBooks within the specified date range."""
        # Default date range if not specified
        if not start_date:
            start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
            
        # Validate date format
        if not self._validate_date(start_date):
            cfo_logger.error(f"Invalid start_date format: {start_date}. Must be YYYY-MM-DD.")
            raise ValueError(f"Invalid start_date format: {start_date}. Must be YYYY-MM-DD.")
            
        if not self._validate_date(end_date):
            cfo_logger.error(f"Invalid end_date format: {end_date}. Must be YYYY-MM-DD.")
            raise ValueError(f"Invalid end_date format: {end_date}. Must be YYYY-MM-DD.")
            
        # Ensure start_date is before end_date
        if start_date > end_date:
            cfo_logger.warning(f"start_date {start_date} is after end_date {end_date}. Swapping dates.")
            start_date, end_date = end_date, start_date
            
        query = f"SELECT * FROM Transaction WHERE TxnDate >= '{start_date}' AND TxnDate <= '{end_date}' ORDER BY TxnDate DESC"
        return self._make_api_request("query", params={"query": query})
        
    def get_invoices(self, start_date=None, end_date=None, status=None):
        """Get invoices from QuickBooks within the specified date range and status."""
        # Default date range if not specified
        if not start_date:
            start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
            
        # Validate date format
        if not self._validate_date(start_date):
            cfo_logger.error(f"Invalid start_date format: {start_date}. Must be YYYY-MM-DD.")
            raise ValueError(f"Invalid start_date format: {start_date}. Must be YYYY-MM-DD.")
            
        if not self._validate_date(end_date):
            cfo_logger.error(f"Invalid end_date format: {end_date}. Must be YYYY-MM-DD.")
            raise ValueError(f"Invalid end_date format: {end_date}. Must be YYYY-MM-DD.")
            
        # Ensure start_date is before end_date
        if start_date > end_date:
            cfo_logger.warning(f"start_date {start_date} is after end_date {end_date}. Swapping dates.")
            start_date, end_date = end_date, start_date
            
        query = f"SELECT * FROM Invoice WHERE TxnDate >= '{start_date}' AND TxnDate <= '{end_date}'"
        
        if status:
            # Validate status
            valid_statuses = ["Paid", "Payable", "PendingPayment"]
            if status not in valid_statuses:
                cfo_logger.warning(f"Invalid invoice status: {status}. Using without status filter.")
            else:
                query += f" AND status = '{status}'"
            
        query += " ORDER BY TxnDate DESC"
        return self._make_api_request("query", params={"query": query})
        
    def get_bills(self, start_date=None, end_date=None, status=None):
        """Get bills from QuickBooks within the specified date range and status."""
        # Default date range if not specified
        if not start_date:
            start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
            
        # Validate date format
        if not self._validate_date(start_date):
            cfo_logger.error(f"Invalid start_date format: {start_date}. Must be YYYY-MM-DD.")
            raise ValueError(f"Invalid start_date format: {start_date}. Must be YYYY-MM-DD.")
            
        if not self._validate_date(end_date):
            cfo_logger.error(f"Invalid end_date format: {end_date}. Must be YYYY-MM-DD.")
            raise ValueError(f"Invalid end_date format: {end_date}. Must be YYYY-MM-DD.")
            
        # Ensure start_date is before end_date
        if start_date > end_date:
            cfo_logger.warning(f"start_date {start_date} is after end_date {end_date}. Swapping dates.")
            start_date, end_date = end_date, start_date
            
        query = f"SELECT * FROM Bill WHERE TxnDate >= '{start_date}' AND TxnDate <= '{end_date}'"
        
        if status:
            # Validate status
            valid_statuses = ["Paid", "Payable", "PendingPayment"]
            if status not in valid_statuses:
                cfo_logger.warning(f"Invalid bill status: {status}. Using without status filter.")
            else:
                query += f" AND status = '{status}'"
            
        query += " ORDER BY TxnDate DESC"
        return self._make_api_request("query", params={"query": query})
        
    def get_profit_and_loss(self, start_date=None, end_date=None):
        """Get profit and loss report data from QuickBooks."""
        # Default date range if not specified
        if not start_date:
            start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
            
        # Validate date format
        if not self._validate_date(start_date):
            cfo_logger.error(f"Invalid start_date format: {start_date}. Must be YYYY-MM-DD.")
            raise ValueError(f"Invalid start_date format: {start_date}. Must be YYYY-MM-DD.")
            
        if not self._validate_date(end_date):
            cfo_logger.error(f"Invalid end_date format: {end_date}. Must be YYYY-MM-DD.")
            raise ValueError(f"Invalid end_date format: {end_date}. Must be YYYY-MM-DD.")
            
        # Ensure start_date is before end_date
        if start_date > end_date:
            cfo_logger.warning(f"start_date {start_date} is after end_date {end_date}. Swapping dates.")
            start_date, end_date = end_date, start_date
            
        report_endpoint = f"reports/ProfitAndLoss?start_date={start_date}&end_date={end_date}&accounting_method=Accrual"
        return self._make_api_request(report_endpoint)
        
    def get_balance_sheet(self, as_of_date=None):
        """Get balance sheet report data from QuickBooks."""
        if not as_of_date:
            as_of_date = datetime.now().strftime("%Y-%m-%d")
            
        # Validate date format
        if not self._validate_date(as_of_date):
            cfo_logger.error(f"Invalid as_of_date format: {as_of_date}. Must be YYYY-MM-DD.")
            raise ValueError(f"Invalid as_of_date format: {as_of_date}. Must be YYYY-MM-DD.")
            
        report_endpoint = f"reports/BalanceSheet?as_of={as_of_date}&accounting_method=Accrual"
        return self._make_api_request(report_endpoint)
        
    def get_cash_flow(self, start_date=None, end_date=None):
        """Get cash flow report data from QuickBooks."""
        # Default date range if not specified
        if not start_date:
            start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
            
        # Validate date format
        if not self._validate_date(start_date):
            cfo_logger.error(f"Invalid start_date format: {start_date}. Must be YYYY-MM-DD.")
            raise ValueError(f"Invalid start_date format: {start_date}. Must be YYYY-MM-DD.")
            
        if not self._validate_date(end_date):
            cfo_logger.error(f"Invalid end_date format: {end_date}. Must be YYYY-MM-DD.")
            raise ValueError(f"Invalid end_date format: {end_date}. Must be YYYY-MM-DD.")
            
        # Ensure start_date is before end_date
        if start_date > end_date:
            cfo_logger.warning(f"start_date {start_date} is after end_date {end_date}. Swapping dates.")
            start_date, end_date = end_date, start_date
            
        report_endpoint = f"reports/CashFlow?start_date={start_date}&end_date={end_date}"
        return self._make_api_request(report_endpoint)

    def query_customers(self, name_query=None):
        """Query customers based on name."""
        if name_query is None:
            query = "SELECT * FROM Customer"
        else:
            # Sanitize the name query to remove leading/trailing whitespace and replace newlines
            sanitized_query = str(name_query).strip().replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')\
            # Escape single quotes for the SQL query
            sanitized_query = sanitized_query.replace("'", "\\'")
            query = f"SELECT * FROM Customer WHERE DisplayName LIKE '{sanitized_query}%'"
        
        try:
            cfo_logger.info(f"Querying customers with query: {query}")
            response = self._make_api_request("query", params={"query": query})
            customers = response.get("QueryResponse", {}).get("Customer", [])
            cfo_logger.info(f"Found {len(customers)} customers matching '{name_query}'.")
            return customers
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                # Log specific QuickBooks error details if available
                try:
                    error_detail = e.response.json()
                    cfo_logger.error(f"QuickBooks query error for name '{name_query}': {json.dumps(error_detail)}")
                except Exception as json_e:
                    cfo_logger.error(f"QuickBooks query error for name '{name_query}': {str(e)}", exc_info=True)
            else:
                 cfo_logger.error(f"Error querying customers for name '{name_query}': {str(e)}", exc_info=True)
            return [] # Return empty list on error
        except Exception as e:
            cfo_logger.error(f"Unexpected error querying customers for name '{name_query}': {str(e)}", exc_info=True)
            return []

    def create_customer(self, customer_name: str) -> Optional[Dict]:
        """Create a new customer in QuickBooks.
        
        Args:
            customer_name: Name of the customer to create
            
        Returns:
            Dictionary containing customer data if successful, None otherwise
        """
        # Basic validation
        if not isinstance(customer_name, str) or not customer_name.strip():
            cfo_logger.error(f"Invalid customer name provided for creation: {customer_name} (Type: {type(customer_name)})")
            return None
        
        sanitized_name = customer_name.strip()
        
        # Split name for GivenName/FamilyName - very basic split
        name_parts = sanitized_name.split(' ', 1)
        given_name = name_parts[0]
        family_name = name_parts[1] if len(name_parts) > 1 else ""

        customer_data = {
            "DisplayName": sanitized_name,
            "GivenName": given_name,
            "FamilyName": family_name,
            "Active": True
        }
        
        try:
            response = self._make_api_request("customer", method="POST", data=customer_data)
            if response and "Customer" in response:
                cfo_logger.info(f"Created customer: {customer_name}")
                return response["Customer"]
        except Exception as e:
            cfo_logger.error(f"Failed to create customer: {customer_name}\n{str(e)}")
            
        return None

    def create_invoice(self, invoice_data=None, customer_id=None, line_items=None, memo=None, draft=False, doc_number=None):
        """Create a new invoice in QuickBooks.
        
        Args:
            invoice_data (dict, optional): Complete invoice data for the QuickBooks API
            customer_id (str, optional): Customer ID if not using invoice_data
            line_items (list, optional): List of line items if not using invoice_data
            memo (str, optional): Memo text for the invoice
            draft (bool, optional): Whether to create as draft (default: False)
            doc_number (str, optional): Invoice/PO number to use as document number
            
        Returns:
            dict: The created invoice data or None if failed
        """
        try:
            # Handle the case where individual parameters are provided instead of complete invoice_data
            if not invoice_data and customer_id and line_items:
                # Build invoice data from parameters
                invoice_data = {
                    "CustomerRef": {
                        "value": str(customer_id)  # Ensure it's a string
                    },
                    "Line": []
                }
                
                # Set document number if provided
                if doc_number:
                    invoice_data["DocNumber"] = doc_number
                    cfo_logger.info(f"Setting invoice DocNumber to: {doc_number}")
                
                # Convert line items to QuickBooks format
                for item in line_items:
                    line_item = {
                        "Amount": float(item['amount']),
                        "Description": item['description'],
                        "DetailType": "SalesItemLineDetail",
                        "SalesItemLineDetail": {}
                    }
                    
                    # Add item reference if available
                    if 'item_id' in item and item['item_id']:
                        line_item["SalesItemLineDetail"]["ItemRef"] = {
                            "value": str(item['item_id'])  # Ensure it's a string
                        }
                    
                    # If activity_type is specified, set it as the custom field or in the description
                    if 'activity_type' in item and item['activity_type']:
                        # Option 1: Add it to the description
                        if not "Customer Specified" in item['activity_type']:
                            line_item["Description"] = f"{item['activity_type']} - {item['description']}"
                        else:
                            line_item["Description"] = f"{item['activity_type']}"
                    
                    invoice_data["Line"].append(line_item)
                
                # Add memo if provided
                if memo:
                    invoice_data["CustomerMemo"] = {
                        "value": memo
                    }
                
                # Set as draft if requested
                if draft:
                    invoice_data["PrivateNote"] = "Draft invoice - requires approval"
            
            if not invoice_data:
                raise ValueError("Invoice data cannot be empty")
            
            # Validate minimum required fields
            if "CustomerRef" not in invoice_data:
                raise ValueError("CustomerRef is required for invoice creation")
            
            if "Line" not in invoice_data or not invoice_data["Line"]:
                raise ValueError("At least one line item is required for invoice creation")
            
            # Add transaction date if not provided
            if "TxnDate" not in invoice_data:
                invoice_data["TxnDate"] = datetime.now().strftime("%Y-%m-%d")
            
            # Set document number if provided as parameter and not already in invoice_data
            if doc_number and "DocNumber" not in invoice_data:
                invoice_data["DocNumber"] = doc_number
            
            # Log what we're sending
            cfo_logger.info(f"Creating invoice with data: {json.dumps(invoice_data)}")
            
            # Create the invoice
            response = self._make_api_request("invoice", method="POST", data=invoice_data)
            
            # Log the response structure to help debug
            cfo_logger.info(f"Invoice creation response type: {type(response)}")
            if isinstance(response, dict):
                cfo_logger.info(f"Invoice response keys: {','.join(response.keys())}")
                
                # Check for nested Invoice object
                if 'Invoice' in response and isinstance(response['Invoice'], dict):
                    invoice_obj = response['Invoice']
                    cfo_logger.info(f"Found nested Invoice object with keys: {','.join(invoice_obj.keys())}")
                    
                    # Extract ID and DocNumber from nested object
                    invoice_id = invoice_obj.get('Id') or invoice_obj.get('id', 'unknown')
                    doc_number = invoice_obj.get('DocNumber') or invoice_obj.get('docNumber')
                    
                    # Add these back to the main response for consistent access
                    response['id'] = invoice_id
                    response['doc_number'] = doc_number
                
                # Directly on response object
                else:
                    invoice_id = response.get('Id') or response.get('id', 'unknown')
                    doc_number = response.get('DocNumber') or response.get('docNumber')
                    
                    # Add normalized keys
                    response['id'] = invoice_id
                    response['doc_number'] = doc_number
                    
                cfo_logger.info(f"Created invoice with ID: {invoice_id}, DocNumber: {doc_number or 'Not assigned'}")
            
            return response
            
        except Exception as e:
            cfo_logger.error(f"Error creating invoice: {str(e)}")
            # Log the data we tried to send
            if invoice_data:
                try:
                    cfo_logger.error(f"Invoice data: {json.dumps(invoice_data)}")
                except:
                    cfo_logger.error(f"Invoice data could not be serialized")
            return None

    def get_invoice_by_id(self, invoice_id):
        """Get a specific invoice by ID."""
        try:
            return self._make_api_request(f"invoice/{invoice_id}")
        except Exception as e:
            cfo_logger.error(f"Error getting invoice {invoice_id}: {str(e)}")
            return None

    def send_invoice(self, invoice_id, email_data=None):
        """Send an invoice to the customer via email.
        
        Args:
            invoice_id (str): ID of the invoice to send
            email_data (dict): Optional custom email data (subject, message)
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            # Construct email data if not provided
            if not email_data:
                email_data = {
                    "EmailMessage": {
                        "Subject": "Your Invoice from " + self.company_name,
                        "Message": "Please find attached your invoice. Thank you for your business."
                    }
                }
            
            endpoint = f"invoice/{invoice_id}/send"
            response = self._make_api_request(endpoint, method="POST", data=email_data)
            
            cfo_logger.info(f"Invoice {invoice_id} sent to customer")
            return True
        except Exception as e:
            cfo_logger.error(f"Error sending invoice {invoice_id}: {str(e)}")
            return False

    def update_invoice(self, invoice_id, invoice_data):
        """Update an existing invoice in QuickBooks.
        
        Args:
            invoice_id (str): ID of the invoice to update
            invoice_data (dict): Updated invoice data
            
        Returns:
            dict: The updated invoice data or None if failed
        """
        try:
            # Get the current invoice first (needed for SyncToken)
            current_invoice = self.get_invoice_by_id(invoice_id)
            if not current_invoice:
                raise ValueError(f"Invoice {invoice_id} not found")
            
            # Ensure the ID and SyncToken are included
            invoice_data["Id"] = invoice_id
            invoice_data["SyncToken"] = current_invoice["SyncToken"]
            
            response = self._make_api_request("invoice", method="POST", data=invoice_data)
            cfo_logger.info(f"Updated invoice {invoice_id}")
            return response
        except Exception as e:
            cfo_logger.error(f"Error updating invoice {invoice_id}: {str(e)}")
            return None

    def approve_invoice(self, invoice_id):
        """Approve a draft invoice and make it ready to send.
        
        Args:
            invoice_id (str): ID of the invoice to approve
            
        Returns:
            bool: True if approved successfully, False otherwise
        """
        try:
            # Get current invoice
            current_invoice = self.get_invoice_by_id(invoice_id)
            if not current_invoice:
                raise ValueError(f"Invoice {invoice_id} not found")
            
            # Update invoice to remove draft status
            current_invoice.pop("DraftStatus", None)
            
            # Update invoice
            result = self.update_invoice(invoice_id, current_invoice)
            if result:
                cfo_logger.info(f"Invoice {invoice_id} approved")
                return True
            return False
        except Exception as e:
            cfo_logger.error(f"Error approving invoice {invoice_id}: {str(e)}")
            return False

    def get_invoice_preview_url(self, invoice_id):
        """Get URL for invoice preview.
        
        Args:
            invoice_id (str): ID of the invoice
            
        Returns:
            str: URL to preview invoice or None if not available
        """
        try:
            base_url = "https://app.qbo.intuit.com" if self.environment == "production" else "https://app.sandbox.qbo.intuit.com"
            return f"{base_url}/app/invoice?txnId={invoice_id}"
        except Exception as e:
            cfo_logger.error(f"Error generating preview URL for invoice {invoice_id}: {str(e)}")
            return None

    def query_items(self, query=None, limit=None):
        """Search for items in QuickBooks by query.
        
        Args:
            query (str, optional): SQL-like query string to filter items
            limit (int, optional): Maximum number of results to return
            
        Returns:
            list: List of items matching the query
        """
        try:
            # Build the query
            if not query:
                base_query = "SELECT * FROM Item WHERE Active = true"
            else:
                base_query = f"SELECT * FROM Item WHERE {query} AND Active = true"
            
            # Add limit if specified
            if limit:
                base_query += f" MAXRESULTS {limit}"
                
            # Make the request
            response = self._make_api_request("query", params={"query": base_query})
            
            # Extract items from response
            if "QueryResponse" in response and "Item" in response["QueryResponse"]:
                return response["QueryResponse"]["Item"]
            
            return []
            
        except Exception as e:
            cfo_logger.error(f"Error querying items: {str(e)}")
            return []
            
    def create_item(self, name, type="Service", income_account_id=None):
        """Create a new item in QuickBooks.
        
        Args:
            name (str): Name of the item
            type (str, optional): Type of item (Service, Inventory, NonInventory)
            income_account_id (str, optional): ID of income account to use
            
        Returns:
            dict: Created item or None if failed
        """
        try:
            # Build item data
            item_data = {
                "Name": name,
                "Type": type,
                "Active": True
            }
            
            # Add income account reference if provided
            if income_account_id:
                item_data["IncomeAccountRef"] = {
                    "value": income_account_id
                }
            
            # Create the item
            response = self._make_api_request("item", method="POST", data=item_data)
            
            cfo_logger.info(f"Created {type} item: {name}")
            return response
            
        except Exception as e:
            cfo_logger.error(f"Error creating item: {str(e)}")
            return None
            
    def query_accounts(self, query=None, limit=None):
        """Search for accounts in QuickBooks by query.
        
        Args:
            query (str, optional): SQL-like query string to filter accounts
            limit (int, optional): Maximum number of results to return
            
        Returns:
            list: List of accounts matching the query
        """
        try:
            # Build the query
            if not query:
                base_query = "SELECT * FROM Account WHERE Active = true"
            else:
                base_query = f"SELECT * FROM Account WHERE {query} AND Active = true"
            
            # Add limit if specified
            if limit:
                base_query += f" MAXRESULTS {limit}"
                
            # Make the request
            response = self._make_api_request("query", params={"query": base_query})
            
            # Extract accounts from response
            if "QueryResponse" in response and "Account" in response["QueryResponse"]:
                return response["QueryResponse"]["Account"]
            
            return []
            
        except Exception as e:
            cfo_logger.error(f"Error querying accounts: {str(e)}")
            return []

    def search_quickbooks(self, search_term: str, entity_types: list[str], search_fields_config: dict = None) -> dict[str, list[dict]]:
        """Search QuickBooks entities based on a search term across specified fields."""
        if not search_term:
            cfo_logger.warning("Search term is empty, skipping QuickBooks search.")
            return {entity: [] for entity in entity_types}
            
        # --- Ultra-Granular Multi-Query Strategy ---

        # 1. Split search term into words
        search_words = search_term.split()
        if not search_words:
            cfo_logger.warning("Search term resulted in no words to search, skipping.")
            return {entity: [] for entity in entity_types}

        # 2. Define reasonable default search fields if config isn't provided or lacks detail
        default_search_fields = {
            "Customer": ["DisplayName", "CompanyName", "Notes", "PrimaryEmailAddr.Address", "BillAddr.Line1", "ShipAddr.Line1"],
            "Estimate": ["DocNumber", "PrivateNote", "Memo", "CustomerMemo"],
            "Invoice": ["DocNumber", "PrivateNote", "Memo", "CustomerMemo", "BillEmail.Address"], 
        }

        # 3. Determine final fields to use for each entity, prioritizing provided config
        final_search_fields = {}
        search_fields_config = search_fields_config or {} # Ensure it's a dict
        for entity in entity_types:
            config_fields = search_fields_config.get(entity)
            if config_fields and isinstance(config_fields, list) and len(config_fields) > 0:
                final_search_fields[entity] = config_fields
            elif entity in default_search_fields:
                final_search_fields[entity] = default_search_fields[entity]
            # If no fields found for an entity, it will be skipped later

        # --- Execute One Query Per Field Per Word --- 
        # Use a dictionary to store results and deduplicate by ID: {entity: {id: record}}
        all_results_by_id = {entity: {} for entity in entity_types}

        for entity in entity_types:
             # Skip if no fields were defined for this entity
             if entity not in final_search_fields:
                 cfo_logger.warning(f"No search fields available for entity {entity}. Skipping granular search.")
                 continue
                 
             entity_fields = final_search_fields[entity]
             
             for word in search_words:
                 # Escape single quotes in the word itself
                 sanitized_word = word.replace("'", "''") 
                 
                 for field in entity_fields:
                     # Construct the simplest possible query: one field, one word
                     query = f"SELECT * FROM {entity} WHERE {field} LIKE '%{sanitized_word}%' MAXRESULTS 50"
                     
                     cfo_logger.info(f"Executing granular query for word '{word}' in {entity}.{field}: {query}")
                 
                     try:
                         response = self._make_api_request("query", params={"query": query})
                         
                         # Add results to our storage, overwriting duplicates (last query wins for a given ID)
                         if response and f'{entity}' in response.get('QueryResponse', {}):
                             records = response['QueryResponse'][f'{entity}']
                             cfo_logger.debug(f"Found {len(records)} {entity}(s) matching word '{word}' in field {field}")
                             for record in records:
                                 record_id = record.get('Id')
                                 if record_id:
                                     all_results_by_id[entity][record_id] = record # Store by ID for deduplication
                                     
                     except requests.exceptions.HTTPError as e:
                         # Log query errors but continue with other fields/words/entities
                         if e.response.status_code == 400:
                             try: error_detail = e.response.json() 
                             except: error_detail = e.response.text
                             cfo_logger.error(f"QB query error searching {entity}.{field} for word '{word}': {error_detail}", exc_info=False)
                         else:
                             cfo_logger.error(f"HTTP error searching {entity}.{field} for word '{word}': {e}", exc_info=True)
                         # Don't stop the whole search if one field query fails
                     except Exception as e:
                          cfo_logger.error(f"Unexpected error searching {entity}.{field} for word '{word}': {e}", exc_info=True)
                          # Continue processing other fields/words/entities

        # --- Consolidate, Filter, and Format Final Results --- 
        final_results = {entity: [] for entity in entity_types}
        for entity in entity_types:
            unique_records = list(all_results_by_id[entity].values())
            cfo_logger.info(f"Total unique {entity} records found across all words: {len(unique_records)}")
            
            # Post-query filtering for Active status
            if entity in ["Customer", "Estimate", "Invoice", "Item", "Account"]: # Entities to check for Active status
                 active_records = [r for r in unique_records if r.get('Active') is True]
                 final_results[entity] = active_records
                 cfo_logger.info(f"Kept {len(active_records)} active {entity} records.")
            else:
                # For entities without an Active field, keep all results
                final_results[entity] = unique_records
                
        return final_results

    def get_estimate_details(self, estimate_id: str) -> Optional[dict]:
        """Retrieve details for a specific Estimate by its ID."""
        if not estimate_id:
            cfo_logger.warning("Estimate ID is required to get details.")
            return None
            
        try:
            # Ensure estimate_id is treated as a string for the URL
            endpoint = f"estimate/{str(estimate_id)}" 
            estimate_data = self._make_api_request(endpoint)
            return estimate_data.get('Estimate') if estimate_data else None
        except requests.exceptions.HTTPError as e:
             if e.response.status_code == 400 and "Invalid Reference Id" in e.response.text:
                 cfo_logger.warning(f"Estimate with ID {estimate_id} not found.")
                 return None
             else:
                 cfo_logger.error(f"Error fetching estimate details for ID {estimate_id}: {e}", exc_info=True)
                 return None
        except Exception as e:
            cfo_logger.error(f"Unexpected error fetching estimate details for ID {estimate_id}: {e}", exc_info=True)
            return None

    def get_related_payments(self, invoice_id: str = None, estimate_id: str = None) -> list[dict]:
        """Retrieve payments related to a specific invoice or estimate."""
        if not invoice_id and not estimate_id:
            cfo_logger.warning("Either invoice_id or estimate_id is required to find related payments.")
            return []
            
        # Construct query based on available ID
        linked_txns_clause = []
        if invoice_id:
            linked_txns_clause.append(f"LinkedTxn.TxnId = '{invoice_id}' AND LinkedTxn.TxnType = 'Invoice'")
        if estimate_id:
             linked_txns_clause.append(f"LinkedTxn.TxnId = '{estimate_id}' AND LinkedTxn.TxnType = 'Estimate'")
        
        query = f"SELECT * FROM Payment WHERE {' OR '.join(linked_txns_clause)}"
        
        try:
            cfo_logger.info(f"Executing related payments query: {query}")
            response = self._make_api_request("query", params={"query": query})
            
            if response and 'Payment' in response.get('QueryResponse', {}):
                return response['QueryResponse']['Payment']
            else:
                 cfo_logger.info(f"No payments found related to Invoice={invoice_id}, Estimate={estimate_id}")
                 return []
                 
        except requests.exceptions.HTTPError as e:
            cfo_logger.error(f"Error fetching related payments: {e}", exc_info=True)
            return []
        except Exception as e:
            cfo_logger.error(f"Unexpected error fetching related payments: {e}", exc_info=True)
            return []

    def get_customer(self, customer_id: str) -> Optional[dict]:
        """Retrieve details for a specific customer by ID."""
        if not customer_id:
            return None
        try:
            endpoint = f"customer/{str(customer_id)}"
            response = self._make_api_request(endpoint)
            return response.get('Customer') if response else None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400 and "Invalid Reference Id" in e.response.text:
                 cfo_logger.warning(f"Customer with ID {customer_id} not found.")
                 return None
            else:
                 cfo_logger.error(f"Error fetching customer {customer_id}: {e}")
                 return None
        except Exception as e:
            cfo_logger.error(f"Unexpected error fetching customer {customer_id}: {e}")
            return None 