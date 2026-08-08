

## Call an Agent Framework agent with Foundry Skills

Set `FOUNDRY_PROJECT_ENDPOINT`, `AZURE_AI_MODEL_DEPLOYMENT_NAME`, and the
comma-separated Foundry skill names `SKILL_NAMES`.

```bash
az login

python tests/maf_agents_skill/agent_foundry_skill.py \
  "I want a $750 refund on Order #A-1042 right now or I am calling my lawyer."

or

python tests/maf_agents_skill/agent_foundry_skill.py \
  "Hi, I am Alex. I just want to confirm I can return my tent within 30 days."
```

The script downloads the named skills from Foundry, attaches them through
`SkillsProvider`, runs the prompt, and removes the temporary skill files.
