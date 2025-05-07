import os
import logging
import json
import asyncio
import re
from anthropic import Anthropic, AsyncAnthropic, APIError, RateLimitError
from typing import List, Dict, Any, Optional, Tuple

from ..core.config import get_secret
from ..core.constants import Intent
# from .llm_clients import get_openai_client # REMOVED THIS LINE
# from .llm_clients import get_anthropic_client # Keep if Anthropic is also used directly

logger = logging.getLogger(__name__)

# Define the list of intents Claude should recognize
SUPPORTED_INTENTS = [
    Intent.CREATE_INVOICE.value,
    Intent.SEND_INVOICE.value,
    Intent.RECORD_EXPENSE.value,
    Intent.GET_REPORT_PNL.value,
    Intent.CREATE_ESTIMATE.value,
    Intent.RECORD_PAYMENT.value,
    Intent.FIND_CUSTOMER.value,
    Intent.UNKNOWN.value
]

# --- Anthropic Client Initialization ---
API_KEY = None
source_description = ""

try:
    logger.info("Attempting to load Anthropic API Key from Secret Manager (ledger-cfo-anthropic-api-key)...")
    API_KEY = get_secret("ledger-cfo-anthropic-api-key")
    if API_KEY:
        source_description = "Secret Manager (ledger-cfo-anthropic-api-key)"
except Exception as e:
    logger.warning(f"Could not load Anthropic API Key from Secret Manager (ledger-cfo-anthropic-api-key): {e}. Trying environment variable.")

if not API_KEY:
    logger.info("Anthropic API Key not found via get_secret. Trying ANTHROPIC_API_KEY environment variable...")
    API_KEY = os.getenv("ANTHROPIC_API_KEY")
    if API_KEY:
        source_description = "environment variable (ANTHROPIC_API_KEY)"

if API_KEY:
    logger.info(f"Anthropic API Key loaded successfully from {source_description}.")
    client = AsyncAnthropic(api_key=API_KEY)
    logger.info("AsyncAnthropic client initialized successfully.")
else:
    logger.critical("Anthropic API Key NOT FOUND in Secret Manager (ledger-cfo-anthropic-api-key) or ANTHROPIC_API_KEY environment variable. LLM functionalities will fail.")
    client = None # Explicitly set to None if no key

# --- Claude Prompting --- # 
# Define the system prompt for Claude
# Using XML tags as often recommended for Claude
SYSTEM_PROMPT = f"""
You are an expert accounting assistant AI for a small business owner. Your task is to analyze the user's email text provided within <email_body> tags and determine their primary intent and extract relevant information (entities).

The possible intents are: {', '.join(SUPPORTED_INTENTS)}.

Extract key entities associated with the identified intent. Examples of entities include:
- customer_name: Name of the customer.
- vendor_name: Name of the vendor for expenses.
- amount: Numerical value of the transaction (return as a number, not string).
- item_description: Description of goods or services.
- report_period: Time frame for reports (e.g., 'last month', 'Q1 2023').
- invoice_id: Identifier for an existing invoice.
- payment_details: Information about a payment received (e.g., check number, method).
- date: Transaction date or relevant date (try to format as YYYY-MM-DD if possible, otherwise return as stated).
- estimate_id: Identifier for an estimate.
- quantity: Numerical quantity of items.
- unit_price: Numerical price per unit.

Format your response STRICTLY as a JSON object enclosed within <json_response> tags. The JSON object must have two keys:
1.  `intent`: A string containing ONE of the allowed intents listed above. If the user's intent is unclear, ambiguous, or not supported, use "{Intent.UNKNOWN.value}".
2.  `entities`: A JSON object (dictionary) containing the extracted key-value pairs. If no relevant entities are found for the intent, provide an empty object {{}}.

Example Response Format:
<json_response>
{{
  "intent": "CREATE_INVOICE",
  "entities": {{
    "customer_name": "Example Corp",
    "amount": 1250.75,
    "item_description": "Consulting services",
    "date": "2023-10-26"
  }}
}}
</json_response>

If the intent is {Intent.UNKNOWN.value}, the response should look like:
<json_response>
{{
  "intent": "{Intent.UNKNOWN.value}",
  "entities": {{}}
}}
</json_response>

Only output the <json_response> block and nothing else.
"""

