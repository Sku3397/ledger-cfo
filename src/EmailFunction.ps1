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

Write-Host "Simplified Entrypoint Script Started."

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
    exit 1 # Exit if listener fails to start
}

Write-Host "Listener started successfully. Waiting for requests..."

while ($listener.IsListening) {
    try {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response

        Write-Host "Received request: $($request.HttpMethod) $($request.Url.AbsolutePath)"

        # Simplified Response - Always OK
        $output = "OK - Simplified Listener"
        $buffer = [System.Text.Encoding]::UTF8.GetBytes($output)

        $response.StatusCode = 200
        $response.ContentType = 'text/plain'
        $response.ContentLength64 = $buffer.Length
        $response.OutputStream.Write($buffer, 0, $buffer.Length)
        $response.Close()

        Write-Host "Sent simplified OK response."

    } catch [System.Net.HttpListenerException] {
        Write-Error "HttpListenerException encountered: $_. Stopping listener."
        break # Exit loop on listener error
    } catch {
        Write-Error "An error occurred processing request: $_"
        # Attempt to send a 500 response if possible, but keep it simple
        try {
            if ($response -ne $null -and $response.OutputStream.CanWrite) {
                 $errorMessage = "Internal Server Error"
                 $buffer = [System.Text.Encoding]::UTF8.GetBytes($errorMessage)
                 $response.StatusCode = 500
                 $response.ContentType = 'text/plain'
                 $response.ContentLength64 = $buffer.Length
                 $response.OutputStream.Write($buffer, 0, $buffer.Length)
                 $response.Close()
            }
        } catch {
             Write-Error "Failed to send error response: $_"
        }
        # Continue listening unless it was an HttpListenerException
    }
}

Write-Host "Listener stopped."
$listener.Close()