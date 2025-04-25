# Use the official PowerShell Core image
FROM mcr.microsoft.com/powershell:latest

# Set working directory
WORKDIR /app

# Copy the application source and service modules
COPY src/EmailFunction.ps1 /app/src/
COPY Services /app/Services/

# Ensure logs directory exists (though stdout/stderr is preferred for Cloud Run)
RUN pwsh -Command "New-Item -ItemType Directory -Path /app/logs -Force"

# Expose the port the app runs on (default 8080 for Cloud Run)
EXPOSE 8080

# Define environment variables if needed (though Cloud Run should inject them)
# ENV GMAIL_CLIENT_ID="your_id"
# ENV GMAIL_CLIENT_SECRET="your_secret"
# ENV GMAIL_REFRESH_TOKEN="your_token"
# ENV QUICKBOOKS_CLIENT_ID="your_qb_id"
# ... etc ...
# ENV AUTHORIZED_EMAIL_SENDERS="sender1@example.com,sender2@example.com"

# Start the PowerShell script that runs the HTTP listener
CMD ["pwsh", "/app/src/EmailFunction.ps1"] 