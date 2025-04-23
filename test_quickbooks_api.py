#!/usr/bin/env python3
"""
Test the QuickBooks API functionality, especially customer creation and invoice generation.
"""

import sys
import json
from datetime import datetime
from quickbooks_api import QuickBooksAPI
from logger import cfo_logger
from config import config

def test_quickbooks_api():
    """Test the QuickBooks API integration."""
    print("Testing QuickBooks API...")
    
    # Initialize the API
    qb_api = QuickBooksAPI()
    
    # 1. Test authentication
    try:
        qb_api._ensure_token()
        print("✅ Authentication successful")
    except Exception as e:
        print(f"❌ Authentication failed: {str(e)}")
        return False
    
    # 2. Test customer creation
    test_customer_name = f"Test Customer {datetime.now().strftime('%Y%m%d%H%M%S')}"
    print(f"\nCreating test customer: {test_customer_name}")
    
    try:
        new_customer = qb_api.create_customer({
            "DisplayName": test_customer_name,
            "GivenName": "Test",
            "FamilyName": "Customer",
            "Active": True
        })
        
        if new_customer and 'Id' in new_customer:
            customer_id = new_customer['Id']
            print(f"✅ Customer created with ID: {customer_id}")
        else:
            print("❌ Failed to create customer")
            return False
    except Exception as e:
        print(f"❌ Error creating customer: {str(e)}")
        return False
    
    # 3. Test item creation or retrieval
    print("\nGetting or creating a service item...")
    
    # First, try to get an existing service item
    items = qb_api.query_items("Type = 'Service'", limit=1)
    
    if items and len(items) > 0:
        item = items[0]
        item_id = item['Id']
        print(f"✅ Found existing service item: {item.get('Name', 'Unknown')} (ID: {item_id})")
    else:
        # No item found, create one
        try:
            # First get an income account
            accounts = qb_api.query_accounts("AccountType = 'Income'", limit=1)
            
            if accounts and len(accounts) > 0:
                income_account_id = accounts[0]['Id']
                print(f"Found income account: {accounts[0].get('Name', 'Unknown')} (ID: {income_account_id})")
                
                # Create service item
                new_item = qb_api.create_item(
                    name="General Services", 
                    type="Service", 
                    income_account_id=income_account_id
                )
                
                if new_item and 'Id' in new_item:
                    item_id = new_item['Id']
                    print(f"✅ Created service item with ID: {item_id}")
                else:
                    print("❌ Failed to create service item")
                    return False
            else:
                print("❌ No income account found to create item")
                return False
        except Exception as e:
            print(f"❌ Error creating service item: {str(e)}")
            return False
    
    # 4. Test invoice creation
    print("\nCreating test invoice...")
    
    try:
        # Create a simple invoice
        invoice = qb_api.create_invoice(
            customer_id=customer_id,
            line_items=[{
                'description': 'Test service item',
                'amount': 123.45,
                'item_id': item_id
            }],
            memo="Test invoice created by API test script",
            draft=True
        )
        
        if invoice and 'Id' in invoice:
            invoice_id = invoice['Id']
            print(f"✅ Invoice created with ID: {invoice_id}")
            if 'DocNumber' in invoice:
                print(f"   Invoice Number: {invoice['DocNumber']}")
        else:
            print("❌ Failed to create invoice")
            return False
    except Exception as e:
        print(f"❌ Error creating invoice: {str(e)}")
        return False
    
    print("\nAll tests completed successfully! 🎉")
    return True

if __name__ == "__main__":
    success = test_quickbooks_api()
    sys.exit(0 if success else 1) 