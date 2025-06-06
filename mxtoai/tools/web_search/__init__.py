"""
Web search tools module.
Independent search tools for different engines with cost/quality tradeoffs.
"""

from .ddg_search import DDGSearchTool
from .brave_search import BraveSearchTool
from .google_search import GoogleSearchTool

__all__ = [
    "DDGSearchTool",
    "BraveSearchTool",
    "GoogleSearchTool",
]