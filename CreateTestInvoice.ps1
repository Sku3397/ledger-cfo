# PowerShell script to create a test invoice in QuickBooks
Write-Host "Creating test invoice in QuickBooks Online..." -ForegroundColor Cyan

# Check if Python is available
$pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonPath) {
    Write-Host "Python not found. Please install Python and add it to your PATH." -ForegroundColor Red
    exit 1
}

# Create a temporary Python script
$tempScript = @"
from quickbooks_api import QuickBooksAPI
from config import config
from logger import cfo_logger

def create_invoice():
    try:
        # Initialize QBO API
        qb_api = QuickBooksAPI()
        
        # Create a test invoice
        invoice_data = {
            "CustomerRef": {
                "value": "1"  # Use a default customer ID
            },
            "Line": [
                {
                    "Amount": 123.00,
                    "Description": "Test invoice - PowerShell",
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {
                        "ItemRef": {
                            "value": "1"
                        }
                    }
                }
            ]
        }
        
        # Create the invoice
        result = qb_api.create_invoice(invoice_data)
        
        if result and 'Id' in result:
            print(f"Invoice created successfully with ID: {result['Id']}")
            url = qb_api.get_invoice_preview_url(result['Id'])
            print(f"Preview URL: {url}")
            return True
        else:
            print("Failed to create invoice")
            return False
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

if create_invoice():
    print("TEST_INVOICE_SUCCESS")
else:
    print("TEST_INVOICE_FAILED")
"@

# Save to temporary file
$tempFile = [System.IO.Path]::GetTempFileName() + ".py"
$tempScript | Out-File -FilePath $tempFile -Encoding utf8

# Execute the script and capture output
Write-Host "Executing test script..." -ForegroundColor Yellow
$output = python $tempFile

# Check for success indicator in output
if ($output -contains "TEST_INVOICE_SUCCESS") {
    Write-Host "Invoice created successfully!" -ForegroundColor Green
    
    # Extract the invoice ID and URL from output
    $invoiceId = ($output | Select-String -Pattern "Invoice created successfully with ID: (.+)").Matches.Groups[1].Value
    $previewUrl = ($output | Select-String -Pattern "Preview URL: (.+)").Matches.Groups[1].Value
    
    Write-Host "Invoice ID: $invoiceId" -ForegroundColor Green
    Write-Host "Preview URL: $previewUrl" -ForegroundColor Green
} else {
    Write-Host "Failed to create invoice. See output below:" -ForegroundColor Red
    $output
}

# Clean up temp file
Remove-Item $tempFile -Force 