#!/usr/bin/env bash
# Sign in and create or update the Fabric IQ UserEntraToken connection.
set -euo pipefail

if [ "$#" -ne 0 ]; then echo "Usage: $0 (no arguments)" >&2; exit 1; fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$SCRIPT_DIR/.env}"
if command -v cygpath >/dev/null 2>&1; then ENV_FILE="$(cygpath -u "$ENV_FILE")"; fi
[ -r "$ENV_FILE" ] || { echo "ERROR: Cannot read environment file: $ENV_FILE" >&2; exit 1; }

load_environment() {
  local name
  local -A overrides=()
  for name in TENANT_ID SUBSCRIPTION_ID AZURE_AI_PROJECT_ID FABRIC_IQ_CONNECTION_NAME \
      FABRIC_IQ_SERVER_URL FABRIC_IQ_ITEM_TYPE FABRIC_WORKSPACE_ID FABRIC_ARTIFACT_ID; do
    if [[ -v "$name" ]]; then overrides["$name"]="${!name}"; fi
  done
  # Source only a trusted, shell-compatible .env; strip Windows line endings.
  source <(sed 's/\r$//' "$ENV_FILE")
  for name in "${!overrides[@]}"; do printf -v "$name" '%s' "${overrides[$name]}"; done
}
load_environment

for name in TENANT_ID AZURE_AI_PROJECT_ID FABRIC_IQ_CONNECTION_NAME; do
  : "${!name:?$name is required}"
done
PROJECT_ID="${AZURE_AI_PROJECT_ID%/}"
PROJECT_SUBSCRIPTION="${PROJECT_ID#/subscriptions/}"
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-${PROJECT_SUBSCRIPTION%%/*}}"

FABRIC_HOST="https://api.fabric.microsoft.com"
TARGET="${FABRIC_IQ_SERVER_URL:-}"
if [ -z "$TARGET" ]; then
  ITEM_TYPE="${FABRIC_IQ_ITEM_TYPE:-dataagent}"
  ITEM_TYPE="${ITEM_TYPE,,}"
  ITEM_TYPE="${ITEM_TYPE//[[:space:]]/}"
  case "$ITEM_TYPE" in
    ontology|dataagent|data-agent|data_agent)
      for name in FABRIC_WORKSPACE_ID FABRIC_ARTIFACT_ID; do
        : "${!name:?$name is required}"
      done
      if [ "$ITEM_TYPE" = ontology ]; then
        TARGET="$FABRIC_HOST/v1/mcp/dataPlane/workspaces/$FABRIC_WORKSPACE_ID/items/$FABRIC_ARTIFACT_ID/ontologyEndpoint"
      else
        TARGET="$FABRIC_HOST/v1/mcp/workspaces/$FABRIC_WORKSPACE_ID/dataagents/$FABRIC_ARTIFACT_ID/agent"
      fi ;;
    semanticmodel|semantic-model|semantic_model|powerbi|pbi)
      TARGET="$FABRIC_HOST/v1/mcp/fabricaihub/integrations/m365" ;;
    *) echo "ERROR: Unrecognized FABRIC_IQ_ITEM_TYPE: $ITEM_TYPE" >&2; exit 1 ;;
  esac
fi
JSON_TARGET="${TARGET//\\/\\\\}"
JSON_TARGET="${JSON_TARGET//\"/\\\"}"
JSON_TARGET="${JSON_TARGET//$'\n'/\\n}"
JSON_TARGET="${JSON_TARGET//$'\r'/\\r}"
JSON_TARGET="${JSON_TARGET//$'\t'/\\t}"
URL="https://management.azure.com$PROJECT_ID/connections/$FABRIC_IQ_CONNECTION_NAME?api-version=2025-10-01-preview"

az login --tenant "$TENANT_ID" --output none

BODY_FILE="$(mktemp)"
trap 'rm -f -- "$BODY_FILE"' EXIT
cat > "$BODY_FILE" <<JSON
{
  "properties": {
    "category": "RemoteTool",
    "authType": "UserEntraToken",
    "target": "$JSON_TARGET",
    "audience": "$FABRIC_HOST",
    "metadata": {"type": "fabric_iq_preview"},
    "isSharedToAll": false
  }
}
JSON
BODY_PATH="$BODY_FILE"
if command -v cygpath >/dev/null 2>&1; then BODY_PATH="$(cygpath -w "$BODY_FILE")"; fi
az rest --subscription "$SUBSCRIPTION_ID" --method put --url "$URL" \
  --headers "Content-Type=application/json" --body "@$BODY_PATH" --output none
echo "Connection created or updated: $FABRIC_IQ_CONNECTION_NAME"
