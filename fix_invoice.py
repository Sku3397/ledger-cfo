import os
import sys
import json
from datetime import datetime, timedelta
import traceback

# Ensure demo mode is off and load environment correctly
os.environ["DEMO_MODE"] = "false"

from config import config
from logger import cfo_logger
from quickbooks_api import QuickBooksAPI

def create_visible_invoice():
    """Create a fully visible invoice in QBO with all required fields."""
    print("\n=== CREATING FULLY VISIBLE QBO INVOICE ===\n")
    
    # Force reload config to ensure demo mode is off
    print(f"Demo mode: {config.demo_mode}")
    print(f"Environment: {config.quickbooks_environment}")
    print(f"Client ID: {config.quickbooks_client_id[:5]}...{config.quickbooks_client_id[-5:] if config.quickbooks_client_id else ''}")
    
    # Initialize API with full debug logging
    qb_api = QuickBooksAPI()
    print("API initialized with full debugging")
    
    try:
        # 1. Get a valid customer
        print("\nFinding a valid customer...")
        customers_query = "SELECT * FROM Customer WHERE Active = true AND DisplayName LIKE '%SPSA%'"
        customers_response = qb_api._make_api_request("query", params={"query": customers_query})
        
        if "QueryResponse" not in customers_response or "Customer" not in customers_response["QueryResponse"]:
            print("SPSA customer not found, trying to get any customer...")
            customers_query = "SELECT * FROM Customer WHERE Active = true LIMIT 5"
            customers_response = qb_api._make_api_request("query", params={"query": customers_query})
        
        if "QueryResponse" in customers_response and "Customer" in customers_response["QueryResponse"]:
            customers = customers_response["QueryResponse"]["Customer"]
            if customers:
                customer = customers[0]
                customer_id = customer.get("Id")
                customer_name = customer.get("DisplayName")
                print(f"Using customer: {customer_name} (ID: {customer_id})")
            else:
                print("No customers found! Cannot create invoice.")
                return
        else:
            print("Failed to retrieve customers! Cannot create invoice.")
            return
        
        # 2. Get a valid service item
        print("\nFinding a valid service item...")
        items_query = "SELECT * FROM Item WHERE Active = true LIMIT 10"
        items_response = qb_api._make_api_request("query", params={"query": items_query})
        
        if "QueryResponse" in items_response and "Item" in items_response["QueryResponse"]:
            items = items_response["QueryResponse"]["Item"]
            if items:
                for item in items:
                    if item.get("Type") in ["Service", "NonInventory"]:
                        item_id = item.get("Id")
                        item_name = item.get("Name")
                        print(f"Using item: {item_name} (ID: {item_id}, Type: {item.get('Type')})")
                        break
                else:
                    # If no Service or NonInventory item found, use the first one
                    item = items[0]
                    item_id = item.get("Id")
                    item_name = item.get("Name")
                    print(f"Using fallback item: {item_name} (ID: {item_id}, Type: {item.get('Type')})")
            else:
                print("No items found! Cannot create invoice.")
                return
        else:
            print("Failed to retrieve items! Cannot create invoice.")
            return
        
        # 3. Get account/income account details if needed
        print("\nGetting income account information...")
        accounts_query = "SELECT * FROM Account WHERE AccountType = 'Income' AND Active = true LIMIT 1"
        accounts_response = qb_api._make_api_request("query", params={"query": accounts_query})
        
        income_account_id = None
        if "QueryResponse" in accounts_response and "Account" in accounts_response["QueryResponse"]:
            accounts = accounts_response["QueryResponse"]["Account"]
            if accounts:
                account = accounts[0]
                income_account_id = account.get("Id")
                print(f"Using income account: {account.get('Name')} (ID: {income_account_id})")
        
        # 4. Create a very distinct invoice number
        timestamp = datetime.now().strftime("%m%d_%H%M")
        doc_number = f"VISIBLE_TEST_{timestamp}"
        print(f"\nUsing unique DocNumber: {doc_number}")
        
        # 5. Create comprehensive invoice data with all required fields
        print("\nPreparing complete invoice data...")
        
        today = datetime.now().strftime("%Y-%m-%d")
        due_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        # Build detailed line item
        line_item = {
            "DetailType": "SalesItemLineDetail",
            "Amount": 123.45,
            "Description": f"VERY VISIBLE TEST INVOICE - please verify - {timestamp}",
            "SalesItemLineDetail": {
                "ItemRef": {
                    "value": item_id,
                    "name": item_name
                },
                "Qty": 1,
                "UnitPrice": 123.45,
            }
        }
        
        # If we have an income account ID, include it
        if income_account_id:
            line_item["SalesItemLineDetail"]["ItemAccountRef"] = {
                "value": income_account_id
            }
        
        # Build full invoice
        invoice_data = {
            "DocNumber": doc_number,
            "CustomerRef": {
                "value": customer_id
            },
            "TxnDate": today,
            "DueDate": due_date,
            "Line": [line_item],
            "CustomerMemo": {
                "value": f"Test invoice created via API - timestamp: {timestamp}"
            },
            "PrintStatus": "NeedToPrint",
            "EmailStatus": "NotSet"
        }
        
        print("Invoice data prepared with all required fields")
        print(json.dumps(invoice_data, indent=2))
        
        # 6. Create the invoice with detailed error handling
        print("\nSending invoice creation request...")
        try:
            # Make the API request with explicit error handling
            result = qb_api._make_api_request("invoice", method="POST", data=invoice_data)
            
            if result and 'Id' in result:
                invoice_id = result['Id']
                doc_number = result.get('DocNumber')
                print(f"\n✓ SUCCESS: Invoice created!")
                print(f"  - Internal ID: {invoice_id}")
                print(f"  - DocNumber: {doc_number}")
                print(f"  - Customer: {customer_name}")
                print(f"  - Amount: $123.45")
                print(f"  - Description: {line_item['Description']}")
                print(f"\nIMPORTANT: Please check your QBO account for invoice: {doc_number}")
                print(f"QBO Preview URL: {qb_api.get_invoice_preview_url(invoice_id)}")
                
                # Verify the invoice was created by retrieving it
                print("\nVerifying invoice was created in QBO...")
                verification_query = f"SELECT * FROM Invoice WHERE DocNumber = '{doc_number}'"
                verify_response = qb_api._make_api_request("query", params={"query": verification_query})
                
                if "QueryResponse" in verify_response and "Invoice" in verify_response["QueryResponse"]:
                    verify_invoices = verify_response["QueryResponse"]["Invoice"]
                    if verify_invoices:
                        print(f"✓ VERIFIED: Invoice '{doc_number}' exists in QBO!")
                        print(f"  - ID: {verify_invoices[0].get('Id')}")
                        print(f"  - Customer: {verify_invoices[0].get('CustomerRef', {}).get('name')}")
                        print(f"  - Amount: ${sum(line.get('Amount', 0) for line in verify_invoices[0].get('Line', [])):.2f}")
                    else:
                        print("✗ ERROR: Verification query returned no results!")
                else:
                    print("✗ ERROR: Could not verify invoice creation!")
                    print(json.dumps(verify_response, indent=2))
            else:
                print("\n✗ ERROR: Failed to create invoice!")
                print("API Response:", json.dumps(result, indent=2))
        except Exception as e:
            print(f"\n✗ ERROR during invoice creation: {str(e)}")
            traceback.print_exc()
            
    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    # Ensure demo mode is off
    os.environ["DEMO_MODE"] = "false"
    
    # Create the invoice
    create_visible_invoice() 