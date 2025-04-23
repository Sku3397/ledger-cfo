#!/bin/bash
# Script to create and manage secrets for the CFO Agent in Google Secret Manager

# Set variables
PROJECT_ID=ledger-457022
SERVICE_NAME=cfo-agent
REGION=us-central1

# Print banner
echo "===== Setting up secrets for CFO Agent ====="
echo "Project: $PROJECT_ID"
echo "Service: $SERVICE_NAME"

# Function to create a secret if it doesn't exist
create_secret() {
    local secret_name=$1
    local secret_value=$2
    local description=$3
    
    # Check if secret exists
    if ! gcloud secrets describe $secret_name --project=$PROJECT_ID > /dev/null 2>&1; then
        echo "Creating secret: $secret_name"
        
        # Create the secret
        echo "Creating secret in Secret Manager..."
        gcloud secrets create $secret_name \
            --project=$PROJECT_ID \
            --replication-policy="automatic" \
            --description="$description"
            
        # Add the secret version
        echo "Adding secret version..."
        echo -n "$secret_value" | gcloud secrets versions add $secret_name \
            --project=$PROJECT_ID \
            --data-file=-
            
        echo "Secret $secret_name created successfully."
    else
        echo "Secret $secret_name already exists."
        
        # Prompt to update the secret
        read -p "Do you want to update the secret with a new value? (y/N): " update_choice
        if [[ $update_choice == "y" || $update_choice == "Y" ]]; then
            echo "Adding new version to secret $secret_name..."
            echo -n "$secret_value" | gcloud secrets versions add $secret_name \
                --project=$PROJECT_ID \
                --data-file=-
            echo "Secret $secret_name updated successfully."
        else
            echo "Skipping update for secret $secret_name."
        fi
    fi
}

# List of required secrets (These would be loaded from your environment or input at runtime)
declare -A secrets=(
    ["QUICKBOOKS_CLIENT_ID"]="QuickBooks API Client ID"
    ["QUICKBOOKS_CLIENT_SECRET"]="QuickBooks API Client Secret"
    ["QUICKBOOKS_REFRESH_TOKEN"]="QuickBooks API Refresh Token"
    ["QUICKBOOKS_REALM_ID"]="QuickBooks Realm ID"
    ["EMAIL_USERNAME"]="Email account username"
    ["EMAIL_PASSWORD"]="Email account password"
    ["JWT_SECRET_KEY"]="JWT Secret Key for authentication"
)

# Create each secret
for secret_name in "${!secrets[@]}"; do
    description="${secrets[$secret_name]}"
    
    # In a production environment, these values would be sourced from a secure location
    # For this script, we'll prompt for the values
    read -p "Enter value for $secret_name ($description): " secret_value
    
    # Create the secret
    create_secret "$secret_name" "$secret_value" "$description"
done

# Update the Cloud Run service to use the secrets
echo "Updating Cloud Run service to use the secrets..."
gcloud run services update $SERVICE_NAME \
    --region=$REGION \
    --update-secrets=\
QUICKBOOKS_CLIENT_ID=projects/$PROJECT_ID/secrets/QUICKBOOKS_CLIENT_ID:latest,\
QUICKBOOKS_CLIENT_SECRET=projects/$PROJECT_ID/secrets/QUICKBOOKS_CLIENT_SECRET:latest,\
QUICKBOOKS_REFRESH_TOKEN=projects/$PROJECT_ID/secrets/QUICKBOOKS_REFRESH_TOKEN:latest,\
QUICKBOOKS_REALM_ID=projects/$PROJECT_ID/secrets/QUICKBOOKS_REALM_ID:latest,\
EMAIL_USERNAME=projects/$PROJECT_ID/secrets/EMAIL_USERNAME:latest,\
EMAIL_PASSWORD=projects/$PROJECT_ID/secrets/EMAIL_PASSWORD:latest,\
JWT_SECRET_KEY=projects/$PROJECT_ID/secrets/JWT_SECRET_KEY:latest

# Check if the update was successful
if [ $? -eq 0 ]; then
    echo "Cloud Run service updated successfully with secrets."
else
    echo "Failed to update Cloud Run service with secrets."
    exit 1
fi

echo "===== Secret setup process complete =====" 