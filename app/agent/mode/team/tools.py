"""Team communication tools — LLM-callable tools for agent-team messaging.

One tool for everyone: team_message(to, content)

Injected into agent.run() at runtime via injected_tools.
Lead and members share the same underlying function but get role-specific
descriptions so the LLM understands the intended usage for each role.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field

from app.agent.tools.registry import Tool

if TYPE_CHECKING:
    from app.agent.mode.team.mailbox import TeamMailbox


_LEAD_DESCRIPTION = (
    "Send a message to one or more team members. "
    "Use to: delegate tasks, provide instructions, relay scope changes, "
    "or ask a member for status."
)

_MEMBER_DESCRIPTION = (
    "Your ONLY way to communicate — plain text output is silently discarded. "
    "Call this tool to: deliver work output (findings, drafts, data) to the lead, "
    "hand off results to a peer, or ask a specific unblocking question."
)


def make_team_message_tool(
    mailbox: "TeamMailbox",
    agent_name: str,
    role: Literal["lead", "member"] = "member",
) -> Tool:
    """Return the team_message tool bound to *agent_name* with role-specific description."""

    async def team_message(
        to: Annotated[
            list[str],
            Field(
                description=(
                    "Recipient names — exact names from the team roster. "
                    "One call per intended audience: if you need to say different things "
                    "to different people, make separate calls. "
                    'Example: ["researcher"], ["writer", "analyst"]'
                )
            ),
        ],
        content: Annotated[
            str,
            Field(
                description=(
                    "The message body. Must be addressed ONLY to recipients in `to`. "
                    "Work output only: findings, drafts, data, task instructions, or questions. "
                    "NEVER greetings, status updates, or acknowledgements. "
                    "Do NOT prefix with your name — the system adds [your-name]: automatically."
                )
            ),
        ],
    ) -> str:
        """Send a message to one or more teammates."""
        from app.agent.mode.team.mailbox import Message

        # Me drop self — agents cannot message themselves
        recipients = [r for r in to if r != agent_name]

        # Me validate all recipients exist
        missing = [r for r in recipients if r not in mailbox.registered_agents]
        if missing:
            available = [a for a in mailbox.registered_agents if a != agent_name]
            return f"Agent(s) not found: {', '.join(missing)}. Available: {', '.join(available)}"

        if not recipients:
            return "No valid recipients (cannot message yourself)."

        # Me strip self-prefix in both "[name]: " and "name: " forms (prevents double-prefix)
        stripped = re.sub(r"^\[?" + re.escape(agent_name) + r"\]?:\s*", "", content)
        formatted = f"[{agent_name}]: {stripped}"

        for recipient in recipients:
            msg = Message(
                from_agent=agent_name,
                to_agent=recipient,
                content=formatted,
            )
            await mailbox.send(to=recipient, message=msg)

        return f"Message sent to {', '.join(recipients)}."

    description = _LEAD_DESCRIPTION if role == "lead" else _MEMBER_DESCRIPTION
    return Tool(team_message, name="team_message", description=description)
