# EmailSender.psm1
# Handles sending emails via the Gmail API.

#Requires -Module ./GmailAuth.psm1

# Import helper functions if needed (e.g., Invoke-RestMethodWithRetry)
# Sourcing the main script is not ideal, consider refactoring shared functions
# For now, assume Invoke-RestMethodWithRetry is available or redefine locally.

# Simple Retry Wrapper (Copied from EmailFunction.ps1 - Refactor candidate)
function Invoke-RestMethodWithRetryLocal {
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
            # Need a logging mechanism here too, ideally passed in or global
            Write-Warning "Invoke-RestMethod failed (Attempt $attempt/$($MaxRetries + 1)). Error: $($_.Exception.Message)"
            if ($attempt -gt $MaxRetries) {
                Write-Error "Max retries reached for Invoke-RestMethod."
                throw $_ # Re-throw the last exception
            }
            Write-Warning "Retrying in $DelaySeconds seconds..."
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

function Send-CfoReplyEmail {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$To, # Should include name and email, e.g., "User <user@example.com>"
        [Parameter(Mandatory=$true)]
        [string]$Subject,
        [Parameter(Mandatory=$true)]
        [string]$Body,
        [Parameter(Mandatory=$true)]
        [string]$ThreadId,
        [Parameter(Mandatory=$false)]
        [string]$OriginalMessageId # Needed for In-Reply-To / References headers
    )

    Write-Host "Preparing to send reply email to $To with subject '$Subject' (Thread: $ThreadId)"

    try {
        $AccessToken = Get-GmailAccessToken
        if (-not $AccessToken) {
            throw "Failed to get Gmail access token for sending email."
        }

        $fromAddress = $env:CFO_AGENT_EMAIL
        if (-not $fromAddress) {
            throw "CFO_AGENT_EMAIL environment variable not set."
        }

        # Construct MIME message parts
        $mimeMessage = @(
            "From: $fromAddress",
            "To: $To",
            "Subject: $Subject",
            "Content-Type: text/plain; charset=utf-8",
            "Content-Transfer-Encoding: base64"
        )
        # Add threading headers if original message ID is available
        if ($OriginalMessageId) {
            $mimeMessage += "In-Reply-To: $OriginalMessageId"
            $mimeMessage += "References: $OriginalMessageId"
        }
        $mimeMessage += "", # Empty line separating headers from body
                         $Body

        $mimeContent = $mimeMessage -join "`r`n" # Use CRLF line endings for MIME
        $base64UrlEncodedContent = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($mimeContent)).Replace('+', '-').Replace('/', '_').Replace("=", "")

        $sendUri = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
        $sendHeaders = @{
            Authorization = "Bearer $AccessToken"
            "Content-Type" = "application/json"
        }
        $sendBody = @{
            raw = $base64UrlEncodedContent
            threadId = $ThreadId # Ensure reply stays in the same thread
        } | ConvertTo-Json

        Write-Host "Sending email via Gmail API..."
        $response = Invoke-RestMethodWithRetryLocal -Parameters @{ Method = 'Post'; Uri = $sendUri; Headers = $sendHeaders; Body = $sendBody }

        if ($response.id) {
            Write-Host "Successfully sent email. Message ID: $($response.id)"
            return $true
        } else {
            Write-Error "Gmail API did not return a message ID after sending."
            return $false
        }
    }
    catch {
        Write-Error "Failed to send reply email: $($_.Exception.Message)"
        # Potentially log full exception details
        return $false
    }
}

Export-ModuleMember -Function Send-CfoReplyEmail 