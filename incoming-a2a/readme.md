## Setup

- Install required python packages.

```bash
pip install "azure-ai-projects>=2.3.0" python-dotenv

pip install "a2a-sdk>=1.1.2" azure-identity "httpx==0.28.1"
```

- Rename `.env.example` file to `.env` - update the environment key:value pairs.

## Enable destination agent with a2a protocol

- Create the destination prompt agent that does web search.

```bash
python 0.create_prompt_agent.py
```

- Validate the destination agent if runs fine at vanilla level.

```bash
python 1.run_agent_stream.py
```

- Enable a2a protocol on the destination agent.

```bash
./3.enable_a2a_destination_agent.sh
```

- Connect to a Foundry A2A agent with the Python A2A SDK.

```bash
python 4.a2a_client_prompt_agent.py
```

## Connect from source Foundry agent

- Create an A2A connection to the target agent

```
-> The connection stores the target agent's A2A endpoint URL and authentication details. 
-> For a Foundry agent target, don't set an agent card path. 
-> Foundry resolves the default agent card path automatically and negotiates the A2A protocol version for you.
-> Over here, "authType" is set as "AgenticIdentityToken". It means caller agent's ID would be used to used to reach the destination agent.
```

```bash
./5.create_remote_a2a_connection_agent.sh
```

- Create the calling agent with the A2A tool

```bash
python 6.create_caller_prompt_agent.py
```

- Assign the caller agent with `Foundry Agent Consumer` role as a2a target connection created to follow `Microsoft Entra Agent Identity` authentication. It means caller agent's ID will be used to reach destination agent.

```bash
./6.1.assign-caller-agent-consumer-role.sh
```

- Run the calling agent

```bash
python 7.run_caller_agent.py
```

On traces side, if reviewing in depth, you would notice the `web_search_call` only be available in case of destination agent. And, the caller agent traces would indicate of just `remote_function_call: SendMessage`. It means caller just initiated the message call here for other agent.

## References
[enable-incoming-a2a](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint?tabs=rest-bash%2Cverify-bash%2Cconnection-bash#enable-incoming-a2a)