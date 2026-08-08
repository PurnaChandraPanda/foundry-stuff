import asyncio
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

from agent_framework import Agent, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

SAMPLE_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(SAMPLE_ROOT / "src" / "agent-framework-agent-foundry-skills-responses" / ".env")


def _safe_extract_zip(zip_file: zipfile.ZipFile, destination: Path) -> None:
    destination_root = destination.resolve()
    for member in zip_file.infolist():
        member_path = (destination_root / member.filename).resolve()
        if destination_root != member_path and destination_root not in member_path.parents:
            raise RuntimeError(f"Refusing to extract unsafe path {member.filename!r}.")
    zip_file.extractall(destination)


async def _download_skills(project: AIProjectClient, names: list[str], destination: Path) -> list[Path]:
    skill_paths = []
    for name in names:
        if Path(name).name != name:
            raise ValueError(f"Invalid skill name {name!r}; expected a directory name.")

        print(f"Downloading Foundry skill {name!r}...")
        stream = await project.beta.skills.download(name)
        archive = b"".join([chunk async for chunk in stream])

        skill_path = destination / name
        skill_path.mkdir()
        with zipfile.ZipFile(io.BytesIO(archive)) as zip_file:
            _safe_extract_zip(zip_file, skill_path)

        if not (skill_path / "SKILL.md").is_file():
            raise RuntimeError(f"Foundry skill {name!r} did not contain SKILL.md at its archive root.")
        skill_paths.append(skill_path)

    return skill_paths


async def main() -> None:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    skill_names = [name.strip() for name in os.environ["SKILL_NAMES"].split(",") if name.strip()]
    if not skill_names:
        raise ValueError("SKILL_NAMES must contain at least one Foundry skill name.")

    message = " ".join(sys.argv[1:]).strip()
    if not message:
        message = input("Message: ").strip()
    if not message:
        raise ValueError("A message is required.")

    with tempfile.TemporaryDirectory(prefix="foundry-skills-") as temp_dir:
        async with (
            DefaultAzureCredential() as credential,
            AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as project,
        ):
            skill_paths = await _download_skills(project, skill_names, Path(temp_dir))
            skills_provider = SkillsProvider.from_paths(
                skill_paths=skill_paths,
                disable_load_skill_approval=True,
            )
            agent = Agent(
                client=FoundryChatClient(
                    project_endpoint=endpoint,
                    model=model,
                    credential=credential,
                ),
                name="foundry-skills-agent",
                instructions="You are a customer-support assistant for Contoso Outdoors.",
                context_providers=[skills_provider],
                default_options={"store": False},
            )
            response = await agent.run(message)
            print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
