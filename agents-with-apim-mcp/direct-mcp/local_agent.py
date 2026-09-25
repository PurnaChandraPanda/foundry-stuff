"""Run a MAF agent on this machine, retaining history through approval rounds."""

import argparse
import asyncio
from collections.abc import Callable

from agent_framework import Agent, Message
from azure.identity import AzureCliCredential

from config import load_environment
from maf_agent import build_agent


async def run_with_approvals(
    agent: Agent, query: str, approve: Callable[[str], str] = input
) -> str:
    session = agent.create_session()
    result = await agent.run(query, session=session)
    for round_number in range(21):
        if not result.user_input_requests:
            return result.text
        if round_number == 20:
            raise RuntimeError("Stopped after 20 approval rounds; inspect the agent and tool behavior.")
        responses = []
        for request in result.user_input_requests:
            call = request.function_call
            if request.type != "function_approval_request" or call is None:
                raise RuntimeError(f"Unsupported user-input request: {request.type}")
            print(f"Tool: {call.name}\nArguments: {call.arguments}")
            accepted = approve("Approve this call? [y/N] ").strip().lower() == "y"
            responses.append(request.to_function_approval_response(accepted))
        result = await agent.run(
            Message(role="user", contents=responses),
            session=session,
        )
    raise AssertionError("Approval loop exited without a response.")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    load_environment()
    print("APIM calls execute from: this machine (VPN/VNet), without a toolbox.")
    with AzureCliCredential() as credential:
        async with build_agent(credential) as agent:
            print(await run_with_approvals(agent, args.query))


if __name__ == "__main__":
    asyncio.run(main())
