#!/bin/bash
# Script to enable all required Google Cloud APIs for the CFO Agent

# Set the project ID
PROJECT_ID=ledger-457022

# Print banner
echo "===== Enabling GCP APIs for CFO Agent project: $PROJECT_ID ====="

# Set the project
echo "Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

# Enable APIs
echo "Enabling required APIs..."

# Core APIs
echo "  - Cloud Run API..."
gcloud services enable run.googleapis.com

echo "  - Cloud Build API..."
gcloud services enable cloudbuild.googleapis.com

echo "  - Artifact Registry API..."
gcloud services enable artifactregistry.googleapis.com

echo "  - Secret Manager API..."
gcloud services enable secretmanager.googleapis.com

echo "  - Cloud Storage API..."
gcloud services enable storage.googleapis.com

echo "  - Cloud Scheduler API..."
gcloud services enable cloudscheduler.googleapis.com

echo "  - Pub/Sub API..."
gcloud services enable pubsub.googleapis.com

echo "  - Cloud Functions API..."
gcloud services enable cloudfunctions.googleapis.com

echo "All required APIs have been enabled successfully."
echo "===== GCP API setup complete =====" 