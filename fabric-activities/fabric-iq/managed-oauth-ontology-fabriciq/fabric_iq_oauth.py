"""UserEntraToken connection checks and delegated-auth consent error reporting."""

import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path

from azure.core.credentials import TokenCredential
from dotenv import load_dotenv
from mcp.shared.exceptions import McpError

from fabric_iq_config import FABRIC_HOST, resolve_server_url

ARM_API_VERSION = "2025-10-01-preview"


def load_environment() -> None:
    load_dotenv(os.environ.get("ENV_FILE", Path(__file__).with_name(".env")))


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required. See .env.example.")
    return value


def validate_user_entra_connection(
    properties: Mapping[str, object], target: str
) -> None:
    if properties.get("category") != "RemoteTool":
        raise ValueError("The connection must have category RemoteTool.")
    if properties.get("authType") != "UserEntraToken":
        raise ValueError(
            f"Expected UserEntraToken, found {properties.get('authType')!r}. "
            "Use the Fabric IQ managed-user connection matching daontology1, "
            "not a PMI or generic OAuth2 connector."
        )
    if properties.get("target") != target:
        raise ValueError(
            f"Connection target {properties.get('target')!r} does not match {target!r}."
        )
    if properties.get("audience") != FABRIC_HOST:
        raise ValueError(
            f"Expected audience={FABRIC_HOST!r}, found {properties.get('audience')!r}."
        )
    metadata = properties.get("metadata")
    if not isinstance(metadata, Mapping) or metadata.get("type") != "fabric_iq_preview":
        raise ValueError("The connection must have metadata.type=fabric_iq_preview.")


def connection_resource_id() -> str:
    project_id = required_env("AZURE_AI_PROJECT_ID").rstrip("/")
    name = required_env("FABRIC_IQ_CONNECTION_NAME")
    return f"{project_id}/connections/{name}"


def verify_user_entra_connection(credential: TokenCredential) -> str:
    """Read ARM metadata only, never the connection's secrets."""
    connection_id = connection_resource_id()
    token = credential.get_token("https://management.azure.com/.default").token
    request = urllib.request.Request(
        f"https://management.azure.com{connection_id}?api-version={ARM_API_VERSION}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            document = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ValueError(
                f"Connection '{connection_id}' does not exist. Run create_fabric_iq_connection.sh, "
                "or set FABRIC_IQ_CONNECTION_NAME to an existing Fabric IQ "
                "UserEntraToken connection such as daontology1, then retry."
            ) from error
        raise
    if not isinstance(document, dict) or not isinstance(document.get("properties"), dict):
        raise ValueError("ARM returned no valid connection properties.")
    properties = document["properties"]
    validate_user_entra_connection(properties, resolve_server_url())
    print(f"Connection: {connection_id}")
    print(f"category={properties['category']} authType={properties['authType']}")
    print(f"target={properties['target']}")
    print(f"audience={properties['audience']} metadata.type=fabric_iq_preview")
    print("UserEntraToken configuration verified; runtime access remains untested.")
    return connection_id


def report_oauth_error(error: BaseException) -> None:
    """Preserve consent links carried in MCP error data or SDK exception causes."""
    print(f"{type(error).__name__}: {error}", file=sys.stderr)
    if isinstance(error, McpError) and error.error.data is not None:
        print(json.dumps(error.error.data, ensure_ascii=True), file=sys.stderr)
    if isinstance(error, urllib.error.HTTPError):
        detail = error.read().decode("utf-8", errors="replace")
        if detail:
            print(detail, file=sys.stderr)
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            report_oauth_error(child)
    elif error.__cause__ is not None:
        report_oauth_error(error.__cause__)


CONSENT_GUIDANCE = (
    "If the error is CONSENT_REQUIRED (-32006), review the returned consent URL, "
    "open it yourself, and sign in as the same user used by az login. "
    "After authorization, rerun the command. Do not share consent URLs or tokens. "
    "For 401/403, check the signed-in user, tenant, Foundry roles, and Fabric/source access."
)
