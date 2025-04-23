import sys
import os
from email_parser import EmailParser

try:
    from logger import cfo_logger
    print("Logger imported successfully")
except Exception as e:
    print(f"Error importing logger: {str(e)}")
    # Create a simple print function to replace logger
    class SimpleLogger:
        def info(self, msg): print(f"INFO: {msg}")
        def error(self, msg): print(f"ERROR: {msg}")
        def warning(self, msg): print(f"WARNING: {msg}")
    cfo_logger = SimpleLogger()

def test_email_parsing():
    """Test the email parser with a sample email."""
    try:
        print("Creating EmailParser instance...")
        parser = EmailParser()
        print("EmailParser created successfully")
        
        # Sample email that should parse correctly
        test_email = {
            'subject': 'new invoice "SPSA-ROB-CARPET"',
            'body': 'create a new invoice for existing customer angie hutchins, invoice/PO number "SPSA-ROB-CARPET" for: materials: Virginia Highlands Carpet Tiles, 24x24 in, 66 cases. total amount is $12,915. email me a link to view the invoice on qbo when done.',
            'from': 'Matt Porter <hello@757handy.com>',
            'from_email': 'hello@757handy.com'
        }
        
        print("\nTesting email parsing with sample invoice request...")
        print(f"Subject: {test_email['subject']}")
        print(f"Body: {test_email['body']}")
        
        # Parse the email
        print("\nCalling parse_email method...")
        result = parser.parse_email(test_email)
        
        if result:
            print("\nParsing successful!")
            print(f"Customer Name: {result.customer_name}")
            print(f"Materials Description: {result.materials_description}")
            print(f"Invoice Amount: ${result.amount:.2f}")
            print(f"Invoice Number: {result.invoice_number or 'None'}")
            print(f"Activity Type: {result.activity_type or 'None'}")
            
            return result
        else:
            print("\nParsing failed! Check the logs for details.")
            return None
            
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print(f"Current directory: {os.getcwd()}")
    print(f"Python version: {sys.version}")
    
    result = test_email_parsing()
    sys.exit(0 if result else 1) 