# Deploy a hosted agent using Python

The deployment script packages agent source code and calls the Foundry
`create_version_from_code` API using `DefaultAzureCredential`.

## Local configuration

Copy [.env.example](.env.example) to `.env` beside
[deploy_hosted_agent.py](deploy_hosted_agent.py) for deployment-only overrides.
Keep shared settings such as `FOUNDRY_PROJECT_ENDPOINT` in the agent source's
`.env`; there is no need to repeat them beside the deployment script. See the
[source configuration template](src/agent-framework-agent-basic-responses/.env.example).
Local `.env` files and the generated ZIP are excluded from Git.

Configuration is loaded in this order, without overriding existing values:

1. Shell or CI environment variables.
2. `.env` beside the deployment script.
3. `.env` inside the selected agent source directory.

Paths are resolved relative to the deployment script, not the current working
directory. `AGENT_SOURCE_DIR` can also be an absolute path. Set it in the shell
or script-level `.env`; it is resolved before loading the agent's own `.env`.

| Variable | Default |
| --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Required |
| `AGENT_NAME` | `diagnostic-agent-python-invocations` |
| `AGENT_SOURCE_DIR` | `src/agent-framework-agent-basic-responses` |
| `AGENT_CPU` | `1` |
| `AGENT_MEMORY` | `2Gi` |
| `AGENT_RUNTIME` | `python_3_13` |
| `AGENT_PROTOCOL` | Required; template uses `invocations` |
| `AGENT_PROTOCOL_VERSION` | Required; template uses `2.0.0` |
| `AGENT_ENTRY_POINT` | Required; template uses `["python", "main.py"]` |
| `AGENT_DEPLOY_TIMEOUT_SECONDS` | `600` (10 minutes) |
| `AGENT_POLL_INTERVAL_SECONDS` | `5` |

Set `AGENT_ENTRY_POINT` to a JSON array of command arguments, not a shell command:

```dotenv
AGENT_PROTOCOL=responses
AGENT_PROTOCOL_VERSION=2.0.0
AGENT_ENTRY_POINT='["python", "main.py"]'
```

The entry point must contain strings and a non-blank executable. It is passed
directly to Foundry; shell expressions are not expanded by the deployment script.

An existing empty value is not replaced by a lower-priority file. An absent or
blank project endpoint produces an error before packaging or contacting Azure.

## Deployment prerequisites

- An accessible Foundry project and an authenticated Azure identity with
  permission to deploy agents.
- A Python environment with `azure-ai-projects` supporting code-based hosted
  agent deployment, `azure-identity`, and `python-dotenv`.
- `main.py` and `requirements.txt` in the selected source directory. The script
  checks for both before uploading; supply the agent's dependency manifest if
  it is missing.

Run `python deploy_hosted_agent.py` from this directory to create a version
and wait for its provisioning status to become `active`.

## Deployment progress and readiness

- Timestamped messages show configuration loading, validation, packaging, client initialization, upload/version creation, readiness polling, and runtime environment verification. 
- Each poll prints the status of the exact version returned by the upload and the elapsed wait time.
- The SDK exposes provisioning status, not detailed remote-build stages or upload percentage; inspect deployment logs in Foundry for those details.

- By default the script polls every 5 seconds for up to 600 seconds after version creation. Configure the two timing variables above with positive integer values. This timeout applies to readiness polling, not packaging or the initial upload. In-flight network requests may add time; polling requests have bounded network timeouts and automatic retries disabled.

- The script succeeds only when Foundry returns `active` and all source environment key/value pairs match the definition read back from that exact version. It exits with an error on `failed`, `deleting`, `deleted`, unexpected statuses, API errors, or timeout.
A timeout does not cancel provisioning or delete the version; check its status in Foundry before rerunning and creating another version `active` means infrastructure readiness, not a successful model invocation.

## Deployment settings versus hosted runtime settings

- The script reads every variable from the `.env` beside the agent's `main.py` (`AGENT_SOURCE_DIR/.env`) and passes it through
`HostedAgentDefinition.environment_variables`. Foundry supplies these variables to the hosted container, so `main.py` can read them with `os.getenv` or `os.environ` without an uploaded `.env` file.

- The source `.env` is required and must contain at least one variable. The script prints its resolved path and variable count so you can confirm the selected `AGENT_SOURCE_DIR`. Runtime values come directly from this file, without shell or deployment-level overrides. 
- Only source-declared keys are sent; the script does not forward the entire local process environment. Runtime values are parsed without `${VARIABLE}` interpolation, so use concrete values rather than references. 
- A bare `KEY` without `=` is rejected; `KEY=` supplies an empty string.

- Keep deployment-only settings in the script-level `.env`. The progress log shows only the number of runtime variables, never their values. All source `.env` values are sent to Foundry as agent configuration, including any secrets placed there; keep only settings intended for the hosted agent in that file.

- After provisioning, the script verifies the persisted version definition returned by `get_version`, not just the local request. Missing or changed values cause an error listing key names only. If the service redacts values, exact verification will also fail rather than claim a match.

- In the Foundry portal, select the exact agent name and version printed by the script, then refresh the environment-variable panel. Versions created before runtime-variable forwarding was added are not changed by editing this script; run it again to create a version containing the configuration. This read-back check verifies stored configuration, not an environment inspection inside the running container.

- The upload excludes `.env`, `.env.*`, virtual environment directories named `.venv` or `venv`, and Python bytecode caches, including in nested directories. Do not put secrets in other source files: those files will still be uploaded.
