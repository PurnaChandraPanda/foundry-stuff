#!/usr/bin/env bash
set -euo pipefail


# Load .env from current folder
set -a
source ./.env
set +a


# API_VERSION="2025-11-15-preview"
API_VERSION="v1"
FOUNDRY_FEATURES="AgentEndpoints=V1Preview"

# Login
az login --identity

# Get access toen
ACCESS_TOKEN="$(az account get-access-token \
  --resource "https://ai.azure.com/" \
  --query accessToken \
  -o tsv)"

REQUEST_URL="${FOUNDRY_PROJECT_ENDPOINT}/agents/${FOUNDRY_AGENT_APPLICATION}?api-version=${API_VERSION}"

curl -sS --fail-with-body \
  -X GET "${REQUEST_URL}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Foundry-Features: ${FOUNDRY_FEATURES}" \
  -H "Accept: application/json"

