# Use the official PowerShell image for Linux Alpine
FROM mcr.microsoft.com/powershell:7.2-alpine

# Set the working directory in the container
WORKDIR /app

# Copy the application source code to the container
COPY ./src /app

# Expose the port the app runs on (Note: Cloud Run uses the PORT env var)
EXPOSE 8080

# Define the entry point for the container.
# It runs the PowerShell script that starts the HTTP listener.
ENTRYPOINT ["pwsh", "-File", "/app/EmailFunction.ps1"] 