# Configuration
$ProjectId = "ledger-457022"
$Region = "us-central1"
$ServiceName = "ledger"
$Repository = "cfo-agent-repo"
$ImageName = "ledger"
$ImageTag = "latest"
$GcloudPath = "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$Troubleshooting = $false
$MaxIterations = 20
$IterationCount = 0

# Full image path
$ImagePath = "$Region-docker.pkg.dev/$ProjectId/$Repository/$ImageName:$ImageTag"

# Function to check if Artifact Registry repository exists and create if not
function Ensure-Repository {
    Write-Host "Checking if repository $Repository exists..."
    $repoExists = & $GcloudPath artifacts repositories list --project=$ProjectId --format="value(name)" | Select-String -Pattern $Repository
    if (-not $repoExists) {
        Write-Host "Repository $Repository does not exist. Creating it..."
        & $GcloudPath artifacts repositories create $Repository `
            --repository-format=docker `
            --location=$Region `
            --project=$ProjectId
    } else {
        Write-Host "Repository $Repository exists."
    }
}

# Function to deploy to Cloud Run
function Deploy-ToCloudRun {
    Write-Host "Deploying to Cloud Run..."
    & $GcloudPath run deploy $ServiceName `
        --image $ImagePath `
        --platform managed `
        --region $Region `
        --allow-unauthenticated `
        --project $ProjectId
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error deploying to Cloud Run" -ForegroundColor Red
        return $false
    }
    
    Write-Host "Deployment to Cloud Run completed successfully!" -ForegroundColor Green
    return $true
}

# Function to perform health check
function Test-HealthCheck {
    Write-Host "Performing health check..."
    $serviceUrl = & $GcloudPath run services describe $ServiceName --platform managed --region $Region --format="value(status.url)" --project $ProjectId
    Write-Host "Service URL: $serviceUrl"
    
    try {
        $response = Invoke-WebRequest -Uri "$serviceUrl/trigger" -Method Post -ContentType "application/json" -Body '{"action":"health_check"}' -ErrorAction Stop
        $statusCode = $response.StatusCode
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
    }
    
    Write-Host "Health check status code: $statusCode"
    return $statusCode -eq 200
}

# Function to check logs for errors
function Check-Logs {
    Write-Host "Checking logs for errors..."
    $logs = & $GcloudPath run logs read $ServiceName --limit=50 --project=$ProjectId
    
    $errorCount = 0
    foreach ($line in $logs) {
        if ($line -match "ERROR|Exception|Error:") {
            $errorCount++
            Write-Host "Found error in logs: $line" -ForegroundColor Red
        }
    }
    
    if ($errorCount -eq 0) {
        Write-Host "No errors found in logs" -ForegroundColor Green
        return $true
    } else {
        Write-Host "Found $errorCount errors in logs" -ForegroundColor Red
        return $false
    }
}

