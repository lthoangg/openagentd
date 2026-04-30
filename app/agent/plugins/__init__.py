"""User-defined plugin system.

Plugins are ``.py`` files placed under ``settings.OPENAGENTD_PLUGINS_DIRS``
(default ``{OPENAGENTD_CONFIG_DIR}/plugins``).  At agent-build time
:func:`load_plugin_hooks` discovers them, imports them, and converts
each into a list of :class:`~app.agent.hooks.BaseAgentHook` instances
ready to be slotted into the existing hook chain.

Two authoring contracts are supported:

1. **Functional** — export ``async def plugin() -> dict`` returning an
   event dict::

       async def plugin():
           return {
               "tool.before": before,
               "tool.after": after,
           }

   The dict is wrapped in a synthetic :class:`BaseAgentHook` adapter.

2. **Class-based** — subclass :class:`BaseAgentHook` and expose it as
   ``Plugin``.  Optional ``applies_to(agent_name, role) -> bool``
   filters per-agent.

Re-exports below are kept stable for plugin authors so they can write
``from app.agent.plugins import BaseAgentHook, RunContext`` regardless
of where those types live internally.
"""

from __future__ import annotations

from app.agent.hooks.base import BaseAgentHook
from app.agent.plugins.events import (
    ToolAfterInput,
    ToolAfterOutput,
    ToolBeforeInput,
    ToolBeforeOutput,
)
from app.agent.plugins.loader import load_plugin_hooks
from app.agent.plugins.role import current_role, set_role
from app.agent.state import AgentState, ModelRequest, RunContext

__all__ = [
    "AgentState",
    "BaseAgentHook",
    "ModelRequest",
    "RunContext",
    "ToolAfterInput",
    "ToolAfterOutput",
    "ToolBeforeInput",
    "ToolBeforeOutput",
    "current_role",
    "load_plugin_hooks",
    "set_role",
]
