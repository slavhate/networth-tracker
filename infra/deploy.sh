#!/usr/bin/env bash
set -euo pipefail

# Deploys the Net Worth Tracker to AWS: packages the Lambda function,
# uploads it, deploys the CloudFormation stack, builds the frontend, and
# syncs it to S3. Run this yourself after `aws configure` / SSO login -
# nothing here runs without you invoking it.
#
# Required environment variables:
#   HOSTED_ZONE_ID       Route 53 hosted zone ID for shrikantlavhate.in
#                         (aws route53 list-hosted-zones-by-name --dns-name shrikantlavhate.in)
#   NOTIFICATION_EMAIL    Email to receive AWS Budget alerts
#   SECRET_KEY            JWT signing secret (generate once, reuse every deploy):
#                          python3 -c "import secrets; print(secrets.token_hex(32))"
#
# Optional:
#   AWS_REGION            Defaults to us-east-1 (required for the CloudFront ACM cert)
#   DOMAIN_NAME           Defaults to nwt.shrikantlavhate.in
#   RESERVED_CONCURRENCY  Defaults to 2
#   STACK_NAME            Defaults to networth-tracker

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AWS_REGION="${AWS_REGION:-us-east-1}"
DOMAIN_NAME="${DOMAIN_NAME:-nwt.shrikantlavhate.in}"
RESERVED_CONCURRENCY="${RESERVED_CONCURRENCY:-2}"
STACK_NAME="${STACK_NAME:-networth-tracker}"

: "${HOSTED_ZONE_ID:?Set HOSTED_ZONE_ID to the Route 53 hosted zone ID for the domain}"
: "${NOTIFICATION_EMAIL:?Set NOTIFICATION_EMAIL for AWS Budget alerts}"
: "${SECRET_KEY:?Set SECRET_KEY (generate once with: python3 -c \"import secrets; print(secrets.token_hex(32))\")}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ARTIFACTS_BUCKET="networth-tracker-lambda-artifacts-${ACCOUNT_ID}"

echo "==> Ensuring Lambda artifacts bucket exists: ${ARTIFACTS_BUCKET}"
if ! aws s3api head-bucket --bucket "${ARTIFACTS_BUCKET}" 2>/dev/null; then
  aws s3 mb "s3://${ARTIFACTS_BUCKET}" --region "${AWS_REGION}"
fi

echo "==> Building Lambda deployment package"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "${BUILD_DIR}"' EXIT

LAMBDA_SOURCE_FILES=(
  main.py models.py auth.py config.py database.py s3_storage.py
  lambda_handler.py stock_service.py exchange_service.py nav_service.py
)
mkdir -p "${BUILD_DIR}/src"
for f in "${LAMBDA_SOURCE_FILES[@]}"; do
  cp "${REPO_ROOT}/backend/${f}" "${BUILD_DIR}/src/${f}"
done
cp "${REPO_ROOT}/backend/requirements.txt" "${BUILD_DIR}/requirements.txt"

# Build inside a Lambda-runtime-compatible container so packages with C
# extensions (bcrypt, pydantic-core) are binary-compatible with Lambda.
docker run --rm \
  -v "${BUILD_DIR}:/build" \
  public.ecr.aws/sam/build-python3.12 \
  /bin/sh -c "pip install -r /build/requirements.txt -t /build/src"

ZIP_PATH="${BUILD_DIR}/backend.zip"
python3 - "${ZIP_PATH}" "${BUILD_DIR}/src" <<'PYEOF'
import os
import sys
import zipfile

zip_path, src_dir = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, _, files in os.walk(src_dir):
        for name in files:
            full_path = os.path.join(root, name)
            arcname = os.path.relpath(full_path, src_dir)
            zf.write(full_path, arcname)
PYEOF

CODE_HASH="$(sha256sum "${ZIP_PATH}" | cut -c1-16)"
LAMBDA_CODE_KEY="lambda/backend-${CODE_HASH}.zip"

echo "==> Uploading Lambda package to s3://${ARTIFACTS_BUCKET}/${LAMBDA_CODE_KEY}"
aws s3 cp "${ZIP_PATH}" "s3://${ARTIFACTS_BUCKET}/${LAMBDA_CODE_KEY}"

echo "==> Deploying CloudFormation stack: ${STACK_NAME}"
aws cloudformation deploy \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --template-file "${REPO_ROOT}/infra/template.yaml" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    DomainName="${DOMAIN_NAME}" \
    HostedZoneId="${HOSTED_ZONE_ID}" \
    NotificationEmail="${NOTIFICATION_EMAIL}" \
    ReservedConcurrency="${RESERVED_CONCURRENCY}" \
    LambdaArtifactsBucket="${ARTIFACTS_BUCKET}" \
    LambdaCodeS3Key="${LAMBDA_CODE_KEY}" \
    SecretKey="${SECRET_KEY}"

CLOUDFRONT_DOMAIN="$(aws cloudformation describe-stacks --region "${AWS_REGION}" --stack-name "${STACK_NAME}" --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDomainName'].OutputValue" --output text)"
DISTRIBUTION_ID="$(aws cloudformation describe-stacks --region "${AWS_REGION}" --stack-name "${STACK_NAME}" --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" --output text)"
FRONTEND_BUCKET="$(aws cloudformation describe-stacks --region "${AWS_REGION}" --stack-name "${STACK_NAME}" --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" --output text)"

echo "==> Building frontend"
( cd "${REPO_ROOT}/frontend" && npm install && npm run build )

echo "==> Syncing frontend to s3://${FRONTEND_BUCKET}"
aws s3 sync "${REPO_ROOT}/frontend/dist" "s3://${FRONTEND_BUCKET}" --delete

echo "==> Invalidating CloudFront cache"
aws cloudfront create-invalidation --distribution-id "${DISTRIBUTION_ID}" --paths "/*"

echo ""
echo "Done. App URL: https://${DOMAIN_NAME}"
echo "(CloudFront domain: ${CLOUDFRONT_DOMAIN})"