# Main script
try {
    Write-Host "Starting deployment of Ledger to Google Cloud Run..." -ForegroundColor Cyan
    
    # Step 1: Build the Docker image
    Write-Host "Building Docker image..." -ForegroundColor Cyan
    docker build -t "$ImageName`:$ImageTag" .
    if ($LASTEXITCODE -ne 0) {
        throw "Error building Docker image"
    }
    
    # Step 2: Ensure repository exists
    Ensure-Repository
    
    # Step 3: Configure Docker to use Google Cloud credentials
    Write-Host "Configuring Docker authentication..." -ForegroundColor Cyan
    & $GcloudPath auth configure-docker "$Region-docker.pkg.dev" --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Error configuring Docker authentication"
    }
    
    # Step 4: Tag the image for Google Cloud Artifact Registry
    Write-Host "Tagging image for Google Cloud Artifact Registry..." -ForegroundColor Cyan
    docker tag "$ImageName`:$ImageTag" $ImagePath
    if ($LASTEXITCODE -ne 0) {
        throw "Error tagging image"
    }
    
    # Step 5: Push the image to Google Cloud Artifact Registry
    Write-Host "Pushing image to Google Cloud Artifact Registry..." -ForegroundColor Cyan
    docker push $ImagePath
    if ($LASTEXITCODE -ne 0) {
        throw "Error pushing image"
    }
    
    # Step 6: Troubleshooting loop
    $deployed = $false
    $healthCheckPassed = $false
    $noErrors = $false
    
    while ($IterationCount -lt $MaxIterations -and ($Troubleshooting -or -not ($deployed -and $healthCheckPassed -and $noErrors))) {
        $IterationCount++
        Write-Host "===== Iteration $IterationCount of $MaxIterations =====" -ForegroundColor Cyan
        
        if (-not $deployed) {
            $deployed = Deploy-ToCloudRun
            if (-not $deployed) {
                Write-Host "Deployment failed, troubleshooting..." -ForegroundColor Yellow
                continue
            }
        }
        
        if (-not $healthCheckPassed) {
            $healthCheckPassed = Test-HealthCheck
            if (-not $healthCheckPassed) {
                Write-Host "Health check failed, checking logs..." -ForegroundColor Yellow
            }
        }
        
        if (-not $noErrors) {
            $noErrors = Check-Logs
            if (-not $noErrors) {
                Write-Host "Errors found in logs, troubleshooting..." -ForegroundColor Yellow
                # TODO: Add automated troubleshooting logic here
                continue
            }
        }
        
        # If everything is successful, break the loop
        if ($deployed -and $healthCheckPassed -and $noErrors) {
            break
        }
    }
    
    # Step 7: Test scheduler jobs if they exist
    Write-Host "Checking for Cloud Scheduler jobs..." -ForegroundColor Cyan
    $schedulerJobs = & $GcloudPath scheduler jobs list --project=$ProjectId | Select-String "cfo-daily-audit"
    
    if ($schedulerJobs) {
        Write-Host "Found scheduler job cfo-daily-audit, running it..." -ForegroundColor Cyan
        & $GcloudPath scheduler jobs run cfo-daily-audit --project=$ProjectId
        
        Write-Host "Checking logs for scheduler job results..." -ForegroundColor Cyan
        Start-Sleep -Seconds 10  # Give the job time to run
        Check-Logs
    } else {
        Write-Host "No scheduler job found named cfo-daily-audit" -ForegroundColor Yellow
    }
    
    # Step 8: Final validation
    Write-Host "Performing final validation..." -ForegroundColor Cyan
    $finalHealth = Test-HealthCheck
    $finalLogs = Check-Logs
    
    # Step 9: Generate report
    Write-Host "Generating deployment report..." -ForegroundColor Cyan
    $serviceUrl = & $GcloudPath run services describe $ServiceName --platform managed --region $Region --format="value(status.url)" --project $ProjectId
    $serviceRevision = & $GcloudPath run services describe $ServiceName --platform managed --region $Region --format="value(status.latestCreatedRevisionName)" --project $ProjectId
    
    $reportContent = @"
# Ledger Deployment Test Report

## Deployment Status
- **Service Name**: $ServiceName
- **Project ID**: $ProjectId
- **Region**: $Region
- **Service URL**: $serviceUrl
- **Revision ID**: $serviceRevision
- **Deployment Iterations**: $IterationCount

## Health Check
- **Status**: $(if ($finalHealth) { "PASSED ✅" } else { "FAILED ❌" })
- **Endpoint**: $serviceUrl/trigger

## Log Analysis
- **Status**: $(if ($finalLogs) { "No Errors ✅" } else { "Errors Found ❌" })

## Scheduler Job
- **Job**: cfo-daily-audit
- **Status**: $(if ($schedulerJobs) { "EXISTS" } else { "NOT FOUND" })
- **Run Result**: $(if ($schedulerJobs) { if ($finalLogs) { "SUCCESS ✅" } else { "ERRORS ❌" } } else { "N/A" })

## Summary
The Ledger service has been $(if ($finalHealth -and $finalLogs) { "successfully" } else { "partially" }) deployed to Google Cloud Run.
$(if (-not ($finalHealth -and $finalLogs)) { "There are still issues that need to be addressed." })

*Report generated on $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")*
"@
    
    $reportContent | Out-File -FilePath "TEST_REPORT.md" -Encoding utf8
    Write-Host "Report generated: TEST_REPORT.md" -ForegroundColor Green
    
    if ($finalHealth -and $finalLogs) {
        Write-Host "Ledger has been successfully deployed to Google Cloud Run!" -ForegroundColor Green
    } else {
        Write-Host "Ledger deployment completed with issues. See TEST_REPORT.md for details." -ForegroundColor Yellow
    }
    
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
} 