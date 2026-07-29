#!/usr/bin/env bash
set -euo pipefail

# create-foundry-toolbox-rest.sh
# Creates a Microsoft Foundry Toolbox version using REST API with:
#   1) web_search
#   2) Azure REST API specs MCP via GitMCP
#   3) Foundry MCP server, optionally backed by a project connection
#
# Prereqs:
#   - Azure CLI logged in: az login
#   - jq installed
#   - Caller has Foundry User or suitable role on project for toolbox operations
#   - If creating a project connection: caller has ARM permissions on the Foundry account/project

# -----------------------------
# Required inputs
# -----------------------------
: "${FOUNDRY_PROJECT_ENDPOINT:?Set full project endpoint, e.g. https://<account>.services.ai.azure.com/api/projects/<project>}"
: "${TOOLBOX_NAME:=agent-tools}"

# Public MCP endpoint for Azure REST API specs. Keep this exact unless you intend to change repo.
AZURE_SPECS_MCP_URL="${AZURE_SPECS_MCP_URL:-https://gitmcp.io/Azure/azure-rest-api-specs}"

# Foundry MCP server URL is required if you want the Foundry MCP tool included.
# Example placeholder only; set the actual Foundry MCP server URL before running.
: "${FOUNDRY_MCP_SERVER_URL:?Set Foundry MCP server URL}"

# -----------------------------
# Optional project connection for Foundry MCP server
# -----------------------------
# If your Foundry MCP endpoint needs no auth, leave CREATE_FOUNDRY_MCP_CONNECTION=false.
# If it needs credentials, set CREATE_FOUNDRY_MCP_CONNECTION=true and choose one supported auth mode below.
CREATE_FOUNDRY_MCP_CONNECTION="${CREATE_FOUNDRY_MCP_CONNECTION:-false}"
FOUNDRY_MCP_CONNECTION_NAME="${FOUNDRY_MCP_CONNECTION_NAME:-foundry-mcp-conn}"
CONNECTION_CATEGORY="${CONNECTION_CATEGORY:-RemoteTool}"

# Supported by this script: None, AAD, CustomKeys
#   None       -> creates a no-auth project connection.
#   AAD        -> creates an AAD project connection.
#   CustomKeys -> creates a custom header based connection.
FOUNDRY_MCP_CONNECTION_AUTH_TYPE="${FOUNDRY_MCP_CONNECTION_AUTH_TYPE:-None}"

# For CustomKeys only. Example:
#   export FOUNDRY_MCP_CUSTOM_HEADER_NAME="Authorization"
#   export FOUNDRY_MCP_CUSTOM_HEADER_VALUE="Bearer <token>"
FOUNDRY_MCP_CUSTOM_HEADER_NAME="${FOUNDRY_MCP_CUSTOM_HEADER_NAME:-Authorization}"
FOUNDRY_MCP_CUSTOM_HEADER_VALUE="${FOUNDRY_MCP_CUSTOM_HEADER_VALUE:-}"

# ARM identity of the Foundry account/project; required only if CREATE_FOUNDRY_MCP_CONNECTION=true.
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-}"
RESOURCE_GROUP="${RESOURCE_GROUP:-}"
ACCOUNT_NAME="${ACCOUNT_NAME:-}"
PROJECT_NAME="${PROJECT_NAME:-}"
ARM_API_VERSION="${ARM_API_VERSION:-2025-06-01}"
FOUNDRY_API_VERSION="${FOUNDRY_API_VERSION:-v1}"

# -----------------------------
# Helpers
# -----------------------------
require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

require_cmd az
require_cmd jq
require_cmd curl

PROJECT_ENDPOINT="${FOUNDRY_PROJECT_ENDPOINT%/}"

AI_TOKEN="$(az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv)"
ARM_TOKEN="$(az account get-access-token --resource https://management.azure.com/ --query accessToken -o tsv)"

# -----------------------------
# 1. Optionally create Foundry MCP project connection
# -----------------------------
PROJECT_CONNECTION_JSON_FIELD=""

