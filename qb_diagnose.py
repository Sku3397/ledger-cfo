import os
import sys
from datetime import datetime, timedelta
import json

# Force demo mode off
os.environ["DEMO_MODE"] = "false"

# Import after setting environment
from config import config
from quickbooks_api import QuickBooksAPI

def diagnose_quickbooks():
    """Comprehensive diagnosis of QuickBooks connection and data."""
    print("\n=== QUICKBOOKS DIAGNOSTIC ===\n")
    
    # Initialize the QuickBooks API
    qb_api = QuickBooksAPI()
    print("QuickBooks API initialized")
    
    try:
        # 1. Verify company information
        print("\nVerifying Company Information:")
        company_info = qb_api._make_api_request(f"companyinfo/{config.quickbooks_realm_id}")
        
        if "CompanyInfo" in company_info:
            info = company_info["CompanyInfo"]
            print(f"  Company Name: {info.get('CompanyName', 'Unknown')}")
            print(f"  Legal Name: {info.get('LegalName', 'Unknown')}")
            print(f"  Company Address: {', '.join([info.get('CompanyAddr', {}).get(k, '') for k in ['Line1', 'City', 'CountrySubDivisionCode'] if k in info.get('CompanyAddr', {})])}")
            print(f"  Email: {info.get('Email', {}).get('Address', 'Unknown')}")
        else:
            print("  Could not retrieve company information")
        
        # 2. Search for the specific invoice numbers mentioned
        print("\nSearching for specific invoices:")
        search_numbers = ["638-RHODE", "1107-ARDITO-2"]
        
        for doc_number in search_numbers:
            print(f"\nSearching for invoice with DocNumber: '{doc_number}'")
            query = f"SELECT * FROM Invoice WHERE DocNumber = '{doc_number}'"
            response = qb_api._make_api_request("query", params={"query": query})
            
            if "QueryResponse" in response and "Invoice" in response["QueryResponse"]:
                invoices = response["QueryResponse"]["Invoice"]
                print(f"  ✓ Found {len(invoices)} match(es)!")
                
                for inv in invoices:
                    print(f"  Invoice Details:")
                    print(f"    ID: {inv.get('Id')}")
                    print(f"    DocNumber: {inv.get('DocNumber')}")
                    print(f"    Customer: {inv.get('CustomerRef', {}).get('name')}")
                    print(f"    Date: {inv.get('TxnDate')}")
                    print(f"    Amount: ${sum(line.get('Amount', 0) for line in inv.get('Line', [])):.2f}")
            else:
                print(f"  ✗ No matches found for DocNumber: '{doc_number}'")
        
        # 3. Get recent invoices with detailed info including DocNumber
        print("\nRetrieving 10 most recent invoices:")
        query = "SELECT * FROM Invoice ORDER BY TxnDate DESC MAXRESULTS 10"
        response = qb_api._make_api_request("query", params={"query": query})
        
        if "QueryResponse" in response and "Invoice" in response["QueryResponse"]:
            invoices = response["QueryResponse"]["Invoice"]
            print(f"Found {len(invoices)} recent invoices:")
            
            for i, inv in enumerate(invoices):
                inv_id = inv.get("Id", "Unknown")
                doc_number = inv.get("DocNumber", "Unknown")
                customer = inv.get("CustomerRef", {}).get("name", "Unknown Customer")
                date = inv.get("TxnDate", "Unknown Date")
                amount = sum(line.get("Amount", 0) for line in inv.get("Line", []))
                
                print(f"  {i+1}. ID: {inv_id} | DocNumber: {doc_number} | {date} | ${amount:.2f} | {customer}")
        else:
            print("No invoices found or error in response")
        
        # 4. Create a new invoice with custom DocNumber that matches your format
        print("\n=== CREATING NEW TEST INVOICE WITH CUSTOM NUMBER ===")
        
        # Get a valid customer
        customers_query = "SELECT * FROM Customer WHERE Active = true LIMIT 5"
        customers_response = qb_api._make_api_request("query", params={"query": customers_query})
        
        if "QueryResponse" in customers_response and "Customer" in customers_response["QueryResponse"]:
            customers = customers_response["QueryResponse"]["Customer"]
            if customers:
                customer = customers[0]
                customer_id = customer.get("Id")
                customer_name = customer.get("DisplayName")
                print(f"Using customer: {customer_name} (ID: {customer_id})")
                
                # Get a valid item
                items_query = "SELECT * FROM Item WHERE Type IN ('Service', 'NonInventory') AND Active = true LIMIT 5"
                items_response = qb_api._make_api_request("query", params={"query": items_query})
                
                if "QueryResponse" in items_response and "Item" in items_response["QueryResponse"]:
                    items = items_response["QueryResponse"]["Item"]
                    if items:
                        item = items[0]
                        item_id = item.get("Id")
                        item_name = item.get("Name")
                        print(f"Using item: {item_name} (ID: {item_id})")
                        
                        # Create custom invoice number similar to the format user mentioned
                        custom_doc_number = f"TEST-QBO-API-{datetime.now().strftime('%m%d')}"
                        
                        print(f"\nPreparing invoice with custom DocNumber: {custom_doc_number}")
                        
                        # Create line item
                        line_item = {
                            "Amount": 456.78,
                            "Description": "API TEST - Virginia Highlands carpet tile",
                            "DetailType": "SalesItemLineDetail",
                            "SalesItemLineDetail": {
                                "ItemRef": {
                                    "value": item_id,
                                    "name": item_name
                                },
                                "Qty": 1
                            }
                        }
                        
                        # Create invoice data with custom DocNumber
                        invoice_data = {
                            "CustomerRef": {
                                "value": customer_id
                            },
                            "DocNumber": custom_doc_number,
                            "Line": [line_item],
                            "TxnDate": datetime.now().strftime("%Y-%m-%d"),
                            "DueDate": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                        }
                        
                        print("Invoice data prepared with custom DocNumber")
                        
                        # Create the invoice
                        try:
                            result = qb_api._make_api_request("invoice", method="POST", data=invoice_data)
                            
                            if result and 'Id' in result:
                                invoice_id = result['Id']
                                doc_number = result.get('DocNumber', 'Unknown')
                                print(f"\n✓ SUCCESS: Invoice created!")
                                print(f"  API ID: {invoice_id}")
                                print(f"  DocNumber: {doc_number}")
                                print(f"  Preview URL: {qb_api.get_invoice_preview_url(invoice_id)}")
                                print("\nPLEASE CHECK YOUR QUICKBOOKS FOR INVOICE: " + doc_number)
                                
                                # Verify the invoice was created
                                verify_invoice = qb_api._make_api_request(f"invoice/{invoice_id}")
                                if verify_invoice and 'Id' in verify_invoice:
                                    print(f"✓ VERIFIED: Invoice exists in QuickBooks API")
                                else:
                                    print("✗ ERROR: Could not verify the new invoice")
                            else:
                                print("\n✗ ERROR: Failed to create invoice")
                                print("Response:", result)
                        except Exception as e:
                            print(f"\n✗ ERROR creating invoice: {str(e)}")
                            import traceback
                            traceback.print_exc()
                    else:
                        print("No items found")
                else:
                    print("Failed to retrieve items")
            else:
                print("No customers found")
        else:
            print("Failed to retrieve customers")
    
    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Force demo mode OFF
    os.environ["DEMO_MODE"] = "false"
    
    # Run diagnosis
    diagnose_quickbooks() 