"""
LinkedIn Fresh Data API implementation.
Provides access to LinkedIn data through the Fresh LinkedIn Profile Data API.
"""

import json
import logging
import os
from typing import Optional

import requests
from smolagents import Tool

from mxtoai.request_context import RequestContext

logger = logging.getLogger(__name__)


class LinkedInFreshDataTool(Tool):
    """Tool for accessing LinkedIn data through Fresh LinkedIn Profile Data API."""

    name: str = "linkedin_fresh_data"
    description: str = (
        "Access LinkedIn profile and company data directly from LinkedIn URLs for research and verification."
    )
    output_type: str = "object"
    inputs: dict = {  # noqa: RUF012
        "action": {
            "type": "string",
            "description": "The action to perform: 'get_linkedin_profile' or 'get_company_by_linkedin_url'",
            "enum": ["get_linkedin_profile", "get_company_by_linkedin_url"],
        },
        "linkedin_url": {"type": "string", "description": "The LinkedIn URL (profile or company)"},
        # Optional parameters for get_linkedin_profile action
        "include_skills": {
            "type": "boolean",
            "description": "Include skills section in response (default: false)",
            "default": False,
            "nullable": True,
        },
        "include_certifications": {
            "type": "boolean",
            "description": "Include certifications section in response (default: false)",
            "default": False,
            "nullable": True,
        },
        "include_publications": {
            "type": "boolean",
            "description": "Include publications section in response (default: false)",
            "default": False,
            "nullable": True,
        },
        "include_honors": {
            "type": "boolean",
            "description": "Include honors and awards section in response (default: false)",
            "default": False,
            "nullable": True,
        },
        "include_volunteers": {
            "type": "boolean",
            "description": "Include volunteer experience section in response (default: false)",
            "default": False,
            "nullable": True,
        },
        "include_projects": {
            "type": "boolean",
            "description": "Include projects section in response (default: false)",
            "default": False,
            "nullable": True,
        },
        "include_patents": {
            "type": "boolean",
            "description": "Include patents section in response (default: false)",
            "default": False,
            "nullable": True,
        },
        "include_courses": {
            "type": "boolean",
            "description": "Include courses section in response (default: false)",
            "default": False,
            "nullable": True,
        },
        "include_organizations": {
            "type": "boolean",
            "description": "Include organizations section in response (default: false)",
            "default": False,
            "nullable": True,
        },
        "include_profile_status": {
            "type": "boolean",
            "description": "Include profile status information (default: false)",
            "default": False,
            "nullable": True,
        },
        "include_company_public_url": {
            "type": "boolean",
            "description": "Include company public URL information (default: false)",
            "default": False,
            "nullable": True,
        },
    }

    def __init__(self, api_key: str, context: RequestContext):
        """
        Initialize the LinkedIn Fresh Data tool.

        Args:
            api_key: The RapidAPI key for authentication.
            context: The request context.

        """
        super().__init__()
        if not api_key:
            msg = "RapidAPI key is required for LinkedIn Fresh Data API."
            raise ValueError(msg)
        self.api_key = api_key
        self.base_url = "https://fresh-linkedin-profile-data.p.rapidapi.com"
        self.headers = {"x-rapidapi-key": self.api_key, "x-rapidapi-host": "fresh-linkedin-profile-data.p.rapidapi.com"}
        self.context = context

    def forward(
        self,
        action: str,
        linkedin_url: str,
        include_skills: bool = False,
        include_certifications: bool = False,
        include_publications: bool = False,
        include_honors: bool = False,
        include_volunteers: bool = False,
        include_projects: bool = False,
        include_patents: bool = False,
        include_courses: bool = False,
        include_organizations: bool = False,
        include_profile_status: bool = False,
        include_company_public_url: bool = False,
    ) -> str:
        """
        Process LinkedIn data requests and return structured output with citations.

        Args:
            action: The type of request to perform ('get_linkedin_profile' or 'get_company_by_linkedin_url')
            linkedin_url: The LinkedIn URL (profile or company)
            include_skills: Include skills section in response (default: false)
            include_certifications: Include certifications section in response (default: false)
            include_publications: Include publications section in response (default: false)
            include_honors: Include honors and awards section in response (default: false)
            include_volunteers: Include volunteer experience section in response (default: false)
            include_projects: Include projects section in response (default: false)
            include_patents: Include patents section in response (default: false)
            include_courses: Include courses section in response (default: false)
            include_organizations: Include organizations section in response (default: false)
            include_profile_status: Include profile status information (default: false)
            include_company_public_url: Include company public URL information (default: false)

        Returns:
            str: JSON string containing the results with citation metadata

        """
        actions = {
            "get_linkedin_profile": self.get_linkedin_profile,
            "get_company_by_linkedin_url": self.get_company_by_linkedin_url,
        }

        if action not in actions:
            msg = f"Unsupported action: {action}"
            raise ValueError(msg)

        try:
            # Get the raw data from LinkedIn API
            if action == "get_linkedin_profile":
                data = actions[action](
                    linkedin_url=linkedin_url,
                    include_skills=include_skills,
                    include_certifications=include_certifications,
                    include_publications=include_publications,
                    include_honors=include_honors,
                    include_volunteers=include_volunteers,
                    include_projects=include_projects,
                    include_patents=include_patents,
                    include_courses=include_courses,
                    include_organizations=include_organizations,
                    include_profile_status=include_profile_status,
                    include_company_public_url=include_company_public_url,
                )
                # Simple: just use the input LinkedIn URL and extract name for title
                profile_name = data.get("full_name", "LinkedIn Profile")
                citation_title = f"{profile_name} - LinkedIn Profile"
            else:
                # get_company_by_linkedin_url
                data = actions[action](linkedin_url=linkedin_url)
                # Simple: just use the input LinkedIn URL and extract name for title
                company_name = data.get("name", "LinkedIn Company")
                citation_title = f"{company_name} - LinkedIn Company"

            # Add web citation for the input LinkedIn URL
            citation_id = self.context.add_web_citation(linkedin_url, citation_title, visited=True)

            # Create structured output with citation reference
            from mxtoai.schemas import ToolOutputWithCitations, CitationCollection, CitationSource

            # Create local citation collection
            local_citations = CitationCollection()
            citation_source = CitationSource(
                id=citation_id,
                title=citation_title,
                url=linkedin_url,
                date_accessed="",  # Will be set by citation manager
                source_type="web",
                description="visited"
            )
            local_citations.add_source(citation_source)

            # Format the content with citation reference
            content = f"**LinkedIn Data Retrieved** [#{citation_id}]\n\n{json.dumps(data, indent=2)}"

            result = ToolOutputWithCitations(
                content=content,
                citations=local_citations,
                metadata={
                    "action": action,
                    "linkedin_url": linkedin_url,
                    "citation_id": citation_id,
                    "data_keys": list(data.keys()) if isinstance(data, dict) else []
                }
            )

            logger.info(f"LinkedIn {action} completed successfully with citation [{citation_id}]")
            return json.dumps(result.model_dump())

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn Fresh Data API request failed: {e}")
            msg = f"LinkedIn Fresh Data API request failed: {e}"
            raise Exception(msg) from e
        except Exception as e:
            logger.error(f"Error processing LinkedIn Fresh Data API request: {e}")
            msg = f"Failed to process LinkedIn Fresh Data API request: {e}"
            raise Exception(msg) from e

    def get_linkedin_profile(
        self,
        linkedin_url: str,
        include_skills: bool = False,
        include_certifications: bool = False,
        include_publications: bool = False,
        include_honors: bool = False,
        include_volunteers: bool = False,
        include_projects: bool = False,
        include_patents: bool = False,
        include_courses: bool = False,
        include_organizations: bool = False,
        include_profile_status: bool = False,
        include_company_public_url: bool = False,
    ) -> dict:
        """
        Get detailed LinkedIn profile information from a LinkedIn profile URL.

        Args:
            linkedin_url: LinkedIn profile URL (e.g., "https://www.linkedin.com/in/username/")
            include_skills: Include skills section in response
            include_certifications: Include certifications section in response
            include_publications: Include publications section in response
            include_honors: Include honors and awards section in response
            include_volunteers: Include volunteer experience section in response
            include_projects: Include projects section in response
            include_patents: Include patents section in response
            include_courses: Include courses section in response
            include_organizations: Include organizations section in response
            include_profile_status: Include profile status information
            include_company_public_url: Include company public URL information

        Returns:
            Dict containing detailed profile information

        """
        endpoint = "/get-linkedin-profile"
        params = {
            "linkedin_url": linkedin_url,
            "include_skills": str(include_skills).lower(),
            "include_certifications": str(include_certifications).lower(),
            "include_publications": str(include_publications).lower(),
            "include_honors": str(include_honors).lower(),
            "include_volunteers": str(include_volunteers).lower(),
            "include_projects": str(include_projects).lower(),
            "include_patents": str(include_patents).lower(),
            "include_courses": str(include_courses).lower(),
            "include_organizations": str(include_organizations).lower(),
            "include_profile_status": str(include_profile_status).lower(),
            "include_company_public_url": str(include_company_public_url).lower(),
        }

        response = requests.get(f"{self.base_url}{endpoint}", headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def get_company_by_linkedin_url(self, linkedin_url: str) -> dict:
        """
        Get company information from a LinkedIn company URL.

        Args:
            linkedin_url: LinkedIn company URL (e.g., "https://www.linkedin.com/company/apple/")

        Returns:
            Dict containing company information

        """
        endpoint = "/get-company-by-linkedinurl"
        params = {"linkedin_url": linkedin_url}

        response = requests.get(f"{self.base_url}{endpoint}", headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()


def initialize_linkedin_fresh_tool() -> Optional[LinkedInFreshDataTool]:
    """
    Initialize the LinkedIn Fresh Data tool if API key is available.

    Returns:
        LinkedInFreshDataTool instance or None if API key not found.

    """
    api_key = os.getenv("RAPIDAPI_KEY")
    if api_key:
        logger.info("RAPIDAPI_KEY found but LinkedInFreshDataTool requires context parameter. Tool initialization deferred to agent.")
        return None  # Return None since we need context from agent
    else:
        logger.info("RAPIDAPI_KEY not found. LinkedIn Fresh Data tool not initialized.")
        return None
