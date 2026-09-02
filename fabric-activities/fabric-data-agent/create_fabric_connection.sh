#!/usr/bin/env bash
#
# Create the Foundry -> Fabric data agent connection from values in .env.
#
# The credential key names must be "workspace-id" and "artifact-id" with
# HYPHENS. This matches what the Foundry portal sends. Using underscores
# produces a connection that looks valid from every API - it is listed, and
# listSecrets returns the keys - but every agent run fails with
# "Workspace ID and Artifact ID are required from connection details or
# additional_properties for Fabric operations".
#
# The connection is a plain ARM resource of type
# Microsoft.CognitiveServices/accounts/projects/connections, so `az rest` can
# create it. There is no create API on the azure-ai-projects SDK
# (ConnectionsOperations exposes only get / get_default / list), there is no
# dedicated `az` command, and `azd ai connection create`
# cannot create the *first* connection in a project (it discovers the ARM
# context by reading an existing connection).
#
# Usage:
#   ./create_fabric_connection.sh            # create or update the connection
#   ./create_fabric_connection.sh --delete   # remove it
#
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
API_VERSION="2025-06-01"

die() { echo "ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------- load .env
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found. Copy .env.example to .env first."

# Values already exported in the shell win over .env, so one-off overrides like
# `FABRIC_CONNECTION_NAME=other ./create_fabric_connection.sh` actually work.
# `set -a; source` would otherwise overwrite them.
_pre_conn="${FABRIC_CONNECTION_NAME:-}"
_pre_rg="${RESOURCE_GROUP:-}"
_pre_sub="${SUBSCRIPTION_ID:-}"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [ -n "$_pre_conn" ]; then FABRIC_CONNECTION_NAME="$_pre_conn"; fi
if [ -n "$_pre_rg" ]; then RESOURCE_GROUP="$_pre_rg"; fi
if [ -n "$_pre_sub" ]; then SUBSCRIPTION_ID="$_pre_sub"; fi

require() {
  local name="$1"
  [ -n "${!name:-}" ] || die "$name is not set in $ENV_FILE"
}

require AZURE_AI_PROJECT_ENDPOINT
require FABRIC_WORKSPACE_ID
require FABRIC_ARTIFACT_ID

CONNECTION_NAME="${FABRIC_CONNECTION_NAME:-fabric-dataagent}"

command -v az >/dev/null 2>&1 || die "az CLI not found on PATH."

# ------------------------------------------------- derive account + project
# Endpoint looks like:
#   https://<account>.services.ai.azure.com/api/projects/<project>
ACCOUNT_NAME="$(printf '%s' "$AZURE_AI_PROJECT_ENDPOINT" \
  | sed -E 's#^https?://([^.]+)\..*#\1#')"
PROJECT_NAME="$(printf '%s' "$AZURE_AI_PROJECT_ENDPOINT" \
  | sed -E 's#.*/projects/([^/?]+).*#\1#')"

# ------------------------------------------------------------------- sign in
# Only sign in when there is no usable session for the target tenant.
# An unconditional `az login` forces a device-code round trip on every run.
CURRENT_TENANT="$(az account show --query tenantId -o tsv 2>/dev/null || true)"
if [ -z "$CURRENT_TENANT" ] || { [ -n "${TENANT_ID:-}" ] && [ "$CURRENT_TENANT" != "$TENANT_ID" ]; }; then
  if [ -n "${TENANT_ID:-}" ]; then
    az login --tenant "$TENANT_ID" --use-device-code
  else
    az login --use-device-code
  fi
fi

# ------------------------------------------------ resolve subscription + RG
# Prefer explicit values, then AZURE_AI_PROJECT_ID, then ask ARM.
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-}"

[ -n "$SUBSCRIPTION_ID" ] || SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
[ -n "$SUBSCRIPTION_ID" ] || die "Could not determine the subscription. Run 'az login'."

# management URL for the connection
URL="https://management.azure.com${AZURE_AI_PROJECT_ID}/connections/${CONNECTION_NAME}?api-version=${API_VERSION}"

echo URL="$URL"

# ------------------------------------------------------------------ delete
if [ "${1:-}" = "--delete" ]; then
  az rest --method delete --url "$URL"
  echo "Deleted connection '$CONNECTION_NAME'."
  exit 0
fi

# ------------------------------------------------------------------ create
# Use a relative path in the current directory rather than mktemp's /tmp path.
# `az` is a native Windows program, so a POSIX /tmp/... path only works while
# Git Bash rewrites it. With MSYS_NO_PATHCONV=1 that rewriting is disabled, az
# cannot open the file, and it falls back to parsing the literal string as JSON
# ("unable to deserialize request body"). A relative path is never rewritten,
# so this works with or without MSYS_NO_PATHCONV.
BODY_FILE="./.fabric-connection.json"
trap 'rm -f "$BODY_FILE"' EXIT

cat > "$BODY_FILE" <<JSON
{
  "properties": {
    "category": "CustomKeys",
    "authType": "CustomKeys",
    "target": "-",
    "isSharedToAll": true,
    "metadata": { "type": "fabric_dataagent_preview" },
    "credentials": {
      "keys": {
        "workspace-id": "${FABRIC_WORKSPACE_ID}",
        "artifact-id": "${FABRIC_ARTIFACT_ID}"
      }
    }
  }
}
JSON

cat "$BODY_FILE"

echo "Creating connection..."
# Recreating a connection whose backing secret is still soft-deleted can fail
# once with a 500 wrapping a "purge" 400. Retrying clears it.
attempt=1
until az rest --method put \
        --url "$URL" \
        --headers "Content-Type=application/json" \
        --body "@$BODY_FILE" \
        --output none
do
  if [ "$attempt" -ge 3 ]; then
    die "Create failed after $attempt attempts."
  fi
  echo "  attempt $attempt failed; retrying in 10s..."
  attempt=$((attempt + 1))
  sleep 10
done

echo "Verifying..."
az rest --method get --url "$URL" \
  --query "{name:name, type:properties.metadata.type, authType:properties.authType}" \
  -o json

cat <<EOF

Done.

Note: 'credentials' is write-only, so workspace_id / artifact_id will read back
as null. That is expected and does not mean the values were lost.
EOF
