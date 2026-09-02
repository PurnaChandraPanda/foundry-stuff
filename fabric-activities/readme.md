# Fabric activities

Two ways to let a Microsoft Foundry agent answer questions over Microsoft Fabric
data. Each folder is self-contained: its own `.env`, `requirements.txt`, scripts
and runbook.

| Folder | Tool | Use it when |
| --- | --- | --- |
| [`fabric-data-agent/`](./fabric-data-agent) | `fabric_dataagent_preview` | You have a published Fabric **data agent** and want the shortest path to it. Also contains the `azd`-deployed hosted agent variant. |
| [`fabric-iq/`](./fabric-iq) | `fabric_iq_preview` (MCP) | You want the broader Fabric IQ surface - ontology, data agent, or Power BI semantic model - reached over MCP. |

Both are built against the same Fabric workspace and answer the same questions,
so they are directly comparable.

- `fabric-data-agent` follows [/tools/fabric/](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/fabric?pivots=python)
- `fabric-iq` follows [/tools/fabric-iq/](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/fabric-iq?pivots=python)

Each folder covers the same three shapes:

1. **Prompt agent** - a server-side agent definition created through the Foundry
   SDK, then invoked.
2. **Local agent** - an Agent Framework agent running on your machine.
3. **Diagnostics** - a script that checks the connection and the Fabric endpoint
   independently of any agent, so a failure can be attributed.

Creating and running are always separate scripts, so a failure points at one
thing rather than a combined step.

`fabric-data-agent` additionally has `hosted-agent/`, an `azd`-deployable
container serving the Responses protocol.

## Common prerequisites

- Fabric item published, on F2+ capacity, with the capacity **resumed**.
- `az login` as a user with read access to the Fabric item and its data sources.
  Both tools run Fabric queries as the calling user.
- A model deployment in the Foundry project.
