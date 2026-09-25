#!/usr/bin/env bash
# Run with bash, not source, so configuration stays in this process.
set +x
set +v
set -euo pipefail

usage() {
    printf 'Usage: bash %s\n' "${0##*/}"
    printf 'Reads .env beside this script and creates the prompt-agent-to-toolbox Entra connection with Azure CLI.\n'
    printf 'Required: AZURE_TENANT_ID, AZURE_AI_PROJECT_ID, AZURE_AI_PROJECT_ENDPOINT,\n'
    printf '          APIM_TOOLBOX_NAME, APIM_TOOLBOX_CONNECTION_NAME.\n'
    printf 'Git Bash: first run export MSYS_NO_PATHCONV=1 manually.\n'
    printf 'Existing connections are not overwritten. No azd context or Python environment is needed.\n'
}

fail() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

if [[ $# -eq 1 && ( $1 == "--help" || $1 == "-h" ) ]]; then
    usage
    exit 0
fi
if [[ $# -ne 0 ]]; then
    usage >&2
    exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
env_file="$script_dir/.env"
[[ -f $env_file && -r $env_file ]] || fail "Missing or unreadable .env beside this script."

unset AZURE_TENANT_ID AZURE_AI_PROJECT_ID AZURE_AI_PROJECT_ENDPOINT
unset APIM_TOOLBOX_NAME APIM_TOOLBOX_CONNECTION_NAME APIM_MCP_CONNECTION_NAME
# Source only trusted Bash-compatible configuration; accept Windows CRLF files.
source <(
    while IFS= read -r line || [[ -n $line ]]; do
        printf '%s\n' "${line%$'\r'}"
    done < "$env_file"
)
unset APIM_SUBSCRIPTION_KEY

for name in AZURE_TENANT_ID AZURE_AI_PROJECT_ID AZURE_AI_PROJECT_ENDPOINT \
    APIM_TOOLBOX_NAME APIM_TOOLBOX_CONNECTION_NAME; do
    value="${!name-}"
    [[ -n "${value//[[:space:]]/}" ]] || fail "Set $name in $env_file."
    [[ $value != *'<'* && $value != *'>'* ]] || fail "Replace the placeholder for $name in $env_file."
    [[ ! $value =~ [[:cntrl:]] ]] || fail "$name must not contain control characters."
done

guid_pattern='^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$'
[[ $AZURE_TENANT_ID =~ $guid_pattern ]] || fail "AZURE_TENANT_ID must be the Foundry resource tenant's GUID."
project_pattern='^/subscriptions/([0-9A-Fa-f-]+)/resourceGroups/[A-Za-z0-9_.()-]+/providers/Microsoft\.CognitiveServices/accounts/[A-Za-z0-9-]+/projects/[A-Za-z0-9_.-]+$'
[[ $AZURE_AI_PROJECT_ID =~ $project_pattern ]] \
    || fail "AZURE_AI_PROJECT_ID must be the full Microsoft.CognitiveServices/accounts/projects ARM resource ID."
subscription_id="${BASH_REMATCH[1]}"
[[ $subscription_id =~ $guid_pattern ]] || fail "The subscription in AZURE_AI_PROJECT_ID must be a GUID."
url_pattern='^https://[^/?#@[:space:]]+(/[^?#[:space:]]*)?$'
[[ $AZURE_AI_PROJECT_ENDPOINT =~ $url_pattern ]] \
    || fail "AZURE_AI_PROJECT_ENDPOINT must be an HTTPS URL without credentials, query, or fragment."
[[ $APIM_TOOLBOX_NAME =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] \
    || fail "APIM_TOOLBOX_NAME must contain only letters, digits, dots, underscores, or dashes."
[[ $APIM_TOOLBOX_CONNECTION_NAME =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] \
    || fail "APIM_TOOLBOX_CONNECTION_NAME must contain only letters, digits, dots, and dashes."
apim_connection_name="${APIM_MCP_CONNECTION_NAME-}"
[[ ${APIM_TOOLBOX_CONNECTION_NAME,,} != "${apim_connection_name,,}" ]] \
    || fail "Use a separate toolbox connection name, not APIM_MCP_CONNECTION_NAME."

command -v az >/dev/null 2>&1 || fail "az is not installed or not on PATH. Install Azure CLI."
if [[ -n ${MSYSTEM-} && ${MSYS_NO_PATHCONV-} != 1 ]]; then
    fail "Run 'export MSYS_NO_PATHCONV=1' manually in Git Bash, then retry."
fi

printf 'Using configuration: %s\n' "$env_file"
az login --tenant "$AZURE_TENANT_ID" --output none --only-show-errors
actual_tenant="$(az account show --subscription "$subscription_id" --query tenantId --output tsv --only-show-errors)"
actual_tenant="${actual_tenant//$'\r'/}"
[[ ${actual_tenant,,} == "${AZURE_TENANT_ID,,}" ]] \
    || fail "The subscription tenant does not match AZURE_TENANT_ID. No connection was written."

api_version="2025-04-01-preview"
project_url="https://management.azure.com${AZURE_AI_PROJECT_ID}"
resource_endpoint="$(az rest --method get --url "$project_url?api-version=$api_version" \
    --subscription "$subscription_id" --query 'properties.endpoints."AI Foundry API"' --output tsv --only-show-errors)"
resource_endpoint="${resource_endpoint//$'\r'/}"
[[ -n $resource_endpoint && ${resource_endpoint%/} == "${AZURE_AI_PROJECT_ENDPOINT%/}" ]] \
    || fail "AZURE_AI_PROJECT_ID does not resolve to AZURE_AI_PROJECT_ENDPOINT. No connection was written."

# ARM PUT is an upsert. Check every page before writing; do not create concurrently.
list_url="$project_url/connections?api-version=$api_version"
declare -A visited_pages=()
while [[ -n $list_url ]]; do
    [[ -z ${visited_pages[$list_url]-} ]] || fail "Repeated ARM pagination URL. No connection was written."
    visited_pages[$list_url]=1
    page="$(az rest --method get --url "$list_url" --subscription "$subscription_id" \
        --query "join('|', [join(',', value[].name), not_null(nextLink, '')])" --output tsv --only-show-errors)"
    page="${page//$'\r'/}"
    [[ $page == *'|'* ]] || fail "Unexpected ARM connection-list response. No connection was written."
    IFS=',' read -r -a existing_names <<< "${page%%|*}"
    for existing_name in "${existing_names[@]}"; do
        [[ ${existing_name,,} != "${APIM_TOOLBOX_CONNECTION_NAME,,}" ]] \
            || fail "Connection '$APIM_TOOLBOX_CONNECTION_NAME' already exists. Reuse it if it matches, or choose a new name."
    done
    list_url="${page#*|}"
    [[ -z $list_url || $list_url == "$project_url/connections?"* ]] \
        || fail "Unexpected ARM pagination URL. No connection was written."
done

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
toolbox_url="${AZURE_AI_PROJECT_ENDPOINT%/}/toolboxes/${APIM_TOOLBOX_NAME}/mcp?api-version=v1"
printf '{"properties":{"category":"RemoteTool","authType":"AgenticIdentityToken","target":%s,"audience":"https://ai.azure.com"}}\n' \
    "$(json_string "$toolbox_url")" > "$payload_file"
payload_path="$payload_file"
if command -v cygpath >/dev/null 2>&1; then
    payload_path="$(cygpath -w "$payload_file")"
fi

connection_url="$project_url/connections/$APIM_TOOLBOX_CONNECTION_NAME?api-version=$api_version"
printf 'Creating toolbox identity connection: %s\n' "$APIM_TOOLBOX_CONNECTION_NAME"
az rest --method put --url "$connection_url" --subscription "$subscription_id" \
    --headers 'Content-Type=application/json' --body "@$payload_path" --output none --only-show-errors
cleanup
payload_file=""

metadata="$(az rest --method get --url "$connection_url" --subscription "$subscription_id" \
    --query "join('|', [properties.category, properties.authType, properties.target, properties.audience])" \
    --output tsv --only-show-errors)"
metadata="${metadata//$'\r'/}"
[[ $metadata == "RemoteTool|AgenticIdentityToken|$toolbox_url|https://ai.azure.com" ]] \
    || fail "Connection write succeeded, but stored metadata did not match. Inspect the connection before using it."
printf 'Connection created and metadata verified. No toolbox or APIM connection was changed.\n'
printf 'Next: create the prompt agent, grant its identity Foundry User access on the toolbox project, and run it.\n'
printf 'This does not verify runtime permissions or MCP connectivity.\n'
