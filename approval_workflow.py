import os
import smtplib
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt
from jose import exceptions as jose_exceptions
from logger import cfo_logger
from config import Config
from invoice_creator import DraftInvoice
import re

class ApprovalWorkflow:
    """
    Handles the workflow for invoice approvals including sending approval emails,
    generating secure approval links, and verifying approval tokens.
    """
    
    def __init__(self, config: Config):
        """
        Initialize approval workflow with configuration.
        
        Args:
            config: Application configuration object
        """
        self.config = config
        self.admin_email = "hello@757handy.com"
        self.smtp_server = config.EMAIL_SMTP_SERVER  # Keep for reference
        self.email_username = config.EMAIL_USERNAME
        self.sender_email = config.EMAIL_USERNAME
        self.secret_key = config.JWT_SECRET_KEY
        self.app_url = config.APP_URL
        self.token_expiry = 7  # Token expires after 7 days
        self.email_monitor = None  # Will be set directly by main.py
        cfo_logger.info("Approval workflow initialized")
        
    def set_email_monitor(self, email_monitor):
        """Set the email_monitor instance directly."""
        self.email_monitor = email_monitor
        cfo_logger.info("Email monitor set in approval workflow")
        
    def generate_approval_token(self, invoice: dict) -> str:
        """Generate a secure token for invoice approval."""
        try:
            # Log invoice data for debugging
            cfo_logger.info(f"Generating token for invoice: {invoice.get('doc_number', 'Draft')}")
            
            # Create a copy of the invoice data to ensure we don't have any non-serializable objects
            simplified_invoice = {
                'invoice_id': invoice.get('invoice_id', 'unknown'),
                'customer_name': invoice.get('customer_name', 'N/A'),
                'total_amount': float(invoice.get('total_amount', 0.0)),
                'doc_number': invoice.get('doc_number', 'Draft'),
                'invoice_date': invoice.get('invoice_date', datetime.now().strftime('%Y-%m-%d')),
                'line_items': []
            }
            
            # Add line items
            for item in invoice.get('line_items', []):
                simplified_invoice['line_items'].append({
                    'description': item.get('description', ''),
                    'amount': float(item.get('amount', 0.0))
                })
            
            # Create the payload
            payload = {
                'invoice_id': simplified_invoice['invoice_id'],
                'customer_name': simplified_invoice['customer_name'],
                'total_amount': simplified_invoice['total_amount'],
                'doc_number': simplified_invoice['doc_number'],
                'invoice_data': simplified_invoice,
                'exp': datetime.now(timezone.utc) + timedelta(days=self.token_expiry)
            }
            
            # Generate the token
            token = jwt.encode(payload, self.secret_key, algorithm='HS256')
            cfo_logger.info(f"Token generated for invoice {simplified_invoice['doc_number']}")
            
            return token
        except Exception as e:
            cfo_logger.error(f"Error generating approval token: {str(e)}")
            # Generate a simple token as fallback
            payload = {
                'invoice_id': invoice.get('invoice_id', 'unknown'),
                'error': 'Token generation error, using fallback',
                'exp': datetime.now(timezone.utc) + timedelta(days=1)
            }
            return jwt.encode(payload, self.secret_key, algorithm='HS256')

    def verify_approval_token(self, token: str) -> Optional[dict]:
        """Verify and decode an approval token."""
        try:
            cfo_logger.info(f"Verifying token: {token[:20]}...")
            
            # Decode the token
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"]
            )
            
            cfo_logger.info(f"Token payload keys: {','.join(payload.keys())}")
            
            # Check if the token has invoice data
            if 'invoice_data' not in payload:
                cfo_logger.warning(f"Invalid approval token - missing invoice_data. Found keys: {list(payload.keys())}")
                return None
            
            # Extract the invoice data
            invoice_data = payload['invoice_data']
            
            # Basic validation
            required_fields = ['invoice_id', 'customer_name', 'total_amount', 'doc_number']
            missing_fields = [field for field in required_fields if field not in invoice_data]
            
            if missing_fields:
                cfo_logger.warning(f"Invalid approval token - missing fields in invoice_data: {', '.join(missing_fields)}")
                return None
            
            cfo_logger.info(f"Approval token verified for invoice {invoice_data.get('doc_number', 'N/A')}")
            return invoice_data

        except jose_exceptions.ExpiredSignatureError:
             cfo_logger.warning("Approval token has expired (ExpiredSignatureError)")
             return None
        except jose_exceptions.JWTError as e:
            cfo_logger.error(f"Invalid approval token (JWTError): {str(e)}")
            return None
        except Exception as e:
            cfo_logger.error(f"Unexpected error verifying token: {str(e)}")
            return None

    def send_approval_email(self, invoice: dict) -> bool:
        """Send approval email to admin using Gmail API with OAuth2."""
        try:
            if not invoice:
                cfo_logger.error("No invoice data provided for approval email")
                return False
            
            # Check if email_monitor is available
            if not self.email_monitor:
                cfo_logger.error("Email monitor not available for sending approval emails")
                return False
                
            # Generate token for approval using our dedicated method
            token = self.generate_approval_token(invoice)
            approval_url = f"{self.app_url}?token={token}"
            
            # Create QuickBooks Online URL for direct invoice viewing
            qbo_url = invoice.get('qbo_url')  # First try to get it directly from the invoice data
            
            # If not available directly, try to get it from QuickBooks API
            if not qbo_url and 'invoice_id' in invoice and invoice['invoice_id'] not in ('unknown', 'unknown-id'):
                try:
                    # Get the QuickBooks API from the main application
                    if hasattr(self, 'qb_api'):
                        qb_api = self.qb_api
                    elif hasattr(self.email_monitor, 'qb_api'):
                        qb_api = self.email_monitor.qb_api
                    
                    if qb_api:
                        qbo_url = qb_api.get_invoice_preview_url(invoice['invoice_id'])
                        if qbo_url:
                            cfo_logger.info(f"Added QuickBooks Online URL for invoice {invoice['doc_number']}: {qbo_url}")
                except Exception as e:
                    cfo_logger.error(f"Error getting QuickBooks URL: {str(e)}")
            
            subject = f"Invoice Approval Request: {invoice.get('doc_number', 'Draft')}"
            customer_name = invoice.get('customer_name', 'N/A')
            total_amount = invoice.get('total_amount', 0.0)
            invoice_date = invoice.get('invoice_date', 'N/A')
            line_items_html = ''
            line_items_text = ''
            for item in invoice.get('line_items', []):
                desc = item.get('description', '')
                amt = item.get('amount', 0.0)
                line_items_html += f'<tr><td>{desc}</td><td>${amt:,.2f}</td></tr>'
                line_items_text += f'- {desc}: ${amt:,.2f}\n'

            # Add QuickBooks link section to the email
            qbo_link_html = ''
            qbo_link_text = ''
            if qbo_url:
                qbo_link_html = f'''
                <div class="qbo-link">
                    <p>You can view this invoice directly in QuickBooks Online:</p>
                    <a href="{qbo_url}" class="qbo-btn">View in QuickBooks</a>
                </div>
                '''
                qbo_link_text = f'\nView this invoice in QuickBooks Online: {qbo_url}\n'

            html_body = f"""
            <html>
            <head>
                <style>
                    {self._get_email_styles()}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>Invoice Approval Request</h2>
                    </div>
                    <p>A new draft invoice has been created and requires your approval.</p>
                    <div class="invoice-details">
                        <h3>Invoice Details:</h3>
                        <table>
                            <tr><th>Invoice Number</th><td>{invoice.get('doc_number', 'Draft')}</td></tr>
                            <tr><th>Customer</th><td>{customer_name}</td></tr>
                            <tr><th>Amount</th><td>${total_amount:,.2f}</td></tr>
                            <tr><th>Date</th><td>{invoice_date}</td></tr>
                        </table>
                        <h3>Line Items:</h3>
                        <table>
                            <tr><th>Description</th><th>Amount</th></tr>
                            {line_items_html}
                        </table>
                    </div>
                    {qbo_link_html}
                    <p>Please review the invoice details and click the link below to approve or reject:</p>
                    <a href="{approval_url}" class="btn">Review Invoice</a>
                    <p>Approval link expires in {self.token_expiry} days.</p>
                </div>
            </body>
            </html>
            """
            
            text_body = f"""
            Invoice Approval Request: {invoice.get('doc_number', 'Draft')}
            
            A new draft invoice has been created and requires your approval.
            
            Invoice Details:
            - Invoice Number: {invoice.get('doc_number', 'Draft')}
            - Customer: {customer_name}
            - Amount: ${total_amount:,.2f}
            - Date: {invoice_date}
            
            Line Items:
            {line_items_text}
            {qbo_link_text}
            To approve/reject this invoice, visit:
            {approval_url}
            
            This approval link will expire in {self.token_expiry} days.
            
            If you have any questions or need to make changes, please contact your accounting department.
            """
            
            # Create the email message
            message = MIMEMultipart('alternative')
            message['Subject'] = subject
            message['From'] = self.sender_email
            message['To'] = self.admin_email
            
            # Add text and HTML parts
            message.attach(MIMEText(text_body, 'plain'))
            message.attach(MIMEText(html_body, 'html'))
            
            # Access the Gmail API via the direct email_monitor reference
            gmail_auth = self.email_monitor.gmail_auth
            if not gmail_auth:
                cfo_logger.error("Gmail authentication not available")
                return False
            
            creds = gmail_auth.authenticate()
            service = gmail_auth.build_service(creds)
            
            if not service:
                cfo_logger.error("Failed to build Gmail API service")
                return False
                
            # Convert the message to the format required by Gmail API
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            # Create the API request body
            create_message = {
                'raw': encoded_message
            }
            
            # Send the message
            sent_message = service.users().messages().send(
                userId='me', 
                body=create_message
            ).execute()
            
            message_id = sent_message.get('id')
            cfo_logger.info(f"Approval email sent for invoice {invoice.get('doc_number', 'Draft')} with Gmail message ID: {message_id}")
            
            return True
            
        except Exception as e:
            cfo_logger.error(f"Error sending approval email via Gmail API: {str(e)}")
            return False

    def _get_email_styles(self):
        return """
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            .header { background-color: #f5f5f5; padding: 10px; border-bottom: 1px solid #ddd; }
            .invoice-details { margin: 20px 0; }
            .invoice-details table { width: 100%; border-collapse: collapse; }
            .invoice-details th, .invoice-details td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            .invoice-details th { background-color: #f5f5f5; }
            .btn { display: inline-block; padding: 10px 20px; background-color: #4CAF50; color: white; 
                   text-decoration: none; border-radius: 4px; margin-top: 20px; }
            .qbo-link { margin: 20px 0; padding: 15px; background-color: #f8f8f8; border: 1px solid #ddd; border-radius: 4px; }
            .qbo-btn { display: inline-block; padding: 10px 20px; background-color: #2C9DEB; color: white;
                       text-decoration: none; border-radius: 4px; margin-top: 10px; }
        """

    def process_email_approval(self, email_body: str) -> Optional[str]:
        """Process approval from email reply."""
        try:
            # Look for approval pattern
            pattern = r'Approve Invoice (\w+)'
            match = re.search(pattern, email_body)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            cfo_logger.error(f"Error processing email approval: {str(e)}")
            return None

    def send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        """Send an email using Gmail API.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            if not self.email_monitor or not self.email_monitor.gmail_auth:
                cfo_logger.error("Gmail authentication not available")
                return False
            
            # Create the email message
            message = MIMEMultipart('alternative')
            message['Subject'] = subject
            message['From'] = self.sender_email
            message['To'] = to_email
            
            # Add HTML content
            message.attach(MIMEText(html_content, 'html'))
            
            # Get Gmail service
            creds = self.email_monitor.gmail_auth.authenticate()
            service = self.email_monitor.gmail_auth.build_service(creds)
            
            if not service:
                cfo_logger.error("Failed to build Gmail API service")
                return False
            
            # Convert the message to the format required by Gmail API
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            # Create the API request body
            create_message = {
                'raw': encoded_message
            }
            
            # Send the message
            sent_message = service.users().messages().send(
                userId='me', 
                body=create_message
            ).execute()
            
            message_id = sent_message.get('id')
            cfo_logger.info(f"Email sent to {to_email} with Gmail message ID: {message_id}")
            
            return True
            
        except Exception as e:
            cfo_logger.error(f"Error sending email via Gmail API: {str(e)}")
            return False

    def request_clarification(self, to_email: str, original_subject: str, message: str) -> bool:
        """Send an email requesting clarification from the original sender.

        Args:
            to_email: The email address of the original sender.
            original_subject: The subject of the original email for context.
            message: The specific question or clarification needed.

        Returns:
            True if the email was sent successfully, False otherwise.
        """
        subject = f"Re: {original_subject} - More Information Needed"
        
        html_body = f"""<html>
        <body>
            <p>Hello,</p>
            <p>Regarding your email with the subject "{original_subject}", we need a bit more information to proceed:</p>
            <p><b>{message}</b></p>
            <p>Please reply to this email with the required details.</p>
            <p>Thank you,<br>CFO Agent</p>
        </body>
        </html>"""
        
        cfo_logger.info(f"Sending clarification request to {to_email}: {message}")
        return self.send_email(to_email, subject, html_body) 