import re
import logging
from decimal import Decimal, InvalidOperation
from datetime import date, timedelta, datetime # Add datetime

from ..core.constants import Intent
from ..integrations import qbo_api # Import qbo_api to use parse_date_range

logger = logging.getLogger(__name__)

# Simple keyword mapping
INTENT_KEYWORDS = {
    Intent.CREATE_INVOICE: ["create invoice", "new invoice", "bill"],
    Intent.SEND_INVOICE: ["send invoice"],
    Intent.FIND_CUSTOMER: ["find customer", "look up customer", "customer details"],
    # Updated keywords for expense
    Intent.RECORD_EXPENSE: ["record expense", "log expense", "add expense", "expense for", "paid"],
    Intent.GET_REPORT_PNL: ["pnl report", "profit and loss", "income statement", "get pnl"],
}

# Regex patterns for entity extraction
REGEX_PATTERNS = {
    # More robust amount, allows optional space after $, handles various formats
    'amount': r'\$? ?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\.\d{1,2})\b',
    # Customer name - make less greedy, look for common terminators
    'customer_name': r'(?:for|to|customer)\s+([A-Za-z0-9\s.&\-\'\*]+?)(?:\s*(?:with amount|for item|due|,|$))'
                     r'|"([A-Za-z0-9\s.&\-\'\*]+)"\s+(?:for|with amount)', # Handles quoted names
    'item_description': r'(?:for item|item:|description:)\s+(.*?)(?:\s+due|,|for \$|for [0-9]|with amount|$)',
    'due_date': r'(?:due on|due by|due date)\s+([A-Za-z0-9\s,\-/]+?)(?:\s+for|$)',
    # Vendor name - look for words after "paid", "expense for", "vendor", etc.
    'vendor_name': r'(?:expense for|paid|vendor|for)\s+"?([A-Za-z0-9\s.&\-\'\*]+?)"?\s+(?:for|with amount|,|category|$)',
    'category': r'(?:category|categorize as)\s+([A-Za-z\s]+?)(?:\s+with amount|,|$)',
    # Date range - capture common phrases or explicit dates
    'date_range': r'(?:for|period)\s+([A-Za-z0-9\s,\-]+(?:\s+to\s+[A-Za-z0-9\s,\-]+)?)'
}

def parse_amount(amount_str: str) -> Decimal | None:
    """Convert extracted amount string to Decimal, removing $ and commas."""
    if not amount_str:
        return None
    try:
        # Remove potential space after $
        cleaned_amount = amount_str.replace('$', '').replace(',', '').strip()
        return Decimal(cleaned_amount)
    except InvalidOperation:
        logger.warning(f"Could not parse '{amount_str}' as Decimal.")
        return None

