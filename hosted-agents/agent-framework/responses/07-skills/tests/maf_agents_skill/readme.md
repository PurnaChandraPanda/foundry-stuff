

## Call an Agent Framework agent with a local skill

Set `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME`.

```bash
az login

python tests/maf_agents_skill/agent_local_skill.py \
  "Create a 3-day PDF travel guide for Lisbon focused on food and viewpoints."
```

The script loads `src/agent-framework-agent-with-skills-responses/skills`
directly through `SkillsProvider`. It can execute the trusted local
`create_travel_guide.py` script and generate a PDF.
