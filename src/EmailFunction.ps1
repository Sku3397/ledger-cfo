# Commenting out #Requires as a test
# #Requires -Modules @{ModuleName = 'ThreadJob'; ModuleVersion = '2.0.3'}

# Import necessary modules if Dispatch-EmailCommand requires them
# Import-Module PnP.PowerShell -ErrorAction SilentlyContinue
# Import-Module QuickBooks -ErrorAction SilentlyContinue

# Load the command dispatcher if it exists
if (Test-Path "/app/Dispatch-EmailCommand.ps1") {
    . "/app/Dispatch-EmailCommand.ps1"
} else {
    Write-Error "Dispatch-EmailCommand.ps1 not found in /app."
    # Define a dummy function if the real one is missing, to allow server startup
    function Dispatch-EmailCommand {
        param()
        Write-Warning "Dispatch-EmailCommand.ps1 was not found. Using dummy implementation."
        return "Dummy Dispatch: No command processed."
    }
}

# Import Pode module
try {
    Import-Module Pode
    Write-Host "Pode module imported successfully."
} catch {
    Write-Error "Failed to import Pode module: $_"
    exit 1
}

Write-Host "Simplified Entrypoint Script Started."

# Get port from environment variable or default to 8080
$port = $env:PORT
if (-not $port) {
    $port = 8080
    Write-Host "PORT environment variable not set. Defaulting to $port."
}

# Pode Server Configuration
$endpoint = @{ Address = '0.0.0.0'; Port = $port; Protocol = 'Http' }

Write-Host "Starting Pode server on $($endpoint.Address):$($endpoint.Port)..."

Start-PodeServer -Endpoint $endpoint -ScriptBlock {
    # Middleware for basic logging
    Add-PodeMiddleware -Name 'RequestLogger' -ScriptBlock {
        param($Request, $Response)
        Write-Host "Pode Request: $($Request.HttpMethod) $($Request.Url.AbsolutePath)"
        # Note: File logging removed for simplicity, relying on stdout/stderr now
    }
    Use-PodeMiddleware -Name 'RequestLogger'

    # Define Route for /process-email
    Add-PodeRoute -Method Get -Path '/process-email' -ScriptBlock {
        param($Request, $Response)
        try {
            Write-Host "Executing Dispatch-EmailCommand..."
            $result = Dispatch-EmailCommand
            $output = @{ status = 'success'; data = $result }
            Write-PodeJsonResponse -Value $output
        } catch {
            Write-Error "Error executing Dispatch-EmailCommand via Pode: $_"
            $errorMessage = @{ status = 'error'; message = "Internal Server Error: $($_.Exception.Message)" }
            $Response.StatusCode = 500
            Write-PodeJsonResponse -Value $errorMessage
        }
    }

    # Default route for 404 (optional, Pode handles this by default but can customize)
    # Add-PodeRoute -Method * -Path '*' -ScriptBlock {
    #     param($Request, $Response)
    #     $Response.StatusCode = 404
    #     Write-PodeJsonResponse -Value @{ status = 'error'; message = 'Not Found' }
    # }

    Write-Host "Pode server configured and running."
}

# Start-PodeServer blocks execution, so script effectively ends here unless server stops.
Write-Host "Pode server stopped."