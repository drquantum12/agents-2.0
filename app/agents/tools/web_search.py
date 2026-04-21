"""
Web search tool — placeholder for future implementation.
Enables the agent to look up recent information during lessons.
"""
import logging
from typing import Optional, Tuple

from app.agents.tools.base import VijayebhavTool, register_tool

logger = logging.getLogger(__name__)


class WebSearchTool(VijayebhavTool):
    name = "web_search"
    description = (
        "Search the web for current information on a topic. "
        "Use when the student asks about recent events or requires "
        "information not available in the concept graph. "
        "Input format: 'query=<search query>'"
    )

    def run(self, input: str) -> Tuple[str, None]:
        # Placeholder — integrate with a search API (e.g. Google Custom Search,
        # Brave Search, or Tavily) when ready.
        logger.info(f"WebSearchTool: {input} (not yet implemented)")
        return ("Web search is not yet available in this session.", None)


register_tool(WebSearchTool())
