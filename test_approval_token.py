#!/usr/bin/env python3
"""
Test script for debugging approval tokens.
"""

import sys
import json
from datetime import datetime
from approval_workflow import ApprovalWorkflow
from config import config
from logger import cfo_logger

def test_approval_tokens():
    """Test approval token generation and validation."""
    print("Testing Approval Token System")
    print("--------------------------")
    
    # Initialize the workflow
    workflow = ApprovalWorkflow(config)
    
    # Create a test invoice
    test_invoice = {
        'invoice_id': 'test-id-123',
        'customer_name': 'Test Customer',
        'total_amount': 123.45,
        'doc_number': 'TEST-123',
        'invoice_date': datetime.now().strftime('%Y-%m-%d'),
        'line_items': [
            {
                'description': 'Test item',
                'amount': 123.45
            }
        ]
    }
    
    # Generate a token
    print("\nGenerating token...")
    token = workflow.generate_approval_token(test_invoice)
    print(f"Token: {token[:30]}...")
    
    # Validate the token
    print("\nValidating token...")
    decoded = workflow.verify_approval_token(token)
    
    if decoded:
        print("✅ Token validation successful!")
        print("\nDecoded invoice data:")
        for key, value in decoded.items():
            if key != 'line_items':
                print(f"  {key}: {value}")
            else:
                print(f"  {key}: {len(value)} items")
    else:
        print("❌ Token validation failed!")
    
    # Test token validation with slight modifications to validation logic
    print("\nTesting different token validation approaches...")
    
    try:
        import jwt
        from jose import jwt as jose_jwt
        
        # Try manual decoding
        print("\nDecoding with PyJWT...")
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
        print(f"PyJWT decode successful, keys: {', '.join(payload.keys())}")
        
        # Try with python-jose
        print("\nDecoding with python-jose...")
        payload2 = jose_jwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
        print(f"python-jose decode successful, keys: {', '.join(payload2.keys())}")
        
        # Check if the invoice_data is present
        if 'invoice_data' in payload:
            invoice_data = payload['invoice_data']
            print(f"\ninvoice_data contains keys: {', '.join(invoice_data.keys())}")
        else:
            print("\n❌ invoice_data not found in payload!")
            
    except Exception as e:
        print(f"\n❌ Manual token decode error: {str(e)}")
    
    print("\nTest completed!")
    return True

if __name__ == "__main__":
    success = test_approval_tokens()
    sys.exit(0 if success else 1) 