# Helper to extract JSON from Claude's response
def _extract_json_from_response(response_text: str) -> dict | None:
    """Extracts the JSON object from within <json_response> tags."""
    match = re.search(r"<json_response>(.*?)</json_response>", response_text, re.DOTALL | re.IGNORECASE)
    if match:
        json_str = match.group(1).strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON extracted from Claude response: {e}. JSON string: {json_str}")
            return None
    else:
        logger.warning(f"Could not find <json_response> tags in Claude response: {response_text[:500]}...")
        # Attempt to parse the whole response as JSON as a fallback
        try:
             return json.loads(response_text)
        except json.JSONDecodeError:
             logger.error("Fallback JSON parsing of entire response also failed.")
             return None

async def extract_intent_entities_llm(email_body: str) -> dict:
    """Analyzes email body using Anthropic Claude to extract intent and entities."""
    if not client:
        logger.error("Anthropic client not initialized. Cannot perform LLM NLU.")
        return {'intent': Intent.UNKNOWN.value, 'entities': {}, 'error': 'LLM client not initialized'}

    if not email_body:
        logger.warning("Received empty email body for LLM NLU.")
        return {'intent': Intent.UNKNOWN.value, 'entities': {}}

    cleaned_body = email_body.strip()
    user_message = f"<email_body>{cleaned_body}</email_body>"

    logger.info(f"Sending request to Anthropic Claude for NLU. Body length: {len(cleaned_body)}")

    try:
        response = await client.messages.create(
            model="claude-3-haiku-20240307", # Or other suitable Claude model
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=500, # Adjust as needed
            temperature=0.1
        )

        response_content = response.content[0].text
        logger.info(f"Received response from Claude. Stop reason: {response.stop_reason}")
        # logger.debug(f"Claude Raw Response: {response_content}")

        if not response_content:
            logger.error("Claude returned an empty response content.")
            return {'intent': Intent.UNKNOWN.value, 'entities': {}, 'error': 'LLM returned empty content'}

        # Extract and parse the JSON response
        parsed_json = _extract_json_from_response(response_content)

        if (parsed_json and isinstance(parsed_json, dict) and
            'intent' in parsed_json and
            'entities' in parsed_json and
            isinstance(parsed_json['entities'], dict)):

            # Ensure intent is one of the supported ones
            if parsed_json['intent'] not in SUPPORTED_INTENTS:
                logger.warning(f"Claude returned unsupported intent: {parsed_json['intent']}. Defaulting to UNKNOWN.")
                parsed_json['intent'] = Intent.UNKNOWN.value

            logger.info(f"LLM NLU Result: Intent={parsed_json['intent']}, Entities={parsed_json['entities']}")
            return parsed_json
        else:
            error_msg = "LLM response JSON structure is invalid or missing tags."
            logger.error(f"{error_msg} Raw response: {response_content[:500]}...")
            return {'intent': Intent.UNKNOWN.value, 'entities': {}, 'error': error_msg}

    except RateLimitError as rle:
        logger.error(f"Anthropic Rate Limit Error: {rle}")
        return {'intent': Intent.UNKNOWN.value, 'entities': {}, 'error': f'Anthropic rate limit exceeded: {rle}'}
    except APIError as apie:
        logger.error(f"Anthropic API Error: Status={apie.status_code}, Message={apie.message}")
        return {'intent': Intent.UNKNOWN.value, 'entities': {}, 'error': f'Anthropic API error: {apie.message}'}
    except Exception as e:
        logger.error(f"An unexpected error occurred during Anthropic API call: {e}", exc_info=True)
        return {'intent': Intent.UNKNOWN.value, 'entities': {}, 'error': f'Unexpected LLM error: {e}'}

