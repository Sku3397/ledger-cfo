# QBOClient.psm1
# Wrapper for QuickBooks Online API interactions.

#Requires -Modules Posh-OAuth # Or handle OAuth manually

# Define required environment variables early
$RequiredEnvVars = @(
    'QUICKBOOKS_CLIENT_ID',
    'QUICKBOOKS_CLIENT_SECRET',
    'QUICKBOOKS_REFRESH_TOKEN',
    'QUICKBOOKS_REALM_ID',
    'QUICKBOOKS_ENVIRONMENT' # 'sandbox' or 'production'
)

foreach ($var in $RequiredEnvVars) {
    if (-not $env.$var) {
        Write-Error "Missing required QBO environment variable: $var"
        # Throwing here will prevent the module from loading if config is missing
        throw "Missing QBO environment variable: $var"
    }
}

# Global state for the access token (consider better state management if needed)
$script:qboAccessToken = $null
$script:qboTokenExpiry = [DateTimeOffset]::MinValue

# Simple Retry Wrapper (Copied from EmailFunction.ps1 - Refactor candidate)
function Invoke-RestMethodWithRetryLocal {
    param(
        [Parameter(Mandatory=$true)]
        [hashtable]$Parameters,
        [int]$MaxRetries = 1,
        [int]$DelaySeconds = 2,
        [Action]$RetryAction = $null # Action to perform before retrying (e.g., refresh token)
    )
    $attempt = 0
    while ($true) {
        try {
            return Invoke-RestMethod @Parameters
        }
        catch [System.Net.WebException] {
            $attempt++
            $statusCode = $_.Exception.Response.StatusCode.value__
            $responseBody = "(Could not read response body)"
            try {
                 $responseStream = $_.Exception.Response.GetResponseStream()
                 $reader = New-Object System.IO.StreamReader($responseStream)
                 $responseBody = $reader.ReadToEnd()
                 $reader.Close()
                 $responseStream.Close()
            } catch { 
                Write-Warning "Error reading response body from WebException: $($_.Exception.Message)"
            }

            Write-Warning "Invoke-RestMethod failed (Attempt $attempt/$($MaxRetries + 1)). Status: $statusCode. Error: $($_.Exception.Message). Response: $responseBody"
            
            # Specific handling for 401 Unauthorized - likely needs token refresh
            if ($statusCode -eq 401 -and $RetryAction) {
                 Write-Warning "Received 401 Unauthorized. Attempting retry action (token refresh)..."
                 try {
                     Invoke-Command $RetryAction
                 } catch {
                     Write-Error "RetryAction failed: $($_.Exception.Message)" 
                     # Don't retry if the retry action itself failed
                     throw "Failed to execute RetryAction after 401: $($_.Exception.Message)"
                 }
                 # Reset attempt count after successful retry action to allow full retries with new token
                 # $attempt = 0 # Or just continue the loop once
            }
            elseif ($attempt -gt $MaxRetries) {
                Write-Error "Max retries reached for Invoke-RestMethod."
                throw $_ # Re-throw the last exception
            }

            Write-Warning "Retrying in $DelaySeconds seconds..."
            Start-Sleep -Seconds $DelaySeconds
        }
        catch {
             # Catch non-WebException errors
             $attempt++
             Write-Warning "Invoke-RestMethod failed (Attempt $attempt/$($MaxRetries + 1)). Non-HTTP Error: $($_.Exception.Message)"
             if ($attempt -gt $MaxRetries) {
                Write-Error "Max retries reached for Invoke-RestMethod."
                throw $_ # Re-throw the last exception
            }
            Write-Warning "Retrying in $DelaySeconds seconds..."
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

#region Configuration
function Get-QBOConfig {
    $envProd = $env:QUICKBOOKS_ENVIRONMENT -eq 'production'
    return [PSCustomObject]@{
        ClientID     = $env:QUICKBOOKS_CLIENT_ID
        ClientSecret = $env:QUICKBOOKS_CLIENT_SECRET
        RefreshToken = $env:QUICKBOOKS_REFRESH_TOKEN
        RealmID      = $env:QUICKBOOKS_REALM_ID
        BaseUrl      = if ($envProd) { "https://quickbooks.api.intuit.com" } else { "https://sandbox-quickbooks.api.intuit.com" }
        TokenUrl     = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
        MinorVersion = "65" # Or pull from config/env if needed
    }
}

#endregion

#region Authentication
function Refresh-QBOAccessToken {
    Write-Host "Refreshing QBO Access Token..."
    $config = Get-QBOConfig

    $headers = @{
        "Authorization" = "Basic $([System.Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes("$($config.ClientID):$($config.ClientSecret)")))"
        "Accept"        = "application/json"
    }
    $body = @{
        grant_type    = "refresh_token"
        refresh_token = $config.RefreshToken
    }

    try {
        $response = Invoke-RestMethod -Uri $config.TokenUrl -Method Post -Headers $headers -Body $body -ContentType 'application/x-www-form-urlencoded' -ErrorAction Stop
        
        $script:qboAccessToken = $response.access_token
        # Set expiry slightly earlier than actual to be safe (e.g., 5 minutes)
        $script:qboTokenExpiry = [DateTimeOffset]::UtcNow.AddSeconds($response.expires_in - 300)
        
        Write-Host "Successfully refreshed QBO Access Token. Expires: $($script:qboTokenExpiry.ToString('o'))"
    }
    catch {
        $errorMessage = "Error refreshing QBO access token: $($_.Exception.Message)"
        if ($_.Exception.Response) {
            $statusCode = $_.Exception.Response.StatusCode.value__
            $responseBody = $_.Exception.Response.GetResponseStream() | New-Object System.IO.StreamReader | Select-Object -ExpandProperty ReadToEnd
            $errorMessage += " | Status: $statusCode | Response: $responseBody"
        }
        Write-Error $errorMessage
        # Clear potentially invalid token info
        $script:qboAccessToken = $null
        $script:qboTokenExpiry = [DateTimeOffset]::MinValue
        throw $errorMessage # Re-throw to signal failure
    }
}

function Get-QBOAccessToken {
    if (-not $script:qboAccessToken -or $script:qboTokenExpiry -lt [DateTimeOffset]::UtcNow) {
        Refresh-QBOAccessToken
    }
    if (-not $script:qboAccessToken) {
        throw "Failed to obtain valid QBO Access Token after refresh attempt."
    }
    return $script:qboAccessToken
}
#endregion

#region API Calls
function Invoke-QBOApiRequest {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Endpoint, # e.g., "invoice", "customer"
        [string]$Method = "GET",
        [object]$Body = $null,
        [hashtable]$QueryParameters = @{},
        [int]$ApiRetryCount = 1 # Retries specific to the API call itself (after auth)
    )

    $config = Get-QBOConfig
    $AccessToken = Get-QBOAccessToken # Ensures token is valid before proceeding

    $Uri = "$($config.BaseUrl)/v3/company/$($config.RealmID)/$Endpoint`?minorversion=$($config.MinorVersion)"
    if ($QueryParameters.Count -gt 0) {
        $QueryString = ($QueryParameters.GetEnumerator() | ForEach-Object { "$($_.Key)=$([System.Web.HttpUtility]::UrlEncode($_.Value))" }) -join '&'
        $Uri += "&$QueryString"
    }

    $headers = @{
        "Authorization" = "Bearer $AccessToken"
        "Accept" = "application/json"
    }

    $requestParams = @{
        Method = $Method
        Uri = $Uri
        Headers = $headers
        ErrorAction = 'Stop' # Let our retry wrapper handle errors
    }

    if ($Body) {
        $requestParams.Body = ($Body | ConvertTo-Json -Depth 10 -Compress)
        $requestParams.ContentType = 'application/json'
    }

    Write-Host "Making QBO API Request: $Method $Uri"

    # Use retry wrapper, passing token refresh as the action on 401
    return Invoke-RestMethodWithRetryLocal -Parameters $requestParams -MaxRetries $ApiRetryCount -RetryAction { Refresh-QBOAccessToken } 
}

#region Service Wrappers

# Invoices
function New-QBOInvoice {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [object]$InvoiceData # Should match QBO Invoice object structure
    )
    Write-Host "Creating new QBO Invoice..."
    # QBO requires Line items
    if (-not $InvoiceData.Line) {
        throw "InvoiceData must include a Line array."
    }
    return Invoke-QBOApiRequest -Endpoint "invoice" -Method "POST" -Body $InvoiceData
}

function Send-QBOInvoice {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$InvoiceId,
        [string]$RecipientEmail = $null # Optional: specify recipient, otherwise uses customer default
    )
    Write-Host "Sending QBO Invoice ID: $InvoiceId..."
    $endpoint = "invoice/$InvoiceId/send"
    $queryParams = @{}
    if ($RecipientEmail) {
        $queryParams.sendTo = $RecipientEmail
    }
    # The send endpoint is POST, but doesn't typically require a body, only query params
    return Invoke-QBOApiRequest -Endpoint $endpoint -Method "POST" -QueryParameters $queryParams
}