# If an existing Foundry MCP project connection is already created,
# reference it from the MCP tool definition.
if [[ -n "${FOUNDRY_MCP_CONNECTION_NAME:-}" ]]; then
  PROJECT_CONNECTION_JSON_FIELD=",\"project_connection_id\":\"${FOUNDRY_MCP_CONNECTION_NAME}\""
fi

if [[ "${CREATE_FOUNDRY_MCP_CONNECTION}" == "true" ]]; then
  : "${SUBSCRIPTION_ID:?Required when CREATE_FOUNDRY_MCP_CONNECTION=true}"
  : "${RESOURCE_GROUP:?Required when CREATE_FOUNDRY_MCP_CONNECTION=true}"
  : "${ACCOUNT_NAME:?Required when CREATE_FOUNDRY_MCP_CONNECTION=true}"
  : "${PROJECT_NAME:?Required when CREATE_FOUNDRY_MCP_CONNECTION=true}"

  echo "Creating/updating project connection '${FOUNDRY_MCP_CONNECTION_NAME}' for Foundry MCP server..."

  case "${FOUNDRY_MCP_CONNECTION_AUTH_TYPE}" in
    None)
      CONNECTION_BODY="$(jq -n \
        --arg category "$CONNECTION_CATEGORY" \
        --arg target "$FOUNDRY_MCP_SERVER_URL" \
        '{
          properties: {
            category: $category,
            target: $target,
            authType: "None"
          }
        }')"
      ;;
    AAD)
      CONNECTION_BODY="$(jq -n \
        --arg category "$CONNECTION_CATEGORY" \
        --arg target "$FOUNDRY_MCP_SERVER_URL" \
        '{
          properties: {
            category: $category,
            target: $target,
            authType: "AAD"
          }
        }')"
      ;;
    CustomKeys)
      : "${FOUNDRY_MCP_CUSTOM_HEADER_VALUE:?Required when FOUNDRY_MCP_CONNECTION_AUTH_TYPE=CustomKeys}"

      CONNECTION_BODY="$(jq -n \
        --arg category "$CONNECTION_CATEGORY" \
        --arg target "$FOUNDRY_MCP_SERVER_URL" \
        --arg headerName "$FOUNDRY_MCP_CUSTOM_HEADER_NAME" \
        --arg headerValue "$FOUNDRY_MCP_CUSTOM_HEADER_VALUE" \
        '{
          properties: {
            category: $category,
            target: $target,
            authType: "CustomKeys",
            credentials: {
              keys: {
                ($headerName): $headerValue
              }
            }
          }
        }')"
      ;;
    *)
      echo "Unsupported FOUNDRY_MCP_CONNECTION_AUTH_TYPE: ${FOUNDRY_MCP_CONNECTION_AUTH_TYPE}" >&2
      echo "Supported by this script: None, AAD, CustomKeys" >&2
      exit 1
      ;;
  esac

  CONNECTION_URL="https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.CognitiveServices/accounts/${ACCOUNT_NAME}/projects/${PROJECT_NAME}/connections/${FOUNDRY_MCP_CONNECTION_NAME}?api-version=${ARM_API_VERSION}"

  curl -sS -X PUT "$CONNECTION_URL" \
    -H "Authorization: Bearer ${ARM_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$CONNECTION_BODY" | jq .

  PROJECT_CONNECTION_JSON_FIELD=",\"project_connection_id\":\"${FOUNDRY_MCP_CONNECTION_NAME}\""
else
  echo "Skipping project connection creation. Foundry MCP tool will be added without project_connection_id."
fi

# -----------------------------
# 2. Create toolbox version using REST API
# -----------------------------
echo "Creating toolbox version for '${TOOLBOX_NAME}'..."

TMP_DIR="./.toolbox-create-$$"
mkdir -p "$TMP_DIR"
trap 'rm -rf "$TMP_DIR"' EXIT

TOOLBOX_BODY_FILE="$TMP_DIR/toolbox-body.json"

