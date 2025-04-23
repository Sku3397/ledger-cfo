#!/usr/bin/env python3
"""
Test script specifically for creating a customer in QuickBooks.
This is a simpler test focused just on customer creation.
"""

import sys
import json
from datetime import datetime
from quickbooks_api import QuickBooksAPI
from logger import cfo_logger

def test_customer_creation():
    """Test creating a customer in QuickBooks."""
    print("Testing QuickBooks Customer Creation")
    print("-----------------------------------")
    
    # Initialize the API
    qb_api = QuickBooksAPI()
    
    # Test authentication
    try:
        qb_api._ensure_token()
        print("✅ Authentication successful")
    except Exception as e:
        print(f"❌ Authentication failed: {str(e)}")
        return False
    
    # Create test customer with timestamp to make it unique
    test_customer_name = f"Customer Test {datetime.now().strftime('%Y%m%d%H%M%S')}"
    print(f"\nCreating customer: {test_customer_name}")
    
    customer_data = {
        "DisplayName": test_customer_name,
        "GivenName": "Customer",
        "FamilyName": "Test",
        "Active": True
    }
    
    try:
        # Create the customer
        new_customer = qb_api.create_customer(customer_data)
        
        if not new_customer:
            print("❌ Customer creation failed - null response")
            return False
            
        # Check if the customer was created successfully
        print("\nCustomer creation response:")
        
        # Try to print the response in a readable format
        try:
            formatted_response = json.dumps(new_customer, indent=2)
            print(formatted_response)
        except:
            print(f"Raw response: {new_customer}")
        
        # Check for customer ID in the response
        customer_id = None
        
        # Check for nested structure
        if 'Customer' in new_customer and isinstance(new_customer['Customer'], dict):
            if 'Id' in new_customer['Customer']:
                customer_id = new_customer['Customer']['Id']
                print(f"\n✅ Created customer with ID: {customer_id} (nested)")
        # Check for direct ID
        elif 'Id' in new_customer:
            customer_id = new_customer['Id']
            print(f"\n✅ Created customer with ID: {customer_id}")
        elif 'id' in new_customer:
            customer_id = new_customer['id']
            print(f"\n✅ Created customer with ID: {customer_id}")
        else:
            print("❌ Failed to find customer ID in response")
            return False
            
        return True
    except Exception as e:
        print(f"❌ Error creating customer: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_customer_creation()
    sys.exit(0 if success else 1) 