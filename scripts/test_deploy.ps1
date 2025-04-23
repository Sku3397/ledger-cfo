# PowerShell Script for testing deployment
# Stop script on error
$ErrorActionPreference = "Stop"

Write-Host "Triggering CI workflow..."
git commit --allow-empty -m "CI test"
git push origin main

Write-Host "Waiting for Actions to complete..."
Write-Host "Check GitHub Actions at: https://github.com/sku3397/ledger-cfo/actions"

Write-Host "`nVerify deployment with:"
Write-Host "gcloud run services describe ledger --platform managed --region us-central1"
Write-Host "gcloud run logs read ledger --project=ledger-457022" 