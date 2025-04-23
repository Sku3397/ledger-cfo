#!/bin/bash
# Script to deploy the CFO Agent to Google Cloud Run

# Set variables
PROJECT_ID=ledger-457022
REGION=us-central1
REPO_NAME=cfo-agent-repo
SERVICE_NAME=cfo-agent
MIN_INSTANCES=1
MAX_INSTANCES=5
MEMORY=512Mi
CPU=1

# Load the version information if available
if [ -f version.txt ]; then
    source version.txt
    echo "Using image: $IMAGE"
else
    # Default to latest if no version file
    IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$SERVICE_NAME:latest"
    echo "No version.txt found. Using default image: $IMAGE"
fi

# Print banner
echo "===== Deploying CFO Agent to Cloud Run ====="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo "Image: $IMAGE"

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --memory $MEMORY \
    --cpu $CPU \
    --min-instances $MIN_INSTANCES \
    --max-instances $MAX_INSTANCES \
    --set-env-vars "PROJECT_ID=$PROJECT_ID,ENVIRONMENT=production" \
    --timeout 300s

# Check if the deployment was successful
if [ $? -eq 0 ]; then
    # Get the service URL
    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)')
    
    echo "CFO Agent deployment successful!"
    echo "Service URL: $SERVICE_URL"
    echo "Trigger endpoint: $SERVICE_URL/trigger"
    echo "Health check: $SERVICE_URL/health"
    
    # Save service information to a file
    echo "SERVICE_URL=$SERVICE_URL" > service_info.txt
    echo "DEPLOYMENT_DATE=$(date -u)" >> service_info.txt
    
    echo "Service information saved to service_info.txt"
else
    echo "Failed to deploy the CFO Agent to Cloud Run."
    exit 1
fi

echo "===== Deployment process complete =====" 