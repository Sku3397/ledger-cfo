#!/usr/bin/env pwsh

# Get the project number
$PROJECT_NUMBER = gcloud projects describe ledger-457022 --format="value(projectNumber)"
Write-Host "Project Number: $PROJECT_NUMBER"

# Bind Artifact Registry writer role to Compute default service account
Write-Host "Granting artifactregistry.writer role to Compute service account..."
gcloud projects add-iam-policy-binding ledger-457022 `
  --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" `
  --role="roles/artifactregistry.writer"

# Bind Logging Writer role to the same service account
Write-Host "Granting logging.logWriter role to Compute service account..."
gcloud projects add-iam-policy-binding ledger-457022 `
  --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" `
  --role="roles/logging.logWriter"

# Also bind to Cloud Build service account (if used)
Write-Host "Granting artifactregistry.writer role to Cloud Build service account..."
gcloud projects add-iam-policy-binding ledger-457022 `
  --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" `
  --role="roles/artifactregistry.writer"

Write-Host "Granting logging.logWriter role to Cloud Build service account..."
gcloud projects add-iam-policy-binding ledger-457022 `
  --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" `
  --role="roles/logging.logWriter"

Write-Host "IAM permissions successfully applied."
Write-Host "You can now run your build and deploy commands." 