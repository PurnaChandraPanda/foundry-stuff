import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AgentVersionDetails,
    CodeConfiguration,
    HostedAgentDefinition,
    ProtocolVersionRecord,
)
from azure.identity import DefaultAzureCredential
from dotenv import dotenv_values, load_dotenv


def log_status(message: str) -> None:
    print(f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] {message}", flush=True)


def wait_until_active(
    project: AIProjectClient,
    agent_name: str,
    agent_version: str,
    timeout_seconds: int,
    poll_interval_seconds: int,
) -> AgentVersionDetails:
    started = time.monotonic()
    deadline = started + timeout_seconds
    last_status = "not checked"
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"Agent {agent_name}, version {agent_version} did not become active "
                f"within {timeout_seconds}s (last status: {last_status}). "
                "Provisioning may still be running in Foundry."
            )
        version = project.agents.get_version(
            agent_name=agent_name,
            agent_version=agent_version,
            connection_timeout=min(30, remaining),
            read_timeout=min(30, remaining),
            retry_total=0,
        )
        last_status = version.status
        log_status(
            f"Provisioning {agent_name}, version {agent_version}: {last_status} "
            f"({time.monotonic() - started:.0f}s elapsed)"
        )
        if last_status == "active":
            return version
        if last_status in ("failed", "deleting", "deleted"):
            raise RuntimeError(
                f"Agent {agent_name}, version {agent_version}: {last_status}. "
                "Check the agent's deployment logs in Foundry."
            )
        if last_status != "creating":
            raise RuntimeError(
                f"Unexpected provisioning status for {agent_name}, "
                f"version {agent_version}: {last_status!r}."
            )
        time.sleep(min(poll_interval_seconds, max(0, deadline - time.monotonic())))


def verify_runtime_environment(
    version: AgentVersionDetails, expected: dict[str, str]
) -> None:
    if not isinstance(version.definition, HostedAgentDefinition):
        raise RuntimeError("Foundry returned a non-hosted definition; runtime variables cannot be verified.")
    actual = version.definition.environment_variables
    if actual is None:
        raise RuntimeError(
            f"Foundry returned no runtime environment variables for {version.name}, "
            f"version {version.version}. Deployment configuration verification failed."
        )
    missing = sorted(key for key in expected if key not in actual)
    mismatched = sorted(key for key in expected if key in actual and actual[key] != expected[key])
    if missing or mismatched:
        raise RuntimeError(
            f"Runtime environment verification failed for {version.name}, version {version.version}. "
            f"Missing keys: {', '.join(missing) or 'none'}. "
            f"Mismatched keys: {', '.join(mismatched) or 'none'}. "
            "Values are not displayed; do not treat this deployment as verified."
        )
    log_status(
        f"Verified all {len(expected)} source .env key/value pairs in Foundry "
        f"for {version.name}, version {version.version} (values not displayed)."
    )


log_status("Stage 1/7: Loading deployment and source configuration.")
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)

# Source directory containing the agent code
SOURCE_DIR = BASE_DIR / os.getenv(
    "AGENT_SOURCE_DIR", "src/agent-framework-agent-basic-responses"
)
load_dotenv(SOURCE_DIR / ".env", override=False)

log_status("Stage 2/7: Validating configuration and source files.")
RUNTIME_ENV_PATH = SOURCE_DIR / ".env"
if not RUNTIME_ENV_PATH.is_file():
    raise FileNotFoundError(f"Required runtime environment file not found: {RUNTIME_ENV_PATH}")

RUNTIME_ENVIRONMENT: dict[str, str] = {}
for key, value in dotenv_values(RUNTIME_ENV_PATH, interpolate=False).items():
    if value is None:
        raise ValueError(
            f"Runtime variable {key!r} has no value in the source .env; "
            "use KEY=value or KEY= for an empty value."
        )
    RUNTIME_ENVIRONMENT[key] = value
if not RUNTIME_ENVIRONMENT:
    raise ValueError(f"No runtime environment variables found in {RUNTIME_ENV_PATH}.")
log_status(
    f"Loaded {len(RUNTIME_ENVIRONMENT)} hosted runtime variables from {RUNTIME_ENV_PATH.resolve()} "
    "(values not displayed)."
)

