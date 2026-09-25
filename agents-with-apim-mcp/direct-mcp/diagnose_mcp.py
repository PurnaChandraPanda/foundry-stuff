"""Check direct private DNS, TLS, MCP initialize, and tools/list; never call a tool."""

import asyncio
import socket
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import PaginatedRequestParams

from config import apim_headers, https_url, load_environment, timeout_seconds


async def diagnose() -> None:
    url = https_url("APIM_MCP_URL")
    headers = apim_headers()
    timeout = timeout_seconds()
    parsed = urlsplit(url)
    addresses = await asyncio.get_running_loop().getaddrinfo(
        parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
    )
    print("DNS addresses:", ", ".join(sorted({str(item[4][0]) for item in addresses})))
    print("Testing Streamable HTTP MCP with TLS verification enabled.")
    async with (
        httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
        ) as http,
        streamable_http_client(url, http_client=http) as (read, write, _),
        ClientSession(read, write, read_timeout_seconds=timedelta(seconds=timeout)) as session,
    ):
        initialized = await session.initialize()
        print(f"Initialized: {initialized.serverInfo.name} {initialized.serverInfo.version}")
        cursor = None
        seen_cursors: set[str] = set()
        count = 0
        while True:
            page = await session.list_tools(params=PaginatedRequestParams(cursor=cursor))
            for tool in page.tools:
                print(f"  {tool.name}")
                count += 1
            cursor = page.nextCursor
            if cursor is None:
                break
            if cursor in seen_cursors:
                raise RuntimeError("MCP server returned a repeated pagination cursor.")
            seen_cursors.add(cursor)
        if count == 0:
            raise RuntimeError("MCP initialized successfully but exposed no tools.")
        print(f"Discovered {count} tools. No tools were executed.")
        print("This proves access from this process only, not from Foundry.")


if __name__ == "__main__":
    load_environment()
    asyncio.run(diagnose())
