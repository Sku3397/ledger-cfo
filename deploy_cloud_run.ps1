# PowerShell script to deploy to Cloud Run
# This script handles the deployment process with proper PowerShell syntax

# Configuration
$PROJECT_ID = "ledger-457022"
$REGION = "us-east4"
$SERVICE_NAME = "ledger"
$REPOSITORY = "cfo-agent-repo"
$IMAGE_NAME = "ledger"

Write-Host "Starting deployment to Cloud Run..." -ForegroundColor Green

# Step 1: Update the workload identity provider
Write-Host "Updating workload identity provider..." -ForegroundColor Yellow
gcloud iam workload-identity-pools providers update-oidc github-provider `
  --workload-identity-pool="github-actions-pool" `
  --location="global" `
  --project=$PROJECT_ID `
  --attribute-condition="attribute.repository=='Matt/CFO_Agent'"

# Step 2: Verify Artifact Registry repository
Write-Host "Verifying Artifact Registry repository exists..." -ForegroundColor Yellow
$repoExists = gcloud artifacts repositories list --project=$PROJECT_ID --location=$REGION --filter="name:$REPOSITORY" --format="value(name)"

if (-not $repoExists) {
    Write-Host "Creating Artifact Registry repository..." -ForegroundColor Yellow
    gcloud artifacts repositories create $REPOSITORY `
      --repository-format=docker `
      --location=$REGION `
      --description="Repository for CFO Agent" `
      --project=$PROJECT_ID
} else {
    Write-Host "Artifact Registry repository already exists." -ForegroundColor Green
}

# Step 3: Build the Docker image locally
Write-Host "Building the Docker image locally..." -ForegroundColor Yellow
try {
    docker build -t "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:latest" .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Docker build failed. Please check that Docker is installed and running." -ForegroundColor Red
        exit 1
    }
}
catch {
    Write-Host "Error: Docker is not installed or not running." -ForegroundColor Red
    Write-Host "Please install Docker Desktop for Windows and try again." -ForegroundColor Red
    exit 1
}

# Step 4: Configure Docker to use Google Cloud auth
Write-Host "Configuring Docker to authenticate with Google Cloud..." -ForegroundColor Yellow
gcloud auth configure-docker $REGION-docker.pkg.dev --quiet

# Step 5: Push the Docker image
Write-Host "Pushing the Docker image to Artifact Registry..." -ForegroundColor Yellow
try {
    docker push "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:latest"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to push Docker image. Please check your permissions." -ForegroundColor Red
        exit 1
    }
}
catch {
    Write-Host "Error pushing Docker image: $_" -ForegroundColor Red
    exit 1
}

# Step 6: Deploy to Cloud Run
Write-Host "Deploying to Cloud Run..." -ForegroundColor Yellow
gcloud run deploy $SERVICE_NAME `
  --image="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:latest" `
  --platform=managed `
  --region=$REGION `
  --project=$PROJECT_ID `
  --allow-unauthenticated

# Step 7: Get the service URL
Write-Host "Getting service URL..." -ForegroundColor Yellow
$serviceUrl = gcloud run services describe $SERVICE_NAME `
  --platform=managed `
  --region=$REGION `
  --project=$PROJECT_ID `
  --format="value(status.url)"

Write-Host "Deployment completed!" -ForegroundColor Green
Write-Host "Service URL: $serviceUrl" 