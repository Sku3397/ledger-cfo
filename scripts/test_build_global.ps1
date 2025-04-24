# PowerShell script to test Cloud Build in global region

$PROJECT_ID = "ledger-457022"
$REGION = "us-east4"
$REPOSITORY = "cfo-agent-repo"
$IMAGE_NAME = "ledger"
$TAG = "test-global"
$IMAGE_URL = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME"

Write-Host "Testing Cloud Build in global region..." -ForegroundColor Cyan
Write-Host "This should build successfully without specifying a region." -ForegroundColor Cyan

# Option 1: Build using Cloud Build with tag (implicitly using global region)
Write-Host "Option 1: Building with tag..." -ForegroundColor Yellow
gcloud builds submit `
  --project=$PROJECT_ID `
  --tag "${IMAGE_URL}:${TAG}" `
  .

# Option 2: Build using Cloud Build with config (implicitly using global region)
Write-Host "`nOption 2: Building with config file..." -ForegroundColor Yellow
gcloud builds submit `
  --project=$PROJECT_ID `
  --config=cloudbuild.yaml `
  .

Write-Host "Build tests completed. Check for any errors above." -ForegroundColor Green 