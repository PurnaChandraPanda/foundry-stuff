"""Opt-in APIM MCP diagnostics; never change the tool result sent to the agent."""

import json
import logging
import os
import socket
from urllib.parse import urlsplit
from urllib.request import getproxies

from agent_framework import Content, MCPStreamableHTTPTool
from mcp.types import CallToolResult

logger = logging.getLogger("apim.mcp.diagnostics")
MAX_RESULT_LOG_CHARS = 4096


def environment_flag(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if value not in {"", "true", "false"}:
        raise ValueError(f"{name} must be true or false.")
    return value == "true"


def bypass_apim_proxy(mcp_url: str) -> None:
    host = urlsplit(mcp_url).hostname
    if not host:
        raise ValueError("APIM_MCP_URL must contain a hostname.")
    existing = getproxies().get("no", "")
    entries = [entry.strip() for entry in existing.split(",") if entry.strip()]
    if host.lower() not in {entry.lower() for entry in entries}:
        entries.append(host)
    # Set both cases so a pre-existing lowercase value cannot defeat the override.
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = ",".join(entries)


def log_network_diagnostics(mcp_url: str, *, bypass_proxy: bool) -> None:
    parsed = urlsplit(mcp_url)
    addresses = sorted({
        address[4][0]
        for address in socket.getaddrinfo(
            parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
        )
    })
    proxies = getproxies()
    logger.info(
        "APIM MCP network: host=%s addresses=%s bypass_env_proxy=%s "
        "proxy_configured=%s no_proxy_configured=%s",
        parsed.hostname,
        addresses,
        bypass_proxy,
        {scheme: bool(proxies.get(scheme)) for scheme in ("http", "https", "all")},
        bool(proxies.get("no")),
    )


def enable_result_diagnostics(
    tool: MCPStreamableHTTPTool, headers: dict[str, str]
) -> None:
    logger.setLevel(logging.INFO)
    # SDK 1.15.0 has no public default-parser helper. Reuse its parser to retain
    # binary content and metadata; tests guard this pinned-SDK integration.
    default_parser = tool.parse_tool_results or tool._parse_tool_result_from_mcp
    sensitive_names = {
        "authorization", "proxyauthorization", "cookie", "setcookie",
        "apikey", "subscriptionkey", "ocpapimsubscriptionkey",
        "password", "secret", "token", "accesstoken", "refreshtoken",
        *(name.lower().replace("-", "").replace("_", "") for name in headers),
    }
    secrets = tuple(value for value in headers.values() if value)

    def redact(value: object) -> object:
        if isinstance(value, dict):
            return {
                key: (
                    "[REDACTED]"
                    if str(key).lower().replace("-", "").replace("_", "") in sensitive_names
                    else redact(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [redact(item) for item in value]
        if isinstance(value, str):
            for secret in secrets:
                value = value.replace(secret, "[REDACTED]")
        return value

    def parse(result: CallToolResult) -> str | list[Content]:
        payload = {
            "content": [
                {"type": item.type, "text": item.text}
                if item.type == "text" else {"type": item.type}
                for item in result.content
            ],
            "structuredContent": result.structuredContent,
        }
        text = json.dumps(redact(payload), ensure_ascii=True)
        logger.info(
            "APIM MCP result: server=%s isError=%s truncated=%s payload=%s",
            tool.name,
            result.isError,
            len(text) > MAX_RESULT_LOG_CHARS,
            text[:MAX_RESULT_LOG_CHARS],
        )
        return default_parser(result)

    tool.parse_tool_results = parse
