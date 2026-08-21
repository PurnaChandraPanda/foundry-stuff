#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: .env file not found at $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${FOUNDRY_PROJECT_ENDPOINT:?FOUNDRY_PROJECT_ENDPOINT is required in $ENV_FILE}"
: "${FOUNDRY_AGENT_NAME:?FOUNDRY_AGENT_NAME is required in $ENV_FILE}"

BASE_URL="${FOUNDRY_PROJECT_ENDPOINT%/}"
AGENT_NAME="$FOUNDRY_AGENT_NAME"

# Get access token
TOKEN=$(az account get-access-token --resource "$TOKEN_SCOPE_URL" \
  --query accessToken -o tsv)

echo "Enabling A2A destination agent: $AGENT_NAME"

# Send a PATCH request to configure the agent card and enable the A2A protocol
curl -fsS -X PATCH "$BASE_URL/agents/$AGENT_NAME?api-version=v1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_card": {
      "description": "A helpful assistant that answers questions",
      "version": "1.0",
      "skills": [
        {
          "id": "general-qa",
          "name": "General Q&A",
          "description": "Answers general questions"
        }
      ]
    },
    "agent_endpoint": {
      "protocol_configuration": {
        "responses": {},
        "a2a": {}
      }
    }
  }'

echo -e "\nA2A destination agent enabled successfully.\n"

# To confirm your agent card is configured correctly, fetch the v1.0 card directly.
curl -fsS -X GET "$BASE_URL/agents/$AGENT_NAME/endpoint/protocols/a2a/agentCard/v1.0" \
  -H "Authorization: Bearer $TOKEN"