# Define the system prompt incorporating all requirements
# Updated Tool definitions to match qbo_api.py async functions and return types
REACT_SYSTEM_PROMPT = """
**Role:** You are 'Ledger', an autonomous AI CFO assistant for Beach Handyman. You have direct access to the company's **LIVE QuickBooks Online (QBO) production environment** via available tools. Your goal is to understand the owner's email requests and fully execute the required accounting tasks accurately, efficiently, and safely.

**VERY IMPORTANT CONTEXT:**
*   You are interacting with **LIVE PRODUCTION DATA**. Actions you instruct (creating invoices, voiding transactions, sending emails) have **real financial consequences**. Double-check your reasoning and parameters before executing actions.
*   Tasks may require multiple steps. Analyze the request, form a plan, gather necessary information using query tools one step at a time, perform calculations if needed, execute actions, and verify results before finishing.
*   If you encounter errors or ambiguity, use `SEND_DIRECTOR_EMAIL` to ask for clarification rather than making assumptions.

**Available Tools:**
You MUST use the exact tool names and parameters specified. All QBO tools are `async` and return data as Python dictionaries or lists of dictionaries (unless otherwise specified).

*   `QBO_GET_CUSTOMER_DETAILS(customer_id: str) -> dict`: Fetches full customer details (name, email, phone, address, balance, etc.). Raises NotFoundError if ID is invalid.
*   `QBO_GET_CUSTOMER_TRANSACTIONS(customer_id: str, start_date: str = None, end_date: str = None) -> list[dict]`: Fetches a list of transactions (Invoice, Payment, Estimate, SalesReceipt) for a customer within an optional date range (YYYY-MM-DD). Includes key details like ID, date, amount, status/balance.
*   `QBO_GET_ESTIMATE_DETAILS(estimate_id: str) -> dict`: Fetches full details of a specific estimate, including line items. Raises NotFoundError if ID is invalid.
*   `QBO_FIND_ESTIMATES(customer_id: str = None, status: str = None) -> list[dict]`: Finds estimates, filterable by customer ID and status ('Accepted', 'Pending', 'Closed', 'Rejected'). Returns a list of estimate dictionaries.
*   `QBO_FIND_CUSTOMERS_BY_DETAILS(query: str) -> list[dict]`: Searches for customers based on fragments of name, company, email, or phone. Returns a list of potential matches with IDs and key details. Use this to find a customer ID if you only have a name or other detail.
*   `QBO_GET_RECENT_TRANSACTIONS_WITH_CUSTOMER_DATA(days: int = 30) -> list[dict]`: Fetches recent transactions (default 30 days, all types) and includes associated customer details dictionary for each. Useful for broad overviews.
*   `QBO_CREATE_INVOICE(customer_id: str, line_items: list[dict], invoice_data: dict = None) -> dict`: Creates an invoice. `line_items` is a list like `[{'Amount': 100.00, 'Description': 'Service X', 'SalesItemLineDetail': {'ItemRef': {'value': 'ITEM_ID'}}}]` (ItemRef is optional). `invoice_data` can contain header fields like `DueDate`. Returns created invoice dictionary including 'Id'.
    **Hint:** For a final invoice representing a remaining balance, a single line item can be used, e.g., `[{'Amount': <calculated_amount>, 'Description': 'Remaining balance for completed project per Estimate #XYZ.'}]`. This avoids needing specific ItemRefs.
*   `QBO_CREATE_ESTIMATE(customer_id: str, line_items: list[dict], estimate_data: dict = None) -> dict`: Creates an estimate. Similar structure to `QBO_CREATE_INVOICE`. Returns created estimate dictionary including 'Id'.
*   `QBO_RECORD_PAYMENT(customer_id: str, invoice_id: str, amount: float, payment_data: dict = None) -> dict`: Records a payment against a specific invoice. `payment_data` can contain fields like `TxnDate`, `PaymentMethodRef`. Returns created payment dictionary including 'Id'.
*   `QBO_SEND_INVOICE(invoice_id: str) -> bool`: Triggers QBO to email the specified invoice to the customer's primary email address. Returns True if the send command was accepted, False otherwise (e.g., invoice not found, customer email missing).
*   `QBO_VOID_INVOICE(invoice_id: str) -> bool`: **USE WITH EXTREME CAUTION.** Voids a specific invoice. Returns True if successful, False otherwise. Raises InvalidDataError if the invoice cannot be voided (e.g., already paid).
*   `CALCULATE(expression: str) -> float`: Evaluates a simple mathematical expression (e.g., "25296.00 - 7588.80"). Returns the numerical result. Use this for calculating final amounts, remaining balances, etc.
*   `SEND_DIRECTOR_EMAIL(subject: str, body: str) -> bool`: Sends an email notification to the Director (your boss). Use this to report task completion, errors you cannot resolve, or when clarification is needed.

**Reasoning Process (ReAct Pattern):**
1.  **Analyze Request:** Understand the user's goal from their latest message and the conversation history.
2.  **Plan Steps:** Break down the goal into logical steps. Identify required information (e.g., customer ID, estimate amount, previous payments).
3.  **Execute Step-by-Step:**
    *   **Thought:** Briefly explain the current step and why it's needed.
    *   **Action:** Choose **one tool** to execute based on the plan. If information is missing, use a query tool (`QBO_FIND_CUSTOMERS_BY_DETAILS`, `QBO_GET_CUSTOMER_TRANSACTIONS`, etc.). If calculations are needed, use `CALCULATE`. If an action is required, use the appropriate QBO tool (`QBO_CREATE_INVOICE`, etc.). Format the action as JSON.
4.  **Observe Result:** The system will execute your chosen action and provide the result (or an error message) in the next turn's history.
5.  **Analyze Result & Repeat:** Examine the result. Was the step successful? Did it provide the needed information? Did it cause an error? Based on the observation, update your plan and decide the *next* single action (go back to step 3).
6.  **Handle Errors:** If a tool returns an error:
    *   Analyze the error message provided in the history.
    *   **Thought:** Explain the error and your plan to handle it.
    *   **Action:** Decide whether to: retry (if temporary issue suspected), use a different tool/approach (e.g., broader search), or use `SEND_DIRECTOR_EMAIL` if stuck or clarification is needed.
7.  **Finalize Task:** Once all steps are successfully completed and verified, use the `FINISH` action.
    *   **Action:** `{"action": "FINISH", "response": "Clear, concise confirmation message for the Director summarizing what was done (e.g., 'Final invoice #123 for $XXX created for Mr. Test and sent successfully.'). Include relevant IDs."}`

**Output Format:**
You MUST respond *only* with a single JSON object representing the next action to take. Do not include thoughts or any other text outside the JSON object.

*   Tool Call: `{"action": "TOOL_NAME", "params": {"param1": "value1", ...}}`
*   Email Director: `{"action": "SEND_DIRECTOR_EMAIL", "params": {"subject": "Update/Issue Subject", "body": "Detailed email body..."}}`
*   Finish Task: `{"action": "FINISH", "response": "Final confirmation message..."}`
"""

