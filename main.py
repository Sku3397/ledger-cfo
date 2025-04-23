import streamlit as st

# Set page configuration - must be the first Streamlit command!
st.set_page_config(
    page_title="CFO Agent",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os
import queue
import threading
import re # Added re import
from typing import Dict, Any, Optional

# Local Imports
from accounting_engine import AccountingEngine
from tax_module import TaxModule
from chat_interface_cfo import CFOChatInterface
from config import config
from logger import cfo_logger
from email_monitor import EmailMonitor
# Removed EmailParser import as LLM will handle interpretation
# from email_parser import EmailParser, InvoiceRequest, IncompleteInvoiceRequest 
from invoice_creator import InvoiceCreator # Keep for now, might be useful later
from approval_workflow import ApprovalWorkflow 
from quickbooks_api import QuickBooksAPI
from llm_interface import simulate_llm_response, get_available_tools_definition # Import LLM simulator


# --- LLM Tool Definitions and Handling ---

# Tool definitions (fetch from llm_interface)
TOOL_DEFINITIONS = get_available_tools_definition()

# Initialize the application components (maintain references for tool execution)
try:
    qb_api = QuickBooksAPI()
    accounting_engine = AccountingEngine(api_instance=qb_api)
    tax_module = TaxModule(accounting_engine)
    chat_interface = CFOChatInterface(accounting_engine, tax_module)
    invoice_creator = InvoiceCreator(qb_api) # Keep for now, might be useful later
    email_monitor = EmailMonitor(config)
    approval_workflow = ApprovalWorkflow(config)
    
    # Set the email_monitor in the approval_workflow directly
    approval_workflow.set_email_monitor(email_monitor)
    
    cfo_logger.info("Application components initialized successfully")
except Exception as e:
    cfo_logger.error(f"Error initializing application components: {str(e)}")
    st.error(f"Error initializing application: {str(e)}")
    # Set components to None to prevent errors later
    qb_api = None
    accounting_engine = None
    tax_module = None
    chat_interface = None
    invoice_creator = None
    approval_workflow = None
    email_monitor = None

# Global queue for communication between email thread and main thread (for UI updates)
update_queue = queue.Queue()

# Remove old tool definition/mapping logic if it exists here
# (Checking the previous file content, it seems the old definitions were already removed/different)

# --- New LLM-based Email Processing Callback ---

def handle_llm_email_processing(email_data: Dict[str, Any]):
    """
    Processes a new email using the simulated LLM to determine actions.
    This function acts as the callback for EmailMonitor.
    """
    if not qb_api or not approval_workflow:
        cfo_logger.error("QB API or Approval Workflow not initialized. Skipping email processing.")
        # Attempt to update UI queue even if components are missing
        try:
             update_queue.put({
                 'type': 'email_status',
                 'message_id': email_data.get('message_id', 'N/A'),
                 'sender': email_data.get('sender', 'Unknown'),
                 'subject': email_data.get('subject', 'No Subject'),
                 'status': 'Error',
                 'result': 'Core components not initialized.',
                 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
             })
        except Exception as q_err:
             cfo_logger.error(f"Failed to put component init error on queue: {q_err}")
        return

    message_id = email_data.get('message_id', 'N/A')
    # Prefer using the pre-extracted 'from_email', fall back to 'sender', then 'from'
    sender_display = email_data.get('sender', email_data.get('from', 'Unknown Sender')) 
    subject = email_data.get('subject', 'No Subject')
    body = email_data.get('body', '')
    # Get the cleaner extracted email if available
    reply_to_address = email_data.get('from_email') 
    
    cfo_logger.info(f"Processing new email via LLM: ID={message_id}, From='{sender_display}', Subject='{subject}'")
    update_queue.put({
        "type": "email_status", 
        "message_id": message_id, 
        "status": "Processing with LLM", 
        "sender": sender_display, # Show raw header in UI log 
        "subject": subject,
        "result": "Starting analysis...",
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    try:
        # Simulate LLM call
        tool_name, tool_args, direct_response = simulate_llm_response(body, TOOL_DEFINITIONS)

        if direct_response:
            cfo_logger.info(f"LLM provided direct response for email {message_id}: {direct_response}")
            update_queue.put({"type": "email_status", "message_id": message_id, "status": "Processed (Direct Response)", "result": direct_response, 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            # Option: Send simple response back? For now, just log.
            # email_address_to_send = email_monitor._extract_email_address(sender) if email_monitor else sender
            # if email_address_to_send:
            #     approval_workflow.send_response_email(to_email=email_address_to_send, subject=f"Re: {subject}", body=direct_response)

        elif tool_name == "ask_user_for_clarification":
            question = tool_args.get("question", "Could you please provide more details?")
            cfo_logger.info(f"LLM requested clarification for email {message_id}: {question}")
            update_queue.put({"type": "email_status", "message_id": message_id, "status": "Action: Request Clarification", "result": question, 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            
            # Determine the address to send to
            email_address_to_send = reply_to_address # Use pre-extracted first
            if not email_address_to_send:
                cfo_logger.warning(f"'from_email' not found in email_data for {message_id}. Attempting extraction from sender header: '{sender_display}'")
                email_address_to_send = email_monitor._extract_email_address(sender_display) if email_monitor else None

            if email_address_to_send:
                try:
                    approval_workflow.request_clarification(
                        to_email=email_address_to_send,
                        original_subject=subject,
                        message=question
                    )
                    cfo_logger.info(f"Clarification email sent to {email_address_to_send}")
                    update_queue.put({"type": "email_status", "message_id": message_id, "status": "Processed (Clarification Sent)", "result": question, 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                except Exception as e:
                    cfo_logger.error(f"Error sending clarification email for {message_id} to {email_address_to_send}: {e}")
                    update_queue.put({"type": "email_status", "message_id": message_id, "status": "Error (Clarification Failed)", "result": str(e), 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            else:
                 cfo_logger.error(f"Could not determine valid email address from sender: '{sender_display}' for clarification request.")
                 update_queue.put({"type": "email_status", "message_id": message_id, "status": "Error (Invalid Sender Email)", "result": "Could not determine email address to ask for clarification.", 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

        # --- Handle QB Search/Retrieval Tools First ---
        elif tool_name == "search_quickbooks_context":
             search_term = tool_args.get("search_term", "")
             if not search_term:
                 raise ValueError("Search term cannot be empty for search_quickbooks_context tool.")
             
             cfo_logger.info(f"LLM requested tool: {tool_name} with term: '{search_term}'")
             update_queue.put({"type": "email_status", "message_id": message_id, "status": f"Running Tool: {tool_name}", "result": f"Searching context for: '{search_term[:50]}...'", 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
             
             # Call the generic handler
             search_results = handle_tool_call(tool_name, tool_args, message_id, reply_to_address or sender_display, subject)
             
             # --- Next Step Simulation (Limited) ---
             # A real LLM would analyze search_results and plan the next step.
             # Here, we log and maybe attempt a default next step if simple.
             if search_results:
                 found_customers = search_results.get('Customer', [])
                 found_estimates = search_results.get('Estimate', [])
                 log_msg = f"Context search found: {len(found_customers)} Customer(s), {len(found_estimates)} Estimate(s)."
                 cfo_logger.info(log_msg)
                 update_queue.put({"type": "email_status", "message_id": message_id, "status": "Tool Result (Context Search)", "result": log_msg, 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                 
                 # TODO: Implement multi-turn logic based on results.
                 # If estimate found -> get details? If customer found -> check email amount? If both -> ???
                 # If nothing found -> ask user for clarification.
                 if not found_customers and not found_estimates:
                     question = f"I searched QuickBooks for '{search_term}' but couldn't find a matching customer or estimate. Could you please provide more details like the customer name or estimate number?"
                     handle_tool_call("ask_user_for_clarification", {"question": question}, message_id, reply_to_address or sender_display, subject)
                 # Add more sophisticated logic here in a real multi-turn setup.
                 
             else:
                 cfo_logger.warning(f"Context search for '{search_term}' returned no results or failed.")
                 update_queue.put({"type": "email_status", "message_id": message_id, "status": "Tool Result (Context Search Failed)", "result": "No context found.", 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                 question = f"I searched QuickBooks for '{search_term}' but couldn't find any matching information. Could you please provide more details like the customer name or estimate number?"
                 handle_tool_call("ask_user_for_clarification", {"question": question}, message_id, reply_to_address or sender_display, subject)

        elif tool_name == "get_quickbooks_estimate":
             estimate_id = tool_args.get("estimate_id")
             if not estimate_id:
                 raise ValueError("Missing estimate_id for get_quickbooks_estimate tool.")
                 
             cfo_logger.info(f"LLM requested tool: {tool_name} with ID: {estimate_id}")
             update_queue.put({"type": "email_status", "message_id": message_id, "status": f"Running Tool: {tool_name}", "result": f"Fetching estimate {estimate_id}...", 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
             
             # Call the generic handler
             estimate_details = handle_tool_call(tool_name, tool_args, message_id, reply_to_address or sender_display, subject)
             
             # --- Next Step Simulation (Limited) ---
             if estimate_details:
                 customer_ref = estimate_details.get('CustomerRef', {})
                 customer_id = customer_ref.get('value')
                 customer_name = customer_ref.get('name', 'Unknown')
                 total_amt = estimate_details.get('TotalAmt', 0)
                 log_msg = f"Found Estimate {estimate_id} for {customer_name} (ID: {customer_id}), Total: ${total_amt:.2f}."
                 cfo_logger.info(log_msg)
                 update_queue.put({"type": "email_status", "message_id": message_id, "status": "Tool Result (Estimate Found)", "result": log_msg, 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

                 # TODO: Implement multi-turn logic. Next step is likely create_invoice.
                 if customer_id:
                     invoice_args = {
                          "customer_id": customer_id,
                          "estimate_id": estimate_id, # Link invoice to this estimate
                          "memo": f"Invoice based on email '{subject}' and Estimate {estimate_id}"
                     }
                     cfo_logger.info(f"Proceeding to create invoice from retrieved estimate {estimate_id} for customer {customer_id}")
                     handle_tool_call("create_quickbooks_invoice", invoice_args, message_id, reply_to_address or sender_display, subject)
                 else:
                      cfo_logger.error(f"Estimate {estimate_id} found, but CustomerRef is missing. Cannot create invoice.")
                      update_queue.put({"type": "email_status", "message_id": message_id, "status": "Error (Missing CustomerRef)", "result": f"Estimate {estimate_id} lacks customer info.", 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                      # Ask user for clarification about the customer?
                      question = f"I found Estimate {estimate_id} but it doesn't seem to be linked to a customer in QuickBooks. Could you please confirm the customer name?"
                      handle_tool_call("ask_user_for_clarification", {"question": question}, message_id, reply_to_address or sender_display, subject)
             else:
                 cfo_logger.warning(f"Tool get_quickbooks_estimate failed to return details for ID: {estimate_id}")
                 # Already logged in handle_tool_call, but maybe ask user?
                 question = f"I tried to look up Estimate ID '{estimate_id}' but couldn't find it in QuickBooks. Could you please double-check the ID?"
                 handle_tool_call("ask_user_for_clarification", {"question": question}, message_id, reply_to_address or sender_display, subject)
        
        # --- Handle Invoice Creation Tool --- 
        # Note: This is usually triggered *after* context search/estimate retrieval
        elif tool_name == "create_quickbooks_invoice":
             cfo_logger.info(f"LLM directly requested tool: {tool_name} with args: {tool_args}")
             update_queue.put({"type": "email_status", "message_id": message_id, "status": f"Running Tool: {tool_name}", "result": "(Creating invoice...)", 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
             handle_tool_call(tool_name, tool_args, message_id, reply_to_address or sender_display, subject)
             
        else:
             cfo_logger.warning(f"LLM returned unhandled tool or no action for email {message_id}: Tool={tool_name}")
             update_queue.put({"type": "email_status", "message_id": message_id, "status": "Processed (Unknown LLM Action)", "result": f"Tool: {tool_name}", 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
             question = f"I received an unexpected instruction ('{tool_name}') while processing your request. Could you please clarify what you need?"
             handle_tool_call("ask_user_for_clarification", {"question": question}, message_id, reply_to_address or sender_display, subject)

    except Exception as e:
        cfo_logger.error(f"Error processing email {message_id} with LLM workflow: {e}", exc_info=True)
        update_queue.put({"type": "email_status", "message_id": message_id, "status": "Error (Processing Failed)", "result": str(e), 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        # Option: Send error email
        try:
            email_address_to_send = reply_to_address # Prioritize extracted address
            if not email_address_to_send:
                email_address_to_send = email_monitor._extract_email_address(sender_display) if email_monitor else None

            if email_address_to_send:
                err_subject = f"Re: {subject} - Error Processing Request"
                err_body = f"Hi,\n\nThere was an error trying to process your request:\n\n{e}\n\nPlease review or try again.\n\nThanks,\nCFO Agent"
                approval_workflow.send_response_email(to_email=email_address_to_send, subject=err_subject, body=err_body)
        except Exception as email_err:
             cfo_logger.error(f"Failed to send processing error email: {email_err}")

# --- Generic Tool Execution Handler ---
def handle_tool_call(tool_name: str, tool_args: Dict[str, Any], message_id: str, sender_info: str, subject: str):
    """Handles the execution of a tool requested by the LLM or internal logic.
    Args:
        sender_info: Can be the extracted email address (from_email) or the raw sender header.
    """
    if not qb_api or not approval_workflow:
        cfo_logger.error(f"Cannot execute tool {tool_name} - QB API or Approval Workflow not initialized.")
        update_queue.put({"type": "email_status", "message_id": message_id, "status": f"Error (Tool Failed: {tool_name})", "result": "Core components missing", 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        return

    # Determine the reply-to address
    reply_to_address = None
    if '@' in sender_info: # Simple check if it looks like an email address
        try:
            reply_to_address = sender_info.lower()
        except (EmailNotValidError, TypeError):
            pass # Not a valid email, try extracting
    
    if not reply_to_address and email_monitor:
        cfo_logger.warning(f"Sender_info '{sender_info}' is not a direct email. Attempting extraction.")
        reply_to_address = email_monitor._extract_email_address(sender_info)

    cfo_logger.info(f"Executing tool: {tool_name} for email {message_id} with args: {tool_args}. Reply target: {reply_to_address or 'N/A'}")
    update_queue.put({"type": "email_status", "message_id": message_id, "status": f"Executing Tool: {tool_name}", "result": f"Args: {str(tool_args)[:100]}...", 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

    try:
        result = None # Initialize result
        
        # --- Implement search_quickbooks_context --- 
        if tool_name == "search_quickbooks_context":
             search_term = tool_args.get("search_term")
             # Define entities and fields to search (can be refined)
             entity_types = ["Customer", "Estimate"]
             search_fields = {
                 "Customer": ["DisplayName", "CompanyName", "BillAddr.Line1", "ShipAddr.Line1", "PrimaryEmailAddr.Address"],
                 "Estimate": ["DocNumber", "PrivateNote"]
                 # Add Invoice search later if needed?
             }
             cfo_logger.info(f"Calling qb_api.search_quickbooks for term '{search_term}' in entities {entity_types}")
             search_results = qb_api.search_quickbooks(search_term, entity_types, search_fields)
             result = search_results # Pass back the dictionary of results
        
        # --- Implement get_quickbooks_estimate --- 
        elif tool_name == "get_quickbooks_estimate":
             estimate_id = tool_args.get("estimate_id")
             if not estimate_id:
                 raise ValueError("Missing estimate_id for get_quickbooks_estimate tool.")
             
             cfo_logger.info(f"Calling qb_api.get_estimate_details for ID: {estimate_id}")
             estimate_details = qb_api.get_estimate_details(estimate_id)
             
             if estimate_details:
                 total_amt = estimate_details.get("TotalAmt", "N/A")
                 cfo_logger.info(f"Successfully retrieved details for estimate {estimate_id}")
                 # Log result in main handler, just return data here
                 result = estimate_details # Pass back details
             else:
                 cfo_logger.warning(f"Could not retrieve details for estimate {estimate_id}")
                 result = None # Indicate not found
        
        elif tool_name == "create_quickbooks_invoice":
            # Map LLM args to qb_api.create_invoice args carefully
            invoice_params = {
                "customer_id": tool_args.get("customer_id"),
                "line_items": tool_args.get("line_items"),
                "memo": tool_args.get("memo"),
                "doc_number": tool_args.get("doc_number"),
                # Handle potential estimate ID for conversion
                "estimate_id": tool_args.get("estimate_id"), 
                "draft": True # Always create as draft first
            }
             # Optional fields from LLM tool definition
            if tool_args.get("invoice_date"):
                # Assume qb_api.create_invoice can handle txnDate key if needed
                # or adapt here: invoice_params["TxnDate"] = tool_args.get("invoice_date")
                pass # Not directly mapped in current qb_api.create_invoice signature
            if tool_args.get("due_date"):
                 # Assume qb_api.create_invoice can handle dueDate key if needed
                 # or adapt here: invoice_params["DueDate"] = tool_args.get("due_date")
                 pass # Not directly mapped
            
            # Validate required fields before calling API
            if not invoice_params["customer_id"]:
                 raise ValueError("Missing required field for invoice creation: customer_id")
            if not invoice_params["line_items"] and not invoice_params["estimate_id"]:
                 # If estimate_id is provided, line_items might be derived by QBO, but explicit lines are safer if estimate_id is absent.
                 raise ValueError("Missing required field for invoice creation: line_items (or estimate_id)")

            # Call the actual QuickBooks API function using keyword arguments
            # Filter out keys with None values before passing
            call_args = {k: v for k, v in invoice_params.items() if v is not None}
            cfo_logger.info(f"Calling qb_api.create_invoice with args: {call_args}")
            created_invoice = qb_api.create_invoice(**call_args)

            if created_invoice and (created_invoice.get('Id') or created_invoice.get('id')):
                invoice_id = created_invoice.get('Id') or created_invoice.get('id')
                # DocNumber might be auto-assigned if not provided
                invoice_num = created_invoice.get('DocNumber') or created_invoice.get('doc_number', 'N/A') 
                total_amt = created_invoice.get('TotalAmt', 0)
                cfo_logger.info(f"Successfully created draft invoice {invoice_num} (ID: {invoice_id}) for ${total_amt:.2f}")
                update_queue.put({"type": "email_status", "message_id": message_id, "status": "Processed (Invoice Created)", "result": f"Draft Invoice {invoice_num} (ID: {invoice_id}) created for ${total_amt:.2f}.", 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                
                # TODO: Initiate approval workflow if needed (config based?)
                # approval_workflow.start_approval_process(created_invoice)
                
                # Send confirmation email
                if reply_to_address:
                    conf_subject = f"Re: {subject} - Draft Invoice Created"
                    conf_body = f"Hi,\n\nA draft invoice ({invoice_num}) for ${total_amt:.2f} has been created based on your request.\n\nIt may require approval before being sent.\n\nThanks,\nCFO Agent"
                    try:
                        approval_workflow.send_response_email(to_email=reply_to_address, subject=conf_subject, body=conf_body)
                        cfo_logger.info(f"Sent confirmation email for invoice {invoice_id} to {reply_to_address}")
                    except Exception as email_err:
                         cfo_logger.error(f"Failed to send confirmation email for invoice {invoice_id}: {email_err}")
                result = created_invoice # Pass back the created invoice data
            else:
                # Log the response if available
                cfo_logger.error(f"Invoice creation call seemed to succeed but returned invalid data: {created_invoice}")
                raise Exception("Invoice creation call succeeded but returned no valid invoice data.")

        elif tool_name == "ask_user_for_clarification":
            question = tool_args.get("question", "Could you please provide more details?")
            if reply_to_address:
                approval_workflow.request_clarification(
                    to_email=reply_to_address,
                    original_subject=subject,
                    message=question
                )
                cfo_logger.info(f"Clarification email sent via tool call to {reply_to_address}")
                update_queue.put({"type": "email_status", "message_id": message_id, "status": "Processed (Clarification Sent)", "result": question, 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                result = True # Indicate success
            else:
                cfo_logger.error(f"Could not determine valid email address from sender_info: '{sender_info}' for clarification tool call.")
                update_queue.put({"type": "email_status", "message_id": message_id, "status": "Error (Invalid Sender Email)", "result": "Could not determine email address for clarification tool.", 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                result = False # Indicate failure

        else:
            cfo_logger.warning(f"Attempted to execute unhandled tool: {tool_name}")
            raise NotImplementedError(f"Tool '{tool_name}' execution not implemented.")
            
        return result # Return the result of the tool execution

    except Exception as e:
        cfo_logger.error(f"Error executing tool '{tool_name}' for email {message_id}: {e}", exc_info=True)
        update_queue.put({"type": "email_status", "message_id": message_id, "status": f"Error (Tool Failed: {tool_name})", "result": str(e), 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        # Send error email
        if reply_to_address:
             err_subject = f"Re: {subject} - Error Processing Request"
             err_body = f"Hi,\n\nThere was an error trying to process your request while running the tool '{tool_name}':\n\n{e}\n\nPlease review or try again.\n\nThanks,\nCFO Agent"
             try:
                 approval_workflow.send_response_email(to_email=reply_to_address, subject=err_subject, body=err_body)
             except Exception as email_err:
                 cfo_logger.error(f"Failed to send tool error email: {email_err}")
        else:
             cfo_logger.warning(f"No valid reply-to address found to send tool error email (Tool: {tool_name}, Email ID: {message_id})")
        return None # Indicate tool failure

# --- Session State Initialization ---
# Function to initialize session state
def initialize_session_state():
    """Initialize session state variables."""
    if "data_loaded" not in st.session_state:
        st.session_state.data_loaded = False
    if "current_view" not in st.session_state:
        st.session_state.current_view = "Dashboard"
    if "processed_emails" not in st.session_state:
        st.session_state.processed_emails = []
    if "pending_invoices" not in st.session_state:
        st.session_state.pending_invoices = []
    if "incomplete_requests" not in st.session_state:
        st.session_state.incomplete_requests = []
    if "email_monitoring_active" not in st.session_state:
        st.session_state.email_monitoring_active = False
    if "kpis" not in st.session_state:
        st.session_state.kpis = None

# Initialize session state
initialize_session_state()

# Process updates from the email monitor queue
updates_processed = False
while not update_queue.empty():
    try:
        update = update_queue.get_nowait()
        if update['type'] == 'email_status':
            # Find existing entry by message_id and update status, or append new
            found = False
            for i, item in enumerate(st.session_state.processed_emails):
                if item.get('message_id') == update.get('message_id') and update.get('message_id') is not None:
                    st.session_state.processed_emails[i] = update
                    found = True
                    break
            if not found:
                 # Remove message_id before appending if it was only for tracking updates
                 update.pop('message_id', None) 
                 st.session_state.processed_emails.append(update)
                 
        elif update['type'] == 'pending_invoice':
            st.session_state.pending_invoices.append(update['data'])
        elif update['type'] == 'pending_request':
            st.session_state.incomplete_requests.append(update['data'])
        updates_processed = True
    except queue.Empty:
        break # Should not happen with while not empty(), but good practice
    except Exception as e:
        cfo_logger.error(f"Error processing update queue: {e}")
        st.toast(f"Error processing background update: {e}", icon="🚨")

# Trigger a rerun if updates were processed to refresh UI
if updates_processed:
    st.rerun()

# Sidebar for navigation
st.sidebar.title("CFO Agent")
st.sidebar.image("https://img.icons8.com/color/96/000000/financial-growth.png", width=100)

# Navigation options
nav_options = [
    "Dashboard", 
    "Financial Reports", 
    "Cash Flow", 
    "Tax Planning", 
    "Chat with CFO",
    "Invoice Automation"
]

st.sidebar.markdown("## Navigation")
selected_view = st.sidebar.radio("Go to", nav_options)

# Update current view in session state
st.session_state.current_view = selected_view

# Data loading section
st.sidebar.markdown("## Data")
if st.sidebar.button("Refresh Financial Data"):
    with st.spinner("Refreshing financial data..."):
        try:
            refresh_result = accounting_engine.refresh_data()
            st.session_state.data_loaded = True
            st.session_state.financial_data = refresh_result
            st.sidebar.success(f"Data refreshed successfully: {refresh_result['accounts']} accounts, {refresh_result['transactions']} transactions")
            
            # Clear previous financial metrics
            if "kpis" in st.session_state:
                del st.session_state.kpis
                
        except Exception as e:
            st.sidebar.error(f"Error refreshing data: {str(e)}")
            cfo_logger.error(f"Error refreshing data via UI: {str(e)}")

# Display data status
if st.session_state.data_loaded:
    st.sidebar.markdown(f"**Last update:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    accounts = st.session_state.financial_data.get("accounts", 0)
    transactions = st.session_state.financial_data.get("transactions", 0)
    st.sidebar.markdown(f"**Accounts:** {accounts}")
    st.sidebar.markdown(f"**Transactions:** {transactions}")
else:
    st.sidebar.warning("No financial data loaded. Click 'Refresh Financial Data' to load.")

# Email monitoring status and control
st.sidebar.markdown("## Email Monitoring")
email_status = "Active" if st.session_state.email_monitoring_active else "Inactive"
st.sidebar.markdown(f"**Status:** {email_status}")

if st.session_state.email_monitoring_active:
    if st.sidebar.button("Stop Email Monitoring"):
        if email_monitor:
            email_monitor.stop_monitoring()
            st.session_state.email_monitoring_active = False
            st.sidebar.success("Email monitoring stopped")
            st.rerun()
        else:
            st.sidebar.warning("Monitor component not initialized.")
else:
    if st.sidebar.button("Start Email Monitoring"):
        if email_monitor and qb_api and approval_workflow: # Ensure all needed components are ready
            if email_monitor.validate_connection():
                # Start monitoring in a background thread with the LLM callback
                email_monitor.start_monitoring(handle_llm_email_processing)
                st.session_state.email_monitoring_active = True
                st.sidebar.success("Email monitoring started")
                st.rerun()
            else:
                st.sidebar.error("Failed to connect to email server. Check configuration.")
        else:
            st.sidebar.error("Cannot start monitor: Core components (EmailMonitor, QB API, ApprovalWorkflow) not initialized.")

# Main content area based on navigation
if st.session_state.current_view == "Dashboard":
    # Dashboard view
    st.title("Financial Dashboard")
    
    # Get financial KPIs if not already loaded
    if "kpis" not in st.session_state and st.session_state.data_loaded:
        with st.spinner("Loading financial metrics..."):
            try:
                st.session_state.kpis = accounting_engine.get_financial_kpis()
            except Exception as e:
                st.error(f"Error loading financial metrics: {str(e)}")
                cfo_logger.error(f"Error loading KPIs for dashboard: {str(e)}")
    
    # Display KPIs in a grid
    if st.session_state.data_loaded and "kpis" in st.session_state:
        kpis = st.session_state.kpis
        
        # Create 3x2 grid for KPIs
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Cash on Hand", 
                f"${kpis.get('cash_on_hand', 0):,.2f}", 
                delta=None
            )
            
            st.metric(
                "Accounts Receivable", 
                f"${kpis.get('accounts_receivable', 0):,.2f}", 
                delta=None
            )
            
        with col2:
            st.metric(
                "Revenue (30 days)", 
                f"${kpis.get('revenue_30d', 0):,.2f}", 
                delta=None
            )
            
            st.metric(
                "Expenses (30 days)", 
                f"${kpis.get('expenses_30d', 0):,.2f}", 
                delta=None
            )
            
        with col3:
            st.metric(
                "Net Income (30 days)", 
                f"${kpis.get('net_income_30d', 0):,.2f}",
                delta=None
            )
            
            if kpis.get('profit_margin_30d') is not None:
                st.metric(
                    "Profit Margin (30 days)", 
                    f"{kpis.get('profit_margin_30d', 0):.2f}%", 
                    delta=None
                )
            else:
                st.metric("Profit Margin (30 days)", "N/A", delta=None)
        
        # Cash Flow Forecast Chart
        st.subheader("Cash Flow Forecast")
        
        try:
            forecast = accounting_engine.forecast_cash_flow(months_ahead=6)
            if forecast:
                forecast_df = pd.DataFrame([
                    {
                        "Month": month["period"],
                        "Ending Cash": month["ending_cash"],
                        "Inflows": month["inflows"],
                        "Outflows": month["outflows"]
                    }
                    for month in forecast
                ])
                
                # Create the cash flow chart
                fig = go.Figure()
                
                fig.add_trace(go.Bar(
                    x=forecast_df["Month"],
                    y=forecast_df["Inflows"],
                    name="Inflows",
                    marker_color='rgba(50, 171, 96, 0.6)'
                ))
                
                fig.add_trace(go.Bar(
                    x=forecast_df["Month"],
                    y=forecast_df["Outflows"] * -1,  # Make outflows negative for the chart
                    name="Outflows",
                    marker_color='rgba(219, 64, 82, 0.6)'
                ))
                
                fig.add_trace(go.Scatter(
                    x=forecast_df["Month"],
                    y=forecast_df["Ending Cash"],
                    name="Ending Cash",
                    mode="lines+markers",
                    line=dict(color='rgba(0, 0, 255, 0.8)', width=2)
                ))
                
                fig.update_layout(
                    title="6-Month Cash Flow Forecast",
                    barmode='relative',
                    height=400,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    margin=dict(l=20, r=20, t=40, b=20),
                    hovermode="x unified"
                )
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Insufficient data for cash flow forecast.")
                
        except Exception as e:
            st.error(f"Error generating cash flow forecast: {str(e)}")
            cfo_logger.error(f"Error generating forecast for dashboard: {str(e)}")
            
        # Revenue vs Expenses Chart
        st.subheader("Revenue vs Expenses (Last 30 Days)")
        
        try:
            # Convert to data for chart
            categories = ["Revenue", "Expenses", "Net Income"]
            values = [
                kpis.get("revenue_30d", 0),
                kpis.get("expenses_30d", 0),
                kpis.get("net_income_30d", 0)
            ]
            
            colors = ['rgba(50, 171, 96, 0.6)', 'rgba(219, 64, 82, 0.6)', 'rgba(50, 50, 171, 0.6)']
            
            # Create the bar chart
            fig = go.Figure([
                go.Bar(x=categories, y=values, marker_color=colors)
            ])
            
            fig.update_layout(
                height=400,
                margin=dict(l=20, r=20, t=20, b=20),
                hovermode="x unified"
            )
            
            st.plotly_chart(fig, use_container_width=True)
                
        except Exception as e:
            st.error(f"Error generating revenue vs expenses chart: {str(e)}")
            cfo_logger.error(f"Error generating rev/exp chart for dashboard: {str(e)}")
            
    else:
        st.info("Please load financial data using the 'Refresh Financial Data' button in the sidebar.")

elif st.session_state.current_view == "Financial Reports":
    st.title("Financial Reports")
    
    # Financial report options
    report_type = st.selectbox(
        "Select Report Type",
        ["Profit and Loss", "Balance Sheet", "Cash Flow Statement"]
    )
    
    # Date range selection
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "Start Date",
            datetime.now() - timedelta(days=90)
        )
    with col2:
        end_date = st.date_input(
            "End Date",
            datetime.now()
        )
    
    # Generate report button
    if st.button("Generate Report"):
        if not st.session_state.data_loaded:
            st.warning("Please load financial data first.")
        else:
            with st.spinner(f"Generating {report_type} report..."):
                try:
                    if report_type == "Profit and Loss":
                        report = accounting_engine.get_profit_and_loss(
                            start_date.strftime("%Y-%m-%d"),
                            end_date.strftime("%Y-%m-%d")
                        )
                    elif report_type == "Balance Sheet":
                        report = accounting_engine.get_balance_sheet(
                            end_date.strftime("%Y-%m-%d")
                        )
                    else:  # Cash Flow Statement
                        report = accounting_engine.get_cash_flow(
                            start_date.strftime("%Y-%m-%d"),
                            end_date.strftime("%Y-%m-%d")
                        )
                    
                    # Display report metadata
                    metadata = report.get("metadata", {})
                    st.subheader(metadata.get("report_name", report_type))
                    st.write(f"Period: {metadata.get('time_period', '')}")
                    st.write(f"Generated: {metadata.get('generated_at', '')}")
                    
                    # Display report data
                    df = report.get("data")
                    if df is not None:
                        # Style the dataframe based on level
                        def style_df(row):
                            level = row["level"]
                            font_weight = "normal"
                            background_color = "white"
                            
                            if level == 0:
                                font_weight = "bold"
                                background_color = "#f0f0f0"
                            elif level == 1:
                                font_weight = "bold"
                                
                            return [
                                f"font-weight: {font_weight}; background-color: {background_color}" 
                                for _ in range(len(row))
                            ]
                        
                        # Apply styling and display
                        styled_df = df.style.apply(style_df, axis=1)
                        st.dataframe(styled_df, use_container_width=True)
                        
                        # Download link
                        csv = df.to_csv(index=False)
                        st.download_button(
                            label="Download Report as CSV",
                            data=csv,
                            file_name=f"{report_type.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.error("No data available for the selected report type and date range.")
                        
                except Exception as e:
                    st.error(f"Error generating report: {str(e)}")
                    cfo_logger.error(f"Error generating {report_type} report in UI: {str(e)}")

elif st.session_state.current_view == "Cash Flow":
    st.title("Cash Flow Management")
    
    # Tabs for cash flow management features
    tab1, tab2, tab3 = st.tabs(["Cash Flow Forecast", "Accounts Receivable", "Accounts Payable"])
    
    with tab1:
        st.header("Cash Flow Forecast")
        
        # Forecast parameters
        months = st.slider("Forecast Months", 1, 12, 6)
        
        if st.button("Generate Forecast"):
            if not st.session_state.data_loaded:
                st.warning("Please load financial data first.")
            else:
                with st.spinner("Generating cash flow forecast..."):
                    try:
                        forecast = accounting_engine.forecast_cash_flow(months_ahead=months)
                        
                        if forecast:
                            # Display forecast as table
                            forecast_df = pd.DataFrame([
                                {
                                    "Month": month["period"],
                                    "Ending Cash": month["ending_cash"],
                                    "Inflows": month["inflows"],
                                    "Outflows": month["outflows"]
                                }
                                for month in forecast
                            ])
                            
                            # Create the cash flow chart
                            fig = go.Figure()
                            
                            fig.add_trace(go.Bar(
                                x=forecast_df["Month"],
                                y=forecast_df["Inflows"],
                                name="Inflows",
                                marker_color='rgba(50, 171, 96, 0.6)'
                            ))
                            
                            fig.add_trace(go.Bar(
                                x=forecast_df["Month"],
                                y=forecast_df["Outflows"] * -1,  # Make outflows negative for the chart
                                name="Outflows",
                                marker_color='rgba(219, 64, 82, 0.6)'
                            ))
                            
                            fig.add_trace(go.Scatter(
                                x=forecast_df["Month"],
                                y=forecast_df["Ending Cash"],
                                name="Ending Cash",
                                mode="lines+markers",
                                line=dict(color='rgba(0, 0, 255, 0.8)', width=2)
                            ))
                            
                            fig.update_layout(
                                title="6-Month Cash Flow Forecast",
                                barmode='relative',
                                height=400,
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                                margin=dict(l=20, r=20, t=40, b=20),
                                hovermode="x unified"
                            )
                            
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info("Insufficient data for cash flow forecast.")
                            
                    except Exception as e:
                        st.error(f"Error generating cash flow forecast: {str(e)}")
                        cfo_logger.error(f"Error generating forecast for cash flow management: {str(e)}")

    with tab2:
        st.header("Accounts Receivable")
        # Implementation for Accounts Receivable tab

    with tab3:
        st.header("Accounts Payable")
        # Implementation for Accounts Payable tab

elif st.session_state.current_view == "Tax Planning":
    st.title("Tax Planning & Preparation")
    
    # Tabs for tax planning features
    tab1, tab2, tab3 = st.tabs(["Estimated Taxes", "Tax Deductions", "Tax Filing Checklist"])
    
    with tab1:
        st.header("Estimated Tax Payments")
        
        tax_year = st.selectbox(
            "Select Tax Year",
            [datetime.now().year, datetime.now().year - 1],
            index=0
        )
        
        if st.button("Calculate Estimated Taxes"):
            if not st.session_state.data_loaded:
                st.warning("Please load financial data first.")
            else:
                with st.spinner("Calculating estimated taxes..."):
                    try:
                        tax_estimate = tax_module.calculate_estimated_taxes(tax_year)
                        
                        if tax_estimate:
                            # Display tax estimate summary
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.metric("Net Income (to date)", f"${tax_estimate.get('net_income_to_date', 0):,.2f}")
                                st.metric("Annualized Income", f"${tax_estimate.get('annualized_income', 0):,.2f}")
                                st.metric("Total Tax Estimate", f"${tax_estimate.get('total_tax_estimate', 0):,.2f}")
                                
                            with col2:
                                st.metric("Federal Tax", f"${tax_estimate.get('federal_tax_estimate', 0):,.2f}")
                                st.metric("State Tax", f"${tax_estimate.get('state_tax_estimate', 0):,.2f}")
                                st.metric("Quarterly Payment", f"${tax_estimate.get('quarterly_payment', 0):,.2f}")
                            
                            # Display payment schedule
                            st.subheader("Estimated Tax Payment Schedule")
                            schedule = tax_estimate.get("payment_schedule", [])
                            if schedule:
                                schedule_df = pd.DataFrame(schedule)
                                
                                # Style by status
                                def color_status(val):
                                    color = "black"
                                    if val == "Past Due":
                                        color = "red"
                                    return f'color: {color}'
                                
                                styled_schedule = schedule_df.style.applymap(
                                    color_status, 
                                    subset=["status"]
                                )
                                
                                st.dataframe(styled_schedule, use_container_width=True)
                            else:
                                st.info("No payment schedule available.")
                        else:
                            st.warning("Unable to calculate tax estimate with available data.")
                            
                    except Exception as e:
                        st.error(f"Error calculating estimated taxes: {str(e)}")
                        cfo_logger.error(f"Error calculating estimated taxes in UI: {str(e)}")
    
    with tab2:
        st.header("Tax Deductions Analysis")
        
        deduction_year = st.selectbox(
            "Select Year for Deduction Analysis",
            [datetime.now().year, datetime.now().year - 1],
            index=0
        )
        
        if st.button("Analyze Potential Deductions"):
            if not st.session_state.data_loaded:
                st.warning("Please load financial data first.")
            else:
                with st.spinner("Analyzing potential tax deductions..."):
                    try:
                        deduction_report = tax_module.generate_tax_deduction_report(deduction_year)
                        
                        if deduction_report:
                            # Summary metrics
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.metric("Total Expenses", f"${deduction_report.get('total_expenses', 0):,.2f}")
                                
                            with col2:
                                st.metric("Total Deductible Amount", f"${deduction_report.get('total_deductible_amount', 0):,.2f}")
                            
                            # Display deduction details
                            st.subheader("Deduction Details")
                            deductions = deduction_report.get("deduction_summary", [])
                            if deductions:
                                deduction_df = pd.DataFrame(deductions)
                                
                                # Create deduction visualization
                                fig = px.bar(
                                    deduction_df.sort_values("deductible_amount", ascending=False).head(10),
                                    x="expense_name",
                                    y="deductible_amount",
                                    title="Top 10 Potential Deductions",
                                    labels={"expense_name": "Expense Category", "deductible_amount": "Deductible Amount ($)"}
                                )
                                
                                fig.update_layout(height=400)
                                st.plotly_chart(fig, use_container_width=True)
                                
                                # Display deduction table
                                st.dataframe(deduction_df, use_container_width=True)
                                
                                # Download link
                                csv = deduction_df.to_csv(index=False)
                                st.download_button(
                                    label="Download Deduction Analysis as CSV",
                                    data=csv,
                                    file_name=f"Tax_Deductions_{deduction_year}_{datetime.now().strftime('%Y%m%d')}.csv",
                                    mime="text/csv"
                                )
                                
                                # Notes
                                st.info(deduction_report.get("notes", ""))
                            else:
                                st.info("No deduction data available for analysis.")
                        else:
                            st.warning("Unable to generate deduction report with available data.")
                            
                    except Exception as e:
                        st.error(f"Error analyzing tax deductions: {str(e)}")
                        cfo_logger.error(f"Error analyzing tax deductions in UI: {str(e)}")
    
    with tab3:
        st.header("Tax Filing Checklist")
        
        if st.button("Generate Tax Filing Checklist"):
            with st.spinner("Generating tax filing checklist..."):
                try:
                    checklist = tax_module.prepare_tax_filing_checklist()
                    
                    if checklist:
                        # Display filing information
                        filing_info = checklist.get("filing_information", {})
                        
                        st.subheader(f"Tax Filing Information for {checklist.get('tax_filing_year')}")
                        st.write(f"**Company:** {checklist.get('company_name')}")
                        st.write(f"**Entity Type:** {checklist.get('company_type')}")
                        st.write(f"**Form:** {filing_info.get('form')}")
                        st.write(f"**Filing Deadline:** {filing_info.get('deadline')}")
                        st.write(f"**Extension Form:** {filing_info.get('extension_form')}")
                        st.write(f"**Extended Deadline:** {filing_info.get('extension_deadline')}")
                        
                        # Display checklist by category
                        st.subheader("Tax Filing Checklist")
                        
                        checklist_items = checklist.get("checklist", [])
                        for category in checklist_items:
                            with st.expander(category.get("category", ""), expanded=True):
                                for item in category.get("items", []):
                                    st.checkbox(item.get("name", ""), value=item.get("status") == "Completed")
                        
                        # Notes
                        st.info(checklist.get("notes", ""))
                    else:
                        st.warning("Unable to generate tax filing checklist.")
                        
                except Exception as e:
                    st.error(f"Error generating tax filing checklist: {str(e)}")
                    cfo_logger.error(f"Error generating tax filing checklist in UI: {str(e)}")

elif st.session_state.current_view == "Chat with CFO":
    st.title("Chat with Your CFO")
    
    # Initialize chat history if needed
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    
    # Display chat messages
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    
    # Chat input
    user_input = st.chat_input("Ask your CFO a question...")
    
    if user_input:
        # Add user message to chat history
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        
        # Display user message
        with st.chat_message("user"):
            st.write(user_input)
        
        # Generate and display assistant response
        with st.chat_message("assistant"):
            with st.spinner("Your CFO is thinking..."):
                try:
                    # Refresh data if needed (for first query or if data not loaded)
                    refresh_data = not st.session_state.data_loaded
                    
                    # Get assistant response
                    response = chat_interface.generate_response(user_input, refresh_data=refresh_data)
                    
                    # Display assistant response
                    st.write(response)
                    
                    # Add assistant response to chat history
                    st.session_state.chat_history.append({"role": "assistant", "content": response})
                    
                except Exception as e:
                    error_message = f"Sorry, I encountered an error: {str(e)}"
                    st.error(error_message)
                    cfo_logger.error(f"Error in chat interface: {str(e)}")
                    
                    # Add error message to chat history
                    st.session_state.chat_history.append({"role": "assistant", "content": error_message})
    
    # Clear chat button
    if st.button("Clear Chat History"):
        st.session_state.chat_history = []
        chat_interface.clear_conversation_history()
        st.rerun()

elif st.session_state.current_view == "Invoice Automation":
    st.title("Invoice Automation")
    
    # Tabs for invoice automation features
    tab1, tab2, tab3, tab4 = st.tabs(["Processed Emails", "Pending Invoices", "Incomplete Requests", "Test Invoice Creation"])
    
    with tab1:
        st.header("Processed Email Requests")
        
        # Display processed emails
        if st.session_state.processed_emails:
            email_df = pd.DataFrame(st.session_state.processed_emails)
            st.dataframe(email_df, use_container_width=True)
        else:
            st.info("No email requests have been processed yet.")
    
    with tab2:
        st.header("Pending Invoices")
        
        # Display pending invoices
        if st.session_state.pending_invoices:
            invoice_data = []
            for invoice in st.session_state.pending_invoices:
                invoice_data.append({
                    'Invoice #': invoice.get('doc_number', 'Draft'),
                    'Customer': invoice.get('customer_name', 'Unknown'),
                    'Amount': f"${invoice.get('total_amount', 0):,.2f}",
                    'Date': invoice.get('invoice_date', 'Unknown'),
                    'Status': 'Pending Approval'
                })
            
            invoice_df = pd.DataFrame(invoice_data)
            st.dataframe(invoice_df, use_container_width=True)
        else:
            st.info("No pending invoices to display.")
    
    with tab3:
        st.header("Incomplete Requests")
        
        # Display incomplete invoice requests
        if st.session_state.incomplete_requests:
            # Create a cleaner display dataframe
            incomplete_data = []
            for req in st.session_state.incomplete_requests:
                incomplete_data.append({
                    'Request ID': req.get('request_id', 'Unknown'),
                    'Customer': req.get('customer_name', 'Unknown'),
                    'Missing Fields': ', '.join(req.get('missing_fields', [])),
                    'Date': req.get('created_at', 'Unknown')[:10] if isinstance(req.get('created_at'), str) else 'Unknown',
                    'Subject': req.get('email_subject', 'No Subject')
                })
            
            # Display the dataframe
            incomplete_df = pd.DataFrame(incomplete_data)
            st.dataframe(incomplete_df, use_container_width=True)
            
            # Form to complete a request
            st.subheader("Complete Pending Request")
            
            # Select request to complete
            request_ids = [req.get('request_id') for req in st.session_state.incomplete_requests]
            selected_request_id = st.selectbox("Select Request ID", request_ids)
            
            # Find the selected request
            selected_request = next((req for req in st.session_state.incomplete_requests 
                                     if req.get('request_id') == selected_request_id), None)
            
            if selected_request:
                # Show current info and missing fields
                missing_fields = selected_request.get('missing_fields', [])
                st.write(f"Request from: {selected_request.get('email_from', 'Unknown')}")
                st.write(f"Subject: {selected_request.get('email_subject', 'No Subject')}")
                
                with st.form("complete_request_form"):
                    # Collect missing information
                    additional_data = {}
                    
                    if "customer_name" in missing_fields:
                        customer_name = st.text_input("Customer Name", selected_request.get('customer_name', ''))
                        if customer_name:
                            additional_data["customer_name"] = customer_name
                    
                    if "materials_description" in missing_fields:
                        materials = st.text_area("Materials/Services Description", 
                                               selected_request.get('materials_description', ''))
                        if materials:
                            additional_data["materials_description"] = materials
                    
                    if "amount" in missing_fields:
                        amount = st.number_input("Amount", 
                                               min_value=0.01, value=0.01, step=0.01)
                        if amount > 0:
                            additional_data["amount"] = amount
                    
                    # Optional invoice number
                    invoice_number = st.text_input("Invoice/PO Number (Optional)", 
                                                 selected_request.get('invoice_number', ''))
                    if invoice_number:
                        additional_data["invoice_number"] = invoice_number
                    
                    submit = st.form_submit_button("Complete Request")
                    
                    if submit:
                        if not additional_data:
                            st.error("Please provide at least one missing field.")
                        else:
                            try:
                                with st.spinner("Creating invoice..."):
                                    # Call the invoice creator to complete the pending request
                                    result = invoice_creator.complete_pending_request(
                                        selected_request_id, additional_data)
                                    
                                    if result:
                                        st.success("Request completed successfully!")
                                        # Remove from incomplete requests
                                        st.session_state.incomplete_requests = [
                                            req for req in st.session_state.incomplete_requests 
                                            if req.get('request_id') != selected_request_id
                                        ]
                                        # Add to pending invoices if it's a dict (complete invoice)
                                        if isinstance(result, dict):
                                            st.session_state.pending_invoices.append(result)
                                        
                                        # Send approval email
                                        if st.button("Send Approval Email"):
                                            if approval_workflow.send_approval_email(result):
                                                st.success("Approval email sent successfully")
                                            else:
                                                st.error("Failed to send approval email")
                                                
                                        st.rerun()  # Refresh the UI
                                    else:
                                        st.error("Failed to complete the request. The information may still be incomplete.")
                            except Exception as e:
                                st.error(f"Error completing request: {str(e)}")
                                cfo_logger.error(f"Error completing request {selected_request_id}: {str(e)}")
            else:
                st.warning("No request selected.")
        else:
            st.info("No incomplete requests to display.")
    
    with tab4:
        st.header("Test Invoice Creation")
        st.write("Use this form to test the invoice creation process without sending an email.")
        
        # Test form for invoice creation (manual data entry)
        with st.form("invoice_test_form"):
            customer_name = st.text_input("Customer Name", "Angie Hutchins")
            materials = st.text_area("Materials Description", "Virginia Highlands carpet tile for all offices on second floor of ROB")
            amount = st.number_input("Amount", min_value=0.01, value=12915.00, step=0.01)
            
            submitted = st.form_submit_button("Create Test Invoice via Form")
            
            if submitted:
                try:
                    # Create test invoice request
                    invoice_request = InvoiceRequest(
                        customer_name=customer_name,
                        materials_description=materials,
                        amount=amount,
                        raw_email={"subject": "Test Invoice", "body": materials, "from_email": "test@example.com"}
                    )
                    
                    # Create draft invoice
                    with st.spinner("Creating draft invoice..."):
                        invoice_data = invoice_creator.create_draft_invoice(invoice_request)
                        
                        if invoice_data:
                            st.success(f"Draft invoice created successfully: {invoice_data.get('doc_number')}")
                            
                            # Add to pending invoices
                            st.session_state.pending_invoices.append(invoice_data)
                            
                            # Send approval email
                            if st.button("Send Approval Email"):
                                with st.spinner("Sending approval email..."):
                                    if approval_workflow.send_approval_email(invoice_data):
                                        st.success("Approval email sent successfully")
                                    else:
                                        st.error("Failed to send approval email")
                        else:
                            st.error("Failed to create draft invoice")
                            
                except Exception as e:
                    st.error(f"Error creating test invoice: {str(e)}")
                    cfo_logger.error(f"Error in test invoice creation: {str(e)}")

        st.markdown("---") # Separator
        st.subheader("Simulate Email Request")
        st.write(f"Simulate an email sent from an authorized sender to the monitored inbox.")

        # Add example templates for simulation
        example_templates = {
            "Complete Request": "Please create an invoice for Customer XYZ for consulting services. Amount: $500. Description: Consulting services for Q2 2025.",
            "Missing Amount": "Please create an invoice for Angie Hutchins. We finished the work at 638 Rhode Island Ave. The carpet tiles look great!",
            "Invoice with PO Number": "Create a new invoice for existing customer Angie Hutchins, invoice/PO number \"SPSA-ROB-CARPET\" for: materials: Virginia Highlands Carpet Tiles, 24x24 in, 66 cases. total amount is $12,915.",
            "Minimal Request": "Generate invoice for 638 Rhode"
        }
        
        template_choice = st.radio("Choose example template or create your own:", 
                                  list(example_templates.keys()) + ["Custom"])
        
        with st.form("simulate_email_form"):
            if template_choice == "Custom":
                sim_subject = st.text_input("Simulated Email Subject", "Invoice Request")
                sim_body = st.text_area("Simulated Email Body", "")
            else:
                if template_choice == "Complete Request":
                    sim_subject = "Invoice Request - Consulting Services"
                elif template_choice == "Missing Amount":
                    sim_subject = "Invoice for 638 Rhode Island"
                elif template_choice == "Invoice with PO Number":
                    sim_subject = "new invoice \"SPSA-ROB-CARPET\""
                else:
                    sim_subject = "Invoice Request - 638 Rhode"
                
                sim_body = example_templates[template_choice]
                st.text_input("Simulated Email Subject", sim_subject, disabled=True)
                st.text_area("Simulated Email Body", sim_body, disabled=True)
            
            sim_submitted = st.form_submit_button("Simulate Email")
            
            if sim_submitted:
                if email_monitor and qb_api and approval_workflow: # Check components again
                    # Ensure the email monitor has the correct callback assigned
                    # (It should have been set when starting, but double-check)
                    if not hasattr(email_monitor, 'callback') or email_monitor.callback != handle_llm_email_processing:
                         email_monitor.callback = handle_llm_email_processing
                         cfo_logger.info("Assigned handle_llm_email_processing callback for simulation.")
                    
                    with st.spinner("Simulating email processing..."):
                        # Use the simulate_email method which should internally use the assigned callback
                        success = email_monitor.simulate_email(sim_subject, sim_body)
                        if success:
                            st.success("Email simulation triggered. Check logs and UI updates below.")
                            # Rerun might be needed if updates take time
                            st.rerun()
                        else:
                            st.error("Failed to simulate email processing. Check terminal logs.")
                else:
                    st.error("Cannot simulate: Core components (EmailMonitor, QB API, ApprovalWorkflow) not initialized.")

# Footer
st.markdown("---")
st.markdown("### CFO Agent © 2023 | Built with Streamlit")

# Start email monitor in background thread if not already running and configured
if not st.session_state.email_monitoring_active and getattr(config, 'auto_start_email_monitoring', False):
    if email_monitor and qb_api and approval_workflow: # Check components
        try:
            # Start monitoring with the LLM callback
            email_monitor.start_monitoring(handle_llm_email_processing)
            st.session_state.email_monitoring_active = True
            cfo_logger.info("Email monitoring auto-started on application launch with LLM callback.")
        except Exception as e:
            cfo_logger.error(f"Failed to auto-start email monitoring: {e}")
    else:
        cfo_logger.warning("Auto-start email monitoring skipped: Core components not initialized.")

# Handle approval links
if 'token' in st.query_params:
    token = st.query_params['token'][0]
    
    # Display approval interface
    st.title("Invoice Approval")
    
    # Log token information
    cfo_logger.info(f"Processing approval token from URL: {token[:20]}...")
    
    # Verify token and get invoice data
    invoice_data = approval_workflow.verify_approval_token(token)
    
    if invoice_data:
        # Log successful verification
        cfo_logger.info(f"Token verified successfully for invoice {invoice_data.get('doc_number', 'Draft')}")
        
        # Display invoice details
        st.subheader("Invoice Details")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Invoice #:** {invoice_data.get('doc_number', 'Draft')}")
            st.write(f"**Customer:** {invoice_data.get('customer_name', 'Unknown')}")
        with col2:
            st.write(f"**Amount:** ${invoice_data.get('total_amount', 0):,.2f}")
            st.write(f"**Date:** {invoice_data.get('invoice_date', 'Unknown')}")
        
        # Display line items
        st.subheader("Line Items")
        items_data = []
        for item in invoice_data.get('line_items', []):
            items_data.append({
                'Description': item.get('description', ''),
                'Amount': f"${item.get('amount', 0):,.2f}"
            })
        
        if items_data:
            items_df = pd.DataFrame(items_data)
            st.dataframe(items_df, use_container_width=True)
        
        # Approval buttons
        if st.button("Approve Invoice", key="approve_button"):
            try:
                # Finalize invoice
                invoice_id = invoice_data.get('invoice_id')
                
                with st.spinner("Finalizing invoice..."):
                    # Call QuickBooks API to finalize the invoice
                    result = qb_api.approve_invoice(invoice_id)
                    
                    if result:
                        st.success(f"Invoice {invoice_data.get('doc_number')} approved and finalized!")
                        
                        # Remove from pending invoices if present
                        st.session_state.pending_invoices = [
                            inv for inv in st.session_state.pending_invoices 
                            if inv.get('invoice_id') != invoice_id
                        ]
                        
                        cfo_logger.info(f"Invoice {invoice_id} approved via web interface")
                    else:
                        st.error("Failed to approve invoice. Please try again or contact support.")
                        cfo_logger.error(f"Failed to approve invoice {invoice_id} via web interface")
                    
            except Exception as e:
                st.error(f"Error approving invoice: {str(e)}")
                cfo_logger.error(f"Error approving invoice via web interface: {str(e)}")
        
        if st.button("Reject Invoice", key="reject_button"):
            try:
                # Delete the draft invoice
                invoice_id = invoice_data.get('invoice_id')
                
                with st.spinner("Rejecting invoice..."):
                    # Call QuickBooks API to delete the draft invoice
                    result = qb_api.delete_invoice(invoice_id)
                    
                    if result:
                        st.success(f"Invoice {invoice_data.get('doc_number')} rejected and deleted.")
                        
                        # Remove from pending invoices if present
                        st.session_state.pending_invoices = [
                            inv for inv in st.session_state.pending_invoices 
                            if inv.get('invoice_id') != invoice_id
                        ]
                        
                        cfo_logger.info(f"Invoice {invoice_id} rejected via web interface")
                    else:
                        st.error("Failed to reject invoice. Please try again or contact support.")
                        cfo_logger.error(f"Failed to reject invoice {invoice_id} via web interface")
                    
            except Exception as e:
                st.error(f"Error rejecting invoice: {str(e)}")
                cfo_logger.error(f"Error rejecting invoice via web interface: {str(e)}")
    else:
        # Log token verification failure
        cfo_logger.error("Token verification failed - invalid or expired approval token")
        st.error("Invalid or expired approval token") 