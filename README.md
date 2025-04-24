# CFO/Accounting Agent - Invoice Automation

A comprehensive accounting automation system with automated invoice generation from email requests.

## Overview

This system extends a CFO/Accounting Agent to handle end-to-end invoice processing:

1. Monitors a designated email inbox for invoice requests from authorized senders
2. Parses the email content to extract customer name, materials, and amount
3. Creates a draft invoice in QuickBooks
4. Sends the invoice for approval via email
5. Provides an approval interface to finalize the invoice
6. Handles error cases gracefully with extensive logging

## Features

- **Email Monitoring**: Continuously checks for new emails from authorized senders
- **Natural Language Parsing**: Extracts invoice details from freeform email text
- **QuickBooks Integration**: Creates and manages invoices through the QuickBooks API
- **Secure Approval Workflow**: JWT-based secure approval links
- **Comprehensive UI**: Streamlit interface to monitor and manage the workflow
- **Robust Error Handling**: Graceful handling of all error scenarios
- **Extensive Logging**: Detailed UTF-8 logging of all activities

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/your-org/cfo-agent.git
   cd cfo-agent
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file with the following settings:
   ```
   # QuickBooks API settings
   QUICKBOOKS_CLIENT_ID=your_client_id
   QUICKBOOKS_CLIENT_SECRET=your_client_secret
   QUICKBOOKS_REFRESH_TOKEN=your_refresh_token
   QUICKBOOKS_REALM_ID=your_realm_id
   QUICKBOOKS_ENVIRONMENT=production

   # Email settings
   EMAIL_IMAP_SERVER=imap.yourserver.com
   EMAIL_SMTP_SERVER=smtp.yourserver.com
   EMAIL_USERNAME=your_email@domain.com
   EMAIL_PASSWORD=your_password
   AUTHORIZED_EMAIL_SENDERS=hello@757handy.com,another@example.com

   # Security settings
   JWT_SECRET_KEY=your_jwt_secret_key
   
   # Application settings
   APP_URL=http://your-app-url.com
   DEMO_MODE=False
   ```

## Usage

### Starting the Application

Run the Streamlit application:

```
streamlit run main.py
```

### Email Monitoring

The system will monitor the specified email account for messages from authorized senders. When an email is received with content like:

```
Please create a new invoice for Angie Hutchins. Customer specified materials: Virginia Highlands carpet tile for all offices on second floor of ROB. It costs $12,915.
```

The system will automatically:
1. Parse the email to extract the customer name, materials description, and amount
2. Create a draft invoice in QuickBooks
3. Send an approval email to the administrator

### Invoice Approval

When you receive an approval email, you can:
1. Click the "Approve Invoice" button in the email to open the approval interface
2. Review the invoice details
3. Click "Approve Invoice" to finalize the invoice in QuickBooks
4. Alternatively, click "Reject Invoice" to delete the draft invoice

### Testing

To run the test suite:

```
python test_invoice_workflow.py
```

### Manual Testing

You can also use the "Invoice Automation" tab in the UI to:
1. View processed emails
2. Check pending invoices
3. Test the invoice creation process without sending an email

## Configuration

### Email Monitoring Settings

- `EMAIL_CHECK_INTERVAL`: How often to check for new emails (in seconds)
- `AUTHORIZED_EMAIL_SENDERS`: Comma-separated list of email addresses authorized to request invoices

### Security Settings

- `JWT_TOKEN_EXPIRY_DAYS`: Number of days before an approval token expires
- `JWT_SECRET_KEY`: Secret key for JWT token generation and verification

### Application Settings

- `DEMO_MODE`: If True, uses mock QuickBooks API instead of the real one
- `AUTO_START_EMAIL_MONITORING`: If True, automatically starts email monitoring when the application launches

## System Components

### 1. Email Monitor (`email_monitor.py`)

Continuously monitors an email inbox for new messages from authorized senders.

### 2. Email Parser (`email_parser.py`)

Extracts invoice details from email content using NLP techniques.

