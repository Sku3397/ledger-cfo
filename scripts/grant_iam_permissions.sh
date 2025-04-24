#!/usr/bin/env bash
set -e

# Get the project number if not already set
if [ -z "${PROJECT_NUMBER}" ]; then
  PROJECT_NUMBER=$(gcloud projects describe ledger-457022 --format="value(projectNumber)")
  echo "Project Number: ${PROJECT_NUMBER}"
fi

# Bind Artifact Registry writer role to Compute default service account
echo "Granting artifactregistry.writer role to Compute service account..."
gcloud projects add-iam-policy-binding ledger-457022 \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

# Bind Logging Writer role to the same service account
echo "Granting logging.logWriter role to Compute service account..."
gcloud projects add-iam-policy-binding ledger-457022 \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/logging.logWriter"

# Also bind to Cloud Build service account (if used)
echo "Granting artifactregistry.writer role to Cloud Build service account..."
gcloud projects add-iam-policy-binding ledger-457022 \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

echo "Granting logging.logWriter role to Cloud Build service account..."
gcloud projects add-iam-policy-binding ledger-457022 \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/logging.logWriter"

echo "IAM permissions successfully applied."
echo "You can now run your build and deploy commands." 