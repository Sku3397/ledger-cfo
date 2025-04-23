import pytest
from email_parser import EmailParser, InvoiceRequest
from invoice_creator import InvoiceCreator, DraftInvoice
from approval_workflow import ApprovalWorkflow
from unittest.mock import Mock, patch

def test_email_parser():
    parser = EmailParser()
    
    # Test valid email
    valid_email = {
        'body': "please create a new invoice for SPSA. Customer specified materials: Virginia Highlands carpet tile for all offices on second floor of ROB. It costs $12,915.",
        'from': 'hello@757handy.com'
    }
    
    result = parser.parse_email(valid_email)
    assert isinstance(result, InvoiceRequest)
    assert result.customer_name == "SPSA"
    assert "Virginia Highlands carpet tile" in result.materials_description
    assert result.amount == 12915.0
    
    # Test invalid emails
    invalid_emails = [
        {'body': "Invalid email with no customer"},
        {'body': "Invalid email with no amount"},
        {'body': "SPSA needs something but no clear materials or amount"}
    ]
    
    for email in invalid_emails:
        result = parser.parse_email(email)
        assert result is None

# Add more tests for InvoiceCreator, ApprovalWorkflow, etc. 