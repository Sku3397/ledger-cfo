@echo off
setlocal enabledelayedexpansion

REM Configuration
set PROJECT_ID=ledger-457022
set REGION=us-east4
set SERVICE_NAME=ledger
set REPOSITORY=cfo-agent-repo
set IMAGE_NAME=ledger
set IMAGE_TAG=latest

REM Full image path
set IMAGE_PATH=%REGION%-docker.pkg.dev/%PROJECT_ID%/%REPOSITORY%/%IMAGE_NAME%:%IMAGE_TAG%

REM Step 1: Build the Docker image
echo Building Docker image...
docker build -t %IMAGE_NAME%:%IMAGE_TAG% .
if %ERRORLEVEL% neq 0 (
    echo Error building Docker image
    exit /b %ERRORLEVEL%
)

REM Step 2: Configure Docker to use Google Cloud credentials
echo Configuring Docker authentication...
"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" auth configure-docker %REGION%-docker.pkg.dev --quiet
if %ERRORLEVEL% neq 0 (
    echo Error configuring Docker authentication
    exit /b %ERRORLEVEL%
)

REM Step 3: Tag the image for Google Cloud Artifact Registry
echo Tagging image for Google Cloud Artifact Registry...
docker tag %IMAGE_NAME%:%IMAGE_TAG% %IMAGE_PATH%
if %ERRORLEVEL% neq 0 (
    echo Error tagging image
    exit /b %ERRORLEVEL%
)

REM Step 4: Push the image to Google Cloud Artifact Registry
echo Pushing image to Google Cloud Artifact Registry...
docker push %IMAGE_PATH%
if %ERRORLEVEL% neq 0 (
    echo Error pushing image
    exit /b %ERRORLEVEL%
)

REM Step 5: Deploy to Cloud Run
echo Deploying to Cloud Run...
"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" run deploy %SERVICE_NAME% ^
  --image %IMAGE_PATH% ^
  --platform managed ^
  --region %REGION% ^
  --allow-unauthenticated ^
  --project %PROJECT_ID%
if %ERRORLEVEL% neq 0 (
    echo Error deploying to Cloud Run
    exit /b %ERRORLEVEL%
)

echo Deployment completed successfully!

REM Step 6: Health check
echo Performing health check...
for /f "tokens=*" %%a in ('"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" run services describe %SERVICE_NAME% --platform managed --region %REGION% --format="value(status.url)" --project %PROJECT_ID%') do (
    set SERVICE_URL=%%a
)

echo Service URL: !SERVICE_URL!
curl -s -o nul -w "%%{http_code}" -X POST "!SERVICE_URL!/trigger" -H "Content-Type: application/json" -d "{\"action\":\"health_check\"}"
echo.

echo Deployment and testing completed. 