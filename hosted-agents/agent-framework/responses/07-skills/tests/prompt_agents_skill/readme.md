

## Create a prompt agent from a local skill

Prompt agents cannot execute local skill scripts. The creation script snapshots
the local `travel-guide/SKILL.md` into the prompt-agent instructions and tells
the agent to return the guide as text.

```
cd ../..
```

- create agent

```bash
az login

python tests/prompt_agents_skill/01.create_prompt_agent_skill.py
```

- test agent

```bash
python tests/prompt_agents_skill/02.run_prompt_agent_skill.py \
  "Create a 3-day Lisbon travel guide focused on food and viewpoints."
```
