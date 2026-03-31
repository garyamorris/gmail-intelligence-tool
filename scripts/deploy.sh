#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?PROJECT_ID required}"
SERVICE_NAME="${SERVICE_NAME:-gmail-intelligence-tool}"
REGION="${REGION:-europe-west1}"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"


gcloud builds submit --config cloudbuild.yaml \
  --substitutions _SERVICE_NAME=${SERVICE_NAME},_REGION=${REGION},_GMAIL_USER_EMAIL="${GMAIL_USER_EMAIL:-}" \
  .

echo "✅ Build finished. Service should now be deploying to Cloud Run."