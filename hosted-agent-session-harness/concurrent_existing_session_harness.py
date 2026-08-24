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
EXISTING_AGENT_SESSION_ID = os.getenv(
    "AGENT_SESSION_ID",
    "PASTE_EXISTING_AGENT_SESSION_ID_HERE",
)
PROTOCOL_PATHS = {
    "responses": "/protocols/openai/responses",
    "invocations": "/protocols/invocations",
}

if PROTOCOL not in PROTOCOL_PATHS:
    raise ValueError("AGENT_PROTOCOL must be 'responses' or 'invocations'")

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

def print_latency_report(samples, turn_samples, failures):
    print("\nRun summary")
    print(
        f"Protocol: {PROTOCOL}  Existing sessions: 1  Concurrency: {CONCURRENCY}  "
        f"Requests per session: {REQUESTS_PER_SESSION}  "
        f"Requests: {len(samples)}  Failures: {failures}"
    )
    print()
    print(f"{'Scope':<14} {'Count':>7} {'Min ms':>10} {'P50 ms':>10} {'P95 ms':>10} {'Max ms':>10}")
    print("-" * 66)

    groups = [("All", samples)]
    groups.extend(
        (f"Turn {turn}", values)
        for turn, values in enumerate(turn_samples)
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

async def one_request(client, token, worker_number, turn):
    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json"}
    if PROTOCOL == "responses":
        payload = {
            "input": (
                f"Concurrency validation turn {turn}, worker {worker_number}; "
                "return a short acknowledgement."
            )
        }
    else:
        payload = {"message": "hi"}
    params = {"api-version": API_VERSION}
    if PROTOCOL == "responses":
        payload["agent_session_id"] = EXISTING_AGENT_SESSION_ID
    else:
        params["agent_session_id"] = EXISTING_AGENT_SESSION_ID

    started = time.perf_counter()
    response = await client.post(
        f"{ENDPOINT}{PROTOCOL_PATHS[PROTOCOL]}",
        headers=headers,
        params=params,
        json=payload,
    )

    elapsed_ms = (time.perf_counter() - started) * 1000
    if response.is_success and PROTOCOL == "responses":
        returned_session_id = response.json().get("agent_session_id")
        if returned_session_id != EXISTING_AGENT_SESSION_ID:
            raise RuntimeError(
                "Response agent_session_id does not match the configured session"
            )

    print(
        f"Turn {turn:>3}  Worker {worker_number:>3}  "
        f"Status {response.status_code:>3}  Client {elapsed_ms:>10.1f} ms"
    )
    if not response.is_success:
        print(f"  Error: {response.text}")

    return elapsed_ms, int(response.status_code >= 400)

async def main():
    if EXISTING_AGENT_SESSION_ID == "PASTE_EXISTING_AGENT_SESSION_ID_HERE":
        raise RuntimeError(
            "Set AGENT_SESSION_ID or replace PASTE_EXISTING_AGENT_SESSION_ID_HERE"
        )

    credential = DefaultAzureCredential()
    try:
        token = (await credential.get_token("https://ai.azure.com/.default")).token
        async with httpx.AsyncClient(timeout=180) as client:
            turn_samples = []
            failures = 0
            for turn in range(REQUESTS_PER_SESSION):
                wave = await asyncio.gather(*[
                    one_request(client, token, worker_number, turn)
                    for worker_number in range(CONCURRENCY)
                ])
                turn_samples.append([elapsed_ms for elapsed_ms, _ in wave])
                failures += sum(failed for _, failed in wave)

        samples = [ms for values in turn_samples for ms in values]
        print_latency_report(samples, turn_samples, failures)
    finally:
        await credential.close()

if __name__ == "__main__":
    asyncio.run(main())
