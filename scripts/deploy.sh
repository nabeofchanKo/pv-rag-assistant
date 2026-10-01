#!/usr/bin/env bash
# Build, push and deploy the App Runner services (web and/or backend).
#
#   ./scripts/deploy.sh web|backend|all [--path /en/about] [--expect "text"]
#
# - Refuses to run on a dirty working tree, so what is deployed is a commit.
# - Fails fast at every step. A failed build must never be followed by a
#   start-deployment, which would silently redeploy the previous :latest image.
# - Waits for each deployment to finish and reports SUCCEEDED / FAILED.
# - Checks the live site afterwards. With --expect, the web page at --path
#   (default /ja/triage) must contain the given text, which proves the new image
#   is the one serving.
#
# The account and service ARNs are looked up at run time; none are stored here.
# The backend build bakes the reference indexes and needs OPENAI_API_KEY from
# ./.env, passed to Docker as a BuildKit secret (never printed or written to a layer).

set -euo pipefail
export MSYS_NO_PATHCONV=1 # Git Bash: keep leading-slash arguments intact

REGION=ap-northeast-1
WEB_PATH=/ja/triage

usage() { echo "usage: $0 web|backend|all [--path /en/about] [--expect \"text\"]" >&2; exit 2; }

[ $# -ge 1 ] || usage
case "$1" in
  web) TARGETS=(web) ;;
  backend) TARGETS=(backend) ;;
  all) TARGETS=(backend web) ;;
  *) usage ;;
esac
shift
EXPECT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --expect) [ $# -ge 2 ] || usage; EXPECT="$2"; shift 2 ;;
    --path) [ $# -ge 2 ] || usage; WEB_PATH="$2"; shift 2 ;;
    *) usage ;;
  esac
done

cd "$(dirname "$0")/.."

step() { printf '\n==> %s\n' "$*"; }

# ---- preflight -------------------------------------------------------------
step "Preflight"
if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree is not clean. Commit or stash before deploying." >&2
  git status --short >&2
  exit 1
fi
COMMIT=$(git rev-parse --short HEAD)
echo "commit: $COMMIT ($(git rev-parse --abbrev-ref HEAD))"

docker info >/dev/null 2>&1 || { echo "Docker is not running." >&2; exit 1; }
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REG="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"

service_arn() {
  local arn
  arn=$(aws apprunner list-services --region "$REGION" \
    --query "ServiceSummaryList[?ServiceName=='pv-rag-assistant-$1'].ServiceArn | [0]" --output text)
  [ -n "$arn" ] && [ "$arn" != "None" ] || { echo "App Runner service pv-rag-assistant-$1 not found." >&2; exit 1; }
  echo "$arn"
}

service_url() {
  aws apprunner describe-service --region "$REGION" --service-arn "$1" \
    --query Service.ServiceUrl --output text
}

# ---- build -----------------------------------------------------------------
for t in "${TARGETS[@]}"; do
  step "Build $t"
  if [ "$t" = backend ]; then
    [ -f .env ] || { echo ".env not found (needed for OPENAI_API_KEY)." >&2; exit 1; }
    (
      set -a; . ./.env; set +a
      [ -n "${OPENAI_API_KEY:-}" ] || { echo "OPENAI_API_KEY is empty in .env." >&2; exit 1; }
      docker build -q --build-arg BAKE_INDEXES=1 \
        --secret id=openai_api_key,env=OPENAI_API_KEY \
        -f backend/Dockerfile -t pv-rag-assistant-backend:local .
    )
  else
    docker build -q -t pv-rag-assistant-web:local ./web
  fi
done

# ---- push ------------------------------------------------------------------
step "Push to ECR"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REG" >/dev/null
for t in "${TARGETS[@]}"; do
  docker tag "pv-rag-assistant-$t:local" "$REG/pv-rag-assistant-$t:latest"
  docker push -q "$REG/pv-rag-assistant-$t:latest"
done

# ---- deploy (backend first, so the web never talks to an older API) --------
for t in "${TARGETS[@]}"; do
  step "Deploy $t"
  ARN=$(service_arn "$t")
  OP=$(aws apprunner start-deployment --region "$REGION" --service-arn "$ARN" --query OperationId --output text)
  echo "operation: $OP"
  STATUS=""
  for _ in $(seq 1 60); do # up to ~15 minutes
    STATUS=$(aws apprunner list-operations --region "$REGION" --service-arn "$ARN" \
      --query "OperationSummaryList[?Id=='$OP'].Status | [0]" --output text)
    case "$STATUS" in
      SUCCEEDED) break ;;
      FAILED | ROLLBACK_*) echo "Deployment of $t ended with $STATUS." >&2; exit 1 ;;
      *) sleep 15 ;;
    esac
  done
  [ "$STATUS" = SUCCEEDED ] || { echo "Timed out waiting for $t (last status: $STATUS)." >&2; exit 1; }
  echo "$t: SUCCEEDED"
done

# ---- verify ----------------------------------------------------------------
step "Verify live site"
for t in "${TARGETS[@]}"; do
  URL="https://$(service_url "$(service_arn "$t")")"
  if [ "$t" = backend ]; then
    # Only / and /docs are open without the shared secret.
    code=$(curl -s -o /dev/null -w '%{http_code}' "$URL/")
    [ "$code" = 200 ] || { echo "backend $URL/ returned $code" >&2; exit 1; }
    echo "backend: $URL/ -> 200"
  else
    page=$(curl -sf "$URL$WEB_PATH") || { echo "web $URL$WEB_PATH did not return 2xx" >&2; exit 1; }
    echo "web: $URL$WEB_PATH -> 2xx"
    if [ -n "$EXPECT" ]; then
      grep -qF -- "$EXPECT" <<<"$page" || { echo "web page does not contain: $EXPECT" >&2; exit 1; }
      echo "web: found expected text"
    fi
  fi
done

step "Done: deployed $COMMIT (${TARGETS[*]})"
