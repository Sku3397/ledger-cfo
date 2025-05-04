# Ledger CFO Agent - Manual Deployment to Google Cloud Run

This document outlines the **manual steps** required to deploy the Ledger CFO Agent to Google Cloud Run. These steps need to be performed by a user with appropriate permissions in the target Google Cloud project. The AI agent assists with code preparation but **cannot perform these infrastructure setup tasks directly**.

**Assumptions:**

*   You have a Google Cloud Platform (GCP) project created.
*   You have `gcloud` (Google Cloud SDK) installed and authenticated locally.
*   You have Docker installed and running locally.
*   The application source code is available locally.

## 1. Prerequisites & API Enablement

Ensure the necessary GCP services are enabled in your project. You can do this via the Cloud Console or `gcloud`.

```bash
# Replace [PROJECT_ID] with your actual GCP project ID
export PROJECT_ID="[YOUR_PROJECT_ID]"
gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    sqladmin.googleapis.com \
    cloudscheduler.googleapis.com \
    iam.googleapis.com # Needed for role management
```

## 2. Configure Secret Manager

The application relies on secrets stored securely in Google Secret Manager. Create the following secrets. Replace placeholder values like `[YOUR_...]` with your actual credentials.

**Secret Naming Convention:** Use lowercase names with hyphens (e.g., `ledger-cfo-qbo-client-id`).

**Steps (Example using `gcloud`):**

1.  **QBO Client ID:**
    ```bash
    echo -n "[YOUR_QBO_CLIENT_ID]" | gcloud secrets create ledger-cfo-qbo-client-id --data-file=- --replication-policy="automatic"
    ```
2.  **QBO Client Secret:**
    ```bash
    echo -n "[YOUR_QBO_CLIENT_SECRET]" | gcloud secrets create ledger-cfo-qbo-client-secret --data-file=- --replication-policy="automatic"
    ```
3.  **QBO Realm ID:**
    ```bash
    echo -n "[YOUR_QBO_REALM_ID]" | gcloud secrets create ledger-cfo-qbo-realm-id --data-file=- --replication-policy="automatic"
    ```
