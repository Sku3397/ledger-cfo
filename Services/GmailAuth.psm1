# GmailAuth.psm1
# Handles Gmail API OAuth2 token retrieval.

function Get-GmailAccessToken {
    [CmdletBinding()]
    param(
        # Consider adding parameters for creds if not relying solely on env vars
    )

    $ClientId = $env:GMAIL_CLIENT_ID
    $ClientSecret = $env:GMAIL_CLIENT_SECRET
    $RefreshToken = $env:GMAIL_REFRESH_TOKEN
    $TokenUri = "https://oauth2.googleapis.com/token"

    if (-not $ClientId -or -not $ClientSecret -or -not $RefreshToken) {
        Write-Error "Missing required environment variables for Gmail OAuth: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN"
        throw "Missing Gmail OAuth environment variables."
    }

    $Body = @{
        client_id     = $ClientId
        client_secret = $ClientSecret
        refresh_token = $RefreshToken
        grant_type    = "refresh_token"
    }

    try {
        # Write-Host "Requesting new Gmail access token..." # Use Write-CLog in main script
        $response = Invoke-RestMethod -Uri $TokenUri -Method Post -Body $Body -ContentType 'application/x-www-form-urlencoded' -ErrorAction Stop
        # Write-Host "Successfully obtained new Gmail access token." # Use Write-CLog
        return $response.access_token
    }
    catch {
        $errorMessage = "Error refreshing Gmail access token: $($_.Exception.Message)"
        if ($_.Exception.Response) {
            $statusCode = $_.Exception.Response.StatusCode.value__
            $responseBody = $_.Exception.Response.GetResponseStream() | New-Object System.IO.StreamReader | Select-Object -ExpandProperty ReadToEnd
            $errorMessage += " | Status: $statusCode | Response: $responseBody"
        }
        Write-Error $errorMessage
        throw $errorMessage # Re-throw to halt execution if token fails
    }
}

Export-ModuleMember -Function Get-GmailAccessToken 