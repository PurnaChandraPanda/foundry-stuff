#!/usr/bin/env bash
#
# Create the Foundry -> Fabric IQ project connection from values in .env.
#
# Fabric IQ is an MCP server, so this is a RemoteTool connection rather than the
# CustomKeys connection used by the Fabric *data agent* tool. Authentication is
# UserEntraToken: Foundry forwards the signed-in user's Entra token to the Fabric
# MCP endpoint, so queries run under the caller's identity and Fabric enforces
# that user's permissions.
#
# Connection names here allow alphanumerics, dashes and dots only. An underscore
# is rejected with "Connection name must be 1-64 characters long and can only
# contain alphanumeric characters, dashes, and dots."
#
# Ontology and Power BI semantic model items need a BYO Entra app or managed
# OAuth connection instead (see readme.md); those are created in the Foundry
# portal because they need a client secret and a one-time admin consent.
#
# Usage:
#   ./create_fabric_iq_connection.sh            # create or update the connection
#   ./create_fabric_iq_connection.sh --delete   # remove it
#
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
# RemoteTool connections with authType UserEntraToken need this preview API.
API_VERSION="2025-10-01-preview"

die() { echo "ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------- load .env
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found. Copy .env.example to .env first."

# Values already exported in the shell win over .env, so one-off overrides like
# `FABRIC_IQ_CONNECTION_NAME=other ./create_fabric_iq_connection.sh` actually
# work. `set -a; source` would otherwise overwrite them.
_pre_conn="${FABRIC_IQ_CONNECTION_NAME:-}"
_pre_url="${FABRIC_IQ_SERVER_URL:-}"
_pre_aud="${FABRIC_IQ_AUDIENCE:-}"
_pre_type="${FABRIC_IQ_ITEM_TYPE:-}"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [ -n "$_pre_conn" ]; then FABRIC_IQ_CONNECTION_NAME="$_pre_conn"; fi
if [ -n "$_pre_url" ]; then FABRIC_IQ_SERVER_URL="$_pre_url"; fi
if [ -n "$_pre_aud" ]; then FABRIC_IQ_AUDIENCE="$_pre_aud"; fi
if [ -n "$_pre_type" ]; then FABRIC_IQ_ITEM_TYPE="$_pre_type"; fi

require() {
  local name="$1"
  [ -n "${!name:-}" ] || die "$name is not set in $ENV_FILE"
}

require AZURE_AI_PROJECT_ID

CONNECTION_NAME="${FABRIC_IQ_CONNECTION_NAME:-fabric-iq-dataagent}"
AUDIENCE="${FABRIC_IQ_AUDIENCE:-https://api.fabric.microsoft.com}"

case "$CONNECTION_NAME" in
  *_*) die "Connection name '$CONNECTION_NAME' contains an underscore. Use dashes." ;;
esac

# Build the MCP URL for the configured item type. The logic lives in
# fabric_iq_config.py so bash and the Python samples cannot drift apart.
if [ -z "${FABRIC_IQ_SERVER_URL:-}" ]; then
  PYTHON_BIN="${PYTHON_BIN:-python}"
  command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "python not found on PATH. Set PYTHON_BIN."
  FABRIC_IQ_SERVER_URL="$(
    PYTHONPATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)${PYTHONPATH:+:$PYTHONPATH}" \
    FABRIC_IQ_ITEM_TYPE="${FABRIC_IQ_ITEM_TYPE:-}" \
    FABRIC_WORKSPACE_ID="${FABRIC_WORKSPACE_ID:-}" \
    FABRIC_ARTIFACT_ID="${FABRIC_ARTIFACT_ID:-}" \
    "$PYTHON_BIN" -c 'import sys, fabric_iq_config
try:
    sys.stdout.write(fabric_iq_config.resolve_server_url())
except ValueError as exc:
    sys.exit(str(exc))'
  )" || die "Could not build the server URL."
fi

echo "Item type : ${FABRIC_IQ_ITEM_TYPE:-dataagent}"
echo "Server URL: $FABRIC_IQ_SERVER_URL"

command -v az >/dev/null 2>&1 || die "az CLI not found on PATH."

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

URL="https://management.azure.com${AZURE_AI_PROJECT_ID}/connections/${CONNECTION_NAME}?api-version=${API_VERSION}"
echo URL="$URL"

# ------------------------------------------------------------------ delete
if [ "${1:-}" = "--delete" ]; then
  az rest --method delete --url "$URL"
  echo "Deleted connection '$CONNECTION_NAME'."
  exit 0
fi

# ------------------------------------------------------------------ create
# Use a relative path rather than mktemp's /tmp path. `az` is a native Windows
# program, so a POSIX /tmp/... path only works while Git Bash rewrites it. With
# MSYS_NO_PATHCONV=1 that rewriting is disabled and az cannot open the file.
BODY_FILE="./.fabric-iq-connection.json"
trap 'rm -f "$BODY_FILE"' EXIT

cat > "$BODY_FILE" <<JSON
{
  "properties": {
    "category": "RemoteTool",
    "authType": "UserEntraToken",
    "target": "${FABRIC_IQ_SERVER_URL}",
    "audience": "${AUDIENCE}"
  }
}
JSON

cat "$BODY_FILE"

echo "Creating connection..."
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
  --query "{name:name, category:properties.category, authType:properties.authType, target:properties.target, audience:properties.audience}" \
  -o json

cat <<EOF

Done.

Next:
  python diagnose_fabric_iq_connection.py
EOF
