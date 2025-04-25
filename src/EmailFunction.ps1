# EmailFunction.ps1
# Cloud Run entrypoint for processing Gmail messages.

#region Imports and Setup
using namespace System.Net

# Import our custom modules
Import-Module ../Services/GmailAuth.psm1 -Force
Import-Module ../Services/CommandParser.psm1 -Force
Import-Module ../Services/InvoiceManager.psm1 -Force
Import-Module ../Services/Bookkeeper.psm1 -Force
Import-Module ../Services/Reporting.psm1 -Force
Import-Module ../Services/QBOClient.psm1 -Force # Needed by InvoiceManager, etc.
Import-Module ../Services/EmailSender.psm1 -Force # <-- Add this

# Cloud Run Port
$Port = $env:PORT
if (-not $Port) {
    $Port = 8080
}
$Prefix = "http://+:$Port/"

# Ensure logs directory exists for any modules that might still use it (though ideally they shouldn't)
$LogBaseDir = Join-Path $PSScriptRoot ".." "logs"
if (-not (Test-Path $LogBaseDir)) {
    New-Item -ItemType Directory -Path $LogBaseDir -Force | Out-Null
}

#endregion

#region Cloud Logging
function Write-CLog {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Message,
        [ValidateSet('INFO', 'WARN', 'ERROR', 'DEBUG')]
        [string]$Level = 'INFO'
    )
    # Simple stdout logging, Cloud Logging will capture and parse
    $Timestamp = Get-Date -Format 'o' # ISO 8601 format
    Write-Host "$Timestamp [$Level] - $Message"
    if ($Level -eq 'ERROR') {
        Write-Error $Message -ErrorAction Continue # Write to stderr as well
    }
}
#endregion

#region Utility Functions

