# Dockerfile
FROM mcr.microsoft.com/powershell:7.4-debian-11

WORKDIR /app
# COPY src/ /app # No longer needed for sleep test

# Install required PowerShell modules
# RUN pwsh -Command "Install-Module -Name Pode -Force -SkipPublisherCheck -AcceptLicense"
# RUN pwsh -Command "Install-Module -Name ThreadJob -RequiredVersion 2.0.3 -Force -SkipPublisherCheck -AcceptLicense" # No longer needed for basic listener

# (Optional) Install any modules ahead of time:
# RUN pwsh -Command "Install-Package MailKit -Source PSGallery -Force"

# EXPOSE 8080 # Not needed for sleep test
# CMD ["pwsh", "-Command", ". /app/EmailFunction.ps1"]
CMD ["/bin/sleep", "600"] # Override CMD to just sleep, bypassing pwsh 