4.  **QBO Refresh Token:** (Obtained via OAuth flow, ensure it's long-lived or handled appropriately)
    ```bash
    echo -n "[YOUR_QBO_REFRESH_TOKEN]" | gcloud secrets create ledger-cfo-qbo-refresh-token --data-file=- --replication-policy="automatic"
    ```
5.  **Gmail Refresh Token:** (Obtained via OAuth flow for the app's sending account)
    ```bash
    echo -n "[YOUR_GMAIL_REFRESH_TOKEN]" | gcloud secrets create ledger-cfo-gmail-refresh-token --data-file=- --replication-policy="automatic"
    ```
6.  **Gmail Client Secret JSON:** (Contents of your `client_secret.json` file)
    ```bash
    gcloud secrets create ledger-cfo-gmail-client-secrets --data-file="path/to/your/client_secret.json" --replication-policy="automatic"
    ```
7.  **Allowed Sender Email:** (The *only* email address the agent will process commands from)
    ```bash
    echo -n "your-email@example.com" | gcloud secrets create ledger-cfo-allowed-sender --data-file=- --replication-policy="automatic"
    ```
8.  **Application Sender Email:** (The email address the agent sends *from*, e.g., `agent@yourdomain.com`)
    ```bash
    echo -n "agent@yourdomain.com" | gcloud secrets create ledger-cfo-sender-email --data-file=- --replication-policy="automatic"
    ```
9.  **Database Username:**
    ```bash
    echo -n "ledger_user" | gcloud secrets create ledger-cfo-db-user --data-file=- --replication-policy="automatic"
    ```
10. **Database Password:**
    ```bash
    echo -n "[YOUR_SECURE_DB_PASSWORD]" | gcloud secrets create ledger-cfo-db-password --data-file=- --replication-policy="automatic"
    ```
11. **Database Name:**
    ```bash
    echo -n "ledger_db" | gcloud secrets create ledger-cfo-db-name --data-file=- --replication-policy="automatic"
    ```
12. **Anthropic API Key:** (Required for LLM NLU - Claude)
    ```bash
    echo -n "[YOUR_ANTHROPIC_API_KEY]" | gcloud secrets create ledger-cfo-anthropic-api-key --data-file=- --replication-policy="automatic"
    ```

## 3. Set up Cloud SQL (PostgreSQL)

Create a PostgreSQL instance on Cloud SQL.

**Steps (Example using Cloud Console or `gcloud`):**

1.  **Create Instance:**
    *   Navigate to Cloud SQL in the GCP Console.
    *   Click "Create Instance".
    *   Choose "PostgreSQL".
    *   Provide an **Instance ID** (e.g., `ledger-cfo-db-instance`).
    *   Set a strong password for the default `postgres` user (or configure IAM authentication later).
    *   Choose a region (e.g., `us-central1`). Match the region you intend to use for Cloud Run.
    *   Select an appropriate machine type (e.g., `db-f1-micro` for testing, larger for production).
    *   Under "Connections", ensure "Public IP" is **disabled** and "Private IP" is **enabled**. Configure the VPC network (usually `default`). This is crucial for secure connection from Cloud Run.
    *   Click "Create". Note the **Instance Connection Name** shown on the instance details page (format: `[PROJECT_ID]:[REGION]:[INSTANCE_ID]`). You will need this later.
2.  **Create Database:**
    *   Once the instance is running, navigate to the "Databases" tab for the instance.
    *   Click "Create database".
    *   Enter the database name you chose for the secret (e.g., `ledger_db`).
    *   Click "Create".
3.  **Create User:**
    *   Navigate to the "Users" tab.
    *   Click "Create user account".
    *   Enter the username you chose for the secret (e.g., `ledger_user`).
    *   Enter the password you chose for the secret.
    *   Click "Create".
    *   **(Recommended Alternative: IAM Database Authentication)** Instead of password auth, you can configure IAM authentication for enhanced security. This involves adding IAM users/service accounts and granting them the `roles/cloudsql.instanceUser` role, then configuring the instance to allow IAM auth. The application code would need adjustments to use IAM auth tokens. Refer to [Cloud SQL IAM Authentication Docs](https://cloud.google.com/sql/docs/postgres/authentication#iam-authentication). If using IAM auth, you might not need the DB password secret.

## 4. Grant Service Account Permissions

Cloud Run services operate using a Service Account. By default, this is the *Compute Engine default service account* (`[PROJECT_NUMBER]-compute@developer.gserviceaccount.com`), or you can specify a dedicated one during deployment. This service account needs permissions to access secrets and connect to Cloud SQL.

**Steps (Example using `gcloud`):**

Find your project number:
```bash
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
# OR if using a custom SA: export YOUR_RUN_SA="your-sa-name@${PROJECT_ID}.iam.gserviceaccount.com"
```

Grant roles to the service account Cloud Run will use (replace `$COMPUTE_SA` if using a custom SA):

1.  **Secret Accessor:** Allows reading secrets from Secret Manager.
    ```bash
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$COMPUTE_SA" \
        --role="roles/secretmanager.secretAccessor"
    ```
2.  **Cloud SQL Client:** Allows connecting to the Cloud SQL instance via the proxy.
    ```bash
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$COMPUTE_SA" \
        --role="roles/cloudsql.client"
    ```

## 5. Build and Deploy to Cloud Run

1.  **Build the Docker Image using Cloud Build:**
    Navigate to the root directory of the application source code (where the `Dockerfile` is).
    ```bash
    # Replace [PROJECT_ID] with your actual GCP project ID
    gcloud builds submit --tag "gcr.io/$PROJECT_ID/ledger-cfo:latest" .
    ```
2.  **Deploy the Image to Cloud Run:**
    Replace placeholders:
    *   `[PROJECT_ID]`: Your GCP Project ID.
    *   `[REGION]`: The GCP region where you created the Cloud SQL instance (e.g., `us-central1`).
    *   `[INSTANCE_CONNECTION_NAME]`: The Cloud SQL Instance Connection Name noted earlier.
    *   `[SERVICE_ACCOUNT_EMAIL]`: The email of the service account Cloud Run should use (e.g., `$COMPUTE_SA` or your custom SA email).

    ```bash
    # Replace secret names with the names you created in Step 2
    gcloud run deploy ledger-cfo \
        --image="gcr.io/$PROJECT_ID/ledger-cfo:latest" \
        --platform="managed" \
        --region="[REGION]" \
        --service-account="[SERVICE_ACCOUNT_EMAIL]" \
        --allow-unauthenticated \
        --add-cloudsql-instances="[INSTANCE_CONNECTION_NAME]" \
        --set-secrets="QBO_CLIENT_ID=ledger-cfo-qbo-client-id:latest,QBO_CLIENT_SECRET=ledger-cfo-qbo-client-secret:latest,QBO_REALM_ID=ledger-cfo-qbo-realm-id:latest,QBO_REFRESH_TOKEN=ledger-cfo-qbo-refresh-token:latest,GMAIL_REFRESH_TOKEN=ledger-cfo-gmail-refresh-token:latest,GMAIL_CLIENT_SECRETS_JSON=ledger-cfo-gmail-client-secrets:latest,ALLOWED_SENDER_EMAIL=ledger-cfo-allowed-sender:latest,SENDER_EMAIL=ledger-cfo-sender-email:latest,DB_USER=ledger-cfo-db-user:latest,DB_PASS=ledger-cfo-db-password:latest,DB_NAME=ledger-cfo-db-name:latest,ANTHROPIC_API_KEY=ledger-cfo-anthropic-api-key:latest,DB_INSTANCE_CONNECTION_NAME=[INSTANCE_CONNECTION_NAME]" \
        --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID" \
        --cpu=1 \
        --memory=512Mi # Adjust resources as needed
        # Add --max-instances=1 if needed for singleton processing initially
    ```

    **Notes:**
    *   `--allow-unauthenticated`: This makes the service publicly accessible. Required for the initial Cloud Scheduler HTTP trigger setup without OIDC. Secure this later by removing the flag and configuring Scheduler to use OIDC authentication.
    *   `--set-secrets`: Maps Secret Manager secrets to environment variables available to the application container. The format is `ENV_VAR_NAME=secret-name:version`. We pass the DB connection name via secrets as well for the connector library.
    *   `--set-env-vars`: Sets standard environment variables.
    *   Adjust CPU/Memory based on performance monitoring.
    *   The Cloud SQL connection is handled automatically by the `--add-cloudsql-instances` flag and the `cloud-sql-python-connector` library when the `DB_INSTANCE_CONNECTION_NAME` environment variable is present.

## 6. Create Cloud Scheduler Job

Set up a job to periodically trigger the email processing endpoint.

**Steps (Example using Cloud Console):**

1.  Navigate to Cloud Scheduler in the GCP Console.
2.  Click "Create Job".
3.  **Define the job:**
    *   **Name:** `ledger-cfo-email-processor`
    *   **Region:** Choose the *same region* as your Cloud Run service.
    *   **Frequency:** Define using unix-cron format (e.g., `*/5 * * * *` for every 5 minutes).
    *   **Timezone:** Select your timezone.
4.  **Configure the execution:**
    *   **Target type:** `HTTP`
    *   **URL:** Get the URL provided by Cloud Run after successful deployment (it looks like `https://ledger-cfo-....run.app`). Append the processing path: `[CLOUDRUN_SERVICE_URL]/tasks/process-emails`
    *   **HTTP method:** `POST`
    *   **Auth header:** Select `No authorization` (if using `--allow-unauthenticated` in deployment).
        *   **(Recommended Secure Method):** Later, change Cloud Run to require authentication, then select `Add OIDC token`. Enter the Service Account email used by Cloud Scheduler (or create a dedicated one and grant it the `roles/run.invoker` role on your Cloud Run service).
5.  **Click "Create".**

## 7. Verification

1.  **Cloud Run Logs:** Check the logs for your `ledger-cfo` service in the Cloud Console (Logging -> Logs Explorer). Look for successful startup messages and logs from the email processing task.
2.  **Cloud Scheduler Logs:** Check the logs for your `ledger-cfo-email-processor` job to ensure it's triggering successfully (HTTP 200 responses from your service).
3.  **Functionality:** Send an email from the `ALLOWED_SENDER_EMAIL` to the application's monitored inbox and verify if it gets processed and a reply is sent. Check database entries if applicable.

This completes the manual deployment process. Remember to secure the Cloud Run service endpoint once initial testing is complete. 