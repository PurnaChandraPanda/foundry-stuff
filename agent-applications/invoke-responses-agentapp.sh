#!/usr/bin/env bash
set -euo pipefail


# Load .env from current folder
set -a
source ./.env
set +a

# define api version: consider v1 for latest
API_VERSION="v1"
# API_VERSION="2025-11-15-preview"

# Login
az login --identity

# Get access toen
ACCESS_TOKEN="$(az account get-access-token \
  --resource "https://ai.azure.com/" \
  --query accessToken \
  -o tsv)"

# Create the new request url for agent app RAPI endpoint
REQUEST_URL="${FOUNDRY_PROJECT_ENDPOINT}/agents/${FOUNDRY_AGENT_APPLICATION}/endpoint/protocols/openai/v1/responses?api-version=${API_VERSION}"

# For non-stream output
curl -v -sS --fail-with-body \
  -X POST "${REQUEST_URL}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"input":"Say hello"}'

# # For stream output
# curl -v -sS --fail-with-body \
#   -X POST "${REQUEST_URL}" \
#   -H "Authorization: Bearer ${ACCESS_TOKEN}" \
#   -H "Content-Type: application/json" \
#   -d '{"input":"Say hello", "stream":true}'


