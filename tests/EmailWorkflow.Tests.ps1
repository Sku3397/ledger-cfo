# EmailWorkflow.Tests.ps1
# Pester tests for the email command workflow (Cloud Run version).

# Import necessary modules
# Note: We might need to adjust paths or use a manifest if structure gets complex
Import-Module ../Services/CommandParser.psm1 -Force
Import-Module ../Services/InvoiceManager.psm1 -Force
Import-Module ../Services/Bookkeeper.psm1 -Force
Import-Module ../Services/Reporting.psm1 -Force
Import-Module ../Services/QBOClient.psm1 -Force

# We need to source the script containing the functions to test, 
# as it's not a module. This makes testing a bit trickier.
. "../src/EmailFunction.ps1"

# Mock external dependencies (Gmail, QBO, Email Sender)
# Mock Invoke-RestMethodWithRetry centrally as it's used for all external calls

$mockResponses = @{}
$sentEmails = @()

InModuleScope 'EmailFunction' {
    Mock Invoke-RestMethodWithRetry { 
        param($Parameters)
        # Simulate Gmail API or QBO calls based on URI
        Write-Host "Mock Invoke-RestMethodWithRetry called with URI: $($Parameters.Uri)" 
        
        if ($Parameters.Uri -like '*googleapis.com/gmail*') {
            # Handle Gmail Mocks
            if ($Parameters.Uri -match '/messages$') { # List messages
                return $mockResponses["gmail_list"] # Should be set per test
            }
             elseif ($Parameters.Uri -match '/messages/([^/]+)\?format=full$') { # Get message
                $msgId = $Matches[1]
                return $mockResponses["gmail_get_$msgId"] # Should be set per test
            }
             elseif ($Parameters.Uri -match '/messages/([^/]+)/modify$') { # Modify (mark read)
                 Write-Host "Mock: Marking message $($Matches[1]) as read"
                 return @{ id = $Matches[1]; labelIds = @('INBOX') } # Simulate success
            }
             elseif ($Parameters.Uri -match '/messages/send$') { # Send message
                 Write-Host "Mock: Sending email..."
                 # Capture details for assertion
                 $emailDetails = $Parameters.Body | ConvertFrom-Json
                 $rawMime = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($emailDetails.raw.Replace('-', '+').Replace('_', '/')))
                 $sentEmails += [PSCustomObject]@{ BodyJson = $Parameters.Body; RawMime = $rawMime }
                 return @{ id = "mock_sent_" + (New-Guid); threadId = "mock_thread_123" }
             }
        }
        elseif ($Parameters.Uri -like '*quickbooks.api.intuit.com*') {
            # Handle QBO Mocks
             if ($Parameters.Uri -match '/invoice$') {
                 Write-Host "Mock: Creating QBO Invoice"
                 return $mockResponses["qbo_create_invoice"] # Set per test
             }
              if ($Parameters.Uri -match '/estimate/([^/]+)$') {
                 Write-Host "Mock: Getting QBO Estimate $($Matches[1])"
                 return $mockResponses["qbo_get_estimate_$($Matches[1])"] # Set per test
             }
        }
        
        Write-Warning "Unhandled mock URI: $($Parameters.Uri)"
        return $null # Default unhandled mock
    } -ModuleName EmailFunction # Ensure mock applies inside the script scope

     # Mock Send-ReplyEmail directly to simplify testing Dispatch-EmailCommand
     Mock Send-ReplyEmail { 
         param($To, $Subject, $Body, $ThreadId)
         Write-Host "Mock Send-ReplyEmail: To=$To, Subject=$Subject, ThreadId=$ThreadId"
         $sentEmails += [PSCustomObject]@{ To = $To; Subject = $Subject; Body = $Body; ThreadId = $ThreadId }
         return $true
     } -ModuleName EmailFunction
}

