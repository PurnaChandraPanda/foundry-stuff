# Illustrative only — align endpoint, auth scope, payload, and session fields with current docs
import asyncio, os, time
import httpx
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

# load environment variables from .env file
load_dotenv()

ENDPOINT = f"{os.environ['PROJECT_ENDPOINT']}/agents/{os.environ['AGENT_NAME']}/endpoint"
API_VERSION = os.getenv("AGENT_API_VERSION")
PROTOCOL = os.environ["AGENT_PROTOCOL"].strip().lower()
CONCURRENCY = int(os.getenv("CONCURRENCY", "10"))
REQUESTS_PER_SESSION = int(os.getenv("REQUESTS_PER_SESSION", "3"))
PROTOCOL_PATHS = {
    "responses": "/protocols/openai/responses",
    "invocations": "/protocols/invocations",
}

if PROTOCOL not in PROTOCOL_PATHS:
    raise ValueError("AGENT_PROTOCOL must be 'responses' or 'invocations'")

async def create_agent_session(client, headers):
    response = await client.post(
        f"{ENDPOINT}/sessions",
        headers=headers,
        params={"api-version": API_VERSION},
        json={},
    )
    response.raise_for_status()
    body = response.json()
    session_id = body.get("agent_session_id") or body.get("session_id")
    if not session_id:
        raise RuntimeError("Session creation response did not include a session ID")
    return session_id

def percentile(ordered_samples, quantile):
    if len(ordered_samples) == 1:
        return ordered_samples[0]

    position = (len(ordered_samples) - 1) * quantile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered_samples) - 1)
    fraction = position - lower_index
    return (
        ordered_samples[lower_index]
        + (ordered_samples[upper_index] - ordered_samples[lower_index]) * fraction
    )

def latency_summary(samples):
    if not samples:
        return None

    ordered = sorted(samples)
    return {
        "count": len(ordered),
        "min_ms": round(ordered[0], 1),
        "p50_ms": round(percentile(ordered, 0.50), 1),
        "p95_ms": round(percentile(ordered, 0.95), 1),
        "max_ms": round(ordered[-1], 1),
    }

def print_latency_report(samples, cold_samples, warm_samples, failures):
    print("\nRun summary")
    print(
        f"Protocol: {PROTOCOL}  Sessions: {CONCURRENCY}  "
        f"Requests: {len(samples)}  Failures: {failures}"
    )
    print()
    print(f"{'Scope':<14} {'Count':>7} {'Min ms':>10} {'P50 ms':>10} {'P95 ms':>10} {'Max ms':>10}")
    print("-" * 66)

    groups = (
        ("All", samples),
        ("Cold turn 0", cold_samples),
        ("Warm turns", warm_samples),
    )
    for label, values in groups:
        summary = latency_summary(values)
        if summary is None:
            print(f"{label:<14} {'0':>7} {'-':>10} {'-':>10} {'-':>10} {'-':>10}")
            continue

        print(
            f"{label:<14} {summary['count']:>7} "
            f"{summary['min_ms']:>10.1f} {summary['p50_ms']:>10.1f} "
            f"{summary['p95_ms']:>10.1f} {summary['max_ms']:>10.1f}"
        )

async def one_session(client, token, session_number):
    durations, failures = [], 0
    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json"}
    session_started = time.perf_counter()
    agent_session_id = (
        await create_agent_session(client, headers)
        if PROTOCOL == "invocations"
        else None
    )
    previous_response_id = None

    for turn in range(REQUESTS_PER_SESSION):
        user_input = f"Concurrency validation turn {turn}; return a short acknowledgement."
        if PROTOCOL == "responses":
            payload = {"input": user_input}
        else:
            payload = {"message": user_input}
        params = {"api-version": API_VERSION}
        if agent_session_id:
            if PROTOCOL == "responses":
                payload["agent_session_id"] = agent_session_id
                payload["previous_response_id"] = previous_response_id
            else:
                params["agent_session_id"] = agent_session_id

        started = session_started if turn == 0 else time.perf_counter()
        response = await client.post(
            f"{ENDPOINT}{PROTOCOL_PATHS[PROTOCOL]}",
            headers=headers,
            params=params,
            json=payload,
        )

        elapsed_ms = (time.perf_counter() - started) * 1000
        durations.append(elapsed_ms)
        failures += int(response.status_code >= 400)

        if response.is_success:
            if PROTOCOL == "responses":
                body = response.json()
                agent_session_id = body.get("agent_session_id")
                previous_response_id = body.get("id")
                if not agent_session_id or not previous_response_id:
                    raise RuntimeError(
                        "Successful response did not include agent_session_id and id"
                    )

        print(
            f"Session {session_number:>3}  Turn {turn:>3}  "
            f"Status {response.status_code:>3}  Client {elapsed_ms:>10.1f} ms  "
            f"Agent session {agent_session_id}"
        )
        if not response.is_success:
            print(f"  Error: {response.text}")
    return session_number, durations, failures

async def main():
    credential = DefaultAzureCredential()
    try:
        token = (await credential.get_token("https://ai.azure.com/.default")).token
        async with httpx.AsyncClient(timeout=180) as client:
            results = await asyncio.gather(*[
                one_session(client, token, session_number)
                for session_number in range(CONCURRENCY)
            ])
        samples = [ms for _, values, _ in results for ms in values]
        cold_samples = [values[0] for _, values, _ in results if values]
        warm_samples = [ms for _, values, _ in results for ms in values[1:]]
        failures = sum(count for _, _, count in results)
        print_latency_report(samples, cold_samples, warm_samples, failures)
    finally:
        await credential.close()

if __name__ == "__main__":
    asyncio.run(main())
