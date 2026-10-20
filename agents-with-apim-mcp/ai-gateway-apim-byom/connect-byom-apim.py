"""Diagnose APIM connectivity and report server-provided gateway/error activity IDs.
Expose context.RequestId as x-apim-request-id for gateway IDs on all responses.

Run with --client httpx (default), --client openai, or --client both.
Both mode sends four requests: two endpoints per client.
Set APIM_MODEL in .env to the model/deployment name used by both endpoints.
"""

import argparse
import asyncio
import json
import socket
import ssl
from contextlib import AsyncExitStack
from time import perf_counter
from typing import Literal
from urllib.parse import urlsplit
import httpx
import os
from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    DefaultAsyncHttpxClient,
    omit,
)
from openai.types.chat.completion_create_params import CompletionCreateParamsNonStreaming
from openai.types.responses.response_create_params import ResponseCreateParamsNonStreaming

# load environment variables from .env file
load_dotenv()

def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value or "<" in value or ">" in value:
        raise ValueError(f"Set {name} to a real value in .env or the environment.")
    return value

def https_url(name: str) -> str:
    value = required(name)
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{name} must be an HTTPS URL without credentials, query, or fragment.")
    return value

def apim_headers() -> dict[str, str]:
    header = required("APIM_SUBSCRIPTION_KEY_HEADER")
    key = required("APIM_SUBSCRIPTION_KEY")
    if "\r" in key or "\n" in key:
        raise ValueError("APIM_SUBSCRIPTION_KEY cannot contain line breaks.")
    return {header: key}

def timeout_seconds() -> int:
    value = int(required("API_TIMEOUT_SECONDS"))
    if value <= 0:
        raise ValueError("API_TIMEOUT_SECONDS must be a positive integer.")
    return value

def report_request_error(error: httpx.RequestError | APIConnectionError) -> None:
    if isinstance(error, (httpx.TimeoutException, APITimeoutError)):
        print(f"Timeout phase: {type(error).__name__}")
    elif isinstance(error, httpx.ProxyError):
        print("Proxy connection failed; check the configured proxy and its DNS/network access.")
    elif isinstance(error, (httpx.ConnectError, APIConnectionError)):
        print("Connection failed before an HTTP response; inspect DNS, TCP, and TLS causes below.")
    else:
        print(f"HTTP transport failed: {type(error).__name__}")
    cause: BaseException | None = error
    seen: set[int] = set()
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        print(f"  {type(cause).__name__}: {cause}")
        if isinstance(cause, socket.gaierror):
            print("  Local name resolution failed; this is not APIM backend DNS resolution.")
        elif isinstance(cause, ssl.SSLError):
            print("  TLS failed; check certificate trust and hostname matching.")
        cause = cause.__cause__ or (
            None if cause.__suppress_context__ else cause.__context__
        )

def report_apim_request_id(response: httpx.Response) -> None:
    request_id = response.headers.get("x-apim-request-id")
    if request_id:
        print("APIM gateway request ID:", request_id)
        return
    if response.is_error:
        try:
            body = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            print("Cannot extract APIM activityId: the error response body is not valid JSON.")
        else:
            if isinstance(body, dict):
                activity_id = body.get("activityId")
                if isinstance(activity_id, str) and activity_id.strip():
                    print("APIM server activity ID (error response):", activity_id)
                    return
    print(
        "APIM server request ID was not returned. Expose context.RequestId as "
        "x-apim-request-id in APIM outbound and on-error policies."
    )

async def send_openai(
    client: AsyncOpenAI,
    endpoint: str,
    url: str,
    payload: CompletionCreateParamsNonStreaming,
    responses_payload: ResponseCreateParamsNonStreaming,
) -> httpx.Response:
    try:
        if endpoint == "chat/completions":
            raw = await client.chat.completions.with_raw_response.create(
                **payload, extra_headers={"Authorization": omit}
            )
        else:
            raw = await client.responses.with_raw_response.create(
                **responses_payload, extra_headers={"Authorization": omit}
            )
    except APIStatusError as error:
        sdk_response = error.response
    else:
        sdk_response = raw.http_response
    # Normalize SDK responses because its HTTP transport can differ from HTTPX.
    return httpx.Response(
        sdk_response.status_code,
        headers=dict(sdk_response.headers),
        content=sdk_response.content,
        request=httpx.Request("POST", url),
    )

