import pytest
from email_monitor import EmailMonitor
from email_parser import EmailParser
from invoice_creator import InvoiceCreator
from approval_workflow import ApprovalWorkflow
from config import Config

@pytest.fixture
def mock_config():
    return Config()  # Using demo mode for testing

def test_end_to_end_flow(mock_config):
    # Simulate email receipt
    email_data = {
        'body': "please create a new invoice for SPSA. Customer specified materials: Virginia Highlands carpet tile for all offices on second floor of ROB. It costs $12,915.",
        'from': 'hello@757handy.com',
        'subject': 'New Invoice Request',
        'date': '2024-03-20'
    }
    
    # Test parsing
    parser = EmailParser()
    request = parser.parse_email(email_data)
    assert request is not None
    
    # Test invoice creation
    creator = InvoiceCreator(mock_config.get_quickbooks_api())
    draft_invoice = creator.create_draft_invoice(request)
    assert draft_invoice is not None
    
    # Test approval workflow
    workflow = ApprovalWorkflow(mock_config)
    token = workflow.generate_approval_token(draft_invoice)
    assert token is not None
    
    # Verify token
    decoded = workflow.verify_approval_token(token)
    assert decoded is not None
    assert decoded['invoice_id'] == draft_invoice.invoice_id 