"""
References Generator Tool for creating formatted references sections.
"""

import json
import logging

from smolagents import Tool

from mxtoai.schemas import ToolOutputWithCitations
from mxtoai.scripts.citation_manager import get_citation_manager

logger = logging.getLogger(__name__)


class ReferencesGeneratorTool(Tool):
    """
    Tool for generating a formatted references section from all collected citations.
    This tool should be called at the end of research to compile all sources.
    """

    name = "generate_references"
    description = (
        "Generate a formatted references section from all citations collected during the current session. "
        "This tool compiles all web sources, attachments, and other sources that have been cited "
        "into a properly formatted references section. Call this tool after completing research "
        "to include all sources in your final output."
    )
    inputs = {
        "include_in_content": {
            "type": "boolean",
            "description": "Whether to include the references in the main content output. Default: True.",
            "default": True,
            "nullable": True
        }
    }
    output_type = "object"

    def __init__(self):
        """Initialize the references generator tool."""
        super().__init__()
        logger.debug("ReferencesGeneratorTool initialized")

    def forward(self, include_in_content: bool = True) -> str:
        """Generate a formatted references section."""
        try:
            logger.info("Generating references section from collected citations")

            citation_manager = get_citation_manager()

            if not citation_manager.has_citations():
                result = ToolOutputWithCitations(
                    content="No citations were collected during this session.",
                    metadata={
                        "total_citations": 0,
                        "has_references": False
                    }
                )
                logger.info("No citations found to generate references")
                return json.dumps(result.model_dump())

            # Generate the references section
            references_section = citation_manager.generate_references_section()
            citations = citation_manager.get_citations()

            content = references_section if include_in_content else "References section generated successfully."

            result = ToolOutputWithCitations(
                content=content,
                metadata={
                    "total_citations": len(citations.sources),
                    "has_references": True,
                    "references_section": references_section,
                    "citation_sources": [
                        {
                            "id": source.id,
                            "title": source.title,
                            "source_type": source.source_type,
                            "url": source.url,
                            "filename": source.filename
                        }
                        for source in citations.sources
                    ]
                }
            )

            logger.info(f"Generated references section with {len(citations.sources)} sources")
            return json.dumps(result.model_dump())

        except Exception as e:
            logger.error(f"Failed to generate references section: {e}")
            raise
