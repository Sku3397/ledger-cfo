#!/bin/bash
set -e

# Configuration
PROJECT_ID="ledger-457022"
REGION="us-east4"
SERVICE_NAME="ledger"
REPOSITORY="cfo-agent-repo"
IMAGE_NAME="ledger"
IMAGE_TAG="latest"

# Full image path
IMAGE_PATH="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:$IMAGE_TAG"

# Step 1: Build the Docker image
echo "Building Docker image..."
docker build -t $IMAGE_NAME:$IMAGE_TAG .

# Step 2: Configure Docker to use Google Cloud credentials
echo "Configuring Docker authentication..."
gcloud auth configure-docker $REGION-docker.pkg.dev --quiet

# Step 3: Tag the image for Google Cloud Artifact Registry
echo "Tagging image for Google Cloud Artifact Registry..."
docker tag $IMAGE_NAME:$IMAGE_TAG $IMAGE_PATH

# Step 4: Push the image to Google Cloud Artifact Registry
echo "Pushing image to Google Cloud Artifact Registry..."
docker push $IMAGE_PATH

# Step 5: Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_PATH \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --project $PROJECT_ID

echo "Deployment completed successfully!"

# Step 6: Health check
echo "Performing health check..."
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format="value(status.url)" --project $PROJECT_ID)
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$SERVICE_URL/trigger" -H "Content-Type: application/json" -d '{"action":"health_check"}')

echo "Health check status: $HTTP_STATUS"
if [ "$HTTP_STATUS" == "200" ]; then
    echo "Health check passed!"
else
    echo "Health check failed with status $HTTP_STATUS"
fi 