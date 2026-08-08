import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from agent_framework import Agent, FileSkill, FileSkillScript, Skill, SkillScript, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

SAMPLE_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = SAMPLE_ROOT / "src" / "agent-framework-agent-with-skills-responses"
SKILLS_ROOT = SOURCE_ROOT / "skills"
load_dotenv(SOURCE_ROOT / ".env")


def run_local_skill_script(
    skill: Skill, script: SkillScript, args: dict[str, Any] | list[str] | None = None
) -> str:
    if not isinstance(skill, FileSkill) or not isinstance(script, FileSkillScript):
        return "Error: only file-based skill scripts can be run by this runner."

    skill_path = Path(skill.path).resolve()
    script_path = Path(script.full_path).resolve()
    if skill_path != script_path and skill_path not in script_path.parents:
        return f"Error: script '{script.name}' resolves outside the skill directory."
    if args is not None and (
        not isinstance(args, list) or not all(isinstance(item, str) for item in args)
    ):
        return f"Error: script '{script.name}' expects a list of string CLI arguments."

    try:
        completed = subprocess.run(
            [sys.executable, str(script_path), *(args or [])],
            cwd=skill_path,
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return f"Error: script '{script.name}' timed out after 60 seconds."

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        details = stderr or stdout or "no error output was produced."
        return f"Error: script '{script.name}' failed with exit code {completed.returncode}: {details}"
    return stdout or f"Script '{script.name}' completed successfully."


async def main() -> None:
    message = " ".join(sys.argv[1:]).strip()
    if not message:
        message = "Create a 3-day PDF travel guide for Lisbon focused on food and viewpoints."

    credential = DefaultAzureCredential()
    skills_provider = SkillsProvider.from_paths(
        skill_paths=SKILLS_ROOT,
        script_runner=run_local_skill_script,
        disable_load_skill_approval=True,
        disable_read_skill_resource_approval=True,
        disable_run_skill_script_approval=True,
    )
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=credential,
        ),
        instructions=(
            "You are a travel planning assistant. Use the travel-guide skill for "
            "travel guides, itineraries, and PDF requests."
        ),
        context_providers=[skills_provider],
        default_options={"store": False},
    )
    response = await agent.run(message)
    print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