Describe "Email Parsing (Parse-GmailMessage)" {
    # Test the helper function within EmailFunction.ps1
    It "Should parse basic text/plain message" {
        $raw = @{ 
            id = 'test1'; threadId = 'thread1'; 
            payload = @{ 
                headers = @(
                    @{ name = 'Subject'; value = 'Test Subject' },
                    @{ name = 'From'; value = 'Tester <test@example.com>' },
                    @{ name = 'To'; value = 'Agent <agent@example.com>' }
                );
                mimeType = 'text/plain';
                body = @{ data = ([System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes('Hello World'))) }
            }
        } | ConvertTo-Json | ConvertFrom-Json # Simulate real object

        InModuleScope 'EmailFunction' {
            $parsed = Parse-GmailMessage -RawMessage $raw
        }
        $parsed.From | Should -Be 'Tester <test@example.com>'
        $parsed.Subject | Should -Be 'Test Subject'
        $parsed.Body | Should -Be 'Hello World'
        $parsed.Error | Should -BeNullOrEmpty
    }

    It "Should parse multipart message finding text/plain" {
         $raw = @{ 
            id = 'test2'; threadId = 'thread2'; 
            payload = @{ 
                headers = @(
                    @{ name = 'Subject'; value = 'Multipart Test' },
                    @{ name = 'From'; value = 'Tester <test@example.com>' }
                );
                mimeType = 'multipart/alternative';
                parts = @(
                    @{ mimeType = 'text/html'; body = @{ data = 'PGgxPkhlbGxvPC9oMT4=' } }, # <h1>Hello</h1>
                    @{ mimeType = 'text/plain'; body = @{ data = ([System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes('Plain Hello'))) } }
                )
            }
        } | ConvertTo-Json | ConvertFrom-Json
        
        InModuleScope 'EmailFunction' {
             $parsed = Parse-GmailMessage -RawMessage $raw
        }
        $parsed.Subject | Should -Be 'Multipart Test'
        $parsed.Body | Should -Be 'Plain Hello'
        $parsed.Error | Should -BeNullOrEmpty
    }
    # TODO: Add tests for missing parts, encoding errors, etc.
}


