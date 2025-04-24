#!/bin/bash
# Test script to verify Cloud Build works in global region

PROJECT_ID="ledger-457022"
REGION="us-east4"
REPOSITORY="cfo-agent-repo"
IMAGE_NAME="ledger"
TAG="test-global"

echo "Testing Cloud Build in global region..."
echo "This should build successfully without specifying a region."

# Build using Cloud Build (implicitly using global region)
gcloud builds submit \
  --project=$PROJECT_ID \
  --tag $REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:$TAG \
  .

echo "Build completed. Check for any errors above." 