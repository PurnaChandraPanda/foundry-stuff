#!/usr/bin/env bash
set -euo pipefail

# <Parameters> [START]
## ADO mcp scope is constant
export ADO_MCP_SCOPE="https://mcp.dev.azure.com"
export DEVOPS_ORG="your-devops-org-name"
export DEVOPS_PROJECT="your-devops-project-name"
export DEVOPS_REPO="your-devops-repo-name"
export DEVOPS_BRANCH="your-devops-repo-branch"
# </Parameters> [END]

ADO_TOKEN=$(az account get-access-token --resource $ADO_MCP_SCOPE --query accessToken -o tsv)

echo "========== TESTING ADO MCP =========="

# init
curl -i -X POST "$ADO_MCP_SCOPE/$DEVOPS_ORG" \
  -H "Authorization: Bearer $ADO_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'

echo "========== TESTING ADO MCP: tools/list =========="

# tools/list
curl -s -X POST "$ADO_MCP_SCOPE/$DEVOPS_ORG" \
  -H "Authorization: Bearer $ADO_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"2","method":"tools/list","params":{}}'

echo "========== TESTING ADO MCP: tools/call core_list_projects =========="

# Then try calling a tool directly
curl -s -X POST "$ADO_MCP_SCOPE/$DEVOPS_ORG" \
  -H "Authorization: Bearer $ADO_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"3","method":"tools/call","params":{"name":"core_list_projects","arguments":{}}}'

echo "========== TESTING ADO MCP: tools/call repo_search_commits =========="

# Then try calling a tool directly
curl -s -X POST "$ADO_MCP_SCOPE/$DEVOPS_ORG" \
  -H "Authorization: Bearer $ADO_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"4","method":"tools/call","params":{"name":"repo_search_commits","arguments":{"project":"'$DEVOPS_PROJECT'","repository":"'$DEVOPS_REPO'","version":"'$DEVOPS_BRANCH'","versionType":"Branch","top":3}}}' | sed -n 's/^data: //p' | jq .

echo "========== DONE =========="