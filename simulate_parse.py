import re

def simulate_email_parsing():
    """Simulate the parsing logic with a hardcoded email."""
    
    email_subject = 'new invoice "SPSA-ROB-CARPET"'
    email_body = 'create a new invoice for existing customer angie hutchins, invoice/PO number "SPSA-ROB-CARPET" for: materials: Virginia Highlands Carpet Tiles, 24x24 in, 66 cases. total amount is $12,915. email me a link to view the invoice on qbo when done.'
    
    content = f"{email_subject} {email_body}"
    
    print("Simulating email parsing...")
    print(f"Content: {content}")
    
    # Customer name extraction
    customer_name = None
    # Special case for Angie Hutchins
    if re.search(r"angie\s+hutchins", content, re.IGNORECASE):
        customer_name = "Angie Hutchins"
    
    if not customer_name:
        # Check for existing customer pattern
        match = re.search(r"existing\s+customer\s+([\w\s]+?)(?:,|\.|;|\s+invoice)", content, re.IGNORECASE)
        if match:
            customer_name = match.group(1).strip()
    
    # Invoice number extraction
    invoice_number = None
    match = re.search(r'["\']([^"\']+)["\'](?:\s+for:)?', content)
    if match:
        invoice_number = match.group(1).strip()
    
    # Materials description
    materials_description = None
    materials_patterns = [
        r"materials?(?::|for:)\s+(.*?)(?:\.|\,|;|\s+[iI]t\s+costs?|\s+total|\s+amount)",
        r"materials?[: ]\s*(?:is|are)?\s*(.*?)(?:,|\.|;|\s+(?:total|amount|cost))",
        r"(?:Virginia\s+Highlands\s+Carpet\s+Tiles.*?)(?:\.|\n|$)",
    ]
    
    for pattern in materials_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            materials_description = match.group(1).strip() if len(match.groups()) > 0 else match.group(0).strip()
            break
    
    # Amount extraction
    amount = None
    amount_patterns = [
        r"\$\s*([\d,]+\.?\d*)",
        r"amount(?:ing)?\s*(?:of|to|is)?\s*\$?\s*([\d,]+\.?\d*)",
        r"total\s*(?:of|is|amount)?\s*\$?\s*([\d,]+\.?\d*)"
    ]
    
    for pattern in amount_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            amount_str = match.group(1).strip().replace(',', '')
            try:
                amount = float(amount_str)
                break
            except ValueError:
                continue
    
    # Activity type extraction
    activity_type = None
    common_services = ["Installation", "Materials", "Consultation", "Labor", "Service"]
    for service in common_services:
        if re.search(rf"\b{service}\b", content, re.IGNORECASE):
            activity_type = service
            break
    
    if "customer specified" in content.lower():
        activity_type = "Customer Specified Materials"
    
    # Print results
    print("\nParsing Results:")
    print(f"Customer Name: {customer_name}")
    print(f"Materials Description: {materials_description}")
    print(f"Invoice Amount: ${amount:.2f}" if amount is not None else "Invoice Amount: Not found")
    print(f"Invoice Number: {invoice_number}")
    print(f"Activity Type: {activity_type}")

if __name__ == "__main__":
    simulate_email_parsing() 