import json
from quickbooks_api import QuickBooksAPI

def main():
    try:
        # Initialize the QuickBooks API
        qb_api = QuickBooksAPI()
        
        # Create a simple test invoice
        invoice_data = {
            "CustomerRef": {
                "value": "1"  # Use a default customer ID (adjust as needed)
            },
            "Line": [
                {
                    "Amount": 123.00,
                    "Description": "Test invoice item",
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {
                        "ItemRef": {
                            "value": "1"  # Default service item
                        }
                    }
                }
            ]
        }
        
        # Create the invoice
        result = qb_api.create_invoice(invoice_data)
        
        # Print the result
        print("Invoice created successfully:")
        print(json.dumps(result, indent=2))
        
        if result and 'Id' in result:
            invoice_url = qb_api.get_invoice_preview_url(result['Id'])
            print(f"\nInvoice URL: {invoice_url}")
            
    except Exception as e:
        print(f"Error creating invoice: {str(e)}")

if __name__ == "__main__":
    main() 