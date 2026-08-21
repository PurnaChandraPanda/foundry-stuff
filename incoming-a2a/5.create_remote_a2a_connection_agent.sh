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

# Set up variables (with foundry project details)
TARGET_A2A_URL="${FOUNDRY_PROJECT_ENDPOINT%/}/agents/${FOUNDRY_AGENT_NAME}/endpoint/protocols/a2a"

# Get access token for Azure Management API
TOKEN=$(az account get-access-token \
  --scope https://management.azure.com/.default \
  --query accessToken -o tsv)

# Create a remote A2A connection to the Foundry agent
echo "Creating remote A2A connection: $FOUNDRY_A2A_CONNECTION_NAME"

curl -fsS --request PUT \
  --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$FOUNDRY_ACCOUNT/projects/$PROJECT_NAME/connections/$FOUNDRY_A2A_CONNECTION_NAME?api-version=2025-04-01-preview" \
  --header "Authorization: Bearer $TOKEN" \
  --header "Content-Type: application/json" \
  --data '{
    "properties": {
      "authType": "AgenticIdentityToken",
      "category": "RemoteA2A",
      "target": "'"$TARGET_A2A_URL"'",
      "audience": "'"$TOKEN_SCOPE_URL"'",
      "Credentials": {},
      "metadata": {}
    }
  }'

echo -e "\nRemote A2A connection created successfully.\n"
