# Reporting.psm1
# Handles generation of financial reports.

#Requires -Module ./QBOClient.psm1

function Invoke-GetPnl {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$false)]
        [int]$DaysPast = 90, # Default to last 90 days
        [Parameter(Mandatory=$false)]
        [ValidateSet('JSON', 'CSV')] # Add PDF support later if possible
        [string]$Format = 'JSON' 
    )
    Write-Host "Generating P&L Report for the last $DaysPast days..."
    
    try {
        $endDate = Get-Date
        $startDate = $endDate.AddDays(-$DaysPast)

        $reportParams = @{
            start_date = $startDate.ToString("yyyy-MM-dd")
            end_date = $endDate.ToString("yyyy-MM-dd")
            # Add other QBO report parameters if needed (e.g., accounting_method, summarize_column_by)
        }

        $reportData = Get-QBOReport -ReportName 'ProfitAndLoss' -ReportParameters $reportParams

        if (-not $reportData) {
            throw "Failed to retrieve ProfitAndLoss report data from QBO."
        }

        # Process/Format the report (QBO JSON structure varies)
        # For now, just return success and potentially a link or raw data summary
        $message = "Profit and Loss report generated successfully (Format: $Format)."
        $reportUrl = $null # Placeholder - QBO API might not provide a direct URL

        if ($Format -eq 'CSV') {
            # TODO: Convert QBO JSON report structure to CSV
            $message += " CSV conversion not implemented yet."
             Write-Warning "CSV conversion not implemented."
        }
        # Else: Return JSON details or summary
        $message += " Raw data available in logs (if enabled)."

        return [PSCustomObject]@{
            Success = $true
            Message = $message
            ReportUrl = $reportUrl # Maybe link to QBO UI?
            RawData = if ($Format -eq 'JSON') { $reportData } else { $null } # Optional
        }
    }
    catch {
         Write-Error "Error during Invoke-GetPnl: $($_.Exception.Message)"
         return [PSCustomObject]@{
             Success = $false
             Message = "Failed to generate P&L report: $($_.Exception.Message)"
         }
    }
}

# Add other report functions as needed (e.g., Invoke-GetBalanceSheet)

Export-ModuleMember -Function Invoke-GetPnl 