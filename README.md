# Ledger CFO - AI Assistant

Ledger CFO is an AI-powered assistant designed to help manage basic bookkeeping tasks within QuickBooks Online (QBO) by interpreting commands sent via email.

## Features (Phase 3)

*   **Email Processing:** Reads unread emails from a designated Gmail account.
*   **Authorization:** Only processes emails from a pre-configured authorized sender.
*   **Natural Language Understanding (NLU):** Extracts intent and entities from email bodies for actions like:
    *   Creating Invoices (`CREATE_INVOICE`)
    *   Sending Invoices (`SEND_INVOICE`)
    *   Finding Customers (`FIND_CUSTOMER`)
    *   **NEW:** Recording Expenses/Purchases (`RECORD_EXPENSE`)
    *   **NEW:** Generating Profit & Loss Reports (`GET_REPORT_PNL`) (Handles date ranges like "last month", "this year", YYYY-MM-DD to YYYY-MM-DD)
*   **QuickBooks Integration:** Interacts with the QBO API v3 to perform accounting tasks.
*   **Confirmation Workflow:** Sends confirmation emails for sensitive actions (creating invoices, sending invoices, recording expenses) requiring the user to reply with `CONFIRM <uuid>` or `CANCEL <uuid>`. Confirmation requests expire after a configurable duration (default 60 minutes).
*   **Database Persistence:**
    *   Caches QBO Customer, **Vendor**, and **Account** data in a PostgreSQL database to reduce API calls.
    *   Stores pending confirmation actions in the database (`pending_actions` table) instead of in-memory.
*   **User Feedback:** Sends email replies confirming task execution, failure, or the need for confirmation.
*   **Deployment Ready:** Includes a `Dockerfile` for easy deployment to services like Google Cloud Run.
*   **Basic Testing:** Initial unit tests for NLU components using `pytest`.

## Setup

1.  **Prerequisites:**
    *   Python 3.10+
    *   Google Cloud Project with Secret Manager API enabled.
    *   Gmail account for the agent.
    *   QuickBooks Online account and Developer App credentials.
    *   PostgreSQL database (e.g., Google Cloud SQL).
2.  **Clone the repository:**
    ```bash
    git clone https://github.com/Sku3397/ledger-cfo.git
    cd ledger-cfo
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configure Secrets:** Store the following secrets in Google Cloud Secret Manager (ensure the service account running the code has `Secret Manager Secret Accessor` role):
    *   `gmail_credentials_json`: Content of your `credentials.json` file obtained from Google Cloud Console for the Gmail API.
    *   `gmail_token_json`: Content of the `token.json` generated after the initial OAuth flow for Gmail.
    *   `qbo_client_id`: Your QBO App's Client ID.
    *   `qbo_client_secret`: Your QBO App's Client Secret.
    *   `qbo_refresh_token`: A valid QBO Refresh Token.
    *   `qbo_realm_id`: Your QBO Company ID.
    *   `qbo_environment`: `sandbox` or `production`.
    *   `ALLOWED_SENDER_EMAIL`: The email address authorized to send commands to the agent.
    *   `SENDER_EMAIL`: The Gmail address the agent uses to send/receive emails.
    *   `DB_USER`: PostgreSQL database username.
    *   `DB_PASS`: PostgreSQL database password.
    *   `DB_NAME`: PostgreSQL database name.
    *   `DB_HOST` or `DB_SOCKET_PATH`: Database host IP address *or* the Cloud SQL instance connection name for socket path (e.g., `your-project:your-region:your-instance`). Use the appropriate one based on your `USE_DB_SOCKET` setting.
    *   `DB_PORT`: PostgreSQL database port (usually 5432, ignored if using socket path).
    *   `GCP_PROJECT_ID`: Your Google Cloud Project ID.
    *   `USE_DB_SOCKET`: Set to `true` if connecting via Cloud SQL Auth Proxy socket path, `false` otherwise.

5.  **Database Setup:** Ensure the PostgreSQL database and user exist. The application will create the necessary tables (`customer_cache`, `pending_actions`, `vendor_cache`, `account_cache`) on startup.

## Running Locally

Set the `GCP_PROJECT_ID` environment variable:

```bash
# Windows (Command Prompt)
set GCP_PROJECT_ID=your-gcp-project-id
# Windows (PowerShell)
$env:GCP_PROJECT_ID="your-gcp-project-id"
# Linux/macOS
export GCP_PROJECT_ID=your-gcp-project-id
```

Run the Flask application:

```bash
python src/ledger_cfo/__main__.py
```

The application will start a Flask server (usually on port 8080). You can trigger email processing by sending a POST request to the `/tasks/process-emails` endpoint (e.g., using `curl` or Postman) or by setting up a Cloud Scheduler job.

## Running with Docker / Cloud Run

1.  **Build the Docker image:**
    ```bash
    docker build -t ledger-cfo-agent .
    ```
    (Ensure your Docker daemon is running)

2.  **Run locally using Docker:**
    ```bash
    docker run -p 8080:8080 -e GCP_PROJECT_ID=your-gcp-project-id -e PORT=8080 ledger-cfo-agent
    ```
    *(You might need to pass other environment variables or configure secrets differently for local Docker)*

3.  **Deploy to Cloud Run:**
    *   Push the image to Google Container Registry (GCR) or Artifact Registry.
        ```bash
        # Example using GCR
        docker tag ledger-cfo-agent gcr.io/your-gcp-project-id/ledger-cfo-agent:latest
        docker push gcr.io/your-gcp-project-id/ledger-cfo-agent:latest
        ```
    *   Deploy using the `gcloud` command-line tool, ensuring the service account has access to Secret Manager and Cloud SQL (if using private IP/socket).
        ```bash
        gcloud run deploy ledger-cfo-agent \
            --image gcr.io/your-gcp-project-id/ledger-cfo-agent:latest \
            --platform managed \
            --region your-gcp-region \
            --allow-unauthenticated `# Or configure IAM invoker` \
            --service-account your-service-account@your-project.iam.gserviceaccount.com \
            --set-secrets=gmail_credentials_json=gmail_credentials_json:latest,qbo_client_id=qbo_client_id:latest,... `# Map all required secrets` \
            --add-cloudsql-instances your-project:your-region:your-instance `# If using Cloud SQL connection name`
            # Add other necessary flags (VPC connector, etc.)
        ```
    *   Configure Cloud Scheduler to periodically send a POST request to the service URL's `/tasks/process-emails` endpoint to trigger email processing.

## Usage

Send emails from the `ALLOWED_SENDER_EMAIL` to the agent's `SENDER_EMAIL` with commands like:

*   `Create invoice for Customer X for $500 for Services Rendered`
*   `Send invoice for Customer Y $1200`
*   `Find customer "Customer Z Inc."`
*   `Record expense for Vendor A $99.95 category Software`
*   `Log expense paid Staples for 30.50`
*   `Get PNL report last month`
*   `Show profit and loss 2024-01-01 to 2024-03-31`

For actions requiring confirmation, you will receive an email. Reply with `CONFIRM <uuid>` or `CANCEL <uuid>`. 