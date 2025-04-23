#!/usr/bin/env python3
# Simple script to create a test invoice in QuickBooks
# This is intended to be called from the main application

from quickbooks_api import QuickBooksAPI
from config import config
from logger import cfo_logger

def create_test_invoice():
    """Create a test invoice in QuickBooks"""
    try:
        # Initialize API with proper configuration
        qb_api = QuickBooksAPI()
        
        # Search for an existing customer or create a default one
        customer_name = "Test Customer"
        customers = qb_api.query_customers(customer_name)
        
        customer_id = "1"  # Default if not found
        if customers:
            customer_id = customers[0]["Id"]
            print(f"Using existing customer: {customers[0]['DisplayName']} (ID: {customer_id})")
        
        # Create invoice line item for $123
        line_item = {
            "Amount": 123.00,
            "Description": "Test invoice item created via API",
            "DetailType": "SalesItemLineDetail",
            "SalesItemLineDetail": {
                "ItemRef": {
                    "value": "1"  # Default service item
                }
            }
        }
        
        # Create invoice data
        invoice_data = {
            "CustomerRef": {
                "value": customer_id
            },
            "Line": [line_item]
        }
        
        # Create the invoice
        result = qb_api.create_invoice(invoice_data)
        
        if result and 'Id' in result:
            invoice_id = result['Id']
            print(f"Successfully created test invoice with ID: {invoice_id}")
            
            # Get invoice URL
            url = qb_api.get_invoice_preview_url(invoice_id)
            if url:
                print(f"Invoice URL: {url}")
            
            return invoice_id
        else:
            print("Failed to create invoice")
            return None
            
    except Exception as e:
        print(f"Error creating test invoice: {str(e)}")
        cfo_logger.error(f"Error creating test invoice: {str(e)}")
        return None

if __name__ == "__main__":
    print("Creating test invoice...")
    invoice_id = create_test_invoice()
    if invoice_id:
        print(f"Test invoice created with ID: {invoice_id}")
    else:
        print("Failed to create test invoice") 