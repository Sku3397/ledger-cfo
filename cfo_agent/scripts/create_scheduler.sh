#!/bin/bash
# Script to create scheduled jobs for the CFO Agent using Google Cloud Scheduler

# Set variables
PROJECT_ID=ledger-457022
REGION=us-east4
SERVICE_NAME=cfo-agent
SCHEDULER_ACCOUNT=cfo-scheduler@${PROJECT_ID}.iam.gserviceaccount.com

# Load service information if available
if [ -f service_info.txt ]; then
    source service_info.txt
    echo "Using service URL: $SERVICE_URL"
else
    # Get service URL if not loaded from file
    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)')
    if [ -z "$SERVICE_URL" ]; then
        echo "Error: Could not determine service URL. Make sure the service is deployed."
        exit 1
    fi
    echo "Retrieved service URL: $SERVICE_URL"
fi

# Ensure the service URL doesn't end with a slash
SERVICE_URL=${SERVICE_URL%/}

# Print banner
echo "===== Setting up scheduled jobs for CFO Agent ====="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo "Endpoint: $SERVICE_URL/trigger"

# Function to create or update a scheduler job
create_or_update_job() {
    local job_name=$1
    local schedule=$2
    local payload=$3
    local description=$4
    
    # Check if job exists
    if gcloud scheduler jobs describe $job_name --location=$REGION > /dev/null 2>&1; then
        echo "Updating existing job: $job_name"
        gcloud scheduler jobs update http $job_name \
            --location=$REGION \
            --schedule="$schedule" \
            --uri="$SERVICE_URL/trigger" \
            --http-method=POST \
            --headers="Content-Type=application/json" \
            --message-body="$payload" \
            --description="$description" \
            --time-zone="America/New_York" \
            --attempt-deadline=180s
            
    else
        echo "Creating new job: $job_name"
        gcloud scheduler jobs create http $job_name \
            --location=$REGION \
            --schedule="$schedule" \
            --uri="$SERVICE_URL/trigger" \
            --http-method=POST \
            --headers="Content-Type=application/json" \
            --message-body="$payload" \
            --description="$description" \
            --time-zone="America/New_York" \
            --attempt-deadline=180s
    fi
    
    # Check if the operation was successful
    if [ $? -eq 0 ]; then
        echo "Job $job_name created/updated successfully."
    else
        echo "Failed to create/update job $job_name."
        return 1
    fi
}

# Create daily financial report job (runs at 6:00 AM Eastern)
echo "Setting up daily financial report job..."
DAILY_REPORT_PAYLOAD='{"trigger_type":"scheduled_task","task_type":"daily_report","start_date":"AUTO","end_date":"AUTO"}'
create_or_update_job "cfo-daily-financial-report" "0 6 * * *" "$DAILY_REPORT_PAYLOAD" "Generate daily financial report for CFO Agent"

# Create weekly tax estimate job (runs every Monday at 7:00 AM Eastern)
echo "Setting up weekly tax estimate job..."
TAX_ESTIMATE_PAYLOAD='{"trigger_type":"scheduled_task","task_type":"tax_estimate","tax_year":2025}'
create_or_update_job "cfo-weekly-tax-estimate" "0 7 * * 1" "$TAX_ESTIMATE_PAYLOAD" "Generate weekly tax estimates for CFO Agent"

# Create data refresh job (runs every 4 hours)
echo "Setting up data refresh job..."
DATA_REFRESH_PAYLOAD='{"trigger_type":"manual_action","action":"refresh_data"}'
create_or_update_job "cfo-data-refresh" "0 */4 * * *" "$DATA_REFRESH_PAYLOAD" "Refresh financial data for CFO Agent"

echo "===== Scheduler setup process complete =====" 