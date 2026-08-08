

## Create a prompt agent with Foundry Skills

Prompt agents cannot consume skills through a toolbox endpoint because toolbox
skills are MCP resources, while prompt-agent MCP integration exposes callable MCP
tools. The Responses API also rejects `skill_reference` as a prompt-agent tool.

```
cd ../..
```

- Create explicit connection for toolbox endpoint

```
azd ai connection create contoso-skills-toolbox-conn \
  --kind remote-tool \
  --target "$TOOLBOX_ENDPOINT" \
  --auth-type agentic-identity \
  --audience "https://ai.azure.com"
```

- create agent

```bash
az login

python tests/prompt_agents_toolbox/01.create_prompt_agent_toolbox.py
```

- For the prompt agent, go to foundry portal. Read the yaml. Go to `instance_identity` section, and grab `principal_id` for downstream role assignments.

```
instance_identity:
  principal_id: 1cc65540-4ebf-4be2-8884-8adda9d15447
  client_id: 1cc65540-4ebf-4be2-8884-8adda9d15447
```

- Assign this prompt agent ID with `Foundry User` role on project level at least.

```
az role assignment create \
  --assignee-object-id "1cc65540-4ebf-4be2-8884-8adda9d15447" \
  --assignee-principal-type ServicePrincipal \
  --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" \
  --scope "$FOUNDRY_PROJECT_ID"

az role assignment list \
  --assignee-object-id "1cc65540-4ebf-4be2-8884-8adda9d15447" \
  --include-inherited \
  --all \
  --output table
```

- test agent

```bash
python tests/prompt_agents_toolbox/02.run_prompt_agent_toolbox.py
```