DEPLOY_TIMEOUT_SECONDS = int(os.getenv("AGENT_DEPLOY_TIMEOUT_SECONDS", "600"))
POLL_INTERVAL_SECONDS = int(os.getenv("AGENT_POLL_INTERVAL_SECONDS", "5"))
if DEPLOY_TIMEOUT_SECONDS <= 0 or POLL_INTERVAL_SECONDS <= 0:
    raise ValueError(
        "AGENT_DEPLOY_TIMEOUT_SECONDS and AGENT_POLL_INTERVAL_SECONDS must be positive integers."
    )

AGENT_PROTOCOL = os.environ["AGENT_PROTOCOL"]
AGENT_PROTOCOL_VERSION = os.environ["AGENT_PROTOCOL_VERSION"]
if not AGENT_PROTOCOL.strip() or not AGENT_PROTOCOL_VERSION.strip():
    raise ValueError("AGENT_PROTOCOL and AGENT_PROTOCOL_VERSION must not be blank.")

try:
    AGENT_ENTRY_POINT = json.loads(os.environ["AGENT_ENTRY_POINT"])
except json.JSONDecodeError as error:
    raise ValueError(
        'AGENT_ENTRY_POINT must be a JSON array, for example ["python", "main.py"].'
    ) from error
if (
    not isinstance(AGENT_ENTRY_POINT, list)
    or not AGENT_ENTRY_POINT
    or not all(isinstance(arg, str) for arg in AGENT_ENTRY_POINT)
    or not AGENT_ENTRY_POINT[0].strip()
):
    raise ValueError(
        "AGENT_ENTRY_POINT must be a non-empty JSON array of strings "
        "with a non-blank executable."
    )

PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
if not PROJECT_ENDPOINT or not PROJECT_ENDPOINT.strip():
    raise ValueError(
        "Set FOUNDRY_PROJECT_ENDPOINT in the environment or the agent source .env file."
    )

for filename in ("main.py", "requirements.txt"):
    if not (SOURCE_DIR / filename).is_file():
        raise FileNotFoundError(f"Required source file not found: {SOURCE_DIR / filename}")

# Put the source folder's contents, not its parent folders, at the ZIP root.
log_status(f"Stage 3/7: Packaging source from {SOURCE_DIR}.")
with TemporaryDirectory() as staging_dir:
    staged_source = Path(staging_dir) / "source"
    shutil.copytree(
        SOURCE_DIR,
        staged_source,
        ignore=shutil.ignore_patterns(
            ".env", ".env.*", ".venv", "venv", "__pycache__", "*.pyc"
        ),
    )
    ZIP_PATH = Path(
        shutil.make_archive(
            base_name=str(BASE_DIR / "agent-code"),
            format="zip",
            root_dir=staged_source,
        )
    )

log_status(f"Package ready: {ZIP_PATH.name} ({ZIP_PATH.stat().st_size:,} bytes).")
log_status("Stage 4/7: Initializing Azure client (authentication occurs on the API request).")
project = AIProjectClient(
    endpoint=PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
)

log_status("Stage 5/7: Uploading source and requesting a hosted agent version.")
with project, ZIP_PATH.open("rb") as code:
    agent = project.agents.create_version_from_code(
        agent_name=os.getenv("AGENT_NAME"),
        definition=HostedAgentDefinition(
            environment_variables=RUNTIME_ENVIRONMENT,
            protocol_versions=[
                ProtocolVersionRecord(
                    protocol=AGENT_PROTOCOL,
                    version=AGENT_PROTOCOL_VERSION,
                )
            ],
            cpu=os.getenv("AGENT_CPU"),
            memory=os.getenv("AGENT_MEMORY"),
            code_configuration=CodeConfiguration(
                runtime=os.getenv("AGENT_RUNTIME"),
                entry_point=AGENT_ENTRY_POINT,
                dependency_resolution="remote_build",
            ),
        ),
        code=code,
    )

    log_status(f"Agent version created: {agent.name}, version: {agent.version}.")
    log_status(
        f"Stage 6/7: Waiting for active (timeout {DEPLOY_TIMEOUT_SECONDS}s, "
        f"poll interval {POLL_INTERVAL_SECONDS}s)."
    )
    active_version = wait_until_active(
        project,
        agent.name,
        agent.version,
        DEPLOY_TIMEOUT_SECONDS,
        POLL_INTERVAL_SECONDS,
    )
    log_status("Stage 7/7: Verifying runtime environment variables read back from Foundry.")
    verify_runtime_environment(active_version, RUNTIME_ENVIRONMENT)
    log_status(
        f"Deployment active: {agent.name}, version: {agent.version}. "
        "Foundry reports infrastructure ready; no agent invocation was tested."
    )