### 3. Invoice Creator (`invoice_creator.py`)

Creates draft invoices in QuickBooks based on parsed invoice requests.

### 4. Approval Workflow (`approval_workflow.py`)

Handles the invoice approval process, including:
- Sending approval emails with secure tokens
- Verifying approval tokens
- Processing approval/rejection actions

### 5. Main Application (`main.py`)

Streamlit-based UI that integrates all components and provides a dashboard for users.

## Error Handling

The system has robust error handling throughout:

1. **Email Monitoring Errors**: Connection failures, authentication issues
2. **Parsing Errors**: Malformed emails, missing information
3. **API Errors**: QuickBooks API failures, network issues
4. **Approval Errors**: Invalid tokens, token expiration

All errors are logged with detailed information to help with troubleshooting.

## Security Considerations

- JWT tokens are used for secure approval links
- Email authentication ensures only authorized senders can request invoices
- HTTPS is recommended for production deployment
- Sensitive information is stored in environment variables, not in code

## License

[Your License Here]

## Contact

For support or questions, please contact [Your Contact Information].

## Recent Updates

### Improved Invoice Parsing (April 2025)

The email parsing system has been enhanced to better extract information from invoice requests:

- Added support for extracting invoice/PO numbers (now used as DocNumber in QuickBooks)
- Added detection of activity type (e.g., "Customer Specified Materials")
- Improved customer name detection, especially for common customers
- Better materials description extraction with support for specific formats
- Fixed formatting of line items to preserve activity type information

These improvements allow the system to more accurately create invoices from email requests without requiring manual editing afterward.

Example email format now supported:
```
Subject: new invoice "INVOICE-NUMBER"
Body: create a new invoice for existing customer Customer Name, invoice/PO number "INVOICE-NUMBER" for: materials: Description of materials. total amount is $1,234.56.
```

The system will correctly extract:
- Customer name
- Invoice/PO number
- Materials description
- Amount
- Activity type (if specified)

# CFO Agent - Cloud Run Edition

CFO Agent is a financial management automation tool that helps with invoice creation, accounting, and tax planning. This version is optimized for deployment to Google Cloud Run.

## Features

- **Email monitoring**: Automatically processes invoice creation requests from email
- **Invoice automation**: Creates QuickBooks invoices based on email requests 
- **Financial reporting**: Generates P&L, balance sheets, and other financial reports
- **Tax planning**: Helps calculate estimated taxes and prepare for filing
- **Cloud-native**: Fully deployable to Google Cloud Run with scheduled tasks

## Prerequisites

- Google Cloud SDK installed and configured
- Docker installed (for local testing)
- Access to the Google Cloud project `ledger-457022`
- QuickBooks Online API credentials
- Email account credentials

## Quick Start - Cloud Deployment

