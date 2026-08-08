# Copyright (c) Microsoft. All rights reserved.

"""Foundry Skills hosted agent sample.

The ``SKILL_SOURCE`` setting controls whether this agent loads the skills named
in ``SKILL_NAMES`` from the deployment package or downloads them from the
project's ``beta.skills`` API. The hosted deployment uses bundled skills so
network calls do not block its readiness endpoint.

Upload the skills to Foundry once with ``provision_skills.py`` before running
this sample.
"""

import asyncio
import io
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Final

from agent_framework import Agent, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

# Hosted agents mount the application directory read-only. Keep downloaded
# skills in the platform's writable, ephemeral temp directory instead.
DOWNLOADED_SKILLS_DIR: Final = Path(tempfile.gettempdir()) / "foundry-skills" / "downloaded_skills"
BUNDLED_SKILLS_DIR: Final = Path(__file__).parent / "skills"

logger = logging.getLogger(__name__)


def _safe_extract_zip(zf: zipfile.ZipFile, dest_dir: Path) -> None:
    """Extract ``zf`` into ``dest_dir``, rejecting entries that escape it (zip-slip guard)."""
    dest_root = dest_dir.resolve()
    for member in zf.infolist():
        member_path = (dest_root / member.filename).resolve()
        if dest_root != member_path and dest_root not in member_path.parents:
            raise RuntimeError(f"Refusing to extract unsafe path '{member.filename}' outside of '{dest_root}'.")
    zf.extractall(dest_dir)


async def _bootstrap_skills(endpoint: str, skill_names: list[str], target_dir: Path) -> None:
    """Download each named skill via ``project.beta.skills`` and unpack it as ``<target_dir>/<name>/SKILL.md``."""
    if target_dir.exists():  # noqa: ASYNC240
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)  # noqa: ASYNC240

    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as project,
    ):
        for name in skill_names:
            logger.info(f"Downloading skill '{name}' from Foundry...")
            stream = await project.beta.skills.download(name)
            zip_bytes = b"".join([chunk async for chunk in stream])
            skill_dir = target_dir / name
            skill_dir.mkdir()
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                _safe_extract_zip(zf, skill_dir)
            if not (skill_dir / "SKILL.md").is_file():
                raise RuntimeError(f"Downloaded archive for '{name}' did not contain a SKILL.md at the root.")


def _resolved_env(name: str) -> str:
    """Return an env var value, treating un-substituted ``${VAR}`` / ``{{VAR}}`` placeholders as empty.

    Hosted-agent runtimes that perform template substitution on ``agent.yaml`` /
    ``agent.manifest.yaml`` may leave the literal ``${VAR}`` or ``{{VAR}}`` text
    when ``VAR`` is undefined at deploy time (e.g. CI smoke runs that don't
    provision optional resources). The sample should treat that case the same
    as "unset" so the container still passes ``/readiness`` and the agent
    responds — just without the optional capability.
    """
    value = os.environ.get(name, "").strip()
    if (value.startswith("${") and value.endswith("}")) or (
        value.startswith("{{") and value.endswith("}}")
    ):
        return ""
    return value


def _bundled_skill_paths(skill_names: list[str]) -> list[Path]:
    """Resolve requested bundled skills and reject missing or unsafe names."""
    skill_paths = []
    for name in skill_names:
        if Path(name).name != name:
            raise ValueError(f"Invalid skill name {name!r}; expected a directory name.")
        skill_path = BUNDLED_SKILLS_DIR / name
        if not (skill_path / "SKILL.md").is_file():
            raise FileNotFoundError(f"Bundled skill {name!r} was not found under '{BUNDLED_SKILLS_DIR}'.")
        skill_paths.append(skill_path)
    return skill_paths


# Hard ceiling on the skill-bootstrap network round-trips so a slow or hung
# Foundry beta.skills API call can't keep ``/readiness`` from returning 200
# past the hosted-agent runtime's session-readiness timeout.
SKILL_BOOTSTRAP_TIMEOUT_SECONDS: Final = 60.0


async def main() -> None:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    skill_names = [name.strip() for name in _resolved_env("SKILL_NAMES").split(",") if name.strip()]
    skill_source = _resolved_env("SKILL_SOURCE") or "foundry"

    context_providers = []
    if not skill_names:
        logger.warning("SKILL_NAMES is empty; no skills will be loaded into the agent.")
    elif skill_source == "bundled":
        skill_paths = _bundled_skill_paths(skill_names)
        logger.info("Loading bundled skills: %s", ", ".join(skill_names))
        context_providers.append(
            SkillsProvider.from_paths(
                skill_paths=skill_paths, 
                # disable approval for load_skill
                disable_load_skill_approval=True,))
    elif skill_source == "foundry":
        # Pull the latest copy of each skill from Foundry into a runtime-only folder.
        await asyncio.wait_for(
            _bootstrap_skills(project_endpoint, skill_names, DOWNLOADED_SKILLS_DIR),
            timeout=SKILL_BOOTSTRAP_TIMEOUT_SECONDS,
        )

        # Build a SkillsProvider over the unpacked folder. The provider advertises
        # each skill's name + description to the model and exposes the ``load_skill``
        # tool the model uses to retrieve the full SKILL.md body on demand. No
        # script_runner is configured because the skills in this sample are
        # instruction-only.
        skills_provider = SkillsProvider.from_paths(
                                skill_paths=str(DOWNLOADED_SKILLS_DIR),
                                disable_load_skill_approval=True,)
        context_providers.append(skills_provider)
    else:
        raise ValueError("SKILL_SOURCE must be either 'bundled' or 'foundry'.")

    async with DefaultAzureCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=project_endpoint,
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=credential,
        )

        agent = Agent(
            client=client,
            instructions="You are a customer-support assistant for Contoso Outdoors.",
            context_providers=context_providers,
            # History will be managed by the hosting infrastructure, thus there
            # is no need to store history by the service. Learn more at:
            # https://developers.openai.com/api/reference/resources/responses/methods/create
            default_options={"store": False},
        )
        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
