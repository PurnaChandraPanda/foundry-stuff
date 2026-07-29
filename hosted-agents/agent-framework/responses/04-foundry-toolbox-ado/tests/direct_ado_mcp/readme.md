
- update the following parameters in test_ado_mcp.sh
```
export ADO_MCP_SCOPE="https://mcp.dev.azure.com"
export DEVOPS_ORG="your-devops-org-name"
export DEVOPS_PROJECT="your-devops-project-name"
export DEVOPS_REPO="your-devops-repo-name"
export DEVOPS_BRANCH="your-devops-repo-branch"
```

- run the sh script

```
cd ../..

./tests/direct_ado_mcp/test_ado_mcp.sh
```