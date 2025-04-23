import os
import sys
from datetime import datetime

# ===== ENVIRONMENT CONFIGURATION =====
# Set critical environment variables
os.environ["DEMO_MODE"] = "false"  # Ensure demo mode is off
os.environ["QUICKBOOKS_ENVIRONMENT"] = "production"  # Force production environment
# Set credentials (use your actual production values from .env)
os.environ["QUICKBOOKS_CLIENT_ID"] = "AB0SA2SxHhhMLmzvRyWutByvY0GlRL3O6HUcVUpdrWuGLsYUal"
os.environ["QUICKBOOKS_CLIENT_SECRET"] = "AHm7R4bRYSnjP0Zzr7pAA6kk8nTEVhjVip3eWYgd"
os.environ["QUICKBOOKS_REFRESH_TOKEN"] = "RT1-66-H0-17534135673w5g3yoerwnt9q1s7hpe"
os.environ["QUICKBOOKS_REALM_ID"] = "9130354335874546"  # No spaces

# Clear any cached modules
import importlib
if 'config' in sys.modules:
    del sys.modules['config']
if 'quickbooks_api' in sys.modules:
    del sys.modules['quickbooks_api']

# Now import with fresh configuration
from config import config
from quickbooks_api import QuickBooksAPI

print("===== ENVIRONMENT CHECK =====")
print(f"Demo Mode: {config.demo_mode}")
print(f"QuickBooks Environment: {config.quickbooks_environment}")
print(f"QuickBooks API URL: {config.quickbooks_environment}")

# ===== API TEST =====
print("\n===== INITIALIZING QUICKBOOKS API =====")
api = QuickBooksAPI()
print(f"API Base URL: {api.base_url}")

# Test company connection
print("\n===== CONNECTING TO COMPANY =====")
try:
    # Create a query to test connection
    company_query = "SELECT * FROM CompanyInfo"
    
    # Make direct API request to eliminate any caching or interception
    from config import config
    import requests
    
    # First, get a fresh token
    print("Getting fresh OAuth token...")
    import base64
    from urllib.parse import urlencode
    
    auth_header = base64.b64encode(
        f"{config.quickbooks_client_id}:{config.quickbooks_client_secret}".encode('utf-8')
    ).decode('utf-8')
    
    token_headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    token_data = {
        "grant_type": "refresh_token",
        "refresh_token": config.quickbooks_refresh_token
    }
    
    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
    token_response = requests.post(token_url, headers=token_headers, data=urlencode(token_data))
    
    if token_response.status_code != 200:
        print(f"Error getting token: {token_response.status_code}")
        print(token_response.text)
        sys.exit(1)
    
    token_data = token_response.json()
    access_token = token_data["access_token"]
    print(f"Got access token: {access_token[:10]}...")
    
    # Now make the API request
    print("Testing connection to company...")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    
    # Try both production and sandbox URLs
    urls = [
        f"https://quickbooks.api.intuit.com/v3/company/{config.quickbooks_realm_id}/query",
        f"https://sandbox-quickbooks.api.intuit.com/v3/company/{config.quickbooks_realm_id}/query"
    ]
    
    connection_successful = False
    for url in urls:
        print(f"Trying URL: {url}")
        response = requests.get(url, headers=headers, params={"query": company_query})
        
        if response.status_code == 200:
            print(f"✓ Connection successful to {url}")
            connection_successful = True
            company_data = response.json()
            
            # Print company info
            if "QueryResponse" in company_data and "CompanyInfo" in company_data["QueryResponse"]:
                company = company_data["QueryResponse"]["CompanyInfo"][0]
                print(f"Company Name: {company.get('CompanyName')}")
                print(f"Legal Name: {company.get('LegalName')}")
                print(f"Address: {company.get('CompanyAddr', {}).get('Line1', 'N/A')}")
                
                # Get real customers
                customer_query = "SELECT Id, DisplayName FROM Customer WHERE Active = true MAXRESULTS 5"
                customer_response = requests.get(
                    url, 
                    headers=headers, 
                    params={"query": customer_query}
                )
                
                if customer_response.status_code == 200:
                    customer_data = customer_response.json()
                    if "QueryResponse" in customer_data and "Customer" in customer_data["QueryResponse"]:
                        customers = customer_data["QueryResponse"]["Customer"]
                        print(f"\nFound {len(customers)} customers:")
                        for cust in customers:
                            print(f"- {cust.get('DisplayName')} (ID: {cust.get('Id')})")
                
                # Create test invoice
                print("\nCreating test invoice...")
                if "QueryResponse" in customer_data and "Customer" in customer_data["QueryResponse"]:
                    customer = customer_data["QueryResponse"]["Customer"][0]
                    
                    # Get service item
                    item_query = "SELECT Id, Name FROM Item WHERE Type='Service' MAXRESULTS 1"
                    item_response = requests.get(
                        url,
                        headers=headers,
                        params={"query": item_query}
                    )
                    
                    if item_response.status_code == 200:
                        item_data = item_response.json()
                        if "QueryResponse" in item_data and "Item" in item_data["QueryResponse"]:
                            item = item_data["QueryResponse"]["Item"][0]
                            
                            # Create invoice
                            invoice_url = url.replace("/query", "/invoice")
                            invoice_data = {
                                "Line": [
                                    {
                                        "DetailType": "SalesItemLineDetail",
                                        "Amount": 1.00,
                                        "Description": "REAL PRODUCTION TEST INVOICE",
                                        "SalesItemLineDetail": {
                                            "ItemRef": {
                                                "value": item["Id"]
                                            },
                                            "Qty": 1,
                                            "UnitPrice": 1.00
                                        }
                                    }
                                ],
                                "CustomerRef": {
                                    "value": customer["Id"]
                                }
                            }
                            
                            # Make API request to create invoice
                            invoice_response = requests.post(invoice_url, headers=headers, json=invoice_data)
                            
                            if invoice_response.status_code == 200:
                                print("✓ Invoice created successfully")
                            else:
                                print(f"Error creating invoice: {invoice_response.status_code}")
                                print(invoice_response.text)
                            break
                        else:
                            print("Error getting item data")
                    else:
                        print("Error getting item data")
                else:
                    print("Error getting customer data")
            else:
                print("Error getting company data")
            break
        else:
            print(f"Error connecting to company: {response.status_code}")
except Exception as e:
    print(f"Error connecting to company: {str(e)}")

print("\n=== TEST COMPLETE ===") 