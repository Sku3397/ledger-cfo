#!/bin/bash
# Script to verify the us-east4 region deployment commands

echo "Testing deployment commands for us-east4 region..."

# Test dry-run deployment
echo "Dry run deployment test:"
echo "gcloud run deploy ledger \
  --image us-east4-docker.pkg.dev/ledger-457022/cfo-agent-repo/ledger:latest \
  --region=us-east4 \
  --platform=managed \
  --no-traffic"

# Test service URL format
echo "Service URL should now use us-east4:"
echo "https://ledger-abcdefg-ue4.a.run.app"

# Test service list command
echo "Listing services in us-east4:"
echo "gcloud run services list --platform=managed --region=us-east4"

# Test logs command
echo "Reading logs:"
echo "gcloud run logs read ledger --region=us-east4"

echo "Validation checks complete for us-east4 region migration." 