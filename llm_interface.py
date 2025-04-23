import json
import re
from logger import cfo_logger
from typing import List, Dict, Any, Optional, Tuple

# Define the structure of the tools for the simulated LLM
TOOLS = [
    {
        "name": "search_quickbooks_context",
        "description": "Searches QuickBooks entities (Customer, Estimate) based on a search term to find context for a request.",
        "parameters": {
            "type": "object",
            "properties": {
                "search_term": {
                    "type": "string",
                    "description": "The identifier to search for (e.g., '638 rhode', 'XYZ Corp', 'E123'). Can be customer name, address fragment, job ID, etc.",
                }
                # Implicitly searches Customer:DisplayName and Estimate:DocNumber/PrivateNote for now
            },
            "required": ["search_term"],
        },
    },
    {
        "name": "get_quickbooks_estimate",
        "description": "Retrieves details of a specific estimate from QuickBooks using its ID.",
         "parameters": {
            "type": "object",
            "properties": {
                "estimate_id": {
                    "type": "string",
                    "description": "The ID of the estimate to retrieve.",
                }
            },
            "required": ["estimate_id"],
        },
    },
    {
        "name": "create_quickbooks_invoice",
        "description": "Creates a new invoice in QuickBooks based on customer ID, line items, or an estimate ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "The ID of the customer to invoice.",
                },
                "estimate_id": {
                    "type": "string",
                    "description": "(Optional) The ID of an estimate to convert into an invoice.",
                },
                 "line_items": {
                    "type": "array",
                    "description": "(Optional) A list of line items for the invoice if not using an estimate.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "amount": {"type": "number"},
                            "item_id": {"type": "string", "description": "(Optional) QuickBooks Item ID"},
                        },
                         "required": ["description", "amount"],
                    },
                },
                "memo": {
                    "type": "string",
                    "description": "(Optional) A memo or note for the invoice.",
                },
                "email_address": {
                    "type": "string",
                    "description": "(Optional) Email address to send the invoice to after creation.",
                },
                 "due_date": {
                    "type": "string",
                    "description": "(Optional) Due date in YYYY-MM-DD format.",
                 },
                 "invoice_date": {
                    "type": "string",
                    "description": "(Optional) Invoice date in YYYY-MM-DD format.",
                 },
                 "amount": {
                     "type": "number",
                     "description": "(Optional) Explicit total amount for the invoice if line items are not provided."
                 }
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "ask_user_for_clarification",
        "description": "Asks the originating user a question to clarify their request or provide missing information.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user.",
                }
            },
            "required": ["question"],
        },
    }
]

def get_available_tools_definition() -> List[Dict[str, Any]]:
    """Returns the list of tools available for the LLM."""
    return TOOLS


