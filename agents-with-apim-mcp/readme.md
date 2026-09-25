# APIM MCP: direct and toolbox samples for public and private endpoints

## Private APIM status and reference

The private APIM prompt/ hosted tool calls tested in the case where APIM just have private inbound enabled, are not working.** APIM returned `403` with "Request originated from client public IP address" and "public network access ... is disabled". However, the agents to apim tool calls are working when outbound is enabled for the VNET the source agent subnet is kept in.

The public mcp direct/ toolbox flows are reported working.

Direct and toolbox paths, with isolated configurations for public and private APIM MCP:

| Folder | Included code | APIM caller |
| --- | --- | --- |
| [direct-mcp](./direct-mcp/readme.md) | Diagnostics, native prompt agent, local MAF agent, direct hosted MAF agent | Foundry for the prompt agent; your Python process for local/hosted MAF |
| [direct-mcp-private](./direct-mcp-private/readme.md) | Isolated private-route copy of direct MCP with separate configuration and agent names | Same execution paths as direct MCP; each caller needs private APIM connectivity |
| [toolbox-mcp](./toolbox-mcp/readme.md) | Public-APIM toolbox publication, native prompt agent, local MAF consumer, toolbox-backed hosted MAF agent | Foundry toolbox service -> public APIM |
| [toolbox-mcp-private](./toolbox-mcp-private/readme.md) | Private-APIM toolbox publication, native prompt agent, local MAF consumer, toolbox-backed hosted MAF agent | Foundry toolbox service -> private APIM; requires private routing/DNS |
| [apim-aca-mcp](./apim-aca-mcp/readme.md) | Private APIM mcp proxy for existing azure hosted MCP serverss | Foundry agent -> private APIM -> MCP servers -> ACA mcp server |

For direct MCP, start with [direct-mcp](./direct-mcp/readme.md), or
[direct-mcp-private](./direct-mcp-private/readme.md) for the isolated private route.
No toolbox is needed for any of their three agent options.
For toolbox execution, choose `toolbox-mcp` for public APIM or
`toolbox-mcp-private` for private APIM.
As selected for this sample, the prompt agent uses native `MCPTool`,
not a custom client-side function bridge. It does not execute Python in Foundry.

## Set up the APIM MCP server

In this sample, the `standard v2` SKU for APIM is followed. Complete this setup before creating the Foundry connections, toolboxes, or agents. The sample exposes an existing Foundry account's **Chat Completions** API through APIM, then exposes that API operation as an MCP tool:

```text
Agent or Foundry toolbox -> APIM MCP server -> imported Chat Completions API
                                             -> Foundry model deployment
```

### 1. Import the Foundry API into APIM

1. Open the APIM instance in Azure portal.
2. Go to **APIs > APIs > + Add API**. Under **Create from Azure resource**,
   select **Microsoft Foundry**.
3. Select the subscription and the **existing Foundry account/service by name**
   that hosts your model deployment.
4. Configure the API display name, base path/API URL suffix, and client
   compatibility. Choose the Azure OpenAI compatibility option matching the API
   you intend to expose; **Azure OpenAI v1** is available for v1 clients.
   Review the optional policies and create the API.
5. Open the imported API and locate its **Chat Completions** operation. Test it
   with a deployed model, a user message, and the parameters required by that
   imported operation. Confirm a successful backend response before adding MCP.

