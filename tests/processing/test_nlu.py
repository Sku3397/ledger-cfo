import pytest
from decimal import Decimal

from src.ledger_cfo.core.constants import Intent
from src.ledger_cfo.processing.nlu import extract_intent_entities, check_for_confirmation

# --- Test Cases for extract_intent_entities ---

@pytest.mark.parametrize("email_body, expected_intent, expected_entities", [
    # Create Invoice
    ("Please create invoice for ACME Corp for $123.45", Intent.CREATE_INVOICE, {'customer_name': 'ACME Corp', 'amount': Decimal('123.45')}),
    ("New invoice to \"Beta Industries\" for item Repair Service amount 99.99", Intent.CREATE_INVOICE, {'customer_name': 'Beta Industries', 'amount': Decimal('99.99'), 'item_description': 'Repair Service'}),
    ("Bill Gamma LLC 500", Intent.CREATE_INVOICE, {'customer_name': 'Gamma LLC', 'amount': Decimal('500')}), # Less explicit

    # Send Invoice (often similar to create)
    ("Send invoice to Delta Co for 1000", Intent.SEND_INVOICE, {'customer_name': 'Delta Co', 'amount': Decimal('1000')}),

    # Find Customer
    ("find customer Epsilon Ltd", Intent.FIND_CUSTOMER, {'customer_name': 'Epsilon Ltd'}),
    ("Look up customer Zeta Inc.", Intent.FIND_CUSTOMER, {'customer_name': 'Zeta Inc.'}),
    ("Show me customer details for \"Eta Group\"", Intent.FIND_CUSTOMER, {'customer_name': 'Eta Group'}),

    # Record Expense
    ("Record expense for Staples $55.20 category Office Supplies", Intent.RECORD_EXPENSE, {'vendor_name': 'Staples', 'amount': Decimal('55.20'), 'category': 'Office Supplies'}),
    ("Log expense paid to Shell for $70.00", Intent.RECORD_EXPENSE, {'vendor_name': 'Shell', 'amount': Decimal('70.00')}),
    ("Add expense: Vendor Theta Supplies Amount: $12.34", Intent.RECORD_EXPENSE, {'vendor_name': 'Theta Supplies', 'amount': Decimal('12.34')}),
    ("Paid Iota Services $250 for consulting", Intent.RECORD_EXPENSE, {'vendor_name': 'Iota Services', 'amount': Decimal('250'), 'description': 'consulting'}),

    # Get PNL Report
    ("Get PNL report for last month", Intent.GET_REPORT_PNL, {'date_range_raw': 'last month', 'start_date': 'YYYY-MM-DD', 'end_date': 'YYYY-MM-DD'}), # Dates need mocking/calculation
    ("Show profit and loss this year", Intent.GET_REPORT_PNL, {'date_range_raw': 'this year', 'start_date': 'YYYY-MM-DD', 'end_date': 'YYYY-MM-DD'}),
    ("Income statement for 2023-01-01 to 2023-03-31", Intent.GET_REPORT_PNL, {'date_range_raw': '2023-01-01 to 2023-03-31', 'start_date': '2023-01-01', 'end_date': '2023-03-31'}),

    # Unknown
    ("Hello there, how are you?", Intent.UNKNOWN, {}),
    ("What invoices are outstanding?", Intent.UNKNOWN, {}), # Not yet supported intent
])
def test_extract_intent_entities(email_body, expected_intent, expected_entities):
    # Note: PNL date tests require mocking qbo_api.parse_date_range or pre-calculating expected dates
    # For simplicity here, we'll check the raw range and presence of start/end dates
    # A more robust test would use mocking (e.g., unittest.mock or pytest-mock)

    result = extract_intent_entities(email_body)

    assert result['intent'] == expected_intent

    # Special handling for PNL dates
    if expected_intent == Intent.GET_REPORT_PNL:
        assert result['entities'].get('date_range_raw') == expected_entities.get('date_range_raw')
        assert ('start_date' in result['entities']) == ('start_date' in expected_entities)
        assert ('end_date' in result['entities']) == ('end_date' in expected_entities)
        if 'start_date' in expected_entities and expected_entities['start_date'] != 'YYYY-MM-DD': # Check specific dates if provided
             assert result['entities'].get('start_date') == expected_entities.get('start_date')
        if 'end_date' in expected_entities and expected_entities['end_date'] != 'YYYY-MM-DD':
             assert result['entities'].get('end_date') == expected_entities.get('end_date')
        # Remove date fields for the general comparison below
        expected_entities_copy = expected_entities.copy()
        result_entities_copy = result['entities'].copy()
        expected_entities_copy.pop('date_range_raw', None)
        expected_entities_copy.pop('start_date', None)
        expected_entities_copy.pop('end_date', None)
        result_entities_copy.pop('date_range_raw', None)
        result_entities_copy.pop('start_date', None)
        result_entities_copy.pop('end_date', None)
        assert result_entities_copy == expected_entities_copy
    else:
        # General entity comparison for other intents
        assert result['entities'] == expected_entities

# --- Test Cases for check_for_confirmation ---

VALID_UUID = "123e4567-e89b-12d3-a456-426614174000"

@pytest.mark.parametrize("text, expected_decision, expected_uuid", [
    (f"Please confirm CONFIRM {VALID_UUID}", "CONFIRM", VALID_UUID),
    (f"confirm {VALID_UUID.lower()}", "CONFIRM", VALID_UUID.lower()),
    (f"CANCEL {VALID_UUID}", "CANCEL", VALID_UUID),
    (f"cancel {VALID_UUID}", "CANCEL", VALID_UUID),
    (f"Subject: Re: Action Required\n\nOk, CONFIRM {VALID_UUID} please", "CONFIRM", VALID_UUID),
    (f"No, CANCEL {VALID_UUID}", "CANCEL", VALID_UUID),
])
def test_check_for_confirmation_valid(text, expected_decision, expected_uuid):
    result = check_for_confirmation(text)
    assert result is not None
    assert result['intent'] == Intent.HANDLE_CONFIRMATION
    assert result['entities']['decision'] == expected_decision
    # UUID matching might be case-insensitive depending on storage/lookup, but regex captures it as is
    assert result['entities']['uuid'].lower() == expected_uuid.lower()

@pytest.mark.parametrize("text", [
    "Please confirm the action",
    "CONFIRM 12345678", # Invalid UUID format
    "CANCEL a-b-c-d-e", # Invalid UUID format
    f"CONFIRM {VALID_UUID} and CANCEL {VALID_UUID}", # Ambiguous?
    "Just confirming",
    "Cancel my subscription",
])
def test_check_for_confirmation_invalid(text):
    result = check_for_confirmation(text)
    assert result is None 