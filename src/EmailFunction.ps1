#Requires -Modules @{ModuleName = 'ThreadJob'; ModuleVersion = '2.0.3'}

# Import necessary modules if Dispatch-EmailCommand requires them
# Import-Module PnP.PowerShell -ErrorAction SilentlyContinue
# Import-Module QuickBooks -ErrorAction SilentlyContinue

# Load the command dispatcher if it exists
if (Test-Path "/app/Dispatch-EmailCommand.ps1") {
    . "/app/Dispatch-EmailCommand.ps1"
} else {
    Write-Error "Dispatch-EmailCommand.ps1 not found in /app."
    # Define a dummy function if the real one is missing, to allow listener startup
    function Dispatch-EmailCommand {
        param()
        Write-Warning "Dispatch-EmailCommand.ps1 was not found. Using dummy implementation."
        return "Dummy Dispatch: No command processed."
    }
}

# Get port from environment variable or default to 8080
$port = $env:PORT
if (-not $port) {
    $port = 8080
    Write-Host "PORT environment variable not set. Defaulting to $port."
}

$prefix = "http://0.0.0.0:$($port)/"
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add($prefix)

Write-Host "Listening on $prefix..."
try {
    $listener.Start()
} catch {
    Write-Error "Failed to start listener: $_"
    exit 1
}

Write-Host "Listener started successfully."

while ($listener.IsListening) {
    try {
        # Wait for a request
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response

        Write-Host "Received request: $($request.HttpMethod) $($request.Url.AbsolutePath)"

        # Routing logic
        if ($request.HttpMethod -eq 'GET' -and $request.Url.AbsolutePath -eq '/process-email') {
            try {
                # Execute the core logic
                $result = Dispatch-EmailCommand # Assuming Dispatch-EmailCommand takes no parameters for now
                $output = ConvertTo-Json -InputObject @{ status = 'success'; data = $result } -Depth 3
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($output)

                $response.StatusCode = 200
                $response.ContentType = 'application/json'
                $response.ContentLength64 = $buffer.Length
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
            } catch {
                Write-Error "Error executing Dispatch-EmailCommand: $_"
                $errorMessage = ConvertTo-Json -InputObject @{ status = 'error'; message = "Internal Server Error: $($_.Exception.Message)" } -Depth 3
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($errorMessage)
                $response.StatusCode = 500
                $response.ContentType = 'application/json'
                $response.ContentLength64 = $buffer.Length
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
            }
        } else {
            # Not Found
            $errorMessage = ConvertTo-Json -InputObject @{ status = 'error'; message = 'Not Found' } -Depth 3
            $buffer = [System.Text.Encoding]::UTF8.GetBytes($errorMessage)
            $response.StatusCode = 404
            $response.ContentType = 'application/json'
            $response.ContentLength64 = $buffer.Length
            $response.OutputStream.Write($buffer, 0, $buffer.Length)
        }

        $response.Close()
        Write-Host "Response sent for $($request.Url.AbsolutePath)"

    } catch {
        Write-Error "An error occurred processing request: $_"
        # Attempt to send a 500 response if possible
        try {
            if ($response -ne $null -and -not $response.OutputStream.CanWrite) {
                 $errorMessage = ConvertTo-Json -InputObject @{ status = 'error'; message = "Internal Server Error: $($_.Exception.Message)" } -Depth 3
                 $buffer = [System.Text.Encoding]::UTF8.GetBytes($errorMessage)
                 $response.StatusCode = 500
                 $response.ContentType = 'application/json'
                 $response.ContentLength64 = $buffer.Length
                 $response.OutputStream.Write($buffer, 0, $buffer.Length)
                 $response.Close()
            }
        } catch {
             Write-Error "Failed to send error response: $_"
        }
        # Consider whether to continue or exit on error
        # If the listener itself fails, we might need to break the loop
        if ($_.Exception -is [System.Net.HttpListenerException]) {
             Write-Error "HttpListenerException encountered. Stopping listener."
             break
        }
    }
}

Write-Host "Listener stopped."
$listener.Close()