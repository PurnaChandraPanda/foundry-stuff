# Copyright (c) Microsoft. All rights reserved.

"""Create a Foundry toolbox that references existing Foundry Skills.

Run ``provision_skills.py`` first so every name in ``SKILL_NAMES`` exists in
the same Foundry project.
"""

import os
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import ToolboxSkillReference
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()


def _skill_names_from_env() -> list[str]:
    names = [name.strip() for name in os.environ["SKILL_NAMES"].split(",") if name.strip()]
    if not names:
        raise ValueError("SKILL_NAMES must contain at least one Foundry skill name.")
    if len(names) != len(set(names)):
        raise ValueError("SKILL_NAMES must not contain duplicate names.")
    return names


def main() -> None:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    toolbox_name = os.environ.get("TOOLBOX_NAME")
    if not toolbox_name:
        raise ValueError("TOOLBOX_NAME must not be empty.")

    skill_names = _skill_names_from_env()
    description = os.environ.get("TOOLBOX_DESCRIPTION")

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint,
            credential=credential,
            allow_preview=True,
        ) as project,
    ):
        available_skills = {skill.name: skill for skill in project.beta.skills.list()}
        missing = [name for name in skill_names if name not in available_skills]
        if missing:
            raise RuntimeError(
                f"Foundry skills not found in this project: {', '.join(missing)}. "
                "Run provision_skills.py first."
            )

        toolbox_version = project.toolboxes.create_version(
            name=toolbox_name,
            description=description,
            tools=[],
            skills=[ToolboxSkillReference(name=name) for name in skill_names],
        )

        # A rerun creates an immutable version; explicitly promote the new one.
        toolbox = project.toolboxes.update(
            name=toolbox_name,
            default_version=toolbox_version.version,
        )
        provisioned = project.toolboxes.get_version(
            name=toolbox_name,
            version=toolbox_version.version,
        )

        attached_names = {skill.name for skill in provisioned.skills or []}
        missing_references = [name for name in skill_names if name not in attached_names]
        if missing_references:
            raise RuntimeError(
                "Toolbox version was created without expected skill references: "
                f"{', '.join(missing_references)}."
            )

        print(
            f"Provisioned toolbox '{toolbox.name}' version {toolbox_version.version} "
            f"as default with skills: {', '.join(skill_names)}."
        )


if __name__ == "__main__":
    main()