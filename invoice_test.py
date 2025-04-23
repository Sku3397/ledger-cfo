#!/usr/bin/env python3
"""
Script to create a test invoice in QuickBooks Online.
This script integrates with the existing CFO Agent codebase.
"""

# Import necessary modules
from quickbooks_api import QuickBooksAPI
from config import config
from logger import cfo_logger
import json
import sys
from datetime import datetime

def create_test_invoice():
    """Create a test invoice for $123.00"""
    try:
        print("Creating test invoice in QuickBooks Online...")
        
        # Initialize the QuickBooks API client
        qb_api = QuickBooksAPI()
        
        # Set up test customer lookup
        customer_name = "Test Customer"
        customers = qb_api.query_customers(customer_name)
        
        # If we found a test customer, use it
        customer_id = "1"  # Default fallback
        if customers:
            customer_id = customers[0]["Id"]
            print(f"Using existing customer: {customers[0].get('DisplayName', 'Test Customer')} (ID: {customer_id})")
        else:
            print("Warning: Could not find test customer, using default ID")
        
        # Create invoice data
        invoice_data = {
            "CustomerRef": {
                "value": customer_id
            },
            "Line": [
                {
                    "Amount": 123.00,
                    "Description": "Test invoice item",
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {
                        "ItemRef": {
                            "value": "1"  # Assuming this is a valid service item
                        }
                    }
                }
            ]
        }
        
        # Create the invoice
        result = qb_api.create_invoice(invoice_data)
        
        if result and 'Id' in result:
            invoice_id = result['Id']
            print(f"Invoice created successfully!")
            print(f"Invoice ID: {invoice_id}")
            print(f"Amount: $123.00")
            
            # Get and print invoice URL
            url = qb_api.get_invoice_preview_url(invoice_id)
            if url:
                print(f"Preview URL: {url}")
                
            # Log success
            cfo_logger.info(f"Test invoice {invoice_id} created successfully")
            return invoice_id
        else:
            print("Failed to create invoice")
            cfo_logger.error("Failed to create test invoice - missing invoice ID in response")
            return None
            
    except Exception as e:
        print(f"Error creating test invoice: {str(e)}")
        cfo_logger.error(f"Error creating test invoice: {str(e)}")
        return None

if __name__ == "__main__":
    invoice_id = create_test_invoice()
    if invoice_id:
        print("\nSUCCESS: Test invoice created")
    else:
        print("\nFAILED: Could not create test invoice")
        sys.exit(1) 