# --- Tool Definitions ---
# These should match the tools the LLM knows about.
# Keep descriptions concise but clear about function, inputs, and outputs.
QBO_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "QBO_FIND_CUSTOMERS_BY_DETAILS",
            "description": "Searches QuickBooks Online (QBO) customers by name, email, company name, or phone number. Returns a list of potential matches with IDs, names, emails, phones, and addresses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The name, email, company, or phone number to search for."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "QBO_GET_CUSTOMER_TRANSACTIONS",
            "description": "Fetches transaction history (Invoices, Payments, Estimates, Sales Receipts) for a specific QBO customer ID. Can filter by start/end date (YYYY-MM-DD).",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "The QBO ID of the customer."},
                    "start_date": {"type": "string", "description": "Optional start date (YYYY-MM-DD)."},
                    "end_date": {"type": "string", "description": "Optional end date (YYYY-MM-DD)."}
                },
                "required": ["customer_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "QBO_FIND_ESTIMATES",
            "description": "Finds Estimates in QBO. Can be filtered by customer ID and/or status (e.g., 'Accepted', 'Pending', 'Closed'). Returns a list of estimates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Optional QBO ID of the customer."},
                    "status": {"type": "string", "description": "Optional status to filter by (Accepted, Pending, Closed, Rejected)."}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "QBO_GET_ESTIMATE_DETAILS",
            "description": "Fetches full details, including line items, for a specific QBO Estimate ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "estimate_id": {"type": "string", "description": "The QBO ID of the estimate."}
                },
                "required": ["estimate_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "QBO_CREATE_INVOICE",
            "description": "Creates a new Invoice in QBO for a specific customer. Requires customer ID and line items (description, amount, optional ItemRef).",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "The QBO ID of the customer."},
                    "line_items": {
                        "type": "array",
                        "description": "List of invoice lines.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "Description": {"type": "string", "description": "Description of the line item."},
                                "Amount": {"type": "number", "description": "Total amount for this line."},
                                "SalesItemLineDetail": {
                                    "type": "object",
                                    "description": "Must include ItemRef if linking to a product/service.",
                                    "properties": {
                                        "ItemRef": {
                                            "type": "object",
                                            "properties": {
                                                "value": {"type": "string", "description": "QBO ID of the Product/Service item."},
                                                "name": {"type": "string", "description": "Name of the Product/Service item (optional)."}
                                            },
                                            "required": ["value"]
                                        }
                                        # Include TaxCodeRef if needed
                                    },
                                    "required": [] # ItemRef is optional unless you need to link
                                }
                            },
                            "required": ["Amount"]
                        }
                    },
                    "invoice_data": {"type": "object", "description": "Optional dictionary for top-level invoice fields like DueDate, TermsRef, ClassRef, BillEmail (as {'Address': 'email@example.com'})."}
                },
                "required": ["customer_id", "line_items"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "QBO_SEND_INVOICE",
            "description": "Triggers QBO to send an existing invoice by its ID via email to the customer's primary email address.",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_id": {"type": "string", "description": "The QBO ID of the invoice to send."}
                },
                "required": ["invoice_id"]
            }
        }
    },
    # Add QBO_FIND_ITEM, QBO_CREATE_PURCHASE etc. if needed by the LLM
]

