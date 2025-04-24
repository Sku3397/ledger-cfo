#!/usr/bin/env bash
set -e

echo "Triggering CI workflow..."
git commit --allow-empty -m "CI test"
git push origin main

echo "Waiting for Actions to complete..."
echo "Check GitHub Actions at: https://github.com/sku3397/ledger-cfo/actions"

echo "Verify deployment with:"
echo "gcloud run services describe ledger --platform managed --region us-east4"
echo "gcloud run logs read ledger --project=ledger-457022" 