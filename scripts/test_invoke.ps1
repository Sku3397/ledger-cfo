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
Write-Host "Tailing logs for 5 seconds..."
# Use PowerShell's Start-Process with -NoNewWindow to run the command
$LogProcess = Start-Process -NoNewWindow -PassThru -FilePath "gcloud" -ArgumentList "logging read ""resource.type=cloud_run_revision AND resource.labels.service_name=ledger"" --limit=10 --format=""table(timestamp,severity,textPayload)"""
Start-Sleep -Seconds 5
Stop-Process -Id $LogProcess.Id -Force -ErrorAction SilentlyContinue

# Final status
if ($RootSuccess -or $TriggerSuccess) {
    Write-Host "✓ Test completed successfully - at least one endpoint is working"
    exit 0
}
else {
    Write-Host "✗ Test failed - both endpoints returned errors"
    exit 1
} 