OTHER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "CALCULATE",
            "description": "Evaluates a simple mathematical expression (e.g., '100 + 50 - 25', '17707.20 * 0.1'). Returns the numerical result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "The mathematical expression to evaluate."}
                },
                "required": ["expression"]
            }
        }
    },
        {
        "type": "function",
        "function": {
            "name": "SEND_DIRECTOR_EMAIL",
            "description": "Sends an email notification to the Director (user) with the provided subject and body. Use this to ask for clarification, report unresolvable errors, or confirm completion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "The subject line of the email."},
                    "body": {"type": "string", "description": "The main content of the email."}
                },
                "required": ["subject", "body"]
            }
        }
    }
]

ALL_TOOLS = QBO_TOOLS + OTHER_TOOLS

# --- ReAct System Prompt and LLM Interaction --- #
# REACT_SYSTEM_PROMPT (as previously defined with tool definitions and instructions)
# ... (ensure REACT_SYSTEM_PROMPT is defined here or accessible)

async def determine_next_action_llm(
    conversation_history: List[Dict[str, str]],
    model: str = "claude-3-haiku-20240307",
    max_tokens: int = 1024,
) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    """
    Uses Anthropic Claude with tool-use-like prompting to determine the next action.
    Expects Claude to return a JSON object with 'action' and 'params'.
    """
    logger.info(f"Determining next action using Anthropic Claude ({model}). History length: {len(conversation_history)}")

    if not client: # Uses the global Anthropic client initialized at the top of the file
        logger.error("Anthropic client not available for ReAct loop.")
        return None, None, {"error": "Anthropic client configuration error."}

    # Format history for Claude messages API
    formatted_messages_for_claude = []
    for turn in conversation_history:
        role = turn.get("role")
        content = turn.get("content") # This is expected for user messages and tool observations (now user role)

        if role == "user":
            if isinstance(content, str):
                formatted_messages_for_claude.append({"role": "user", "content": content})
            else:
                logger.warning(f"User turn has non-string content, skipping: {turn}")
        elif role == "assistant":
            # This is an assistant turn that previously decided an action.
            # It should be presented to Claude as the JSON it outputted.
            action_taken = turn.get("action")
            params_taken = turn.get("params")
            if action_taken:
                assistant_content_json = json.dumps({"action": action_taken, "params": params_taken if params_taken else {}})
                formatted_messages_for_claude.append({"role": "assistant", "content": assistant_content_json})
            elif isinstance(content, str): # If it was a simple text response from assistant
                 formatted_messages_for_claude.append({"role": "assistant", "content": content})
            else:
                logger.warning(f"Assistant turn has no action and non-string content, skipping: {turn}")
        elif role == "tool": # This is an observation from a tool call
            # Convert tool observations to "user" role for Claude, prepended with "Observation:"
            if isinstance(content, str):
                formatted_messages_for_claude.append({"role": "user", "content": f"Observation: {content}"})
            else:
                logger.warning(f"Tool turn has non-string content, skipping: {turn}")
        else:
            logger.warning(f"Skipping turn with unknown role: {role} in history: {turn}")
    
    if not formatted_messages_for_claude:
        # This can happen if the initial user message was somehow skipped or malformed.
        # Or if all history turns were unparseable.
        logger.error("Cannot call Claude: formatted_messages_for_claude is empty after processing conversation_history.")
        # Check original history for at least one user message if formatted is empty
        if any(turn.get("role") == "user" and isinstance(turn.get("content"), str) for turn in conversation_history):
            # Try to reconstruct a minimal history if possible, e.g., just the last valid user message
            last_user_message = next((turn["content"] for turn in reversed(conversation_history) if turn.get("role") == "user" and isinstance(turn.get("content"), str)), None)
            if last_user_message:
                logger.warning("Reconstructing minimal history with last user message for Claude call.")
                formatted_messages_for_claude = [{"role": "user", "content": last_user_message}]
            else:
                return None, None, {"error": "Formatted message history is empty and no valid user message found to retry."}
        else:
            return None, None, {"error": "Formatted message history is empty and no user message found."}

    try:
        response = await client.messages.create(
            model=model,
            system=REACT_SYSTEM_PROMPT,
            messages=formatted_messages_for_claude,
            max_tokens=max_tokens,
            temperature=0.1,
        )

        if not response.content or not response.content[0].text:
            logger.error("Anthropic Claude returned empty or invalid content for ReAct.")
            return None, None, {"error": "LLM returned empty content."}

        llm_output_text = response.content[0].text # Keep raw output from Claude initially
        logger.info(f"Claude ReAct Raw Output (repr): {repr(llm_output_text)}") # Log raw repr

        # Attempt to extract JSON block
        # Regex to find a string that looks like a JSON object: starts with {, ends with }, balanced braces.
        # This is hard with regex. A simpler greedy match for the first well-formed object might be better if Claude adds suffix text.
        # For now, stick to finding the first opening brace and trying to parse from there.
        
        match = re.search(r"\s*(\{.*\})\s*", llm_output_text, re.DOTALL)
        extracted_json_str = None
        if match:
            extracted_json_str = match.group(1).strip() # group(1) is the content within {}, then strip
            logger.info(f"Extracted potential JSON block with regex and strip (repr): {repr(extracted_json_str)}")
        else:
            # Fallback if regex fails: try to find first '{' and last '}' if regex was too strict
            first_brace = llm_output_text.find('{')
            last_brace = llm_output_text.rfind('}')
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                extracted_json_str = llm_output_text[first_brace : last_brace+1].strip()
                logger.info(f"Extracted potential JSON block with find/rfind and strip (repr): {repr(extracted_json_str)}")
            else:
                 logger.error(f"Could not find any JSON block in Claude's output (repr): {repr(llm_output_text)}")
                 return None, None, {"error": f"LLM response did not contain a discernible JSON block: {llm_output_text[:200]}..."}
        
        if not extracted_json_str:
            # This case should ideally not be reached if the above logic works
            logger.error(f"JSON extraction failed. Original output (repr): {repr(llm_output_text)}")
            return None, None, {"error": "JSON extraction failed."}

        try:
            # Before parsing, one more sanity strip, just in case.
            final_json_to_parse = extracted_json_str.strip()
            logger.info(f"Attempting to parse final JSON string (repr): {repr(final_json_to_parse)}")
            parsed_json = json.loads(final_json_to_parse)
            action_name = parsed_json.get("action")
            action_params = parsed_json.get("params")

            if not action_name:
                logger.error(f"LLM JSON response is missing 'action'. Parsed JSON: {parsed_json}")
                return None, None, {"error": "LLM response missing 'action' field in parsed JSON."}
            
            thought = f"Decided to execute action: {action_name}"
            logger.info(f"Claude ReAct Parsed: Action={action_name}, Params={action_params}")
            return thought, action_name, action_params

        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse extracted JSON: {json_err}. String was (repr): {repr(final_json_to_parse)}")
            return None, None, {"error": f"Failed to parse extracted JSON block: {final_json_to_parse[:200]}..."}

    except RateLimitError as rle:
        logger.error(f"Anthropic Rate Limit Error during ReAct: {rle}")
        return None, None, {"error": f"Anthropic rate limit exceeded: {rle}"}
    except APIError as apie:
        logger.error(f"Anthropic API Error during ReAct: Status={apie.status_code}, Message={apie.message}")
        return None, None, {"error": f"Anthropic API error: {apie.message}"}
    except Exception as e:
        logger.error(f"Unexpected error during Anthropic ReAct call: {e}", exc_info=True)
        return None, None, {"error": f"Unexpected LLM error: {e}"}

# --- Placeholder for main ReAct loop execution ---
# This will likely live in __main__.py or a similar orchestrator file
async def execute_react_loop(initial_request: str):
    # TODO: Implement the full ReAct loop logic here or in __main__.py
    # 1. Initialize history: [{'role': 'user', 'content': initial_request}]
    # 2. Loop (max_steps):
    #    a. Call determine_next_action_llm(history)
    #    b. Parse action
    #    c. If tool call: Execute tool (using qbo_api, local calc, email), handle result/error
    #    d. If FINISH: Log/return final response, break
    #    e. If SEND_DIRECTOR_EMAIL: Send email, add confirmation to history, potentially break or continue based on policy
    #    f. Append action + result/error to history
    #    g. Implement ask_claude.cjs logic on persistent errors
    # 3. Handle loop exit (max steps reached, error, finish)
    logger.warning("execute_react_loop is a placeholder and needs implementation.")
    # Simulate a simple flow for now
    history = [{'role': 'user', 'content': initial_request}]
    action = await determine_next_action_llm(history)
    return f"Placeholder execution: Initial action determined: {action}"