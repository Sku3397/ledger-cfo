#!/bin/bash
# Script to test the deployed CFO Agent endpoints

# Set variables
PROJECT_ID=ledger-457022
REGION=us-east4
SERVICE_NAME=cfo-agent

# Load service information if available
if [ -f service_info.txt ]; then
    source service_info.txt
    echo "Using service URL: $SERVICE_URL"
else
    # Get service URL if not loaded from file
    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)')
    if [ -z "$SERVICE_URL" ]; then
        echo "Error: Could not determine service URL. Make sure the service is deployed."
        exit 1
    fi
    echo "Retrieved service URL: $SERVICE_URL"
fi

# Ensure the service URL doesn't end with a slash
SERVICE_URL=${SERVICE_URL%/}

# Print banner
echo "===== Testing CFO Agent endpoints ====="
echo "Project: $PROJECT_ID"
echo "Service: $SERVICE_NAME"
echo "URL: $SERVICE_URL"

# Function to test an endpoint
test_endpoint() {
    local endpoint=$1
    local method=$2
    local payload=$3
    local expected_status=$4
    local description=$5
    
    echo -e "\n-> Testing $description"
    echo "   Endpoint: $endpoint"
    echo "   Method: $method"
    
    if [ "$method" == "GET" ]; then
        # For GET requests
        response=$(curl -s -o response.txt -w "%{http_code}" -X GET "$SERVICE_URL$endpoint")
    else
        # For POST requests with payload
        echo "   Payload: $payload"
        response=$(curl -s -o response.txt -w "%{http_code}" \
            -X POST "$SERVICE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -d "$payload")
    fi
    
    # Check the response status code
    if [ "$response" -eq "$expected_status" ]; then
        echo "   ✓ Success: Status code $response"
        # Print the response body (trimmed if it's too long)
        body=$(cat response.txt)
        if [ ${#body} -gt 500 ]; then
            echo "   Response: ${body:0:500}... (truncated)"
        else
            echo "   Response: $body"
        fi
        return 0
    else
        echo "   ✗ Failure: Expected status code $expected_status, got $response"
        echo "   Response: $(cat response.txt)"
        return 1
    fi
}

# Test 1: Health check endpoint
test_endpoint "/health" "GET" "" 200 "Health check endpoint"

# Test 2: Trigger endpoint with data refresh action
DATA_REFRESH_PAYLOAD='{"trigger_type":"manual_action","action":"refresh_data"}'
test_endpoint "/trigger" "POST" "$DATA_REFRESH_PAYLOAD" 200 "Data refresh action"

# Test 3: Trigger endpoint with financial report task
REPORT_PAYLOAD='{"trigger_type":"scheduled_task","task_type":"daily_report","start_date":"2025-01-01","end_date":"2025-01-31"}'
test_endpoint "/trigger" "POST" "$REPORT_PAYLOAD" 200 "Daily report task"

# Test 4: Trigger endpoint with simulated email
EMAIL_PAYLOAD='{
    "trigger_type":"email",
    "email_data":{
        "message_id":"test-123",
        "sender":"test@example.com",
        "subject":"Test Email",
        "body":"Please create an invoice for Customer XYZ for consulting services. Amount: $500."
    }
}'
test_endpoint "/trigger" "POST" "$EMAIL_PAYLOAD" 200 "Email trigger"

echo -e "\n===== Testing complete =====" 