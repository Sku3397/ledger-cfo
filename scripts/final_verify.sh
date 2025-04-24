#!/bin/bash
# Final verification script for us-east4 deployment

set -e

echo "====== FINAL VERIFICATION OF US-EAST4 DEPLOYMENT ======"

# Variables
PROJECT_ID="ledger-457022"
REGION="us-east4"
SERVICE_NAME="ledger"

echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"

# Print service URL format check
echo "Expected service URL format: https://$SERVICE_NAME-[hash]-ue4.a.run.app"
echo ""

# Test endpoint access command
echo "Command to check service endpoint:"
echo "gcloud run services describe $SERVICE_NAME --platform=managed --region=$REGION --format=\"value(status.url)\""
echo ""

# Command to view traffic allocation
echo "Command to check traffic allocation:"
echo "gcloud run services describe $SERVICE_NAME --platform=managed --region=$REGION --format=\"value(status.traffic)\""
echo ""

# Command to stream logs
echo "Command to check logs:"
echo "gcloud run logs read $SERVICE_NAME --region=$REGION --limit=10"
echo ""

# Create a test report template for post-deployment verification
cat > ../FINAL_VERIFICATION.md << EOF
# US-EAST4 Migration Verification Report

## Deployment Status
- **Service Name**: $SERVICE_NAME
- **Project ID**: $PROJECT_ID 
- **Region**: $REGION
- **Migration Date**: $(date +"%Y-%m-%d")

## Verification Checks
- [ ] Service is accessible at us-east4 endpoint
- [ ] Service URL shows 'ue4' region code
- [ ] Logs are streaming properly
- [ ] No deployment errors during migration
- [ ] GitHub Actions workflow using us-east4 references
- [ ] Traffic successfully routed to new revision

## Rollback Plan
If issues are encountered with us-east4 deployment, execute:
\`\`\`bash
# Deploy back to us-central1
gcloud run deploy $SERVICE_NAME \\
  --image us-central1-docker.pkg.dev/$PROJECT_ID/cfo-agent-repo/$SERVICE_NAME:latest \\
  --platform managed \\
  --region us-central1 \\
  --allow-unauthenticated
\`\`\`

## Next Steps
1. Monitor performance in the new region
2. Update DNS and client configurations if applicable
3. Delete old artifacts from us-central1 after 7 days

_Report generated: $(date)_
EOF

echo "Final verification script completed."
echo "FINAL_VERIFICATION.md template created for post-deployment validation." 