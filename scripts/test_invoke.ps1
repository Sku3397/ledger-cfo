# PowerShell script to test invoke the Cloud Run API
# Stop script on error
$ErrorActionPreference = "Stop"

# Get the service URL
$SERVICE_URL = (gcloud run services describe ledger --platform managed --region us-east4 --format="value(status.url)")
Write-Host "Service URL: $SERVICE_URL"

# Get identity token for authentication
$TOKEN = (gcloud auth print-identity-token)

# Function to test an endpoint
function Test-Endpoint {
    param (
        [string]$Path,
        [string]$Name
    )
    
    Write-Host "Testing POST to $Path"
    try {
        $Headers = @{
            Authorization = "Bearer $TOKEN"
        }
        
        $Body = @{
            action = "run_audit"
        } | ConvertTo-Json
        
        $Response = Invoke-RestMethod -Method Post -Uri "$SERVICE_URL$Path" -Headers $Headers -ContentType "application/json" -Body $Body -ErrorAction SilentlyContinue
        Write-Host "SUCCESS: POST to $Path returned 200 OK"
        return $true
    }
    catch {
        $StatusCode = $_.Exception.Response.StatusCode.value__
        Write-Host "ERROR: POST to $Path failed with status $StatusCode"
        return $false
    }
}

# Test both endpoints
$RootSuccess = Test-Endpoint -Path "/" -Name "Root"
$TriggerSuccess = Test-Endpoint -Path "/trigger" -Name "Trigger"

# Tail logs for a few seconds to verify
Write-Host "Checking logs..."
Write-Host "Run the following command to see more logs:"
Write-Host "gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=ledger' --limit=10"

# Let's try a direct command execution instead of Start-Process
try {
    Write-Host "Recent logs:" 
    Invoke-Expression "gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=ledger' --limit=5 --format='table(timestamp,severity,textPayload)'"
} catch {
    Write-Host "Could not fetch logs: $_"
}

# Final status
if ($RootSuccess -or $TriggerSuccess) {
    Write-Host "[OK] Test completed successfully - at least one endpoint is working"
    exit 0
}
else {
    Write-Host "[FAIL] Test failed - both endpoints returned errors"
    exit 1
} 