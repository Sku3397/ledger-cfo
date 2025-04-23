from typing import Optional, Dict, List, Any, Union
from dataclasses import dataclass
from datetime import datetime, timedelta
from logger import cfo_logger
from quickbooks_api import QuickBooksAPI
from email_parser import InvoiceRequest, IncompleteInvoiceRequest

@dataclass
class DraftInvoice:
    invoice_id: str
    customer_id: str
    amount: float
    description: str
    created_at: datetime
    status: str
    preview_url: Optional[str] = None
    
@dataclass
class PendingInvoiceRequest:
    """Represents a pending invoice request that needs additional information.
    
    This class is used to store incomplete invoice requests that need further
    information before they can be processed as draft invoices.
    """
    incomplete_request: IncompleteInvoiceRequest
    request_id: str
    created_at: datetime = datetime.now()
    customer_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "request_id": self.request_id,
            "created_at": self.created_at.isoformat(),
            "customer_id": self.customer_id,
            "missing_fields": list(self.incomplete_request.missing_fields),
            "customer_name": self.incomplete_request.customer_name,
            "materials_description": self.incomplete_request.materials_description,
            "amount": self.incomplete_request.amount,
            "email_subject": self.incomplete_request.raw_email.get("subject", ""),
            "email_from": self.incomplete_request.raw_email.get("from_email", "")
        }