1. **Initialize the repository**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   ```

2. **Enable required Google Cloud APIs**:
   ```bash
   cd cfo_agent
   chmod +x scripts/*.sh  # Make scripts executable
   ./scripts/enable_gcp_apis.sh
   ```

3. **Configure secrets**:
   ```bash
   ./scripts/create_secrets.sh
   ```
   Follow the prompts to enter your QuickBooks API credentials and other sensitive information.

4. **Build and push the container image**:
   ```bash
   ./scripts/build_and_push.sh
   ```

5. **Deploy to Cloud Run**:
   ```bash
   ./scripts/deploy.sh
   ```

6. **Set up scheduled tasks**:
   ```bash
   ./scripts/create_scheduler.sh
   ```

7. **Test the deployment**:
   ```bash
   ./scripts/test_endpoints.sh
   ```

## Local Development

### Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r cfo_agent/requirements.txt
   ```

3. Create a `.env` file with required environment variables:
   ```
   QUICKBOOKS_CLIENT_ID=your_client_id
   QUICKBOOKS_CLIENT_SECRET=your_client_secret
   QUICKBOOKS_REFRESH_TOKEN=your_refresh_token
   QUICKBOOKS_REALM_ID=your_realm_id
   EMAIL_USERNAME=your_email
   EMAIL_PASSWORD=your_password
   JWT_SECRET_KEY=your_secret_key
   ```

4. Run the application locally:
   ```bash
   cd cfo_agent
   python main.py
   ```

### Running with Docker

1. Build the container:
   ```bash
   cd cfo_agent
   docker build -t cfo-agent:local .
   ```

2. Run the container:
   ```bash
   docker run -p 8080:8080 --env-file .env cfo-agent:local
   ```

3. Access the application at http://localhost:8080

## Architecture

The CFO Agent deployed to Google Cloud Run has the following components:

- **Cloud Run Service**: Container running the Flask application
- **Cloud Scheduler**: Triggers scheduled reports and data refresh operations
- **Secret Manager**: Stores sensitive credentials securely
- **Cloud Storage**: Stores generated reports and temporary data

## Endpoints

- **`/trigger`**: Main POST endpoint for triggering the CFO Agent
- **`/health`**: GET endpoint for checking the health of the service

## Trigger Types

The `/trigger` endpoint accepts the following trigger types:

1. **Email triggers**:
   ```json
   {
     "trigger_type": "email",
     "email_data": {
       "message_id": "123456",
       "sender": "user@example.com",
       "subject": "Invoice Request",
       "body": "Please create an invoice for Customer XYZ..."
     }
   }
   ```

2. **Scheduled tasks**:
   ```json
   {
     "trigger_type": "scheduled_task",
     "task_type": "daily_report",
     "start_date": "2025-01-01",
     "end_date": "2025-01-31"
   }
   ```

3. **Manual actions**:
   ```json
   {
     "trigger_type": "manual_action",
     "action": "refresh_data"
   }
   ```

## Logs and Monitoring

View Cloud Run logs with:
```bash
gcloud run services logs read cfo-agent --region us-east4
```

## Rollback to Previous Version

List available revisions:
```bash
gcloud run revisions list --service cfo-agent --region us-east4
```

Rollback to a specific revision:
```bash
gcloud run services update-traffic cfo-agent --to-revisions=REVISION_ID=100 --region us-east4
```

## Setting Up Email Triggers

To process emails and send them to the CFO Agent:

1. Set up a Gmail filter to forward specific emails to a Pub/Sub topic
2. Create a Pub/Sub topic (e.g., `cfo-email-triggers`)
3. Set up a Cloud Function triggered by Pub/Sub that forwards the email data to your Cloud Run service

Alternatively, the local version of CFO Agent can monitor an inbox directly if deployed with appropriate permissions.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is proprietary and confidential.

## CI/CD Deployment

This project uses GitHub Actions for continuous deployment to Google Cloud Run.

### Workflow Configuration

The deployment workflow is defined in `.github/workflows/deploy.yml` and automatically deploys the application to Cloud Run when changes are pushed to the `main` branch.

### GitHub Secrets

The following secrets need to be added to your GitHub repository (Settings → Secrets → Actions):

- `GCP_PROJECT_ID`: ledger-457022
- `GCP_PROJECT_NUMBER`: [Retrieved from Google Cloud Console]
- `GCP_SERVICE_ACCOUNT`: ledger-deployer@ledger-457022.iam.gserviceaccount.com

### Triggering a Deployment

To trigger a deployment, simply push to the `main` branch:

```bash
git push origin main
```

Or use the test script:

```bash
# Make the script executable (Linux/Mac)
chmod +x scripts/test_deploy.sh
./scripts/test_deploy.sh

# Or on Windows
bash scripts/test_deploy.sh

# Or using PowerShell
.\scripts\test_deploy.ps1
```

### Verifying Deployment

To verify the deployment status:

```bash
gcloud run services describe ledger --platform managed --region us-east4
```

To check logs:

```bash
gcloud run logs read ledger --project=ledger-457022
```

## Deployment

This application is deployed on Google Cloud Run in the `us-east4` region. 