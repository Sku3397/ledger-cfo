#!/usr/bin/env python3

from quickbooks_api import QuickBooksAPI
from config import config
from logger import cfo_logger
import sys

def create_test_customer(qb_api):
    """Create a test customer if it doesn't exist"""
    try:
        # Search for "Test Customer" first
        customers = qb_api.query_customers("Test Customer")
        for customer in customers:
            if customer['DisplayName'].lower() == "test customer":
                cfo_logger.info(f"Found existing test customer with ID: {customer['Id']}")
                return customer
        
        # Customer doesn't exist, create it
        customer_data = {
            "DisplayName": "Test Customer",
            "CompanyName": "Test Company",
            "GivenName": "Test",
            "FamilyName": "Customer",
            "Active": True
        }
        
        # Note: This is just a stub - the actual customer creation API call would go here
        # In the real system, we'd call the QuickBooks API to create a customer
        cfo_logger.info("Creating new test customer")
        
        # For this sample, we'll just use a simulated response
        return {
            "Id": "123456",
            "DisplayName": "Test Customer",
            "CompanyName": "Test Company"
        }
    except Exception as e:
        cfo_logger.error(f"Error creating test customer: {str(e)}")
        return None

def create_test_invoice(amount=123.00):
    """Create a test invoice for the specified amount"""
    try:
        # Initialize the QB API
        qb_api = QuickBooksAPI()
        
        # Get or create test customer
        customer = create_test_customer(qb_api)
        if not customer:
            raise ValueError("Failed to get or create test customer")
        
        # Create invoice line item
        line_item = {
            "Amount": amount,
            "Description": "Test invoice item",
            "DetailType": "SalesItemLineDetail",
            "SalesItemLineDetail": {
                "ItemRef": {
                    "value": "1",  # Default item for services
                    "name": "Services"
                }
            }
        }
        
        # Create invoice data
        invoice_data = {
            "CustomerRef": {
                "value": customer['Id']
            },
            "Line": [line_item]
        }
        
        # Create the invoice
        result = qb_api.create_invoice(invoice_data)
        
        if result and 'Id' in result:
            invoice_id = result['Id']
            invoice_url = qb_api.get_invoice_preview_url(invoice_id)
            
            print(f"Successfully created test invoice!")
            print(f"Invoice ID: {invoice_id}")
            print(f"Amount: ${amount:.2f}")
            print(f"Customer: {customer['DisplayName']}")
            if invoice_url:
                print(f"Invoice URL: {invoice_url}")
            
            return invoice_id
        else:
            print("Failed to create invoice. Check logs for details.")
            return None
            
    except Exception as e:
        print(f"Error: {str(e)}")
        cfo_logger.error(f"Error creating test invoice: {str(e)}")
        return None

if __name__ == "__main__":
    # Parse command line arguments for amount if provided
    amount = 123.00
    if len(sys.argv) > 1:
        try:
            amount = float(sys.argv[1])
        except ValueError:
            print(f"Invalid amount: {sys.argv[1]}, using default: $123.00")
    
    create_test_invoice(amount) 