# Simple Retry Wrapper for Invoke-RestMethod
function Invoke-RestMethodWithRetry {
    param(
        [Parameter(Mandatory=$true)]
        [hashtable]$Parameters,
        [int]$MaxRetries = 1,
        [int]$DelaySeconds = 2
    )
    
    $attempt = 0
    while ($true) {
        try {
            return Invoke-RestMethod @Parameters
        }
        catch {
            $attempt++
            Write-CLog "Invoke-RestMethod failed (Attempt $attempt/$($MaxRetries + 1)). Error: $($_.Exception.Message)" -Level WARN
            if ($attempt -gt $MaxRetries) {
                Write-CLog "Max retries reached for Invoke-RestMethod." -Level ERROR
                throw $_ # Re-throw the last exception
            }
            Write-CLog "Retrying in $DelaySeconds seconds..." -Level WARN
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

# Parses Gmail Full Message Format
function Parse-GmailMessage {
    param(
        [Parameter(Mandatory=$true)]
        [PSCustomObject]$RawMessage
    )

    $output = [PSCustomObject]@{
        Id = $RawMessage.id
        ThreadId = $RawMessage.threadId
        From = $null
        To = $null # Might be useful
        Subject = $null
        Body = $null
        Error = $null
    }

    try {
        # Extract Headers
        $headers = @{}
        $RawMessage.payload.headers | ForEach-Object { $headers[$_.name] = $_.value }

        $output.From = $headers.From
        $output.To = $headers.To
        $output.Subject = $headers.Subject

        # Extract Body (handle multipart)
        if ($RawMessage.payload.mimeType -like 'text/plain') {
            $bodyData = $RawMessage.payload.body.data
        } elseif ($RawMessage.payload.mimeType -like 'multipart/*') {
            # Find the text/plain part
            $textPart = $RawMessage.payload.parts | Where-Object { $_.mimeType -eq 'text/plain' } | Select-Object -First 1
            if ($textPart) {
                $bodyData = $textPart.body.data
            } else {
                 Write-CLog "No text/plain part found in multipart message $($RawMessage.id)." -Level WARN
                 # Fallback: try first part?
                 $bodyData = $RawMessage.payload.parts[0].body.data
            }
        } else {
             Write-CLog "Unsupported top-level MIME type: $($RawMessage.payload.mimeType) for message $($RawMessage.id)." -Level WARN
        }

        if ($bodyData) {
            # Decode Base64URL
            $base64 = $bodyData.Replace('-', '+').Replace('_', '/')
            # Add padding if needed
            $padding = ($base64.Length % 4) 
            if ($padding -ne 0) { $base64 += ('=' * (4 - $padding)) }
            $output.Body = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($base64))
        } else {
             $output.Body = "(Could not extract body)"
        }
    }
    catch {
        $output.Error = "Error parsing raw Gmail message: $($_.Exception.Message)"
        Write-CLog $output.Error -Level ERROR
    }

    return $output
}

# Main Dispatch Logic
function Dispatch-EmailCommand {
    param(
        [Parameter(Mandatory=$true)]
        [PSCustomObject]$RawMessage
    )

    Write-CLog "Dispatching raw message ID: $($RawMessage.id)"
    $parsedEmail = Parse-GmailMessage -RawMessage $RawMessage

    if ($parsedEmail.Error) {
        Write-CLog "Failed to parse email $($RawMessage.id): $($parsedEmail.Error)" -Level ERROR
        # Don't send reply on parsing errors to avoid loops/noise
        return
    }

    # Extract original message ID for threading headers
    $originalMessageIdHeader = $RawMessage.payload.headers | Where-Object { $_.name -eq 'Message-ID' } | Select-Object -First 1
    $originalMessageId = if ($originalMessageIdHeader) { $originalMessageIdHeader.value } else { $null }

    # Check Authorized Senders
    $AuthorizedSenders = ($env:AUTHORIZED_EMAIL_SENDERS -split ',').Trim()
    $senderEmail = ($parsedEmail.From -split '[<>]')[-1] # Extract email from 'Name <email@domain.com>'
    if ($AuthorizedSenders -notcontains $senderEmail) {
        Write-CLog "Skipping email from unauthorized sender: $($parsedEmail.From) ($senderEmail)" -Level WARN
        # Mark as read later, but don't process or reply
        return
    }

    Write-CLog "Processing command from $($parsedEmail.From) - Subject: $($parsedEmail.Subject)" -Level INFO

    # Use CommandParser
    $commandDetails = Parse-EmailCommand -Subject $parsedEmail.Subject -Body $parsedEmail.Body
    $result = $null
    $serviceInvoked = $false

    try {
        # Switch based on command
        switch ($commandDetails.Command) {
            'GenerateInvoice' {
                Write-CLog "Invoking InvoiceManager for estimate $($commandDetails.Parameters.EstimateID)" -Level DEBUG
                # TODO: Update InvoiceManager signature if needed
                $result = Invoke-NewInvoice -CommandParameters $commandDetails.Parameters
                $serviceInvoked = $true
            }
            'RecordPayment' { # Assuming CommandParser might return this
                 Write-CLog "Invoking Bookkeeper for payment processing" -Level DEBUG
                 # TODO: Update Bookkeeper signature if needed
                 $result = Invoke-RecordPayment -CommandParameters $commandDetails.Parameters
                 $serviceInvoked = $true
            }
             'GetReport' { # Assuming CommandParser might return this
                 Write-CLog "Invoking Reporting for report generation" -Level DEBUG
                 # TODO: Update Reporting signature if needed
                 $result = Invoke-GetPnl -CommandParameters $commandDetails.Parameters
                 $serviceInvoked = $true
            }
            default {
                Write-CLog "Command '$($commandDetails.Command)' not recognized or failed parsing." -Level WARN
                $tmpMessage = $commandDetails.Error # Use error from parser if available
                # Ensure Message is not null/empty
                if (-not $tmpMessage) { $tmpMessage = "Unrecognized command or parsing failed." }
                $result = [PSCustomObject]@{
                    Success = $false
                    Message = $tmpMessage # Corrected assignment
                }
                # Indicate that processing was attempted for unknown commands to trigger a reply
                $serviceInvoked = $true 
            }
        }
    } # <-- End of Try block
    catch {
        # Catch errors from the service module invocation
        Write-CLog "Error invoking service for command '$($commandDetails.Command)': $($_.Exception.Message)" -Level ERROR
        $result = [PSCustomObject]@{ 
            Success = $false; 
            Message = "Internal error processing command: $($_.Exception.Message)" 
        }
        # Ensure we still try to send a reply for service errors
        $serviceInvoked = $true 
    } # <-- End of Catch block

    # Send Reply only if a service was invoked (successfully or with error)
    if ($serviceInvoked -and $result) { # Ensure $result is populated
        $replySubject = "Re: $($parsedEmail.Subject)"
        $replyBody = ""
        if ($result.Success) {
            $replySubject += " - Success"
            $replyBody = "Command executed successfully. `n`nDetails: $($result.Message)"
             # Add specific details if available (e.g., Invoice URL/ID)
             if ($result.InvoiceID) { $replyBody += "`nInvoice ID: $($result.InvoiceID)" }
             if ($result.InvoiceUrl) { $replyBody += "`nInvoice URL: $($result.InvoiceUrl)" }
             if ($result.ReportUrl) { $replyBody += "`nReport URL: $($result.ReportUrl)" }
        } else {
            $replySubject += " - Failed"
            $replyBody = "Command execution failed. `n`nReason: $($result.Message)"
            # TODO: Consider including a request ID or partial log safely?
        }

        # Use the new EmailSender module
        Send-CfoReplyEmail -To $parsedEmail.From `
                           -Subject $replySubject `
                           -Body $replyBody `
                           -ThreadId $parsedEmail.ThreadId `
                           -OriginalMessageId $originalMessageId # Pass Original Message ID
    }
    else {
         Write-CLog "No reply sent for message ID: $($RawMessage.id) (likely unauthorized sender or no service invoked)." -Level INFO
    }
}

#endregion

#region HTTP Server Logic

$Listener = New-Object System.Net.HttpListener
$Listener.Prefixes.Add($Prefix)

Write-CLog "Starting HTTP listener on $Prefix..." -Level INFO
$Listener.Start()

while ($Listener.IsListening) {
    Write-CLog "Waiting for request..." -Level DEBUG
    $Context = $Listener.GetContext() # Blocks until request
    $Request = $Context.Request
    $Response = $Context.Response

    $statusCode = 200
    $responseBody = "OK"

    Write-CLog "Received $($Request.HttpMethod) request for $($Request.Url.AbsolutePath)" -Level INFO

    if ($Request.HttpMethod -eq "GET" -and $Request.Url.AbsolutePath -eq "/process-email") {
        try {
            Write-CLog "Processing /process-email request..." -Level INFO
            $startTime = Get-Date

            $AccessToken = Get-GmailAccessToken
            if (-not $AccessToken) {
                throw "Failed to get Gmail access token."
            }

            # List unread messages
            $listUri = "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=is:unread label:inbox"
            $listHeaders = @{ Authorization = "Bearer $AccessToken" }
            Write-CLog "Listing unread messages..." -Level DEBUG
            $messagesResponse = Invoke-RestMethodWithRetry -Parameters @{ Method = 'Get'; Uri = $listUri; Headers = $listHeaders }
            $messageIds = $messagesResponse.messages # This might be null if no messages

            if ($messageIds -and $messageIds.Count -gt 0) {
                Write-CLog "Found $($messageIds.Count) unread messages." -Level INFO

                foreach ($msgHeader in $messageIds) {
                    $messageId = $msgHeader.id
                    Write-CLog "Fetching full message ID: $messageId" -Level DEBUG
                    $getUri = "https://gmail.googleapis.com/gmail/v1/users/me/messages/$($messageId)?format=full"
                    $getHeaders = @{ Authorization = "Bearer $AccessToken" }
                    $fullMessage = $null
                    $dispatchError = $null

                    try {
                        $fullMessage = Invoke-RestMethodWithRetry -Parameters @{ Method = 'Get'; Uri = $getUri; Headers = $getHeaders }
                        Dispatch-EmailCommand -RawMessage $fullMessage
                    }
                    catch {
                        $dispatchError = "Error dispatching/processing message $messageId: $($_.Exception.Message)"
                        Write-CLog $dispatchError -Level ERROR
                        # TODO: Send error reply?
                    }
                    
                    # Mark as read regardless of processing errors to avoid loops
                    Write-CLog "Marking message $messageId as read..." -Level DEBUG
                    $modifyUri = "https://gmail.googleapis.com/gmail/v1/users/me/messages/$messageId/modify"
                    $modifyHeaders = @{ Authorization = "Bearer $AccessToken"; Content_Type = 'application/json' }
                    $modifyBody = (@{ removeLabelIds = @("UNREAD") } | ConvertTo-Json)
                    try {
                         Invoke-RestMethodWithRetry -Parameters @{ Method = 'Post'; Uri = $modifyUri; Headers = $modifyHeaders; Body = $modifyBody }
                         Write-CLog "Successfully marked $messageId as read." -Level INFO
                    } catch {
                         Write-CLog "Failed to mark message $messageId as read: $($_.Exception.Message)" -Level ERROR
                         # Log error but continue - important not to get stuck
                    }
                }
            } else {
                 Write-CLog "No unread messages found." -Level INFO
            }
            
            $duration = (Get-Date) - $startTime
            Write-CLog "/process-email completed in $($duration.TotalSeconds) seconds." -Level INFO
            $responseBody = "Processed emails successfully."
        }
        catch {
            Write-CLog "Error processing /process-email: $($_.Exception.Message)" -Level ERROR
            $statusCode = 500
            $responseBody = "Internal Server Error: $($_.Exception.Message)"
        }
    }
    elseif ($Request.Url.AbsolutePath -eq "/health") {
        $statusCode = 200
        $responseBody = "Healthy"
    }
    else {
        $statusCode = 404
        $responseBody = "Not Found"
    }

    # Send Response
    $Response.StatusCode = $statusCode
    $Response.ContentType = "text/plain"
    $buffer = [System.Text.Encoding]::UTF8.GetBytes($responseBody)
    $Response.ContentLength64 = $buffer.Length
    $Response.OutputStream.Write($buffer, 0, $buffer.Length)
    $Response.Close()
    Write-CLog "Responded with status $statusCode" -Level DEBUG
}

Write-CLog "HTTP Listener stopped." -Level INFO
#endregion 