class InvoiceCreator:
    """
    Creates draft invoices in QuickBooks based on parsed email requests.
    Handles customer lookup, item creation, and invoice generation.
    """
    
    def __init__(self, qb_api):
        """
        Initialize the invoice creator with QuickBooks API.
        
        Args:
            qb_api: Instance of QuickBooks API wrapper
        """
        self.qb_api = qb_api
        self.pending_requests = {}  # Store incomplete requests by ID
        cfo_logger.info("Invoice creator initialized")
    
    def create_draft_invoice(self, invoice_request) -> Optional[Union[Dict, PendingInvoiceRequest]]:
        """
        Create a draft invoice in QuickBooks based on the invoice request.
        
        Args:
            invoice_request: InvoiceRequest or IncompleteInvoiceRequest object
            
        Returns:
            Dictionary containing draft invoice details if successful, 
            PendingInvoiceRequest if additional information is needed,
            or None if failed
        """
        try:
            if not invoice_request:
                cfo_logger.error("No invoice request provided")
                return None
            
            # Handle incomplete requests
            if isinstance(invoice_request, IncompleteInvoiceRequest):
                return self._handle_incomplete_request(invoice_request)
            
            cfo_logger.info(f"Creating draft invoice for {invoice_request.customer_name}")
            
            # Lookup customer in QuickBooks
            customer = self._find_customer(invoice_request.customer_name)
            if not customer:
                cfo_logger.error(f"Customer not found: {invoice_request.customer_name}")
                return None
            
            # Create invoice line item (for the materials specified)
            line_items = [{
                'description': invoice_request.materials_description,
                'amount': invoice_request.amount,
                'item_id': self._get_default_item_id()
            }]
            
            # If we have an activity type, use it to set the line item description prefix
            if invoice_request.activity_type:
                line_items[0]['description'] = f"{invoice_request.materials_description}"
                line_items[0]['activity_type'] = invoice_request.activity_type
            
            # Generate a draft invoice
            invoice_data = {
                'customer_id': customer['id'],
                'customer_name': customer['display_name'],
                'line_items': line_items,
                'memo': f"Invoice created automatically from email request.",
                'total_amount': invoice_request.amount,
                'draft': True,  # Mark as draft
                'invoice_date': datetime.now().strftime('%Y-%m-%d'),
                'due_date': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            }
            
            # Add invoice number if available
            if invoice_request.invoice_number:
                invoice_data['doc_number'] = invoice_request.invoice_number
                cfo_logger.info(f"Using invoice/PO number: {invoice_request.invoice_number}")
            
            # Create the invoice in QuickBooks
            qb_invoice = self.qb_api.create_invoice(
                customer_id=customer['id'],
                line_items=line_items,
                memo=invoice_data['memo'],
                draft=True,
                doc_number=invoice_data.get('doc_number')  # Pass invoice number if available
            )
            
            if not qb_invoice:
                cfo_logger.error("Failed to create draft invoice in QuickBooks")
                return None
            
            # Log the response for debugging
            cfo_logger.info(f"QB Invoice response structure: {str(type(qb_invoice))}")
            
            # Handle nested Invoice structure
            if 'Invoice' in qb_invoice and isinstance(qb_invoice['Invoice'], dict):
                invoice_obj = qb_invoice['Invoice']
                cfo_logger.info(f"Found nested Invoice object with keys: {','.join(invoice_obj.keys())}")
            else:
                invoice_obj = qb_invoice
            
            # Add QuickBooks invoice ID and doc number to our invoice data
            # Check for both upper and lower case field names
            invoice_data['invoice_id'] = (
                invoice_obj.get('Id') or 
                invoice_obj.get('id') or 
                'unknown-id'
            )
            
            # If we already set a doc_number from invoice_number, use that
            # Otherwise, get it from the QuickBooks response
            if 'doc_number' not in invoice_data:
                invoice_data['doc_number'] = (
                    invoice_obj.get('DocNumber') or 
                    invoice_obj.get('docNumber') or 
                    invoice_obj.get('doc_number') or
                    f"Draft-{datetime.now().strftime('%Y%m%d%H%M%S')}"  # Fallback
                )
            
            # Add QuickBooks preview URL
            if invoice_data['invoice_id'] != 'unknown-id':
                try:
                    invoice_data['qbo_url'] = self.qb_api.get_invoice_preview_url(invoice_data['invoice_id'])
                    cfo_logger.info(f"Added QBO preview URL: {invoice_data['qbo_url']}")
                except Exception as e:
                    cfo_logger.error(f"Error getting QBO preview URL: {str(e)}")
            
            cfo_logger.info(f"Draft invoice created successfully: {invoice_data['doc_number']}")
            return invoice_data
            
        except Exception as e:
            cfo_logger.error(f"Error creating draft invoice: {str(e)}")
            return None
    
    def _handle_incomplete_request(self, incomplete_request) -> PendingInvoiceRequest:
        """
        Handle an incomplete invoice request by creating a pending request.
        
        Args:
            incomplete_request: IncompleteInvoiceRequest object
            
        Returns:
            PendingInvoiceRequest: A pending request with customer info if found
        """
        # Generate a unique ID for this request
        request_id = f"req-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Create a pending request
        pending_request = PendingInvoiceRequest(
            incomplete_request=incomplete_request,
            request_id=request_id
        )
        
        # Log which fields are missing
        missing_fields = ", ".join(incomplete_request.missing_fields)
        cfo_logger.info(f"Created pending invoice request {request_id}. Missing fields: {missing_fields}")
        
        # Try to identify the customer if we have a customer name
        if incomplete_request.customer_name:
            try:
                customer = self._find_customer(incomplete_request.customer_name)
                if customer:
                    pending_request.customer_id = customer['id']
                    cfo_logger.info(f"Found customer ID {customer['id']} for pending request {request_id}")
            except Exception as e:
                cfo_logger.error(f"Error finding customer for pending request: {str(e)}")
        
        # Store the pending request
        self.pending_requests[request_id] = pending_request
        
        return pending_request
    
    def complete_pending_request(self, request_id, additional_data) -> Optional[Dict]:
        """
        Complete a pending invoice request with the additional data provided.
        
        Args:
            request_id: ID of the pending request to complete
            additional_data: Dictionary with additional fields (amount, materials_description, etc.)
            
        Returns:
            Dictionary containing draft invoice details if successful or None if failed
        """
        if request_id not in self.pending_requests:
            cfo_logger.error(f"Pending request {request_id} not found")
            return None
            
        pending_request = self.pending_requests[request_id]
        incomplete_request = pending_request.incomplete_request
        
        # Update the incomplete request with the additional data
        for field, value in additional_data.items():
            if hasattr(incomplete_request, field):
                setattr(incomplete_request, field, value)
                if field in incomplete_request.missing_fields:
                    incomplete_request.missing_fields.remove(field)
        
        # Check if we have all required fields now
        if incomplete_request.is_complete():
            # Convert to a complete request
            complete_request = incomplete_request.to_complete_request()
            if complete_request:
                # Remove from pending requests
                self.pending_requests.pop(request_id, None)
                # Create a draft invoice with the complete request
                return self.create_draft_invoice(complete_request)
            else:
                cfo_logger.error(f"Failed to create complete request from pending request {request_id}")
        else:
            # Still missing fields
            missing_fields = ", ".join(incomplete_request.missing_fields)
            cfo_logger.info(f"Pending request {request_id} still missing fields: {missing_fields}")
            
        return None
        
    def _find_customer(self, customer_name):
        """Find a customer by name in QuickBooks or create if not found."""
        try:
            # Query QuickBooks for the customer
            customers = self.qb_api.query_customers(name_query=customer_name)
            
            if customers:
                # Get the first matching customer
                customer = customers[0]
                
                # Convert to expected format - handle both uppercase and lowercase field names
                return {
                    'id': customer.get('Id') or customer.get('id'),
                    'display_name': customer.get('DisplayName') or customer.get('displayName'),
                    'company_name': customer.get('CompanyName', '') or customer.get('companyName', ''),
                    'email': (customer.get('Email', {}) or customer.get('email', {})).get('Address', '') or 
                             (customer.get('Email', {}) or customer.get('email', {})).get('address', '')
                }
            else:
                # Customer not found by exact DisplayName match. 
                # For now, DO NOT automatically create a customer based on potentially ambiguous parsed names.
                # Future enhancement: Implement broader search (address, job ID) before deciding to create.
                cfo_logger.warning(f"Customer '{customer_name}' not found by DisplayName search. Not automatically creating customer.")
                return None
                
                # --- OLD CODE - Removed automatic creation ---
                # cfo_logger.info(f"Customer '{customer_name}' not found. Creating new customer.")
                # created_customer = self.qb_api.create_customer(customer_name)
                # if not created_customer:
                #     cfo_logger.error(f"Failed to create customer: {customer_name}")
                #     return None
                # if 'Customer' in created_customer and isinstance(created_customer['Customer'], dict):
                #     created_customer = created_customer['Customer']
                # return {
                #     'id': created_customer.get('Id') or created_customer.get('id'),
                #     'display_name': created_customer.get('DisplayName') or created_customer.get('displayName'),
                #     'company_name': created_customer.get('CompanyName', '') or created_customer.get('companyName', ''),
                #     'email': (created_customer.get('Email', {}) or created_customer.get('email', {})).get('Address', '') or 
                #              (created_customer.get('Email', {}) or created_customer.get('email', {})).get('address', '')
                # }
            
        except Exception as e:
            cfo_logger.error(f"Error finding customer: {str(e)}")
            return None
    
    def get_pending_requests(self) -> List[Dict]:
        """
        Get a list of all pending invoice requests.
        
        Returns:
            List of dictionaries with pending request details
        """
        return [req.to_dict() for req in self.pending_requests.values()]
    
    def _get_default_item_id(self):
        """
        Get a default item ID for the invoice line item.
        This could be customized based on the invoice request.
        
        Returns:
            ID of a default service item
        """
        try:
            # Query for a generic service item
            items = self.qb_api.query_items(query="Type = 'Service'", limit=1)
            if items and len(items) > 0:
                # Get the item ID, handling both upper and lowercase field names
                return items[0].get('Id') or items[0].get('id')
            
            # If no service items exist, try to create one
            cfo_logger.info("No service items found, creating a default one")
            income_account_id = self._get_income_account_id()
            
            # If no income account found, we'll try to create an item without it
            new_item = self.qb_api.create_item(
                name="Professional Services",
                type="Service",
                income_account_id=income_account_id
            )
            
            if new_item:
                # Get ID, handling both formats
                return new_item.get('Id') or new_item.get('id')
            
            # If all else fails, use a fake ID that can be replaced later
            cfo_logger.warning("Could not find or create a default item, using a placeholder ID")
            return "1"  # This will be replaced by QuickBooks with a valid item ID
            
        except Exception as e:
            cfo_logger.error(f"Error getting default item ID: {str(e)}")
            # Fallback to a placeholder ID
            return "1"
    
    def _get_income_account_id(self):
        """
        Get the ID of an income account to use for items.
        
        Returns:
            ID of an income account
        """
        try:
            # Query for an income account
            accounts = self.qb_api.query_accounts(query="AccountType = 'Income'", limit=1)
            if accounts and len(accounts) > 0:
                return accounts[0]['id']
            
            cfo_logger.warning("No income account found")
            return None
            
        except Exception as e:
            cfo_logger.error(f"Error getting income account ID: {str(e)}")
            return None 