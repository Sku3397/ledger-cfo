# PowerShell script to test Cloud Build in global region using only tag

$PROJECT_ID = "ledger-457022"
$REGION = "us-east4"
$REPOSITORY = "cfo-agent-repo"
$IMAGE_NAME = "ledger"
$TAG = "test-tag-only"
$IMAGE_URL = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME"

Write-Host "Testing Cloud Build in global region with tag only..." -ForegroundColor Cyan
Write-Host "This should build successfully without specifying a region." -ForegroundColor Cyan

# Copy the test Dockerfile to the current directory as Dockerfile
Copy-Item -Path "Dockerfile.test" -Destination "Dockerfile" -Force

# Build using Cloud Build with tag (implicitly using global region)
gcloud builds submit `
  --project=$PROJECT_ID `
  --tag "${IMAGE_URL}:${TAG}" `
  .

# Clean up
Remove-Item -Path "Dockerfile" -Force -ErrorAction SilentlyContinue

Write-Host "Build test completed. Check for any errors above." -ForegroundColor Green 