cat > "$TOOLBOX_BODY_FILE" <<JSON
{
  "description": "Toolbox with web search, Azure REST API specs MCP, and Foundry MCP server",
  "tools": [
    {
      "type": "web_search",
      "name": "web",
      "description": "Search the web for current information"
    },
    {
      "type": "mcp",
      "server_label": "azure_specs",
      "server_url": "${AZURE_SPECS_MCP_URL}",
      "require_approval": "never"
    },
    {
      "type": "mcp",
      "server_label": "foundry",
      "server_url": "${FOUNDRY_MCP_SERVER_URL}",
      "require_approval": "always"${PROJECT_CONNECTION_JSON_FIELD}
    },
    {
      "type": "toolbox_search_preview"
    }
  ]
}
JSON

CREATE_URL="${PROJECT_ENDPOINT}/toolboxes/${TOOLBOX_NAME}/versions?api-version=${FOUNDRY_API_VERSION}"

CREATE_RESPONSE_FILE="$TMP_DIR/create-response.json"

HTTP_STATUS="$(curl -sS -w '%{http_code}' -o "$CREATE_RESPONSE_FILE" -X POST "$CREATE_URL" \
  -H "Authorization: Bearer ${AI_TOKEN}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d "@$TOOLBOX_BODY_FILE")"

cat "$CREATE_RESPONSE_FILE" | jq .

if [[ "$HTTP_STATUS" != "200" && "$HTTP_STATUS" != "201" ]]; then
  echo "Toolbox version create failed with HTTP status ${HTTP_STATUS}" >&2
  exit 1
fi

VERSION="$(jq -r '.version // .id // empty' "$CREATE_RESPONSE_FILE")"

if [[ -z "$VERSION" || "$VERSION" == "null" ]]; then
  echo "Could not parse toolbox version from response. Inspect output above." >&2
else
  echo "Created toolbox version: ${VERSION}"
fi

# -----------------------------
# 3. Print consumer and versioned MCP endpoints
# -----------------------------
CONSUMER_ENDPOINT="${PROJECT_ENDPOINT}/toolboxes/${TOOLBOX_NAME}/mcp?api-version=${FOUNDRY_API_VERSION}"

if [[ -n "$VERSION" && "$VERSION" != "null" ]]; then
  VERSIONED_ENDPOINT="${PROJECT_ENDPOINT}/toolboxes/${TOOLBOX_NAME}/versions/${VERSION}/mcp?api-version=${FOUNDRY_API_VERSION}"
else
  VERSIONED_ENDPOINT="${PROJECT_ENDPOINT}/toolboxes/${TOOLBOX_NAME}/versions/<version>/mcp?api-version=${FOUNDRY_API_VERSION}"
fi

echo
echo "Toolbox endpoint for agent consumption:"
echo "${CONSUMER_ENDPOINT}"
echo
echo "Version-specific endpoint for validation:"
echo "${VERSIONED_ENDPOINT}"
echo
echo "For your hosted agent sample, set:"
echo "export TOOLBOX_ENDPOINT='${CONSUMER_ENDPOINT}'"

# -----------------------------
# 4. Optional REST MCP tools/list validation
# -----------------------------
if [[ "${VALIDATE_TOOLBOX:-true}" == "true" && -n "$VERSION" && "$VERSION" != "null" ]]; then
  echo
  echo "Validating toolbox tools/list over MCP..."

  MCP_URL="$VERSIONED_ENDPOINT"

  curl -sS -X POST "$MCP_URL" \
    -H "Authorization: Bearer ${AI_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
      "jsonrpc": "2.0",
      "id": 1,
      "method": "initialize",
      "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {
          "name": "toolbox-rest-smoke-test",
          "version": "1.0"
        }
      }
    }' >/dev/null

  curl -sS -X POST "$MCP_URL" \
    -H "Authorization: Bearer ${AI_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
      "jsonrpc": "2.0",
      "method": "notifications/initialized"
    }' >/dev/null || true

  curl -sS -X POST "$MCP_URL" \
    -H "Authorization: Bearer ${AI_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
      "jsonrpc": "2.0",
      "id": 2,
      "method": "tools/list",
      "params": {}
    }' | jq .
fi

