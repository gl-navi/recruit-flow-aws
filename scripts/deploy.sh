#!/usr/bin/env bash
# Deploy one Lambda function's code to AWS.
# Usage: scripts/deploy.sh <receiver|worker|marketo_sync|error_notifier> <dev|prod> [--dry-run]
# The worker is a container image (build, push to ECR, update). The others are zip packages.
# Set IMAGE_TAG=<existing tag> to deploy an already pushed worker image without rebuilding.
set -euo pipefail

FUNCTION="${1:-}"
ENVIRONMENT="${2:-}"
DRY_RUN="${3:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  sed -n '2,3p' "$0"
  exit 2
}
if [[ -z "$FUNCTION" || -z "$ENVIRONMENT" ]]; then usage; fi
if [[ -n "$DRY_RUN" && "$DRY_RUN" != "--dry-run" ]]; then usage; fi

# Read one setting from config/environments.json (python3 is used so jq is not needed).
read_config() {
  python3 - "$ROOT/config/environments.json" "$ENVIRONMENT" "$FUNCTION" "$1" <<'PY'
import json
import sys

path, env, function, key = sys.argv[1:5]
with open(path, encoding="utf-8") as f:
    config = json.load(f)
try:
    environment = config["environments"][env]
    values = {
        "region": config["region"],
        "ecr_repository": config["ecr_repository"],
        "profile": environment["profile"],
        "name": environment["functions"][function],
    }
    print(values[key])
except KeyError as err:
    sys.exit(f"config/environments.json has no entry for {err}")
PY
}

REGION="$(read_config region)"
PROFILE="$(read_config profile)"
NAME="$(read_config name)"

# The worker ships as a container image; every other function ships as a zip.
IMAGE_MODE=false
if [[ "$FUNCTION" == "worker" ]]; then IMAGE_MODE=true; fi

if [[ "$IMAGE_MODE" == true ]]; then
  REPO="$(read_config ecr_repository)"
  TAG="${IMAGE_TAG:-build-$(date -u +%Y%m%d-%H%M%S)}"
  IMAGE_URI="$REPO:$TAG"
  if [[ -z "${IMAGE_TAG:-}" ]]; then
    echo "Building worker image $IMAGE_URI ..."
    docker buildx build --platform linux/amd64 --provenance=false \
      -f "$ROOT/src/worker/Dockerfile" -t "$IMAGE_URI" --load "$ROOT"
  else
    echo "Using the existing image $IMAGE_URI (no rebuild)."
  fi
else
  ZIP="$ROOT/build/${FUNCTION}.zip"
  echo "Building $FUNCTION ..."
  python3 "$ROOT/scripts/build_zip.py" "$FUNCTION" "$ZIP"
fi

if [[ "$DRY_RUN" == "--dry-run" ]]; then
  echo "Dry run: built the package, nothing uploaded."
  exit 0
fi

if [[ "$ENVIRONMENT" == "prod" ]]; then
  read -r -p "Deploy $NAME to PROD? Type the function name to confirm: " answer
  if [[ "$answer" != "$NAME" ]]; then
    echo "Cancelled."
    exit 1
  fi
fi

# Use the AWS CLI installed in WSL if there is one, otherwise the Windows one.
if command -v aws >/dev/null 2>&1; then
  AWS=(aws)
  AWS_IS_WINDOWS=false
elif command -v aws.exe >/dev/null 2>&1; then
  AWS=(aws.exe)
  AWS_IS_WINDOWS=true
else
  echo "AWS CLI not found. Install AWS CLI v2 and set up the profile '$PROFILE'." >&2
  exit 1
fi

if [[ "$IMAGE_MODE" == true ]]; then
  if [[ -z "${IMAGE_TAG:-}" ]]; then
    echo "Pushing $IMAGE_URI ..."
    # tr removes the carriage return that the Windows aws.exe adds to its output.
    "${AWS[@]}" ecr get-login-password --region "$REGION" --profile "$PROFILE" | tr -d '\r' \
      | docker login --username AWS --password-stdin "${REPO%%/*}"
    docker push "$IMAGE_URI"
  fi
  echo "Updating $NAME ($ENVIRONMENT, $REGION) to $IMAGE_URI ..."
  "${AWS[@]}" lambda update-function-code \
    --function-name "$NAME" \
    --image-uri "$IMAGE_URI" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query '{Function:FunctionName,Type:PackageType,Updated:LastModified}' \
    --output table
else
  if [[ "$AWS_IS_WINDOWS" == true ]]; then
    ZIP_ARG="fileb://$(wslpath -w "$ZIP")"
  else
    ZIP_ARG="fileb://$ZIP"
  fi
  echo "Uploading to $NAME ($ENVIRONMENT, $REGION) ..."
  "${AWS[@]}" lambda update-function-code \
    --function-name "$NAME" \
    --zip-file "$ZIP_ARG" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query '{Function:FunctionName,Type:PackageType,Updated:LastModified}' \
    --output table
fi

"${AWS[@]}" lambda wait function-updated \
  --function-name "$NAME" \
  --profile "$PROFILE" \
  --region "$REGION"
echo "Done."
