import json
from datetime import datetime, timedelta
from logger import cfo_logger

class MockQuickBooksAPI:
    """Mock version of the QuickBooks API for testing and demo purposes.
    
    Provides sample data that matches the structure of real QuickBooks responses.
    """
    
    def __init__(self):
        """Initialize the mock QuickBooks API."""
        cfo_logger.info("Initializing Mock QuickBooks API")
        self.demo_mode = True
        
    def get_accounts(self):
        """Get sample accounts data."""
        return {
            "QueryResponse": {
                "Account": [
                    {
                        "Id": "1",
                        "Name": "Cash",
                        "AccountType": "Bank",
                        "AccountSubType": "Checking",
                        "CurrentBalance": 25000.00
                    },
                    {
                        "Id": "2",
                        "Name": "Accounts Receivable",
                        "AccountType": "Accounts Receivable",
                        "AccountSubType": "AccountsReceivable",
                        "CurrentBalance": 12500.00
                    },
                    {
                        "Id": "3",
                        "Name": "Inventory",
                        "AccountType": "Other Current Asset",
                        "AccountSubType": "Inventory",
                        "CurrentBalance": 15000.00
                    },
                    {
                        "Id": "4",
                        "Name": "Accounts Payable",
                        "AccountType": "Accounts Payable",
                        "AccountSubType": "AccountsPayable",
                        "CurrentBalance": 8500.00
                    },
                    {
                        "Id": "5",
                        "Name": "Sales Revenue",
                        "AccountType": "Income",
                        "AccountSubType": "ServiceFeeIncome",
                        "CurrentBalance": 45000.00
                    },
                    {
                        "Id": "6",
                        "Name": "Cost of Goods Sold",
                        "AccountType": "Cost of Goods Sold",
                        "AccountSubType": "CostOfGoodsSold",
                        "CurrentBalance": 18000.00
                    },
                    {
                        "Id": "7",
                        "Name": "Utilities Expense",
                        "AccountType": "Expense",
                        "AccountSubType": "UtilitiesExpense",
                        "CurrentBalance": 3500.00
                    },
                    {
                        "Id": "8",
                        "Name": "Rent Expense",
                        "AccountType": "Expense",
                        "AccountSubType": "RentExpense",
                        "CurrentBalance": 6000.00
                    }
                ],
                "startPosition": 1,
                "maxResults": 10,
                "totalCount": 8
            },
            "time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-07:00")
        }
        
    def get_transactions(self, start_date=None, end_date=None):
        """Get sample transactions within the specified date range."""
        transactions = []
        current_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
        
        # Generate 10 sample transactions over the date range
        for i in range(10):
            transaction_date = (current_date - timedelta(days=i*3)).strftime("%Y-%m-%d")
            transactions.append({
                "Id": f"{1000 + i}",
                "TxnDate": transaction_date,
                "Amount": round(500 + (i * 100), 2),
                "Description": f"Sample Transaction {i+1}",
                "AccountRef": {
                    "value": "1",
                    "name": "Cash"
                }
            })
        
        return {
            "QueryResponse": {
                "Transaction": transactions,
                "startPosition": 1,
                "maxResults": 10,
                "totalCount": len(transactions)
            },
            "time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-07:00")
        }
        
    def get_invoices(self, start_date=None, end_date=None, status=None):
        """Get sample invoices within the specified date range and status."""
        invoices = []
        current_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
        
        # Generate sample invoices
        for i in range(5):
            due_date = (current_date + timedelta(days=(i+1)*10)).strftime("%Y-%m-%d")
            invoice_date = (current_date - timedelta(days=i*7)).strftime("%Y-%m-%d")
            
            # Alternate between paid and unpaid
            paid = i % 2 == 0
            balance = 0 if paid else round(1000 + (i * 250), 2)
            
            invoices.append({
                "Id": f"{2000 + i}",
                "DocNumber": f"INV-{100 + i}",
                "TxnDate": invoice_date,
                "DueDate": due_date,
                "Balance": balance,
                "TotalAmt": round(1000 + (i * 250), 2),
                "CustomerRef": {
                    "value": f"{10 + i}",
                    "name": f"Sample Customer {i+1}"
                }
            })
        
        return {
            "QueryResponse": {
                "Invoice": invoices,
                "startPosition": 1,
                "maxResults": 5,
                "totalCount": len(invoices)
            },
            "time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-07:00")
        }
        
    def get_bills(self, start_date=None, end_date=None, status=None):
        """Get sample bills within the specified date range and status."""
        bills = []
        current_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
        
        # Generate sample bills
        for i in range(4):
            due_date = (current_date + timedelta(days=(i+1)*15)).strftime("%Y-%m-%d")
            bill_date = (current_date - timedelta(days=i*5)).strftime("%Y-%m-%d")
            
            # Alternate between paid and unpaid
            paid = i % 2 == 0
            balance = 0 if paid else round(500 + (i * 200), 2)
            
            bills.append({
                "Id": f"{3000 + i}",
                "DocNumber": f"BILL-{200 + i}",
                "TxnDate": bill_date,
                "DueDate": due_date,
                "Balance": balance,
                "TotalAmt": round(500 + (i * 200), 2),
                "VendorRef": {
                    "value": f"{20 + i}",
                    "name": f"Sample Vendor {i+1}"
                }
            })
        
        return {
            "QueryResponse": {
                "Bill": bills,
                "startPosition": 1,
                "maxResults": 4,
                "totalCount": len(bills)
            },
            "time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-07:00")
        }
        
    def get_profit_and_loss(self, start_date=None, end_date=None):
        """Get sample profit and loss report data."""
        # Create a sample P&L structure
        return {
            "Header": {
                "ReportName": "Profit and Loss",
                "StartPeriod": start_date,
                "EndPeriod": end_date,
                "Time": f"From {start_date} to {end_date}"
            },
            "Rows": {
                "Row": [
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Income"},
                                {"value": "45000.00"}
                            ]
                        },
                        "Rows": {
                            "Row": [
                                {
                                    "type": "Data",
                                    "Summary": {
                                        "ColData": [
                                            {"value": "Sales Revenue"},
                                            {"value": "45000.00"}
                                        ]
                                    }
                                }
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Total Income"},
                                {"value": "45000.00"}
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Cost of Goods Sold"},
                                {"value": "18000.00"}
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Gross Profit"},
                                {"value": "27000.00"}
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Expenses"},
                                {"value": "9500.00"}
                            ]
                        },
                        "Rows": {
                            "Row": [
                                {
                                    "type": "Data",
                                    "Summary": {
                                        "ColData": [
                                            {"value": "Utilities Expense"},
                                            {"value": "3500.00"}
                                        ]
                                    }
                                },
                                {
                                    "type": "Data",
                                    "Summary": {
                                        "ColData": [
                                            {"value": "Rent Expense"},
                                            {"value": "6000.00"}
                                        ]
                                    }
                                }
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Total Expenses"},
                                {"value": "9500.00"}
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Net Income"},
                                {"value": "17500.00"}
                            ]
                        }
                    }
                ]
            }
        }
        
    def get_balance_sheet(self, as_of_date=None):
        """Get sample balance sheet report data."""
        # Create a sample balance sheet structure
        return {
            "Header": {
                "ReportName": "Balance Sheet",
                "Time": f"As of {as_of_date}"
            },
            "Rows": {
                "Row": [
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Assets"},
                                {"value": "52500.00"}
                            ]
                        },
                        "Rows": {
                            "Row": [
                                {
                                    "type": "Section",
                                    "Summary": {
                                        "ColData": [
                                            {"value": "Current Assets"},
                                            {"value": "52500.00"}
                                        ]
                                    },
                                    "Rows": {
                                        "Row": [
                                            {
                                                "type": "Data",
                                                "Summary": {
                                                    "ColData": [
                                                        {"value": "Cash and Cash Equivalents"},
                                                        {"value": "25000.00"}
                                                    ]
                                                }
                                            },
                                            {
                                                "type": "Data",
                                                "Summary": {
                                                    "ColData": [
                                                        {"value": "Accounts Receivable"},
                                                        {"value": "12500.00"}
                                                    ]
                                                }
                                            },
                                            {
                                                "type": "Data",
                                                "Summary": {
                                                    "ColData": [
                                                        {"value": "Inventory"},
                                                        {"value": "15000.00"}
                                                    ]
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Total Current Assets"},
                                {"value": "52500.00"}
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Total Assets"},
                                {"value": "52500.00"}
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Liabilities"},
                                {"value": "8500.00"}
                            ]
                        },
                        "Rows": {
                            "Row": [
                                {
                                    "type": "Section",
                                    "Summary": {
                                        "ColData": [
                                            {"value": "Current Liabilities"},
                                            {"value": "8500.00"}
                                        ]
                                    },
                                    "Rows": {
                                        "Row": [
                                            {
                                                "type": "Data",
                                                "Summary": {
                                                    "ColData": [
                                                        {"value": "Accounts Payable"},
                                                        {"value": "8500.00"}
                                                    ]
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Total Current Liabilities"},
                                {"value": "8500.00"}
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Total Liabilities"},
                                {"value": "8500.00"}
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Equity"},
                                {"value": "44000.00"}
                            ]
                        },
                        "Rows": {
                            "Row": [
                                {
                                    "type": "Data",
                                    "Summary": {
                                        "ColData": [
                                            {"value": "Owner's Equity"},
                                            {"value": "44000.00"}
                                        ]
                                    }
                                }
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Total Equity"},
                                {"value": "44000.00"}
                            ]
                        }
                    }
                ]
            }
        }
        
    def get_cash_flow(self, start_date=None, end_date=None):
        """Get sample cash flow report data."""
        # Create a sample cash flow structure
        return {
            "Header": {
                "ReportName": "Statement of Cash Flows",
                "StartPeriod": start_date,
                "EndPeriod": end_date,
                "Time": f"From {start_date} to {end_date}"
            },
            "Rows": {
                "Row": [
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Operating Activities"},
                                {"value": "15000.00"}
                            ]
                        },
                        "Rows": {
                            "Row": [
                                {
                                    "type": "Data",
                                    "Summary": {
                                        "ColData": [
                                            {"value": "Net Income"},
                                            {"value": "17500.00"}
                                        ]
                                    }
                                },
                                {
                                    "type": "Data",
                                    "Summary": {
                                        "ColData": [
                                            {"value": "Changes in Accounts Receivable"},
                                            {"value": "-2500.00"}
                                        ]
                                    }
                                }
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Net cash provided by operating activities"},
                                {"value": "15000.00"}
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Investing Activities"},
                                {"value": "-5000.00"}
                            ]
                        },
                        "Rows": {
                            "Row": [
                                {
                                    "type": "Data",
                                    "Summary": {
                                        "ColData": [
                                            {"value": "Purchase of Equipment"},
                                            {"value": "-5000.00"}
                                        ]
                                    }
                                }
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Net cash used in investing activities"},
                                {"value": "-5000.00"}
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Financing Activities"},
                                {"value": "0.00"}
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Net cash provided by financing activities"},
                                {"value": "0.00"}
                            ]
                        }
                    },
                    {
                        "type": "Section",
                        "Summary": {
                            "ColData": [
                                {"value": "Net Change in Cash"},
                                {"value": "10000.00"}
                            ]
                        }
                    }
                ]
            }
        }

    def query_customers(self, name_query=None):
        """Get sample customers matching the name query."""
        # Sample customer data
        customers = [
            {
                "Id": "1",
                "DisplayName": "Test Customer",
                "GivenName": "Test",
                "FamilyName": "Customer",
                "CompanyName": "Test Company",
                "Active": True,
                "Balance": 0.00,
                "Email": "test@example.com"
            },
            {
                "Id": "2",
                "DisplayName": "Beach Handyman LLC",
                "GivenName": "Matt",
                "FamilyName": "Porter",
                "CompanyName": "Beach Handyman LLC",
                "Active": True,
                "Balance": 0.00,
                "Email": "hello@757handy.com"
            },
            {
                "Id": "3",
                "DisplayName": "Angie Hutchins",
                "GivenName": "Angie",
                "FamilyName": "Hutchins",
                "CompanyName": "",
                "Active": True,
                "Balance": 0.00,
                "Email": "angie@example.com"
            }
        ]
        
        if name_query:
            # Case-insensitive partial match on DisplayName or CompanyName
            name_query = name_query.lower()
            filtered_customers = [
                c for c in customers 
                if name_query in c["DisplayName"].lower() 
                or name_query in c.get("CompanyName", "").lower()
            ]
        else:
            filtered_customers = customers
            
        return {
            "QueryResponse": {
                "Customer": filtered_customers,
                "startPosition": 1,
                "maxResults": len(filtered_customers),
                "totalCount": len(filtered_customers)
            },
            "time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-07:00")
        }

    def create_invoice(self, invoice_data):
        """Mock method to create a new invoice."""
        try:
            cfo_logger.info("Creating mock invoice with data: " + str(invoice_data))
            
            # Generate a mock invoice ID
            invoice_id = str(4000 + len(self.get_invoices().get("QueryResponse", {}).get("Invoice", [])))
            
            # Create a sample response
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            mock_invoice = {
                "Id": invoice_id,
                "SyncToken": "0",
                "MetaData": {
                    "CreateTime": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-07:00"),
                    "LastUpdatedTime": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-07:00")
                },
                "DocNumber": f"INV-{invoice_id}",
                "TxnDate": invoice_data.get("TxnDate", current_date),
                "CustomerRef": invoice_data.get("CustomerRef", {"value": "1001", "name": "SPSA"}),
                "DueDate": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                "TotalAmt": sum(line.get("Amount", 0) for line in invoice_data.get("Line", [])),
                "Line": invoice_data.get("Line", []),
                "DraftStatus": invoice_data.get("DraftStatus", "Pending")
            }
            
            cfo_logger.info(f"Created mock invoice with ID: {invoice_id}")
            return mock_invoice
        except Exception as e:
            cfo_logger.error(f"Error creating mock invoice: {str(e)}")
            return None

    def get_invoice_by_id(self, invoice_id):
        """Mock method to get a specific invoice by ID."""
        try:
            invoices = self.get_invoices().get("QueryResponse", {}).get("Invoice", [])
            for invoice in invoices:
                if invoice.get("Id") == invoice_id:
                    return invoice
                
            # If not found in existing invoices, create a mock one
            mock_invoice = {
                "Id": invoice_id,
                "SyncToken": "0",
                "MetaData": {
                    "CreateTime": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-07:00"),
                    "LastUpdatedTime": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-07:00")
                },
                "DocNumber": f"INV-{invoice_id}",
                "TxnDate": datetime.now().strftime("%Y-%m-%d"),
                "CustomerRef": {"value": "1001", "name": "SPSA"},
                "DueDate": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                "TotalAmt": 12915.00,
                "Line": [{
                    "Amount": 12915.00,
                    "Description": "Virginia Highlands carpet tile for all offices on second floor of ROB",
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {
                        "ItemRef": {
                            "value": "1",
                            "name": "Materials"
                        }
                    }
                }],
                "DraftStatus": "Pending"
            }
            return mock_invoice
        except Exception as e:
            cfo_logger.error(f"Error getting mock invoice {invoice_id}: {str(e)}")
            return None

    def send_invoice(self, invoice_id, email_data=None):
        """Mock method to send an invoice to the customer."""
        try:
            cfo_logger.info(f"Mock sending invoice {invoice_id} to customer")
            return True
        except Exception as e:
            cfo_logger.error(f"Error in mock send invoice {invoice_id}: {str(e)}")
            return False

    def update_invoice(self, invoice_id, invoice_data):
        """Mock method to update an existing invoice."""
        try:
            cfo_logger.info(f"Updating mock invoice {invoice_id}")
            mock_invoice = invoice_data.copy()
            mock_invoice["Id"] = invoice_id
            mock_invoice["MetaData"] = {
                "CreateTime": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-07:00"),
                "LastUpdatedTime": datetime.now().strftime("%Y-%m-%dT%H:%M:%S-07:00")
            }
            mock_invoice["SyncToken"] = str(int(mock_invoice.get("SyncToken", "0")) + 1)
            return mock_invoice
        except Exception as e:
            cfo_logger.error(f"Error updating mock invoice {invoice_id}: {str(e)}")
            return None

    def approve_invoice(self, invoice_id):
        """Mock method to approve a draft invoice."""
        try:
            cfo_logger.info(f"Approving mock invoice {invoice_id}")
            invoice = self.get_invoice_by_id(invoice_id)
            if invoice:
                invoice.pop("DraftStatus", None)
                self.update_invoice(invoice_id, invoice)
                return True
            return False
        except Exception as e:
            cfo_logger.error(f"Error approving mock invoice {invoice_id}: {str(e)}")
            return False

    def get_invoice_preview_url(self, invoice_id):
        """Mock method to get URL for invoice preview."""
        return f"https://mock-quickbooks.example.com/preview/invoice/{invoice_id}" 