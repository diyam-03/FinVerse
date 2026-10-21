#!/usr/bin/env bash
# Deploys FinVerse to AWS. Run from the project root (works in AWS CloudShell).
set -euo pipefail

STACK=finverse
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || true)}}"
REGION="${REGION:-ap-south-1}"
echo ">> Region: $REGION"

echo ">> Building backend"
sam build

echo ">> Deploying stack (first run takes ~5-10 min because of CloudFront)"
sam deploy --stack-name "$STACK" --region "$REGION" --resolve-s3 \
  --capabilities CAPABILITY_IAM --no-confirm-changeset --no-fail-on-empty-changeset

out() {
  aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}
API_URL=$(out ApiUrl)
BUCKET=$(out SiteBucket)
SITE_URL=$(out SiteUrl)

echo ">> Uploading frontend"
echo "window.FINVERSE_API = \"$API_URL\";" > /tmp/finverse-config.js
aws s3 sync frontend "s3://$BUCKET" --exclude config.js --region "$REGION"
aws s3 cp /tmp/finverse-config.js "s3://$BUCKET/config.js" --content-type application/javascript --region "$REGION"

echo
echo "DONE"
echo "  Website : $SITE_URL"
echo "  API     : $API_URL/health"