Reference: [Import a Microsoft Foundry API](https://learn.microsoft.com/en-us/azure/api-management/azure-ai-foundry-api).

### 2. Expose the imported API as an MCP server

1. In the same APIM instance, go to **APIs > MCP Servers > + Create MCP server**.
2. Select **Expose an API as an MCP server**. This exposes operations from the existing REST API; it is not the option for proxying an existing MCP server.
3. Select the API imported above, then select the **Chat Completions** operation to expose as a tool. Expose only the operations intended for these agents.
4. Enter the MCP server name, display name, and description. Configure product association/subscription requirements as appropriate for your access model, then select **Create**.
5. Copy the exact **Server URL** from the MCP server listing into `APIM_MCP_URL` in the chosen sample folder. Preserve its path and any trailing slash. Do not substitute the original REST Chat Completions URL or Foundry project endpoint.
6. Review the MCP server's **Tools** and confirm the names and input schemas with MCP discovery. Set `APIM_ALLOWED_TOOLS` to the exact exposed names and configure the APIM key/header for the subscription allowed to access this server.

### For private API MCP

- On the APIM network, keep public network access (PNA) disabled.
- Add an **inbound private endpoint** for the APIM gateway, reachable from the caller's network (the Foundry execution subnet). This can be the same VNet or a **peered** VNet — same VNet is not required.
- Add **outbound VNet integration** so APIM can reach its backend (and the MCP self-call). The backend can be in the same or a **peered** VNet. The integration subnet must be delegated to `Microsoft.Web/serverFarms` and have an NSG attached; otherwise adding outbound integration fails.
- Use **separate subnets** for the two roles: the inbound private endpoint subnet hosts the PE and must **not** be delegated (PE subnets cannot be delegated), while the outbound integration subnet carries the `Microsoft.Web/serverFarms` delegation described above.

Same-vs-peered is not the deciding factor for either hop. Per [Azure Private Link](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-overview), private endpoints are reachable from the same VNet, regionally or globally peered VNets, and on-premises over VPN/ExpressRoute. What actually determines success:

- **DNS**: the `privatelink.azure-api.net` zone must resolve the gateway hostname to the private endpoint's private IP from the caller's network (zone linked to the caller VNet, or DNS forwarding). Wrong DNS is the usual cause of a public-path `403`; peering alone does not fix it.
- **Direct peering**: VNet peering is non-transitive. A hub-spoke `A ↔ hub ↔ B` does not give `A → B` unless directly peered or routed via a gateway/NVA with UDRs.
- **NSG / UDR / firewall** must permit the path on both subnets, and the private endpoint connection must be **Approved**.

In this sample, the selected operation is exposed as `createsAChatCompletion`. Use the actual discovered schema rather than assuming every import produces that name or the same argument layout. For the schema used in the sample prompts, `api-version` is a top-level argument and the body fields belong inside `AzureCreateChatCompletionRequest`. That is an imported-schema detail, not a
universal MCP requirement.

Reference: [Expose a REST API as an MCP server](https://learn.microsoft.com/en-us/azure/api-management/export-rest-mcp-server).

### 3. Choose public or private APIM gateway access

The API import and MCP exposure steps are the same. The difference is how the
caller reaches the APIM gateway:

| Setting | Public APIM sample | Private APIM sample |
| --- | --- | --- |
| Public network access (PNA) | Enabled / all networks | Disabled |
| Inbound private endpoint | Not required for the public route | Create for the APIM **Gateway** subresource; connection must be approved |
| Gateway DNS | Public resolution | Resolve the gateway hostname to the private-endpoint IP from the calling network |
| Calling network | Must reach the public gateway | Must have routing and DNS access to the private endpoint |
| APIM authentication | Subscription key and applicable policies still required | Subscription key and applicable policies still required |

For the **public case**, enable public network access from **all networks** in
APIM's network settings. This enables network reachability, not anonymous access;
retain subscription requirements and the intended access policies.

For the **private case**, use an APIM tier/topology that supports inbound private
endpoints:

1. In APIM's **Network / Inbound private endpoint connections** settings, add an inbound private endpoint for **Gateway** in the intended VNet/subnet.
2. Ensure the private endpoint connection is **Approved**.
3. Configure private DNS integration (normally `privatelink.azure-api.net` for the default gateway hostname), VNet links or DNS forwarding, and private routing from the actual caller. Keep using the certificate-matching gateway hostname in `APIM_MCP_URL`, not a raw private IP.
4. Once the private endpoint is configured, disable APIM **public network access** and verify the tool call over the private path.

An APIM inbound private endpoint does not configure Foundry outbound networking or APIM-to-backend networking. For toolbox consumers, the **Foundry toolbox executor** must reach private APIM; for direct hosted MCP, the **hosted runtime** must do so. 

Reference: [Set up an inbound private endpoint for APIM](https://learn.microsoft.com/en-us/azure/api-management/private-endpoint).

## Network requirements

Assumptions: a public APIM gateway for `toolbox-mcp`, or a private-network-only gateway for `toolbox-mcp-private` and the private direct route; subscription-key authentication, an actual **Streamable HTTP MCP** Server URL, and a new Foundry project with a compatible model deployment. 

| Execution path | Required connectivity |
| --- | --- |
| Native prompt agent -> APIM | Foundry tool execution must resolve/reach APIM |
| Local direct MAF -> APIM | Your machine's VPN/VNet must resolve/reach APIM |
| Hosted direct MAF -> APIM | Hosted runtime outbound VNet must resolve/reach APIM |
| Prompt agent or local/hosted MAF -> public toolbox -> APIM | Client must reach Foundry; Foundry toolbox execution must reach the public APIM gateway |
| Prompt agent or local/hosted MAF -> private toolbox -> APIM | Client must reach Foundry; Foundry toolbox execution must privately resolve/reach APIM |

Public APIM still requires the configured subscription key and gateway policies that permit the Foundry caller. It does not require a private route to APIM. The private-network guidance below applies when targeting a private gateway.

**Direct does not mean automatic network access.** Your laptop VPN is not inherited by Foundry. A Foundry inbound private endpoint, project connection, or toolbox does not create an outbound network route.

Microsoft Learn documents
[private MCP support](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/model-context-protocol#public-and-private-mcp-server-endpoints),
[tool traffic through your VNet](https://learn.microsoft.com/en-us/azure/foundry/how-to/configure-private-link#agent-tools-with-network-isolation),
and [hosted outbound VNet support](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents#private-networking).
The private-MCP reference deployment uses internal Container Apps; validate your
existing APIM/project topology rather than assuming that reference configures it.

Before invoking a private APIM endpoint from Foundry:

1. Configure a supported
   [network-secured Foundry deployment](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/virtual-networks).
   Follow its subnet delegation, sizing, setup, and regional requirements.
2. Configure APIM gateway DNS for the actual execution network, including private
   zone links or custom DNS forwarding.
3. Permit HTTPS through routing, peering, NSGs, UDRs, firewalls, and APIM policies.
4. Use a hostname matching APIM's TLS certificate; do not disable verification.
5. Verify APIM-to-backend networking/authentication independently.
6. Invoke an actual tool and correlate with APIM logs. Agent creation and a
   natural-language answer alone do not prove connectivity.

All paths still send tool schemas/results to the Foundry model for reasoning.
Local orchestration is not offline inference.

## APIM project connection

The local direct agent takes its key from local configuration. The direct native prompt agent, direct hosted agent, and toolbox publisher use a Foundry **RemoteTool** project connection with **CustomKeys** authentication:

Each toolbox-backed prompt agent additionally needs a separate Entra-authenticated connection to its **toolbox endpoint**. See the
[public setup](./toolbox-mcp/readme.md#4-create-and-run-a-native-prompt-agent-through-the-toolbox) or [private setup](./toolbox-mcp-private/readme.md#4-create-and-run-a-prompt-agent-through-the-toolbox). The connection script below creates only the downstream APIM-key connection.

| Setting | Value |
| --- | --- |
| Name | `APIM_MCP_CONNECTION_NAME`, e.g. `public-apim-mcp` or `private-route-apim-mcp` |
| Target | Exact APIM MCP Server URL, including path and trailing slash |
| Credential/header name | Usually `api-key` |
| Credential value | Least-privilege APIM subscription key |

Create it on demand with [create_mcp_connection.sh](./create_mcp_connection.sh).
The script uses [Azure CLI `az rest`](https://learn.microsoft.com/en-us/cli/azure/reference-index#az-rest)
to create the connection through Azure Resource Manager (ARM), using API version
`2025-04-01-preview`. It maps your selected path to its configuration:

| Argument | Configuration read |
| --- | --- |
| `direct-mcp` | [direct-mcp/.env](./direct-mcp/.env.example) (copy the linked template first) |
| `direct-mcp-private` | [direct-mcp-private/.env](./direct-mcp-private/.env.example) (copy the linked template first) |
| `toolbox-mcp` | [toolbox-mcp/.env](./toolbox-mcp/.env.example) (copy the linked template first) |
| `toolbox-mcp-private` | [toolbox-mcp-private/.env](./toolbox-mcp-private/.env.example) (copy the linked template first) |

Set these seven values in the selected `.env`:

- `AZURE_TENANT_ID`: the GUID of the tenant containing the Foundry resource.
- `AZURE_AI_PROJECT_ID`: the full project ARM resource ID, not its endpoint.
- `AZURE_AI_PROJECT_ENDPOINT`
- `APIM_MCP_URL`
- `APIM_MCP_CONNECTION_NAME`
- `APIM_SUBSCRIPTION_KEY_HEADER`
- `APIM_SUBSCRIPTION_KEY`

The project ID has this form:

```text
/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>
```

Use the project's Resource ID from Azure portal, not just the parent account ID.
The script derives the subscription from this value and verifies that the
project's ARM-reported endpoint matches `AZURE_AI_PROJECT_ENDPOINT`.

From this sample root in Git Bash:

```bash
# Set manually in each Git Bash terminal before running the commands.
export MSYS_NO_PATHCONV=1
# Choose the folder whose connection you want to create.
# New public direct-MCP setup:
./create_mcp_connection.sh direct-mcp
# New isolated private-APIM setup:
./create_mcp_connection.sh direct-mcp-private
# New Public APIM toolbox setup:
./create_mcp_connection.sh toolbox-mcp
# New Private-APIM toolbox setup:
./create_mcp_connection.sh toolbox-mcp-private
```

From inside `direct-mcp-private`, run:

```bash
export MSYS_NO_PATHCONV=1

../create_mcp_connection.sh direct-mcp-private
```
