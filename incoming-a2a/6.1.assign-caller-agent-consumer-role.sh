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

# Set up variables (with foundry project details)
PROJECT_SCOPE="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$FOUNDRY_ACCOUNT/projects/$PROJECT_NAME"

# Get access token generated for the Foundry use
TOKEN=$(az account get-access-token \
  --resource "$TOKEN_SCOPE_URL" \
  --query accessToken -o tsv)

# Grab the object ID of the agent's managed identity
OBJECT_ID=$(az rest \
  --method get \
  --url "$FOUNDRY_PROJECT_ENDPOINT/agents/$FOUNDRY_CALLER_AGENT_NAME?api-version=v1" \
  --resource "$TOKEN_SCOPE_URL" \
  --query "instance_identity.principal_id" \
  -o tsv)

# Assign the "Foundry Agent Consumer" role to the agent's managed identity if does not already exist
ROLE_NAME="Foundry Agent Consumer"
ASSIGNMENT_COUNT=$(az role assignment list \
  --assignee "$OBJECT_ID" \
  --scope "$PROJECT_SCOPE" \
  --include-inherited \
  --query "[?roleDefinitionName=='$ROLE_NAME'] | length(@)" \
  -o tsv)

if (( ASSIGNMENT_COUNT > 0 )); then
  echo "'$ROLE_NAME' is already assigned to agent identity $OBJECT_ID."
else
  echo "Assigning '$ROLE_NAME' to agent identity $OBJECT_ID..."
  az role assignment create \
    --assignee-object-id "$OBJECT_ID" \
    --assignee-principal-type ServicePrincipal \
    --role "$ROLE_NAME" \
    --scope "$PROJECT_SCOPE" \
    -o none
  echo "Role assigned successfully."
fi