def simulate_llm_response(email_body: str, tools: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """
    Simulates an LLM call to decide the next action based on email content.

    Args:
        email_body: The content of the email.
        tools: A list of available tool definitions.

    Returns:
        A tuple containing:
        - tool_name (Optional[str]): The name of the tool to call, if any.
        - tool_arguments (Optional[Dict[str, Any]]): The arguments for the tool call.
        - direct_response (Optional[str]): A direct text response if no tool is called.
    """
    cfo_logger.info(f"Simulating LLM response for email body: {email_body[:200]}...") # Log snippet
    lower_body = email_body.lower()

    # --- Simple keyword-based simulation ---

    # 1. Invoice Generation Request
    if "invoice" in lower_body and ("generate" in lower_body or "create" in lower_body or "send" in lower_body):
        cfo_logger.info("LLM Simulation: Detected invoice creation request.")

        # Try to extract customer info (very basic)
        customer_match = re.search(r"(?:for|at|client|customer)[:\s]+([\w\s\d.\-_]+)(?:\n|$)", email_body, re.IGNORECASE)
        customer_query = customer_match.group(1).strip() if customer_match else None
        cfo_logger.info(f"LLM Simulation: Extracted customer query: '{customer_query}'")

        # Try to extract amount (very basic)
        amount_match = re.search(r"[$£€](\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)", email_body)
        amount = float(amount_match.group(1).replace(',', '')) if amount_match else None
        cfo_logger.info(f"LLM Simulation: Extracted amount: {amount}")

        # Try to extract estimate ID (basic)
        estimate_match = re.search(r"(?:estimate|quote|proposal)\s*(?:id|#|number)?[:\s]*(\w+)", lower_body)
        estimate_id = estimate_match.group(1) if estimate_match else None
        cfo_logger.info(f"LLM Simulation: Extracted estimate ID: {estimate_id}")

        # --- Updated Decision Logic ---:
        if estimate_id and customer_query:
             # If estimate ID AND customer query are present, assume we can find customer later.
             # Prioritize getting estimate details first to confirm amount/lines.
             cfo_logger.info("LLM Simulation: Choosing 'get_quickbooks_estimate' first.")
             return "get_quickbooks_estimate", {"estimate_id": estimate_id}, None
        
        elif customer_query and amount:
            # If customer and explicit amount are found, try finding the customer first.
            # The next step (after finding customer) would be to create the invoice with this amount.
            # Use the context search which implicitly includes customers.
            cfo_logger.info("LLM Simulation: Choosing 'search_quickbooks_context' to verify customer and context.")
            return "search_quickbooks_context", {"search_term": customer_query}, None
            
        elif customer_query:
             # Customer query is present, but NO amount or estimate ID.
             # Instead of asking user, search QB for context first.
             cfo_logger.info("LLM Simulation: Choosing 'search_quickbooks_context' (missing amount/estimate).")
             return "search_quickbooks_context", {"search_term": customer_query}, None
             
        elif estimate_id: 
             # Estimate ID is present, but NO customer query/info extracted.
             # Get estimate details first, which should contain customer ref.
             cfo_logger.info("LLM Simulation: Choosing 'get_quickbooks_estimate' first (customer TBD from estimate).")
             return "get_quickbooks_estimate", {"estimate_id": estimate_id}, None
             
        else:
            # If not enough info (no customer query, no estimate id), then ask for clarification.
            cfo_logger.info("LLM Simulation: Choosing 'ask_user_for_clarification' (missing customer/estimate).")
            question = "I understand you want an invoice generated. Could you please provide the customer name/address or an estimate number?"
            return "ask_user_for_clarification", {"question": question}, None

    # 2. Simple Question (e.g., status) - Basic check
    elif "status" in lower_body or "update" in lower_body:
         cfo_logger.info("LLM Simulation: Detected status request.")
         return None, None, "I've received your request. I'll look into the status and get back to you if I find any updates."

    # 3. Default / Fallback
    else:
        cfo_logger.info("LLM Simulation: Email content not recognized for specific tool use. Asking for clarification.")
        question = "Thank you for your email. Could you please clarify what action you'd like me to take?"
        return "ask_user_for_clarification", {"question": question}, None

# Example usage (for testing purposes)
if __name__ == '__main__':
    test_email_1 = """
    Subject: generate invoice for 638 rhode

    we are done with the work at 638 rhode. please generate the final invoice for $1250.50.

    Thanks,
    Matt
    """
    test_email_2 = """
    Subject: Invoice needed

    Hi, please create an invoice for the job at 123 Oak Street. Use estimate EST1001.

    Thanks
    """
    test_email_3 = """
    Subject: Need help

    Please make an invoice for Mrs. Smith.
    """
    test_email_4 = """
    Subject: What's the status?

    Hi, any update on the invoice I requested yesterday?
    """

    available_tools = get_available_tools_definition()

    print("--- Test Email 1 ---")
    tool_name, tool_args, response = simulate_llm_response(test_email_1, available_tools)
    print(f"Tool: {tool_name}, Args: {tool_args}, Response: {response}\n")

    print("--- Test Email 2 ---")
    tool_name, tool_args, response = simulate_llm_response(test_email_2, available_tools)
    print(f"Tool: {tool_name}, Args: {tool_args}, Response: {response}\n")

    print("--- Test Email 3 ---")
    tool_name, tool_args, response = simulate_llm_response(test_email_3, available_tools)
    print(f"Tool: {tool_name}, Args: {tool_args}, Response: {response}\n")

    print("--- Test Email 4 ---")
    tool_name, tool_args, response = simulate_llm_response(test_email_4, available_tools)
    print(f"Tool: {tool_name}, Args: {tool_args}, Response: {response}\n") 