Describe "Email Command Dispatching (Dispatch-EmailCommand)" {
    # Set environment variable for authorized senders
    $env:AUTHORIZED_EMAIL_SENDERS = 'auth@example.com,another@example.com'
    $env:CFO_AGENT_EMAIL = 'agent@example.com' # Needed for Send-CfoReplyEmail mock checks

    # Setup common mock message
    $mockRawMessageBase = @{ 
        id = 'dispatch_test_1'; threadId = 'thread_dispatch_1'; 
        payload = @{ 
            headers = @(
                @{ name = 'Subject'; value = 'placeholder subject' },
                @{ name = 'From'; value = 'Authorized User <auth@example.com>' },
                @{ name = 'Message-ID'; value = '<original_msg_id_123>' } # For reply headers
            );
            mimeType = 'text/plain';
            body = @{ data = ([System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes('placeholder body'))) }
        }
    } 

    # Reset mocks and captures before each test
    BeforeEach {
        $global:mockResponses = @{}
        $global:sentEmails = @()
    }

    It "Should dispatch GenerateInvoice, call QBO, and send success reply" {
        # Arrange
        $mockRawMessage = $mockRawMessageBase | ConvertTo-Json | ConvertFrom-Json # Clone
        $mockRawMessage.payload.headers[0].value = 'Generate invoice for estimate #777 deposit 25%' # Set Subject
        $mockRawMessage.payload.body.data = ([System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes('Please process this.')))

        # Mock QBO responses needed by InvoiceManager
        $mockResponses["qbo_get_estimate_777"] = @{ Estimate = @{ Id = '777'; TotalAmt = 1000; CustomerRef = @{ value = 'cust_1' } } }
        $mockResponses["qbo_create_invoice"] = @{ Invoice = @{ Id = 'qbo-inv-12345'; TotalAmt = 750 } } # Assuming 25% deposit = 750

        # Act
        InModuleScope 'EmailFunction' {
            Dispatch-EmailCommand -RawMessage $mockRawMessage
        }

        # Assert
        # Check that Send-CfoReplyEmail mock was called with success
        $sentEmails.Count | Should -Be 1
        $sentEmails[0].To | Should -Be 'Authorized User <auth@example.com>'
        $sentEmails[0].Subject | Should -Match 'Success'
        $sentEmails[0].Subject | Should -Be 'Re: Generate invoice for estimate #777 deposit 25% - Success'
        $sentEmails[0].Body | Should -Match 'Invoice qbo-inv-12345 created successfully'
        $sentEmails[0].Body | Should -Match 'Invoice URL: https://app.qbo.intuit.com/app/invoice?txnId=qbo-inv-12345'
        $sentEmails[0].ThreadId | Should -Be 'thread_dispatch_1'
        # Verify reply headers (via raw MIME check in mock)
        $sentEmails[0].RawMime | Should -Match 'In-Reply-To: <original_msg_id_123>'
        $sentEmails[0].RawMime | Should -Match 'References: <original_msg_id_123>'
        # TODO: Deeper mocking/spying in InvoiceManager/QBOClient needed to verify QBO calls *parameters* were correct
    }

    It "Should handle QBO failure during Invoice generation and send failure reply" {
         # Arrange
        $mockRawMessage = $mockRawMessageBase | ConvertTo-Json | ConvertFrom-Json # Clone
        $mockRawMessage.payload.headers[0].value = 'Generate invoice for estimate #888 deposit 10%'
        $mockRawMessage.payload.body.data = ([System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes('Try this one.')))

        # Mock QBO Get Estimate success, but Create Invoice failure
        $mockResponses["qbo_get_estimate_888"] = @{ Estimate = @{ Id = '888'; TotalAmt = 500; CustomerRef = @{ value = 'cust_2' } } }
        # Simulate failure by not providing a mock response for qbo_create_invoice, mock will return $null
        # $mockResponses["qbo_create_invoice"] = $null # Implicitly null

        # Act
        InModuleScope 'EmailFunction' {
            Dispatch-EmailCommand -RawMessage $mockRawMessage
        }

        # Assert
        $sentEmails.Count | Should -Be 1
        $sentEmails[0].Subject | Should -Match 'Failed'
        $sentEmails[0].Body | Should -Match 'Failed to generate invoice from Estimate 888'
        # Check for specific error from QBOClient if possible (e.g., the throw message)
        $sentEmails[0].Body | Should -Match 'Failed to create Invoice in QBO' 
    }

    It "Should skip email from unauthorized sender" {
         # Arrange
         $unauthMessage = $mockRawMessageBase | ConvertTo-Json | ConvertFrom-Json # Clone
         $unauthMessage.payload.headers = @(
                @{ name = 'Subject'; value = 'Test' },
                @{ name = 'From'; value = 'Unauthorized <unauth@example.com>' },
                @{ name = 'Message-ID'; value = '<original_msg_id_unauth>' }
            )
        
         # Act
         InModuleScope 'EmailFunction' {
            Dispatch-EmailCommand -RawMessage $unauthMessage
        }

        # Assert
        # Check that Send-CfoReplyEmail mock was NOT called
        $sentEmails.Count | Should -Be 0
    }

     It "Should send failure reply if command is not recognized" {
         # Arrange
         $unknownCommandMessage = $mockRawMessageBase | ConvertTo-Json | ConvertFrom-Json # Clone
         $unknownCommandMessage.payload.headers = @(
                @{ name = 'Subject'; value = 'What is this?' },
                @{ name = 'From'; value = 'Authorized User <auth@example.com>' },
                @{ name = 'Message-ID'; value = '<original_msg_id_unknown>' }
            )
         $unknownCommandMessage.payload.body.data = ([System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes('Some unknown request')))

         # Act
         InModuleScope 'EmailFunction' {
            Dispatch-EmailCommand -RawMessage $unknownCommandMessage
        }

        # Assert
        $sentEmails.Count | Should -Be 1
        $sentEmails[0].Subject | Should -Match 'Failed'
        $sentEmails[0].Subject | Should -Be 'Re: What is this? - Failed'
        $sentEmails[0].Body | Should -Match 'Unrecognized command or parsing failed'
    }

    # TODO: Add tests for:
    # - GetReport command flow
    # - ReconcileBooks command flow (when implemented)
    # - Specific error conditions (e.g., Gmail API errors during fetch/mark read - requires more mock complexity)
    # - Email parsing errors (e.g., missing body, bad encoding)
}

# Cleanup environment variable
Remove-Variable -Name AUTHORIZED_EMAIL_SENDERS -Scope Env -Force -ErrorAction SilentlyContinue

# TODO: Add Describe blocks for Bookkeeper, Reporting, Watch-Email loop logic, etc. 