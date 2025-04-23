Write-Host "Diagnosing gcloud command execution..." -ForegroundColor Cyan

$GcloudPath = "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"

Write-Host "Checking if gcloud path exists..."
if (Test-Path $GcloudPath) {
    Write-Host "gcloud.cmd found at: $GcloudPath" -ForegroundColor Green
} else {
    Write-Host "gcloud.cmd not found at expected location: $GcloudPath" -ForegroundColor Red
    
    # Try to find it elsewhere
    Write-Host "Searching for gcloud.cmd in Program Files..."
    $gcloudPaths = Get-ChildItem -Path "C:\Program Files" -Recurse -Filter "gcloud.cmd" -ErrorAction SilentlyContinue
    $gcloudPaths += Get-ChildItem -Path "C:\Program Files (x86)" -Recurse -Filter "gcloud.cmd" -ErrorAction SilentlyContinue
    
    if ($gcloudPaths.Count -gt 0) {
        Write-Host "Found gcloud.cmd at the following locations:" -ForegroundColor Yellow
        foreach ($path in $gcloudPaths) {
            Write-Host "  $($path.FullName)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Could not find gcloud.cmd anywhere in Program Files" -ForegroundColor Red
    }
}

Write-Host "Trying to execute a simple gcloud command..."
try {
    $output = & $GcloudPath --version
    Write-Host "Command executed successfully:" -ForegroundColor Green
    Write-Host $output
} catch {
    Write-Host "Error executing gcloud command: $_" -ForegroundColor Red
}

Write-Host "Testing if Windows is blocking script execution..."
$executionPolicy = Get-ExecutionPolicy
Write-Host "Current PowerShell execution policy: $executionPolicy" -ForegroundColor Cyan

Write-Host "Testing a direct command call with cmd.exe..."
try {
    $output = cmd.exe /c "$GcloudPath --version"
    Write-Host "Command executed through cmd.exe successfully:" -ForegroundColor Green
    Write-Host $output
} catch {
    Write-Host "Error executing through cmd.exe: $_" -ForegroundColor Red
}

Write-Host "Checking Google Cloud authentication..."
try {
    $output = & $GcloudPath auth list
    Write-Host "Authentication information:" -ForegroundColor Green
    Write-Host $output
} catch {
    Write-Host "Error checking authentication: $_" -ForegroundColor Red
}

Write-Host "Checking active Google Cloud project..."
try {
    $output = & $GcloudPath config list project
    Write-Host "Project configuration:" -ForegroundColor Green
    Write-Host $output
} catch {
    Write-Host "Error checking project configuration: $_" -ForegroundColor Red
}

Write-Host "Diagnostic complete" -ForegroundColor Cyan 