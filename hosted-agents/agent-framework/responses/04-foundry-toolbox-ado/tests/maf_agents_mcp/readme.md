
## Call ADO MCP tool server directly

- In [agent_direct_ado_mcp.py](./agent_direct_ado_mcp.py) [line-19], update `ado_org` value that is point of interest.

- Run the agent

```bash
python tests/maf_agents_mcp/agent_direct_ado_mcp.py 
```

## Call ADO MCP toolbox

- In [agent_foundry_ado_mcp.py](./agent_foundry_ado_mcp.py) [line-17], update `toolbox_name` value as its reflected in the Foundry Project level.

```bash
python tests/maf_agents_mcp/agent_foundry_ado_mcp.py 
```

