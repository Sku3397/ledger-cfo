# CommandParser.psm1
# Parses email subjects and bodies to extract commands and parameters.

function Parse-EmailCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$Subject,
        [Parameter(Mandatory=$true)]
        [string]$Body
    )

    # TODO: Implement robust parsing logic (Regex, potentially NLP/Keyword matching)
    Write-Warning "Placeholder: Command parsing not yet implemented."

    # Example structure of returned object
    $commandDetails = [PSCustomObject]@{
        Command = 'Unknown' # e.g., 'GenerateInvoice', 'RunReport', 'QueryBookkeeping'
        Parameters = @{}    # e.g., @{ EstimateID = 12345; DepositPercent = 30; SendMethod = 'QBO' }
        OriginalSubject = $Subject
        OriginalBody = $Body
        Error = $null
    }

    # --- Placeholder Parsing Logic --- 
    if ($Subject -match 'generate invoice' -or $Body -match 'generate invoice') {
        $commandDetails.Command = 'GenerateInvoice'
        
        # Example: Extract Estimate ID
        if ($Subject -match 'estimate #?(\d+)' -or $Body -match 'estimate #?(\d+)') {
            $commandDetails.Parameters.EstimateID = $Matches[1]
        }

        # Example: Extract Deposit Percentage
        if ($Subject -match '(\d+)% deposit' -or $Body -match '(\d+)% deposit') {
            $commandDetails.Parameters.DepositPercent = $Matches[1]
        }
        
        # Example: Extract Send Method
         if ($Subject -match 'send via (QBO|email)' -or $Body -match 'send via (QBO|email)') {
            $commandDetails.Parameters.SendMethod = $Matches[1].ToUpper()
        }

    } else {
        $commandDetails.Error = "Could not determine command from subject or body."
        # Consider more commands here
    }
    # --- End Placeholder --- 

    return $commandDetails
}

Export-ModuleMember -Function Parse-EmailCommand 