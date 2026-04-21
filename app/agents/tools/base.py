"""
Tool plug-in pattern for the reimagined vijayebhav agent.

Adding a tool:
1. Implement a subclass of VijayebhavTool with name, description, and run().
2. Call register_tool(MyTool()) at module level.
3. Enable via device_config.active_tools (persistent) or
   extra_tools arg to run_agent() (per-call).

Critical contract: any tool that reveals student knowledge MUST return a
WorldModelDelta alongside the text output so the knowledge graph reflects
what the student demonstrated.
"""
import logging
from abc import ABC, abstractmethod
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_REGISTRY: dict = {}


class VijayebhavTool(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    def run(self, input: str) -> Tuple[str, Optional[object]]:
        """
        Execute the tool.
        Returns (text_output, WorldModelDelta | None).
        """

    def __repr__(self) -> str:
        return f"<VijayebhavTool name={self.name!r}>"


def register_tool(tool: VijayebhavTool) -> None:
    _REGISTRY[tool.name] = tool
    logger.debug(f"Registered tool: {tool.name}")


def get_tool(name: str) -> Optional[VijayebhavTool]:
    return _REGISTRY.get(name)


def list_tools() -> list:
    return list(_REGISTRY.values())
