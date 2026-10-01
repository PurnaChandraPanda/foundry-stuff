"""Create the Fabric IQ UserEntraToken connection using tenant-scoped ARM REST."""

import argparse
import json
import sys
import urllib.error
import urllib.request

from azure.core.credentials import TokenCredential
from azure.core.exceptions import AzureError
from azure.identity import AzureCliCredential

from fabric_iq_config import FABRIC_HOST, resolve_server_url
from fabric_iq_oauth import (
    ARM_API_VERSION,
    connection_resource_id,
    load_environment,
    report_oauth_error,
    required_env,
    verify_user_entra_connection,
)


def create_connection(
    credential: TokenCredential, url: str, properties: dict[str, object]
) -> None:
    token = credential.get_token("https://management.azure.com/.default").token
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=45
        ):
            raise ValueError(
                "The connection already exists; it has not been changed. "
                "Run python diagnose_fabric_iq_connection.py --connection-only to check it, "
                "or choose a different FABRIC_IQ_CONNECTION_NAME."
            )
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        error.close()

    # ARM PUT is an upsert, so refuse existing names before sending it.
    request = urllib.request.Request(
        url,
        data=json.dumps({"properties": properties}).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(request, timeout=45):
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print the ARM request without authentication or network calls.")
    args = parser.parse_args()
    load_environment()
    try:
        tenant_id = required_env("TENANT_ID")
        connection_id = connection_resource_id()
        url = f"https://management.azure.com{connection_id}?api-version={ARM_API_VERSION}"
        properties: dict[str, object] = {
            "category": "RemoteTool",
            "authType": "UserEntraToken",
            "target": resolve_server_url(),
            "audience": FABRIC_HOST,
            "metadata": {"type": "fabric_iq_preview"},
            "isSharedToAll": False,
        }
        print(f"Azure CLI user tenant: {tenant_id}")
        if args.dry_run:
            print(f"GET {url} (must return 404 before creating)")
            print(f"PUT {url}")
            print(json.dumps({"properties": properties}, indent=2))
            print("Dry run only; no login, token requests, or Azure API calls were made.")
            return 0
        with AzureCliCredential(tenant_id=tenant_id) as credential:
            create_connection(credential, url, properties)
            print("Verifying the saved Fabric IQ UserEntraToken connection...")
            verify_user_entra_connection(credential)
        return 0
    except (AzureError, urllib.error.URLError, TimeoutError, ValueError) as error:
        report_oauth_error(error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
