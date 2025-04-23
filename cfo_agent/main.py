import os
import json
import logging
from flask import Flask, request, jsonify
from typing import Dict, Any, Optional

# Local imports from existing codebase
from accounting_engine import AccountingEngine
from tax_module import TaxModule
from chat_interface_cfo import CFOChatInterface
from config import config
from logger import cfo_logger
from email_monitor import EmailMonitor
from approval_workflow import ApprovalWorkflow
from quickbooks_api import QuickBooksAPI
from llm_interface import simulate_llm_response, get_available_tools_definition

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cfo-agent")

# Initialize the application components
try:
    qb_api = QuickBooksAPI()
    accounting_engine = AccountingEngine(api_instance=qb_api)
    tax_module = TaxModule(accounting_engine)
    chat_interface = CFOChatInterface(accounting_engine, tax_module)
    email_monitor = EmailMonitor(config)
    approval_workflow = ApprovalWorkflow(config)
    
    # Set the email_monitor in the approval_workflow directly
    approval_workflow.set_email_monitor(email_monitor)
    
    logger.info("Application components initialized successfully")
except Exception as e:
    logger.error(f"Error initializing application components: {str(e)}")
    # Set components to None to prevent errors later
    qb_api = None
    accounting_engine = None
    tax_module = None
    chat_interface = None
    approval_workflow = None
    email_monitor = None

# Tool definitions 
TOOL_DEFINITIONS = get_available_tools_definition()

@app.route('/trigger', methods=['POST'])
def trigger():
    """
    Main trigger endpoint for CFO Agent that can be called by Cloud Scheduler, Pub/Sub, or directly.
    
    Accepts:
    - Email triggers for invoice/payment processing
    - Scheduled audit/reporting tasks
    - Manual actions requested via API

    Returns:
        JSON response with status and details
    """
    try:
        # Get the request data as JSON or form data
        if request.is_json:
            data = request.get_json()
        else:
            # Handle form data or other content types
            data = request.form.to_dict()
            
            # If no form data, try to parse the raw body
            if not data and request.data:
                try:
                    data = json.loads(request.data)
                except json.JSONDecodeError:
                    data = {'raw_content': request.data.decode('utf-8', errors='replace')}
        
        logger.info(f"Received trigger request: {data}")
        
        # Determine the type of trigger
        trigger_type = data.get('trigger_type', 'manual')
        
        # Process based on trigger type
        if trigger_type == 'email':
            result = process_email_trigger(data)
        elif trigger_type == 'scheduled_task':
            result = process_scheduled_task(data)
        elif trigger_type == 'manual_action':
            result = process_manual_action(data)
        else:
            # Default processing
            result = process_default_trigger(data)
        
        return jsonify({
            'status': 'success',
            'trigger_type': trigger_type,
            'result': result
        }), 200
        
    except Exception as e:
        logger.error(f"Error processing trigger: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

def process_email_trigger(data: Dict[str, Any]) -> Dict[str, Any]:
    """Process an email-based trigger."""
    if not email_monitor or not approval_workflow:
        raise ValueError("Email processing components not initialized")
    
    # Extract email data
    email_data = data.get('email_data', {})
    message_id = email_data.get('message_id', 'N/A')
    sender = email_data.get('sender', email_data.get('from', 'Unknown Sender'))
    subject = email_data.get('subject', 'No Subject')
    body = email_data.get('body', '')
    
    logger.info(f"Processing email trigger: ID={message_id}, From='{sender}', Subject='{subject}'")
    
    # Process with simulated LLM
    tool_name, tool_args, direct_response = simulate_llm_response(body, TOOL_DEFINITIONS)
    
    if direct_response:
        logger.info(f"LLM provided direct response for email {message_id}: {direct_response}")
        return {
            'email_id': message_id,
            'action': 'direct_response',
            'response': direct_response
        }
    elif tool_name:
        logger.info(f"LLM requested tool: {tool_name} with args: {tool_args}")
        # Here we would execute the tool, but for now just log it
        return {
            'email_id': message_id,
            'action': 'tool_execution',
            'tool': tool_name,
            'args': tool_args
        }
    else:
        return {
            'email_id': message_id,
            'action': 'no_action',
            'status': 'No action determined from email content'
        }

def process_scheduled_task(data: Dict[str, Any]) -> Dict[str, Any]:
    """Process a scheduled task trigger."""
    task_type = data.get('task_type')
    
    if task_type == 'daily_report':
        # Generate daily financial report
        if accounting_engine:
            # Example: generate P&L report
            report = accounting_engine.get_profit_and_loss(
                data.get('start_date'),
                data.get('end_date')
            )
            return {'task': 'daily_report', 'status': 'completed', 'report_data': 'Report generated'}
        else:
            raise ValueError("Accounting engine not initialized")
            
    elif task_type == 'tax_estimate':
        # Generate tax estimates
        if tax_module:
            tax_year = data.get('tax_year', 2025)
            tax_estimate = tax_module.calculate_estimated_taxes(tax_year)
            return {'task': 'tax_estimate', 'status': 'completed', 'tax_year': tax_year}
        else:
            raise ValueError("Tax module not initialized")
            
    else:
        return {'task': task_type, 'status': 'unknown_task_type'}

def process_manual_action(data: Dict[str, Any]) -> Dict[str, Any]:
    """Process a manual action trigger."""
    action = data.get('action')
    
    if action == 'refresh_data':
        if accounting_engine:
            refresh_result = accounting_engine.refresh_data()
            return {'action': 'refresh_data', 'status': 'completed', 'result': refresh_result}
        else:
            raise ValueError("Accounting engine not initialized")
            
    elif action == 'create_invoice':
        if qb_api:
            # Example: create invoice with minimal data
            invoice_params = {
                'customer_id': data.get('customer_id'),
                'line_items': data.get('line_items'),
                'memo': data.get('memo', 'Invoice created via API'),
                'draft': True
            }
            # Filter out None values
            call_args = {k: v for k, v in invoice_params.items() if v is not None}
            created_invoice = qb_api.create_invoice(**call_args)
            
            if created_invoice:
                invoice_id = created_invoice.get('Id') or created_invoice.get('id')
                invoice_num = created_invoice.get('DocNumber') or 'N/A'
                return {
                    'action': 'create_invoice', 
                    'status': 'completed', 
                    'invoice_id': invoice_id,
                    'invoice_number': invoice_num
                }
            else:
                return {'action': 'create_invoice', 'status': 'failed', 'error': 'Invoice creation failed'}
        else:
            raise ValueError("QuickBooks API not initialized")
            
    else:
        return {'action': action, 'status': 'unknown_action'}

def process_default_trigger(data: Dict[str, Any]) -> Dict[str, Any]:
    """Process a generic trigger with no specific type."""
    # Just acknowledge receipt of the trigger
    return {
        'received_data': data,
        'status': 'acknowledged'
    }

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Cloud Run."""
    component_status = {
        'quickbooks_api': qb_api is not None,
        'accounting_engine': accounting_engine is not None,
        'tax_module': tax_module is not None,
        'email_monitor': email_monitor is not None,
        'approval_workflow': approval_workflow is not None
    }
    
    all_healthy = all(component_status.values())
    
    if all_healthy:
        return jsonify({
            'status': 'healthy',
            'components': component_status
        }), 200
    else:
        return jsonify({
            'status': 'degraded',
            'components': component_status
        }), 503

if __name__ == '__main__':
    # Use PORT environment variable provided by Cloud Run, or default to 8080
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False) 