def extract_intent_entities(email_body: str) -> dict:
    """
    Extracts intent and entities from email body using keywords and regex.
    Handles basic date parsing for PNL reports.
    """
    lower_body = email_body.lower()
    detected_intent = Intent.UNKNOWN
    entities = {}

    # 1. Intent Detection
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(keyword in lower_body for keyword in keywords):
            detected_intent = intent
            logger.info(f"Detected intent: {intent.value}")
            break

    # 2. Entity Extraction based on Intent
    if detected_intent != Intent.UNKNOWN:
        # Always try to extract amount first, as it's common
        match_amount = re.search(REGEX_PATTERNS['amount'], email_body)
        if match_amount: entities['amount'] = parse_amount(match_amount.group(1))

        if detected_intent in [Intent.CREATE_INVOICE, Intent.SEND_INVOICE]:
            match_cust = re.search(REGEX_PATTERNS['customer_name'], email_body, re.IGNORECASE)
            match_item = re.search(REGEX_PATTERNS['item_description'], email_body, re.IGNORECASE)
            match_due = re.search(REGEX_PATTERNS['due_date'], email_body, re.IGNORECASE)

            # Prefer quoted name if found
            if match_cust and match_cust.group(2):
                entities['customer_name'] = match_cust.group(2).strip()
            elif match_cust and match_cust.group(1):
                entities['customer_name'] = match_cust.group(1).strip()

            if match_item: entities['item_description'] = match_item.group(1).strip()
            if match_due: entities['due_date'] = match_due.group(1).strip() # Keep as string for now

        elif detected_intent == Intent.FIND_CUSTOMER:
            match_cust = re.search(REGEX_PATTERNS['customer_name'], email_body, re.IGNORECASE)
            if match_cust and match_cust.group(2):
                 entities['customer_name'] = match_cust.group(2).strip()
            elif match_cust and match_cust.group(1):
                 entities['customer_name'] = match_cust.group(1).strip()
            # Fallback if regex fails but keyword present
            elif 'customer' in lower_body:
                 parts = lower_body.split('customer', 1)
                 if len(parts) > 1:
                     potential_name_part = parts[1].strip()
                     # Take text up to the next likely entity or end of line
                     potential_name = re.split(r'\s*(?:with amount|for item|due|,|\n)', potential_name_part, 1)[0]
                     entities['customer_name'] = potential_name.strip().title()

        elif detected_intent == Intent.RECORD_EXPENSE:
            match_vendor = re.search(REGEX_PATTERNS['vendor_name'], email_body, re.IGNORECASE)
            match_cat = re.search(REGEX_PATTERNS['category'], email_body, re.IGNORECASE)
            # Also try to find vendor name if amount is mentioned near a potential name not matched by vendor regex
            if not match_vendor and entities.get('amount') and 'paid' in lower_body:
                # Very basic: find word before "paid" or after "paid"
                 paid_match = re.search(r'([A-Za-z0-9\s.&\-\']+?)\s+paid | paid\s+([A-Za-z0-9\s.&\-\']+)', email_body, re.IGNORECASE)
                 if paid_match:
                      entities['vendor_name'] = (paid_match.group(1) or paid_match.group(2)).strip()
            elif match_vendor:
                 entities['vendor_name'] = match_vendor.group(1).strip()

            if match_cat: entities['category'] = match_cat.group(1).strip()
            # Add simple description extraction if available
            desc_match = re.search(r'(?:description:|memo:)\s+(.*?)(?:\s+category|\s+for|$)|' # Explicit desc
                                 r'expense\s+for\s+(?:.+?)\s+of\s+\$\s?\d+(?:\.\d+)?\s+(.*)', # Desc after amount?
                                 email_body, re.IGNORECASE)
            if desc_match:
                entities['description'] = (desc_match.group(1) or desc_match.group(2) or '').strip()

        elif detected_intent == Intent.GET_REPORT_PNL:
            date_range_str = "this month" # Default
            match_range = re.search(REGEX_PATTERNS['date_range'], email_body, re.IGNORECASE)
            if match_range:
                date_range_str = match_range.group(1).strip()
            else:
                # Check common phrases if regex fails
                if "last month" in lower_body: date_range_str = "last month"
                # ... (add other common phrases: last quarter, this year, etc.)
                elif "last quarter" in lower_body: date_range_str = "last quarter"
                elif "this year" in lower_body: date_range_str = "this year"

            entities['date_range_raw'] = date_range_str
            # Use the QBO API helper to parse into start/end dates
            start_date, end_date = qbo_api.parse_date_range(date_range_str)
            if start_date and end_date:
                entities['start_date'] = start_date
                entities['end_date'] = end_date
            else:
                 logger.warning(f"Could not parse date range '{date_range_str}' into start/end dates.")

    # Clean up None amounts if they were parsed incorrectly
    if entities.get('amount') is None:
        entities.pop('amount', None)

    logger.info(f"Extracted Entities: {entities}")

    return {
        'intent': detected_intent,
        'entities': entities,
        'original_text': email_body
    }

# --- Confirmation Check ---
CONFIRMATION_REGEX = r'(CONFIRM|CANCEL)\s+([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})'

def check_for_confirmation(text: str) -> dict | None:
    """Checks if the text contains a confirmation command."""
    match = re.search(CONFIRMATION_REGEX, text, re.IGNORECASE)
    if match:
        decision = match.group(1).upper()
        uuid_str = match.group(2)
        logger.info(f"Detected confirmation reply: {decision} for {uuid_str}")
        return {
            'intent': Intent.HANDLE_CONFIRMATION, # Keep internal intent type
            'entities': {'decision': decision, 'uuid': uuid_str},
            'original_text': text
        }
    return None 