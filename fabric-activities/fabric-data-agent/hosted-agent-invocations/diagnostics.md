# Diagnostics: `main_diag.py` + `_diagnostics.py`

A short guide to the diagnostic build of this sample - what it is, how to turn
it on, and what each line of its output means.

## What these files are

| File | Role |
|---|---|
| `src/fabric-dataagent-invocations/main.py` | The agent you ship. Zero diagnostics code. |
| `src/fabric-dataagent-invocations/main_diag.py` | The same agent, plus every diagnostic hook wired in. |
| `src/fabric-dataagent-invocations/_diagnostics.py` | The reusable diagnostics module. Does nothing until switched on. |

The split is deliberate. `main.py` stays clean and you never edit it to debug a
deployment - you change one line of config to choose which file runs.

## How to enable

### Locally

```bash
python src/fabric-dataagent-invocations/main_diag.py
```

Probes are **on by default** in `main_diag.py`: it reads
`AGENT_DIAG_PROBE` with a default of `"1"`. Set `AGENT_DIAG_PROBE=0` to silence
them and behave exactly like `main.py`.

### Deployed

Point the manifest at it and redeploy:

```yaml
# azure.yaml
services:
    agent:
        config:
            entryPoint: main_diag.py     # normally main.py
```

```bash
azd up
azd ai agent monitor --follow
```

Then look for `AGENTDIAG` lines in the stream.

`main_diag.py` is **deliberately not excluded** by `.agentignore` - it has to be
in the deployment ZIP for this swap to work.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_DIAG_PROBE` | `0` in the module, **`1` in `main_diag.py`** | Master switch |
| `AGENT_DIAG_INTERVAL` | `60` | Seconds between probe cycles |
| `AGENT_DIAG_EGRESS` | derived | Comma-separated FQDN list for the egress probe |
| `AGENT_DIAG_STDOUT` | `1` | Set `0` for stderr only (needed for stdio MCP servers) |

## How it works

A **daemon thread** runs every registered probe on a repeating timer. It repeats
rather than running once at startup because `azd ai agent monitor` attaches to an
already-running container and would miss a one-shot line.

Each cycle emits something like:

```
AGENTDIAG | --- probe cycle 3 ---
AGENTDIAG | identity: oid=5203b70c-... appid=5203b70c-... idtyp=app tid=e951fcc7-...
AGENTDIAG | project listSecrets -> 403 body={"error":{"code":"AuthorizationFailed",...
AGENTDIAG | account listSecrets -> 403 body=...
AGENTDIAG | egress login.microsoftonline.com:443 -> OK via curl http=302 src=10.0.0.4:41022 dst=20.190.160.14:443 dns=0.03s tcp=0.06s tls=1.01s total=1.16s
AGENTDIAG | connection_id: /subscriptions/.../connections/fabric_dataagent_basic1
AGENTDIAG | fabric_tool: {"fabric_dataagent_preview": {...}, "type": "fabric_dataagent_preview"}
```

What each probe tells you:

- **identity** - decodes the container's own token **locally**, with no service
  call, so it still works when every outbound authorization is failing. `oid` is
  what `az role assignment create --assignee-object-id` expects; `idtyp=app`
  confirms a service principal rather than a user.
- **connection** - `listSecrets` at both project and account scope. The two are
  granted by different roles, so a caller can hold one without the other.
- **egress** - DNS + TCP + TLS on 443 to AAD, ARM, this project's Foundry
  endpoint and Fabric. Split per phase, so a stalled TLS with a healthy TCP
  points at an inspecting proxy rather than a blocked port. Uses `curl` when it
  is on PATH and falls back to a stdlib socket check otherwise, because slim
  Python images usually ship without curl.
- **context** - whatever was passed to `set_context()`, echoed every cycle so a
  monitor session attached long after startup still sees the exact tool payload
  that was built at boot.

Every probe runs inside its own `try/except`: one failing probe still lets the
rest report, and a diagnostic must never take the agent down.

### Reading the egress line

`dst=` is the address actually connected to - worth comparing against a Private
Endpoint or a firewall allowlist. `src=` is the container's **own NIC address**,
not the public address the destination sees, because a hosted agent egresses
through SNAT.

## Where the hooks go, and why

| Location in `main_diag.py` | Hook | Why there |
|---|---|---|
| `build_agent()` | `configure()`, `set_context()`, `start()` | With `dependencyResolution: remote_build` the runtime **imports the module and supplies its own launcher**, so `main()` never executes in the container. Anything started there is dead code. |
| module scope | `install_asgi(app)` | Must be registered while the app is still being built, i.e. at import time. |
| `handle_invoke()` | `log_request(request)` | Per-request caller identity, read from `request.state`. |

`install_asgi` catches requests that never reach the agent - 404s, health probes,
protocol mismatches - which agent-level middleware by definition cannot see. It
is how the route was confirmed to be `/invocations` rather than `/invoke`.

## Output goes to stdout *and* stderr

`print()` writes to stdout; `logging` writes to **stderr**. Which one a hosted
log collector scrapes is not documented, so `emit()` writes to both and lets
whichever is captured win. The logger copy is identifiable by its
`INFO:agent-diagnostics:` prefix.

`flush=True` on the print is load-bearing, not cosmetic: when stdout is a pipe
rather than a TTY - i.e. any container - Python block-buffers it at about 8 KB,
so an unflushed line can sit in the buffer and never be written.

## Extending it

Add a probe without touching `_diagnostics.py`:

```python
@diagnostics.probe("my-check")
def _check() -> None:
    resp = diagnostics.call_arm(f"{PROJECT_ID}/connections", method="GET")
    diagnostics.emit(f"connections -> {resp.status_code}")
```

Override the egress host list:

```python
diagnostics.check_egress("management.azure.com", "api.fabric.microsoft.com")
```

Data-plane checks are not generic - every service has its own scope, paths and
error semantics - but the scaffolding is reusable, so each one is a few lines:

```python
@diagnostics.probe("fabric-dataplane")
def _check() -> None:
    token = diagnostics.credential.get_token(
        "https://api.fabric.microsoft.com/.default"
    ).token
    resp = httpx.get(URL, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    diagnostics.emit(f"fabric GET -> {resp.status_code} {resp.text[:200]}")
```

## Notes

- `_diagnostics.py` is duplicated in this sample and in `hosted-agent/`. The two
  copies must stay byte-identical; drift between them would be silent.
- The module itself defaults to **off** and every hook is a no-op while disabled,
  which is why the hooks are safe to leave in place permanently.
- Only `call_arm`/`probe_connection_access` need httpx, `agent_middlewares()`
  needs agent_framework, and `log_request` needs a Starlette-style request. All
  are imported lazily, so the rest of the module works without them.
