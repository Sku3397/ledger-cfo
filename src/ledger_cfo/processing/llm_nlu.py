import os
import logging
import json
import asyncio
import re
from anthropic import Anthropic, AsyncAnthropic, APIError, RateLimitError

from ..core.config import get_secret
from ..core.constants import Intent

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

# --- Claude Client Initialization ---
# Use ANTHROPIC_API_KEY from environment variable primarily for local dev/testing as requested.
# For deployed version, it should ideally still fetch from Secret Manager.
API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Fallback to Secret Manager if env var is not set (recommended for deployment)
if not API_KEY:
    logger.info("ANTHROPIC_API_KEY not found in environment variables. Trying Secret Manager...")
    try:
        API_KEY = get_secret("ANTHROPIC_API_KEY")
        if not API_KEY:
             logger.critical("Anthropic API Key not found in environment or Secret Manager. LLM NLU will fail.")
             client = None
        else:
             logger.info("Anthropic API Key loaded from Secret Manager.")
             client = AsyncAnthropic(api_key=API_KEY)
    except Exception as e:
        logger.critical(f"Failed to load Anthropic API key from Secret Manager: {e}. LLM NLU will fail.", exc_info=True)
        client = None
else:
    logger.info("Anthropic API Key loaded from environment variable.")
    client = AsyncAnthropic(api_key=API_KEY)

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

        if parsed_json and isinstance(parsed_json, dict) and \ 
           'intent' in parsed_json and \ 
           'entities' in parsed_json and \ 
           isinstance(parsed_json['entities'], dict):

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