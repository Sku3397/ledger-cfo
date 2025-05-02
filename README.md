# CFO Agent - Ledger CFO

[Placeholder for project description/overview. This system automates accounting tasks, focusing on invoice processing from email requests and integration with QuickBooks, deployable to Google Cloud Run.]

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Testing](#testing)
- [System Components](#system-components)
- [Error Handling](#error-handling)
- [Security Considerations](#security-considerations)
- [Cloud Deployment (Cloud Run Edition)](#cloud-deployment-cloud-run-edition)
- [License](#license)
- [Contact](#contact)
- [Recent Updates](#recent-updates)

## Overview

[Placeholder: High-level description of the project, its goals, and primary functionalities.]

This system extends a CFO/Accounting Agent to handle end-to-end invoice processing, optimized for deployment to Google Cloud Run. It monitors a designated email inbox, parses invoice requests, creates draft invoices in QuickBooks, manages an approval workflow, and provides comprehensive logging and error handling.

## Architecture

[Placeholder: Description of the system architecture, key components (like email monitor, parser, QBO integration, CLI/UI), and their interactions.]

## Features

- **Email Monitoring**: Continuously checks for new emails from authorized senders for invoice requests.
- **Natural Language Parsing**: Extracts invoice details (customer, materials, amount, PO number) from freeform email text.
- **QuickBooks Integration**: Creates and manages invoices through the QuickBooks API.
- **Secure Approval Workflow**: JWT-based secure approval links for invoices.
- **Comprehensive UI**: Streamlit interface to monitor and manage the workflow (if applicable).
- **Robust Error Handling**: Graceful handling of connection failures, parsing errors, API issues, etc.
- **Extensive Logging**: Detailed UTF-8 logging of all activities.
- **Financial reporting**: Generates P&L, balance sheets, and other financial reports.
- **Tax planning**: Helps calculate estimated taxes and prepare for filing.
- **Cloud-native**: Designed for deployment to Google Cloud Run with scheduled tasks.

## Quick Start

[Placeholder: Minimal steps to get the project running locally or deployed.]

```bash
# Clone the repository
git clone https://github.com/your-org/cfo-agent.git
cd cfo-agent

# Install dependencies (adjust based on final setup)
pip install -r requirements.txt 
# or: poetry install

# Configure environment variables (create .env file)
cp .env.example .env 
# (Edit .env with your credentials)

# Run the application (example)
streamlit run src/ledger_cfo/__main__.py 
# or: python src/ledger_cfo/__main__.py --help (for CLI usage)
```

## Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-org/cfo-agent.git
    cd cfo-agent
    ```

2.  **Install dependencies**:
    ```bash
    # Using pip:
    pip install -r requirements.txt
    # Or using Poetry (if setup):
    # poetry install
    ```

3.  **Configure environment variables**:
    Create a `.env` file in the project root. You can copy the structure from `.env.example` (if available) or use the list below. Fill in your specific credentials and settings.
    ```dotenv
    # QuickBooks API settings
    QUICKBOOKS_CLIENT_ID=your_client_id
    QUICKBOOKS_CLIENT_SECRET=your_client_secret
    QUICKBOOKS_REFRESH_TOKEN=your_refresh_token
    QUICKBOOKS_REALM_ID=your_realm_id
    QUICKBOOKS_ENVIRONMENT=sandbox # or production

    # Email settings
    EMAIL_IMAP_SERVER=imap.yourserver.com
    EMAIL_SMTP_SERVER=smtp.yourserver.com
    EMAIL_USERNAME=your_email@domain.com
    EMAIL_PASSWORD=your_password
    AUTHORIZED_EMAIL_SENDERS=sender1@example.com,sender2@example.com

    # Security settings
    JWT_SECRET_KEY=your_very_secret_jwt_key

    # Application settings
    APP_URL=http://localhost:8501 # or your deployed URL
    DEMO_MODE=False # Use True for mock QBO API
    # Add other settings like EMAIL_CHECK_INTERVAL, JWT_TOKEN_EXPIRY_DAYS if needed
    ```

## Usage

### Starting the Application

Run the Streamlit application (if configured):
```bash
streamlit run src/ledger_cfo/__main__.py # Adjust path if entry point differs
```
Or use the command-line interface:
```bash
python src/ledger_cfo/__main__.py [command] [options]
# Example: python src/ledger_cfo/__main__.py check-emails
```

### Email Monitoring and Invoice Workflow

The system monitors the specified email account for messages from authorized senders. When an email is received with content like:
```
Subject: new invoice "PO-123"
Body: Please create a new invoice for Example Corp, invoice/PO number "PO-123" for: materials: Product A and Service B. total amount is $5,432.10.
```
The system will automatically:
1. Parse the email to extract customer name, PO number, materials description, and amount.
2. Create a draft invoice in QuickBooks.
3. Send an approval email (if configured) or log the action.

### Invoice Approval

If an approval workflow is enabled:
1. An approval email with a secure link (using JWT) is sent.
2. Clicking the link opens an interface to review and approve/reject the invoice.
3. Approval finalizes the invoice in QuickBooks; rejection deletes the draft.

## Configuration

Configuration is primarily managed through environment variables loaded from the `.env` file.

Key settings include:
- **QuickBooks API**: Client ID, Secret, Refresh Token, Realm ID, Environment (sandbox/production).
- **Email**: IMAP/SMTP server details, username, password, authorized sender list.
- **Security**: `JWT_SECRET_KEY` for approval tokens, `JWT_TOKEN_EXPIRY_DAYS`.
- **Application**: `APP_URL`, `DEMO_MODE`, `EMAIL_CHECK_INTERVAL`, `AUTO_START_EMAIL_MONITORING`.

Refer to the `.env` or `.env.example` file for a complete list.

## Testing

### Automated Tests

Run the automated test suite using pytest:
```bash
pytest
```
Ensure necessary test dependencies are installed (check `requirements-dev.txt` or `pyproject.toml`).

### Manual Testing (`test_invoice_workflow.py`)

The script `test_invoice_workflow.py` (if still applicable) might provide specific workflow tests:
```bash
python test_invoice_workflow.py
```

### UI Testing

If using the Streamlit UI, use the "Invoice Automation" tab (or similar) to:
1. View processed emails.
2. Check pending invoices.
3. Test invoice creation manually.

## System Components

(Paths reflect the refactored structure)

- **Main Entry Point**: `src/ledger_cfo/__main__.py` (Handles CLI and potentially launches UI)
- **CLI Logic**: [`src/ledger_cfo/cli.py`](src/ledger_cfo/cli_README.md), [`src/ledger_cfo/simple_cli.py`](src/ledger_cfo/simple_cli_README.md)
- **Core Logic**: [`src/ledger_cfo/core/`](src/ledger_cfo/core/README.md)
- **Email Processing**: `src/ledger_cfo/email.py` (Placeholder README needed)
- **Invoice Logic**: `src/ledger_cfo/invoice.py` (Placeholder README needed)
- **QuickBooks Integration**: `src/ledger_cfo/qbo.py` (Placeholder README needed)
- **Google Ads Integration**: [`src/ledger_cfo/google_ads_agent/`](src/ledger_cfo/google_ads_agent/README.md)
- **UI**: Potentially integrated within `__main__.py` or a separate module if complex.

## Error Handling

The system implements robust error handling for:
- Email server connection/authentication issues.
- Email parsing failures (malformed content, missing details).
- QuickBooks API errors (authentication, invalid requests, rate limits).
- Approval workflow problems (invalid/expired tokens).

Errors are logged comprehensively to aid debugging.

## Security Considerations

- **Credentials**: Store sensitive data (API keys, passwords) securely using environment variables and potentially a secret manager (like Google Secret Manager for cloud deployments). Do not commit secrets to Git.
- **Approval Tokens**: Use strong, short-lived JWTs for approval links.
- **Email Validation**: Strictly enforce the `AUTHORIZED_EMAIL_SENDERS` list.
- **Input Sanitization**: Sanitize data extracted from emails before using it in API calls.
- **HTTPS**: Ensure the application (especially any web UI or approval endpoints) is served over HTTPS.
- **Dependencies**: Keep libraries updated to patch security vulnerabilities.

## Cloud Deployment (Cloud Run Edition)

This version is optimized for deployment to Google Cloud Run.

### Prerequisites

- Google Cloud SDK (`gcloud`) installed and authenticated.
- Docker installed locally.
- A Google Cloud Project with necessary APIs enabled (Cloud Build, Cloud Run, Secret Manager, Cloud Scheduler).
- Project ID: `ledger-457022` (or your project)

### Deployment Scripts

Scripts are provided in the `./scripts/` directory:

1.  **Enable GCP APIs**: `./scripts/enable_gcp_apis.sh`
2.  **Create/Update Secrets**: `./scripts/create_secrets.sh` (Stores `.env` contents in Google Secret Manager)
3.  **Build & Push Container**: `./scripts/build_and_push.sh` (Builds Docker image using Cloud Build and pushes to Artifact Registry)
4.  **Deploy to Cloud Run**: `./scripts/deploy_cloud_run.sh` (Deploys the container to Cloud Run)
5.  **Schedule Jobs**: `./scripts/schedule_jobs.sh` (Sets up Cloud Scheduler jobs, e.g., for periodic email checks)

**General Workflow:**
```bash
cd cfo_agent # Or project root
chmod +x scripts/*.sh 
./scripts/enable_gcp_apis.sh
./scripts/create_secrets.sh # Follow prompts
./scripts/build_and_push.sh
./scripts/deploy_cloud_run.sh
./scripts/schedule_jobs.sh # If using scheduled tasks
```

## License

[Specify Your License Here - e.g., MIT, Apache 2.0]

## Contact

For support or questions, please contact [Your Name/Email/Project Link].

## Recent Updates

[Keep existing recent updates or add new ones.]

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
The system will correctly extract: Customer name, Invoice/PO number, Materials description, Amount, Activity type (if specified). 