# InvoiceManager.psm1
# Handles invoice creation, updates, and sending via QuickBooks or other methods.

#Requires -Module ./QBOClient.psm1

# Helper function to find customer ID (example)
function Get-QBOCustomerIdFromEstimate {
    param (
        [Parameter(Mandatory=$true)]
        [object]$Estimate # QBO Estimate object from Get-QBOEstimate
    )
    if ($Estimate.Estimate -and $Estimate.Estimate.CustomerRef -and $Estimate.Estimate.CustomerRef.value) {
        return $Estimate.Estimate.CustomerRef.value
    } else {
        throw "Could not determine CustomerRef from the provided Estimate object."
    }
}

function Invoke-NewInvoice {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [PSCustomObject]$CommandParameters # Expects: EstimateID, DepositPercent (optional), SendMethod (optional, e.g., 'QBO')
    )

    Write-Host "Processing GenerateInvoice command with parameters: $($CommandParameters | ConvertTo-Json -Depth 3)"

    $estimateId = $CommandParameters.EstimateID
    $depositPercent = $CommandParameters.DepositPercent
    $sendMethod = $CommandParameters.SendMethod

    if (-not $estimateId) {
         throw "EstimateID is required to generate an invoice."
    }

    try {
        # 1. Fetch estimate details from QBO
        $estimateResponse = Get-QBOEstimate -EstimateId $estimateId
        if (-not $estimateResponse -or -not $estimateResponse.Estimate) {
            throw "Failed to retrieve Estimate details for ID: $estimateId from QBO."
        }
        $estimateDetails = $estimateResponse.Estimate

        # 2. Fetch Customer details (needed for Invoice)
        $customerId = Get-QBOCustomerIdFromEstimate -Estimate $estimateResponse
        # Potentially fetch full customer if more details needed: Get-QBOCustomerByQuery -Query "Id = '$customerId'"
        
        # 3. Construct Invoice Data based on Estimate
        $invoiceLines = @()
        if ($estimateDetails.Line) {
            foreach ($line in $estimateDetails.Line) {
                # Create invoice lines based on estimate lines
                # This might need adjustment based on exact QBO structure
                $invoiceLine = @{
                    Description = $line.Description
                    Amount = $line.Amount 
                    DetailType = $line.DetailType 
                    # Copy relevant SalesItemLineDetail, GroupLineDetail, etc.
                    SalesItemLineDetail = if ($line.SalesItemLineDetail) { $line.SalesItemLineDetail } else { $null } 
                    # Add more Detail types as needed
                }
                # Remove nulls to avoid QBO errors
                $invoiceLine = $invoiceLine.PSObject.Properties | Where-Object { $_.Value -ne $null } | ForEach-Object { @{ $_.Name = $_.Value } } | Select-Object -ExpandProperty Keys | ForEach-Object { $ht = @{} } { $ht[$_] = $invoiceLine[$_] } { $ht }
                
                $invoiceLines += $invoiceLine
            }
        }
        
        if ($invoiceLines.Count -eq 0) {
            throw "No lines found on Estimate $estimateId to create an Invoice."
        }

        # Apply deposit if specified
        if ($depositPercent -and $depositPercent -gt 0 -and $depositPercent -lt 100) {
             Write-Host "Applying $depositPercent% deposit..."
             $depositMultiplier = $depositPercent / 100.0
             $discountLine = @{
                 Amount = ($estimateDetails.TotalAmt * $depositMultiplier) 
                 DetailType = "DiscountLineDetail"
                 DiscountLineDetail = @{
                     PercentBased = $false # Apply as fixed amount
                     # Optional: Link to a specific Discount account
                     # DiscountAccountRef = @{ value = "YOUR_DISCOUNT_ACCOUNT_ID" }
                 }
             }
             $invoiceLines += $discountLine
        }

        # Construct the main Invoice object for QBO
        $invoicePayload = @{
            Line = $invoiceLines
            CustomerRef = @{ value = $customerId }
            # Add other details if needed: DocNumber, TxnDate, DueDate, EmailStatus, etc.
            # Example: Link to Estimate (if QBO supports this directly)
            # LinkedTxn = @( @{ TxnId = $estimateId; TxnType = "Estimate" } )
        }

        # 4. Create the Invoice in QBO
        $createResponse = New-QBOInvoice -InvoiceData $invoicePayload
        if (-not $createResponse -or -not $createResponse.Invoice) {
            throw "Failed to create Invoice in QBO. API response did not contain expected Invoice object."
        }
        $newInvoiceId = $createResponse.Invoice.Id
        $newInvoiceTotal = $createResponse.Invoice.TotalAmt
        Write-Host "Successfully created QBO Invoice ID: $newInvoiceId, Total: $newInvoiceTotal"

        $invoiceUrl = "https://app.qbo.intuit.com/app/invoice?txnId=$newInvoiceId" # Construct typical URL

        # 5. Send via QBO if requested
        if ($sendMethod -eq 'QBO') {
            Write-Host "Sending Invoice $newInvoiceId via QBO..."
            # Optionally get customer email first
            # $customerDetails = ... Get-QBOCustomerByQuery ...
            # $recipient = $customerDetails.PrimaryEmailAddr.Address
            Send-QBOInvoice -InvoiceId $newInvoiceId # -RecipientEmail $recipient
             Write-Host "Successfully requested QBO to send Invoice $newInvoiceId."
        }

        # 6. Return success details
        return [PSCustomObject]@{ 
            Success = $true
            Message = "Invoice $newInvoiceId created successfully for Estimate $estimateId." 
            InvoiceID = $newInvoiceId
            InvoiceUrl = $invoiceUrl # Provide a link
        }

    }
    catch {
        Write-Error "Error in Invoke-NewInvoice: $($_.Exception.Message)"
        # Return failure object
        return [PSCustomObject]@{ 
            Success = $false
            Message = "Failed to generate invoice from Estimate $estimateId: $($_.Exception.Message)"
            InvoiceID = $null
        }
    }
}

Export-ModuleMember -Function Invoke-NewInvoice 