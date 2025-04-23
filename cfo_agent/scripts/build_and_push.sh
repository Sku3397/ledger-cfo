#!/bin/bash
# Script to build and push the CFO Agent container image to Google Artifact Registry

# Set variables
PROJECT_ID=ledger-457022
REGION=us-central1
REPO_NAME=cfo-agent-repo
IMAGE_NAME=cfo-agent
VERSION=$(date +%Y%m%d-%H%M%S)

# Print banner
echo "===== Building and pushing CFO Agent container image ====="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Repository: $REPO_NAME"
echo "Image: $IMAGE_NAME:$VERSION"

# Create the Artifact Registry repository if it doesn't exist
if ! gcloud artifacts repositories describe $REPO_NAME --location=$REGION > /dev/null 2>&1; then
    echo "Creating Artifact Registry repository $REPO_NAME in $REGION..."
    gcloud artifacts repositories create $REPO_NAME \
        --repository-format=docker \
        --location=$REGION \
        --description="CFO Agent Container Repository"
else
    echo "Artifact Registry repository $REPO_NAME already exists."
fi

# Build the container image using Cloud Build
echo "Building container image using Cloud Build..."
gcloud builds submit --tag $REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:$VERSION \
    --tag $REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:latest \
    .

# Check if the build was successful
if [ $? -eq 0 ]; then
    echo "Container image built and pushed successfully:"
    echo "  $REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:$VERSION"
    echo "  $REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:latest"
    
    # Create a version file for tracking
    echo "IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:$VERSION" > version.txt
    echo "VERSION=$VERSION" >> version.txt
    echo "BUILD_DATE=$(date -u)" >> version.txt
    
    echo "Version information saved to version.txt"
else
    echo "Failed to build and push the container image."
    exit 1
fi

echo "===== Build and push process complete =====" 