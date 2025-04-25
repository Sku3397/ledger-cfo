# Dockerfile
FROM mcr.microsoft.com/powershell:7.4-debian-11

WORKDIR /app
COPY src/ /app

# (Optional) Install any modules ahead of time:
# RUN pwsh -Command "Install-Package MailKit -Source PSGallery -Force"

EXPOSE 8080
CMD ["pwsh","-File","/app/EmailFunction.ps1"] 