# Estimates
function Get-QBOEstimate {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$EstimateId
    )
     Write-Host "Getting QBO Estimate ID: $EstimateId..."
    return Invoke-QBOApiRequest -Endpoint "estimate/$EstimateId" -Method "GET"
}

# Customers
function Get-QBOCustomerByQuery {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$Query # e.g., "DisplayName = 'John Doe'"
    )
    Write-Host "Querying QBO Customers: $Query"
    # Query endpoint requires URL encoding
    $encodedQuery = [System.Web.HttpUtility]::UrlEncode($Query)
    $endpoint = "query?query=select * from Customer where $encodedQuery"
    return Invoke-QBOApiRequest -Endpoint $endpoint -Method "GET"
}

# Reports
function Get-QBOReport {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet('ProfitAndLoss', 'BalanceSheet', 'CustomerBalance')] # Add more as needed
        [string]$ReportName,
        [hashtable]$ReportParameters = @{} # e.g., @{ start_date = '...'; end_date = '...' }
    )
    Write-Host "Generating QBO Report: $ReportName..."
    $endpoint = "reports/$ReportName"
    return Invoke-QBOApiRequest -Endpoint $endpoint -Method "GET" -QueryParameters $ReportParameters
}

# Bookkeeping (Placeholder)
function Reconcile-Books {
    Write-Warning "Placeholder: Reconcile-Books function not implemented."
    # This would involve complex logic: 
    # 1. Fetching bank transactions (requires Bank Feeds API scope/permissions)
    # 2. Fetching QBO transactions
    # 3. Matching or creating new entries
    return [PSCustomObject]@{ Success=$false; Message="Reconciliation not implemented."}
}

#endregion

Export-ModuleMember -Function Get-QBOConfig, Get-QBOAccessToken, Invoke-QBOApiRequest, New-QBOInvoice, Send-QBOInvoice, Get-QBOEstimate, Get-QBOCustomerByQuery, Get-QBOReport, Reconcile-Books 