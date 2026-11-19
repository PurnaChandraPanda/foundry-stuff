## Dev env - virtual environment

```
python --version
python -m venv .lgenv
.\.lgenv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run the sample

- Rename the `.env.example` into `.env`.
- Update the correct key-value pairs of Foundry and Application Insights resource.

- As os environment key `APPLICATIONINSIGHTS_CONNECTION_STRING` is already set, it will be effective to push in code to push the telemtries in the sink - via `use_microsoft_opentelemetry(...)` API. It need not be explicitly set in code at times.

- Run `az login` in terminal to leverage the bearer token based client side access flow working.

- With langchain, invoke the LLM model in Azure OpenAI with bearer token. At the same time, the llm usage get tracked in the application insights sink.

```bash
python sample_foundry_responses_api.py
```

- With langchain, create agent with tools that invokes the LLM model in Azure OpenAI with bearer token. At the same time, the llm usage get tracked in the application insights sink.

```bash
python sample_langchain_instrumentation.py
```

- With langgraph, create graph involving basic agent with tools that invokes the LLM model in Azure OpenAI with bearer token. At the same time, the llm usage get tracked in the application insights sink.

```bash
python sample_nested_graph.py
```

- All these runs would allow push events directly from wherever this code is running, into the sink of associated application insights. 

- To review if anything is tracked in application insights, follow the KQL in applicaiton insights.

```kql
dependencies
| where customDimensions contains "gen_ai"
```

- Follow [Register external agent in Foundry](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/register-external-agent?tabs=portal#register-the-external-agent-in-foundry) to add the already tracked agent in application insights. In Foundry connected Agent -> Traces, you ll view the existing trace. If any new calls are tried on same agent id, those traces would perfectly be visible in Foundry Traces page.

## Reference
[microsoft opentelemetry - langchain](https://github.com/microsoft/opentelemetry-distro-python/tree/main/samples/langchain)

