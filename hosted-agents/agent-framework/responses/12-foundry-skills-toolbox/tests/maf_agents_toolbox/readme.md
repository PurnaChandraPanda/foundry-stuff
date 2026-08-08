

## Call an Agent Framework agent with Foundry Toolbox

Set `FOUNDRY_PROJECT_ENDPOINT`, `AZURE_AI_MODEL_DEPLOYMENT_NAME`, and the
comma-separated Foundry toolbox endpoint: `TOOLBOX_ENDPOINT`.

```
cd ..
```

```bash
az login

python tests/maf_agents_toolbox/agent_toolbox_call.py \
  "I want a $750 refund on Order #A-1042 right now or I am calling my lawyer."

or

python tests/maf_agents_toolbox/agent_toolbox_call.py \
  "Hi, I am Alex. I just want to confirm I can return my tent within 30 days."
```

The script connects to the Foundry toolbox MCP endpoint, discovers its skills
as MCP resources through `MCPSkillsSource`, attaches them through
`SkillsProvider`, and runs the prompt. A skills-only toolbox does not expose a
tool manifest, so it must not be loaded as an `MCPStreamableHTTPTool` agent
tool.
