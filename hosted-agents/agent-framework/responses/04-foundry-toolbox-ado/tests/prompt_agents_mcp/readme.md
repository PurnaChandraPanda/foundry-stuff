

## if following `tool` way for devops mcp server

```
cd ../..
```

- create agent

```
python tests/prompt_agents_mcp/01b.create_prompt_agent_tools.py 
```

- test agent

```
python tests/prompt_agents_mcp/02b.run_prompt_agent_tools.py 
```

## if following `toolbox` way for devops mcp server

- create the toolbox connection with USER token auth
- so that downstream tool > resource access will be carried by caller user token
- in short, keep toolbox and tool connection level auth type values identical

```bash
azd ai connection create ado-toolbox-conn \
  --kind remote-tool \
  --target "$TOOLBOX_ENDPOINT" \
  --auth-type user-entra-token \
  --audience https://ai.azure.com/ \
  -p "$FOUNDRY_PROJECT_ENDPOINT"
```

- read this toolbox related connection in create agent time with MCPTool()

- create agent

```
python tests/prompt_agents_mcp/01.create_prompt_agent_toolbox.py 
```

- test agent

```
python tests/prompt_agents_mcp/02.run_prompt_agent_toolbox.py 
```

