#!/usr/bin/env bash
# Run with bash, not source, so configuration variables stay in this process.
set +x
set +v
set -euo pipefail

usage() {
    printf 'Usage: bash %s <direct-mcp|direct-mcp-private|toolbox-mcp|toolbox-mcp-private>\n' "${0##*/}"
    printf 'Reads <selected-folder>/.env, logs in to its Azure tenant, then creates its APIM MCP connection.\n'
    printf '\nFolders:\n'
    printf '  direct-mcp           Existing direct-MCP setup\n'
    printf '  direct-mcp-private   Isolated private-APIM direct-MCP setup\n'
    printf '  toolbox-mcp          Public-APIM toolbox setup\n'
    printf '  toolbox-mcp-private  Private-APIM toolbox setup\n'
    printf '\nPrivate-route example from the sample root:\n'
    printf '  export MSYS_NO_PATHCONV=1  # Git Bash on Windows\n'
    printf '  bash ./create_mcp_connection.sh direct-mcp-private\n'
    printf '  bash ./create_mcp_connection.sh toolbox-mcp-private\n'
    printf 'Configure <selected-folder>/.env first, using its .env.example as a template.\n'
    printf 'Use a distinct APIM_MCP_CONNECTION_NAME; existing connections are not overwritten.\n'
}

fail() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

