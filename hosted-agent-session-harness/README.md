# Foundry Hosted Agent Concurrency Harness

These scripts measure end-to-end latency for Microsoft Foundry hosted agents using either the Responses or Invocations protocol.

## Setup

Install the Python dependencies:

```bash
pip install azure-identity httpx python-dotenv
```

Authenticate with Azure:

```bash
az login
```

Copy `.env.example` to `.env` and update the values:

```env
PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
AGENT_NAME=<agent-name>
AGENT_PROTOCOL=<responses or invocations>
AGENT_API_VERSION=v1

CONCURRENCY=10
REQUESTS_PER_SESSION=3

AGENT_SESSION_ID=<existing-session-id>
```

Set `AGENT_PROTOCOL` to either `responses` or `invocations`. Because these protocols can use different agents, update `AGENT_NAME` when switching protocols.

## Test new sessions

Run:

```bash
python concurrent_session_harness.py
```

This harness creates `CONCURRENCY` logical sessions in parallel. Each session sends `REQUESTS_PER_SESSION` sequential requests.

```text
Total requests = CONCURRENCY * REQUESTS_PER_SESSION
```

- Responses sessions are created by the first Responses request.
- Invocations sessions are created explicitly through the `/sessions` endpoint.
- Turn 0 includes session creation or startup overhead.
- Later turns reuse the same session and represent warm-session latency.

## Test one existing session

Set `AGENT_SESSION_ID` to an existing session, then run:

```bash
python concurrent_existing_session_harness.py
```

This harness sends `CONCURRENCY` simultaneous requests to the same existing session. It waits for each concurrent wave to finish before starting the next turn.

```text
Total requests = CONCURRENCY * REQUESTS_PER_SESSION
```

This test measures concurrent access to one sandbox session. It does not create a continuous conversation because concurrent requests do not use `previous_response_id`.

## Session and sandbox concepts

Hosted agents separate three related concepts:

| Concept | Meaning |
| --- | --- |
| Session | A logical workload with persisted sandbox state, including `$HOME` and uploaded files |
| VM-isolated sandbox | Compute provisioned for a session while it is active |
| Conversation | Message and response history; distinct from sandbox state |

The platform provisions sandbox compute on demand for a session. After the configured idle timeout, it can deprovision the compute while retaining session state. Calling the same session later resumes compute and restores that state.

```text
New or resumed session request
  -> Foundry authentication and routing
  -> sandbox provision or restore
  -> request reaches the agent container
  -> agent and model processing
  -> response reaches the client
```

This explains why the first request can be slower than later requests even when the session ID already exists.

### What each harness demonstrates

| Harness | Sessions | Concurrency interpretation |
| --- | ---: | --- |
| `concurrent_session_harness.py` | One per concurrent worker | Scale-out across multiple session sandboxes |
| `concurrent_existing_session_harness.py` | One existing session | Concurrent contention within one sandbox |

High concurrency against one existing session does not demonstrate sandbox scale-out. To observe per-session scale-out, use the new-session harness.

For Responses, `agent_session_id` reuses sandbox state while `previous_response_id` provides conversation continuity. For Invocations, the session ID reuses the sandbox, but the agent application is responsible for any conversational state.

## Suggested experiments

1. **Cold versus warm:** Run one session with at least three requests. Compare turn 0 with later turns.
2. **Idle resume:** Warm an existing session, wait longer than its configured idle timeout, and run the existing-session harness again.
3. **Session scale-out:** Increase `CONCURRENCY` in the new-session harness and observe cold-turn latency and failure rate.
4. **Single-session contention:** Increase `CONCURRENCY` in the existing-session harness and compare each turn.
5. **Platform baseline:** Test an agent handler that returns immediately without a model call. This helps separate platform/session overhead from model processing.
6. **Resource comparison:** Repeat the same workload against agent versions with different CPU and memory allocations.

## Protocol payloads

Responses requests use:

```json
{"input": "..."}
```

Invocations requests use:

```json
{"message": "..."}
```

The Invocations payload must match the schema implemented by that agent.

## Reading the results

- `min`: fastest request
- `p50`: median latency
- `p95`: latency below which approximately 95% of samples fall
- `max`: slowest request
- `cold turn 0`: first request for each newly created session
- `warm turns`: subsequent requests on those sessions

The harness uses linear interpolation for P50 and P95. Percentiles based on very few samples are not statistically meaningful; use at least 20 samples for an indication and preferably 100 or more for P95.

Client latency is end to end and includes network connection setup, Foundry authentication and routing, session provisioning or resume, agent processing, and response transfer. Foundry agent traces usually measure only the processing that occurs after the request reaches the agent container.

An existing session can still have a slow first request if its compute was deprovisioned after the idle timeout and must be resumed.

Do not label the difference between client latency and agent trace duration as microVM startup time. The difference can also include authentication, routing, queueing, network connection setup, and response transfer. Use **platform/network/session overhead** unless service-side traces isolate the provisioning phase.

For more information, see [Hosted agents in Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents).
