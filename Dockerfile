# Use the official PowerShell image for Linux Alpine
FROM mcr.microsoft.com/powershell:7.4-alpine-3.20

# Set the working directory in the container
WORKDIR /app

# Copy the application source code to the container
COPY ./src /app

# Install required PowerShell modules
RUN pwsh -Command "Install-Module -Name ThreadJob -RequiredVersion 2.0.3 -Force -SkipPublisherCheck -AcceptLicense"

# Expose the port the app runs on (Note: Cloud Run uses the PORT env var)
EXPOSE 8080

# Define the entry point for the container.
# It runs the PowerShell script that starts the HTTP listener.
ENTRYPOINT ["pwsh", "-File", "/app/EmailFunction.ps1"] 