if [[ $# -eq 1 && ( $1 == "--help" || $1 == "-h" ) ]]; then
    usage
    exit 0
fi
if [[ $# -ne 1 ]]; then
    usage >&2
    exit 2
fi
case "$1" in
    direct-mcp|direct-mcp-private|toolbox-mcp|toolbox-mcp-private|apim-aca-mcp) selected_folder=$1 ;;
    *) usage >&2; exit 2 ;;
esac

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
env_file="$script_dir/$selected_folder/.env"
[[ -f "$env_file" ]] || fail "Missing $selected_folder/.env. Copy its .env.example and fill in the connection settings."
[[ -r "$env_file" ]] || fail "Cannot read $selected_folder/.env."

# Only the selected file supplies connection settings; never inherit another path's key.
unset AZURE_TENANT_ID AZURE_AI_PROJECT_ID AZURE_AI_PROJECT_ENDPOINT APIM_MCP_URL APIM_MCP_CONNECTION_NAME
unset APIM_SUBSCRIPTION_KEY_HEADER APIM_SUBSCRIPTION_KEY

# .env is trusted Bash-compatible configuration. Strip CRLF for Windows-edited files.
source <(
    while IFS= read -r line || [[ -n $line ]]; do
        printf '%s\n' "${line%$'\r'}"
    done < "$env_file"
)

for name in AZURE_TENANT_ID AZURE_AI_PROJECT_ID AZURE_AI_PROJECT_ENDPOINT APIM_MCP_URL APIM_MCP_CONNECTION_NAME \
    APIM_SUBSCRIPTION_KEY_HEADER APIM_SUBSCRIPTION_KEY; do
    value="${!name-}"
    [[ -n "${value//[[:space:]]/}" ]] || fail "Set $name in $selected_folder/.env."
    [[ $value != *'<'* && $value != *'>'* ]] || fail "Replace the placeholder for $name in $selected_folder/.env."
    [[ ! $value =~ [[:cntrl:]] ]] || fail "$name must not contain control characters."
done

tenant_pattern='^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$'
[[ $AZURE_TENANT_ID =~ $tenant_pattern ]] || fail "AZURE_TENANT_ID must be the Foundry resource tenant's GUID."

project_pattern='^/subscriptions/([0-9A-Fa-f-]+)/resourceGroups/[A-Za-z0-9_.()-]+/providers/Microsoft\.CognitiveServices/accounts/[A-Za-z0-9-]+/projects/[A-Za-z0-9_.-]+$'
[[ $AZURE_AI_PROJECT_ID =~ $project_pattern ]] \
    || fail "AZURE_AI_PROJECT_ID must be a full Microsoft.CognitiveServices/accounts/projects ARM resource ID."
subscription_id="${BASH_REMATCH[1]}"
[[ $subscription_id =~ $tenant_pattern ]] || fail "The subscription in AZURE_AI_PROJECT_ID must be a GUID."

url_pattern='^https://[^/?#@[:space:]]+(/[^?#[:space:]]*)?$'
for name in AZURE_AI_PROJECT_ENDPOINT APIM_MCP_URL; do
    [[ ${!name} =~ $url_pattern ]] || fail "$name must be an HTTPS URL without credentials, query, or fragment."
done
[[ $APIM_MCP_CONNECTION_NAME =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] \
    || fail "APIM_MCP_CONNECTION_NAME must contain only letters, digits, dots, and dashes."
header_pattern="^[!#\$%&'*+.^_\`|~0-9A-Za-z-]+$"
[[ $APIM_SUBSCRIPTION_KEY_HEADER =~ $header_pattern ]] \
    || fail "APIM_SUBSCRIPTION_KEY_HEADER must be a valid HTTP header name."

command -v az >/dev/null 2>&1 || fail "az is not installed or not on PATH. Install Azure CLI."
if [[ -n ${MSYSTEM-} && ${MSYS_NO_PATHCONV-} != 1 ]]; then
    fail "Run 'export MSYS_NO_PATHCONV=1' manually in your Git Bash terminal, then retry."
fi

# Preserve the selected endpoint aliases for child processes; ARM uses the project ID.
export AZURE_AI_PROJECT_ENDPOINT
export FOUNDRY_PROJECT_ENDPOINT="$AZURE_AI_PROJECT_ENDPOINT"

printf 'Using configuration: %s\n' "$env_file"
printf 'Authenticating to Azure tenant: %s\n' "$AZURE_TENANT_ID"
az login --tenant "$AZURE_TENANT_ID" --output none --only-show-errors

actual_tenant="$(az account show --subscription "$subscription_id" --query tenantId --output tsv --only-show-errors)"
actual_tenant="${actual_tenant//$'\r'/}"
[[ ${actual_tenant,,} == "${AZURE_TENANT_ID,,}" ]] \
    || fail "The subscription's Azure CLI tenant does not match AZURE_TENANT_ID. No connection was written."

api_version="2025-04-01-preview"
project_url="https://management.azure.com${AZURE_AI_PROJECT_ID}"
resource_endpoint="$(az rest --method get --url "$project_url?api-version=$api_version" \
    --subscription "$subscription_id" --query 'properties.endpoints."AI Foundry API"' --output tsv --only-show-errors)"
resource_endpoint="${resource_endpoint//$'\r'/}"
[[ -n $resource_endpoint && ${resource_endpoint%/} == "${AZURE_AI_PROJECT_ENDPOINT%/}" ]] \
    || fail "AZURE_AI_PROJECT_ID does not resolve to AZURE_AI_PROJECT_ENDPOINT. No connection was written."

# ARM PUT can replace credentials. Refuse existing names, including on later pages.
list_url="$project_url/connections?api-version=$api_version"
while [[ -n $list_url ]]; do
    page="$(az rest --method get --url "$list_url" --subscription "$subscription_id" \
        --query "join('|', [join(',', value[].name), not_null(nextLink, '')])" --output tsv --only-show-errors)"
    page="${page//$'\r'/}"
    [[ $page == *'|'* ]] || fail "Unexpected ARM connection-list response. No connection was written."
    IFS=',' read -r -a existing_names <<< "${page%%|*}"
    for existing_name in "${existing_names[@]}"; do
        [[ ${existing_name,,} != "${APIM_MCP_CONNECTION_NAME,,}" ]] \
            || fail "Connection '$APIM_MCP_CONNECTION_NAME' already exists. Reuse it or choose a new name; this script will not overwrite it."
    done
    next_url="${page#*|}"
    if [[ -n $next_url ]]; then
        [[ $next_url == "$project_url/connections?"* && $next_url != "$list_url" ]] \
            || fail "Unexpected ARM pagination URL. No connection was written."
    fi
    list_url="$next_url"
done

# Inputs cannot contain control characters; escape the remaining JSON metacharacters.
json_string() {
    local escaped="${1//\\/\\\\}"
    escaped="${escaped//\"/\\\"}"
    printf '"%s"' "$escaped"
}

payload_file=""
cleanup() {
    if [[ -n $payload_file ]]; then
        rm -f -- "$payload_file"
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
umask 077
payload_file="$(mktemp)"
printf '{"properties":{"category":"RemoteTool","authType":"CustomKeys","target":%s,"credentials":{"keys":{%s:%s}}}}\n' \
    "$(json_string "$APIM_MCP_URL")" "$(json_string "$APIM_SUBSCRIPTION_KEY_HEADER")" \
    "$(json_string "$APIM_SUBSCRIPTION_KEY")" > "$payload_file"

unset APIM_SUBSCRIPTION_KEY value
payload_path="$payload_file"
if command -v cygpath >/dev/null 2>&1; then
    payload_path="$(cygpath -w "$payload_file")"
fi

connection_url="$project_url/connections/$APIM_MCP_CONNECTION_NAME?api-version=$api_version"
printf 'Creating MCP connection: %s\n' "$APIM_MCP_CONNECTION_NAME"
az rest --method put --url "$connection_url" --subscription "$subscription_id" \
    --headers 'Content-Type=application/json' --body "@$payload_path" --output none --only-show-errors
cleanup
payload_file=""

connection_metadata="$(az rest --method get --url "$connection_url" --subscription "$subscription_id" \
    --query "join('|', [properties.category, properties.authType, properties.target])" --output tsv --only-show-errors)"
connection_metadata="${connection_metadata//$'\r'/}"
[[ $connection_metadata == "RemoteTool|CustomKeys|$APIM_MCP_URL" ]] \
    || fail "Connection write succeeded, but its stored metadata did not match. Inspect the connection before using it."
printf 'Connection creation completed and stored metadata verified. This does not verify MCP connectivity.\n'