async def diagnose(client_mode: Literal["httpx", "openai", "both"] = "httpx") -> None:
    base_url = https_url("APIM_API_URL")
    headers = apim_headers()
    timeout = timeout_seconds()
    payload: CompletionCreateParamsNonStreaming = {
        "model": required("APIM_MODEL"),
        "messages": [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "How are you?"},
        ],
        "max_completion_tokens": 50,
    }
    responses_payload: ResponseCreateParamsNonStreaming = {
        "model": required("APIM_MODEL"),
        "instructions": "You are a helpful assistant",
        "input": "How are you?",
        "max_output_tokens": 50,
    }
    checks = [
        ("chat completion", "chat/completions", payload),
        ("Responses API", "responses", responses_payload),
    ]
    parsed = urlsplit(base_url)
    print(f"Resolving DNS for {parsed.hostname}...")
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(
            parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
        )
    except socket.gaierror as error:
        print(f"Local DNS lookup failed for the APIM hostname: {error}")
        raise
    print("DNS addresses:", ", ".join(sorted({str(item[4][0]) for item in addresses})))
    print("DNS lookup above tests this machine, not APIM's backend DNS.")
    proxy_names = [
        name for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
        if os.environ.get(name) or os.environ.get(name.lower())
    ]
    print("Proxy environment variables set:", ", ".join(proxy_names) or "none")
    failures: list[httpx.HTTPError | APIConnectionError] = []
    results: list[str] = []
    modes = ("httpx", "openai") if client_mode == "both" else (client_mode,)
    for mode in modes:
        async with AsyncExitStack() as stack:
            http = None
            sdk = None
            if mode == "httpx":
                http = await stack.enter_async_context(
                    httpx.AsyncClient(
                        headers=headers,
                        timeout=httpx.Timeout(timeout),
                        follow_redirects=False,
                    )
                )
            else:
                sdk = await stack.enter_async_context(
                    AsyncOpenAI(
                        base_url=f"{base_url.rstrip('/')}/openai/v1/",
                        # SDK requires a key; omit its bearer header on each request.
                        api_key="apim-subscription-auth",
                        default_headers=headers,
                        timeout=float(timeout),
                        max_retries=0,
                        http_client=DefaultAsyncHttpxClient(follow_redirects=False),
                    )
                )
            for label, endpoint, request_payload in checks:
                check_label = f"{mode} / {label}"
                url = f"{base_url.rstrip('/')}/openai/v1/{endpoint}"
                print(f"[{mode}] Attempting HTTPS POST to {url}...")
                started = perf_counter()
                try:
                    if http is not None:
                        response = await http.post(url, json=request_payload)
                    elif sdk is not None:
                        response = await send_openai(sdk, endpoint, url, payload, responses_payload)
                    else:
                        raise RuntimeError(f"No client configured for {mode}.")
                except (httpx.RequestError, APIConnectionError) as error:
                    print(f"Elapsed: {perf_counter() - started:.2f} seconds")
                    report_request_error(error)
                    failures.append(error)
                    results.append(f"{check_label}: FAILED ({type(error).__name__})")
                    continue
                print(f"Elapsed: {perf_counter() - started:.2f} seconds")
                print(f"HTTP status: {response.status_code} {response.reason_phrase}")
                report_apim_request_id(response)
                print("Response body:", response.text)
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as error:
                    print("An HTTPS HTTP response was received; this is not a local DNS/TCP failure.")
                    if response.status_code >= 500:
                        print(
                            "APIM/backend returned a server error. A generic 5xx cannot identify "
                            "backend DNS, routing, TLS, policy, or service failure. Correlate the "
                            "response activityId/request IDs with APIM logs or tracing."
                        )
                    elif response.status_code in (401, 403):
                        print("Check APIM/backend authentication, authorization, and access policies.")
                    elif response.status_code == 404:
                        print("Check the API suffix, operation path, and backend routing.")
                    failures.append(error)
                    results.append(f"{check_label}: FAILED (HTTP {response.status_code})")
                    continue
                print(f"APIM {check_label} check succeeded.")
                results.append(f"{check_label}: PASSED (HTTP {response.status_code})")
    print("Diagnostic summary:")
    for result in results:
        print(f"  {result}")
    if failures:
        raise failures[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--client",
        choices=("httpx", "openai", "both"),
        default="httpx",
        help="Client to test (default: httpx). Both sends two requests per client.",
    )
    args = parser.parse_args()
    asyncio.run(diagnose(args.client))