"""
LinkedIn Data API implementation.
Provides access to LinkedIn data through the LinkedIn Data API (different from Fresh Data API).
"""

import json
import logging
import os
from typing import Any, Optional

import requests
from smolagents import Tool

from mxtoai.request_context import RequestContext

logger = logging.getLogger(__name__)

# Constants
LINKEDIN_API_TIMEOUT = 30


class LinkedInDataAPIError(Exception):
    """Base exception for LinkedIn Data API errors."""


class LinkedInDataAPIRequestError(LinkedInDataAPIError):
    """Exception for LinkedIn Data API request failures."""


class LinkedInDataAPIProcessingError(LinkedInDataAPIError):
    """Exception for LinkedIn Data API processing failures."""


class LinkedInDataAPITool(Tool):
    """Tool for accessing LinkedIn data through LinkedIn Data API."""

    name: str = "linkedin_data_api"
    description: str = "Access LinkedIn profile and company data using LinkedIn Data API for research and verification."
    output_type: str = "object"
    inputs: dict = {  # noqa: RUF012
        "action": {
            "type": "string",
            "description": "The action to perform",
            "enum": [
                "get_profile_data",
                "get_profile_by_url",
                "search_people",
                "search_people_by_url",
                "get_company_details",
                "search_companies",
            ],
        },
        # Parameters for get_profile_data and get_company_details
        "username": {
            "type": "string",
            "description": "LinkedIn username (for get_profile_data and get_company_details actions)",
            "nullable": True,
        },
        # Parameters for get_profile_by_url and search_people_by_url
        "profile_url": {
            "type": "string",
            "description": "LinkedIn profile URL (for get_profile_by_url action)",
            "nullable": True,
        },
        "search_url": {
            "type": "string",
            "description": "LinkedIn search URL (for search_people_by_url action)",
            "nullable": True,
        },
        # Parameters for search_people action
        "keywords": {"type": "string", "description": "Search keywords for people search (optional)", "nullable": True},
        "start": {
            "type": "string",
            "description": "Pagination start position for people search - could be one of: 0, 10, 20, 30, etc. (optional)",
            "nullable": True,
        },
        "geo": {
            "type": "string",
            "description": "Geographic location codes for people search, comma-separated (e.g., '103644278,101165590') (optional)",
            "nullable": True,
        },
        "school_id": {
            "type": "string",
            "description": "School identifier for education filter in people search (optional)",
            "nullable": True,
        },
        "first_name": {
            "type": "string",
            "description": "First name filter for people search (optional)",
            "nullable": True,
        },
        "last_name": {
            "type": "string",
            "description": "Last name filter for people search (optional)",
            "nullable": True,
        },
        "keyword_school": {
            "type": "string",
            "description": "School-related keywords for people search (optional)",
            "nullable": True,
        },
        "keyword_title": {
            "type": "string",
            "description": "Job title keywords for people search (optional)",
            "nullable": True,
        },
        "company": {"type": "string", "description": "Company filter for people search (optional)", "nullable": True},
        # Parameters for search_companies action
        "keyword": {
            "type": "string",
            "description": "Search keyword for company name/description in company search (optional)",
            "nullable": True,
        },
        "locations": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "List of location codes for company search (e.g., [103644278]) (optional)",
            "nullable": True,
        },
        "company_sizes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of company size codes for company search (e.g., ['D', 'E', 'F', 'G']) where D=1001-5000, E=5001-10000, F=10001+, etc. (optional)",
            "nullable": True,
        },
        "has_jobs": {
            "type": "boolean",
            "description": "Whether the company has active job postings in company search (optional)",
            "nullable": True,
        },
        "industries": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "List of industry codes for company search (e.g., [96, 4]) (optional)",
            "nullable": True,
        },
        "page": {
            "type": "integer",
            "description": "Page number for pagination in company search (default: 1)",
            "default": 1,
            "nullable": True,
        },
    }

    def __init__(self, api_key: str, context: RequestContext):
        """
        Initialize the LinkedIn Data API tool.

        Args:
            api_key: The RapidAPI key for authentication.
            context: The request context.

        """
        super().__init__()
        if not api_key:
            msg = "RapidAPI key is required for LinkedIn Data API."
            raise ValueError(msg)
        self.api_key = api_key
        self.base_url = "https://linkedin-data-api.p.rapidapi.com"
        self.headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": "linkedin-data-api.p.rapidapi.com",
            "Content-Type": "application/json",
        }
        self.context = context

    def forward(  # noqa: PLR0912, PLR0915
        self,
        action: str,
        username: Optional[str] = None,
        profile_url: Optional[str] = None,
        search_url: Optional[str] = None,
        keywords: Optional[str] = None,
        start: Optional[str] = None,
        geo: Optional[str] = None,
        school_id: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        keyword_school: Optional[str] = None,
        keyword_title: Optional[str] = None,
        company: Optional[str] = None,
        keyword: Optional[str] = None,
        locations: Optional[list[int]] = None,
        company_sizes: Optional[list[str]] = None,
        has_jobs: Optional[bool] = None,
        industries: Optional[list[int]] = None,
        page: int = 1,
    ) -> dict[str, Any]:
        """
        Process LinkedIn data requests and return structured output with citations.

        Args:
            action: The type of search to perform
            username: LinkedIn username (for get_profile_data and get_company_details actions)
            profile_url: LinkedIn profile URL (for get_profile_by_url action)
            search_url: LinkedIn search URL (for search_people_by_url action)
            keywords: Search keywords for people search
            start: Pagination start position for people search
            geo: Geographic location codes for people search
            school_id: School identifier for education filter in people search
            first_name: First name filter for people search
            last_name: Last name filter for people search
            keyword_school: School-related keywords for people search
            keyword_title: Job title keywords for people search
            company: Company filter for people search
            keyword: Search keyword for company name/description in company search
            locations: List of location codes for company search
            company_sizes: List of company size codes for company search
            has_jobs: Whether the company has active job postings in company search
            industries: List of industry codes for company search
            page: Page number for pagination in company search

        Returns:
            dict[str, Any]: JSON string containing the search results with citation metadata

        """
        actions = {
            "get_profile_data": self.get_profile_data,
            "get_profile_by_url": self.get_profile_by_url,
            "search_people": self.search_people,
            "search_people_by_url": self.search_people_by_url,
            "get_company_details": self.get_company_details,
            "search_companies": self.search_companies,
        }

        if action not in actions:
            msg = f"Unsupported action: {action}"
            raise ValueError(msg)

        try:
            # Get the raw data from LinkedIn API
            if action == "get_profile_data":
                if not username:
                    msg = "username is required for get_profile_data action"
                    raise ValueError(msg)
                data = actions[action](username=username)
                # Generate LinkedIn URL from username and add citation
                linkedin_url = f"https://www.linkedin.com/in/{username}/"
                profile_name = data.get("full_name", username)
                citation_title = f"{profile_name} - LinkedIn Profile"
                citation_id = self.context.add_web_citation(linkedin_url, citation_title, visited=True)

            elif action == "get_profile_by_url":
                if not profile_url:
                    msg = "profile_url is required for get_profile_by_url action"
                    raise ValueError(msg)
                data = actions[action](profile_url=profile_url)
                # Use the provided URL for citation
                profile_name = data.get("full_name", "LinkedIn Profile")
                citation_title = f"{profile_name} - LinkedIn Profile"
                citation_id = self.context.add_web_citation(profile_url, citation_title, visited=True)

            elif action == "search_people_by_url":
                if not search_url:
                    msg = "search_url is required for search_people_by_url action"
                    raise ValueError(msg)
                data = actions[action](search_url=search_url)
                # Extract LinkedIn profile URLs from search results
                citation_ids = []
                if data.get("success") and data.get("data", {}).get("items"):
                    for item in data["data"]["items"]:
                        item_profile_url = item.get("profileURL")
                        full_name = item.get("fullName", "LinkedIn Profile")
                        if item_profile_url:
                            citation_title = f"{full_name} - LinkedIn Profile"
                            citation_id = self.context.add_web_citation(item_profile_url, citation_title, visited=True)
                            citation_ids.append(citation_id)

                # Set citation_id to first one for metadata, or None if no results
                citation_id = citation_ids[0] if citation_ids else None

            elif action == "get_company_details":
                if not username:
                    msg = "username is required for get_company_details action"
                    raise ValueError(msg)
                data = actions[action](username=username)
                # Generate LinkedIn company URL from username and add citation
                linkedin_url = f"https://www.linkedin.com/company/{username}/"
                company_name = data.get("name", username)
                citation_title = f"{company_name} - LinkedIn Company"
                citation_id = self.context.add_web_citation(linkedin_url, citation_title, visited=True)

            elif action == "search_people":
                data = actions[action](
                    keywords=keywords,
                    start=start,
                    geo=geo,
                    school_id=school_id,
                    first_name=first_name,
                    last_name=last_name,
                    keyword_school=keyword_school,
                    keyword_title=keyword_title,
                    company=company,
                )
                # Extract LinkedIn profile URLs from search results based on schema
                citation_ids = []
                if data.get("success") and data.get("data", {}).get("items"):
                    for item in data["data"]["items"]:
                        item_profile_url = item.get("profileURL")
                        full_name = item.get("fullName", "LinkedIn Profile")
                        if item_profile_url:
                            citation_title = f"{full_name} - LinkedIn Profile"
                            citation_id = self.context.add_web_citation(item_profile_url, citation_title, visited=True)
                            citation_ids.append(citation_id)

                # Set citation_id to first one for metadata, or None if no results
                citation_id = citation_ids[0] if citation_ids else None

            elif action == "search_companies":
                data = actions[action](
                    keyword=keyword,
                    locations=locations,
                    company_sizes=company_sizes,
                    has_jobs=has_jobs,
                    industries=industries,
                    page=page,
                )
                # Extract LinkedIn company URLs from search results based on schema
                citation_ids = []
                if data.get("success") and data.get("data", {}).get("items"):
                    for item in data["data"]["items"]:
                        # Based on schema: linkedinURL field contains the company URL
                        company_url = item.get("linkedinURL")
                        company_name = item.get("name", "LinkedIn Company")
                        if company_url:
                            citation_title = f"{company_name} - LinkedIn Company"
                            citation_id = self.context.add_web_citation(company_url, citation_title, visited=True)
                            citation_ids.append(citation_id)

                # Set citation_id to first one for metadata, or None if no results
                citation_id = citation_ids[0] if citation_ids else None

            else:
                msg = f"Action '{action}' not implemented in forward method"
                raise ValueError(msg)

            # Create structured output
            from mxtoai.schemas import CitationCollection, ToolOutputWithCitations

            # Create local citation collection if we have citations
            local_citations = CitationCollection()
            if citation_id:
                # We need to get the citation details from the request context
                context_citations = self.context.get_citations()

                # For search actions, we may have multiple citations
                if action in ["search_people", "search_companies"] and "citation_ids" in locals():
                    # Add all citations from search results
                    for cid in citation_ids:
                        recent_citation = next((s for s in context_citations.sources if s.id == cid), None)
                        if recent_citation:
                            local_citations.add_source(recent_citation)
                else:
                    # Single citation for other actions
                    recent_citation = next((s for s in context_citations.sources if s.id == citation_id), None)
                    if recent_citation:
                        local_citations.add_source(recent_citation)

            # Format the content with citation references if available
            if citation_id:
                if action in ["search_people", "search_companies"] and "citation_ids" in locals() and citation_ids:
                    # For search results, show all citation IDs
                    citation_refs = ", ".join([f"#{cid}" for cid in citation_ids])
                    content = (
                        f"**LinkedIn Search Results with Citations** [{citation_refs}]\n\n{json.dumps(data, indent=2)}"
                    )
                else:
                    # Single citation for other actions
                    content = f"**LinkedIn Data Retrieved** [#{citation_id}]\n\n{json.dumps(data, indent=2)}"
            else:
                content = f"**LinkedIn Search Results**\n\n{json.dumps(data, indent=2)}"

            # Calculate total citations for metadata
            total_citations = 0
            if action in ["search_people", "search_companies"] and "citation_ids" in locals():
                total_citations = len(citation_ids)
            elif citation_id:
                total_citations = 1

            result = ToolOutputWithCitations(
                content=content,
                citations=local_citations,
                metadata={
                    "action": action,
                    "citation_id": citation_id,
                    "data_keys": list(data.keys()) if isinstance(data, dict) else [],
                    "has_citation": citation_id is not None,
                    "total_citations": total_citations,
                    "citation_ids": citation_ids if "citation_ids" in locals() else [],
                },
            )

            # Log completion with citation info
            if action in ["search_people", "search_companies"] and "citation_ids" in locals() and citation_ids:
                logger.info(
                    f"LinkedIn {action} completed successfully with {len(citation_ids)} citations: {citation_ids}"
                )
            elif citation_id:
                logger.info(f"LinkedIn {action} completed successfully with citation [{citation_id}]")
            else:
                logger.info(f"LinkedIn {action} completed successfully")
            return json.dumps(result.model_dump())

        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn Data API request failed: {e}")
            msg = f"LinkedIn Data API request failed: {e}"
            raise LinkedInDataAPIRequestError(msg) from e
        except Exception as e:
            logger.error(f"Error processing LinkedIn Data API request: {e}")
            msg = f"Failed to process LinkedIn Data API request: {e}"
            raise LinkedInDataAPIProcessingError(msg) from e

    def get_profile_data(self, username: str) -> dict:
        """
        Get profile data by LinkedIn username.

        Args:
            username: LinkedIn username

        Returns:
            Dict containing profile data

        """
        endpoint = "/get-profile-data"
        params = {"username": username}
        response = requests.post(
            f"{self.base_url}{endpoint}", params=params, headers=self.headers, timeout=LINKEDIN_API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    def get_profile_by_url(self, profile_url: str) -> dict:
        """
        Get profile data by URL (alternative endpoint).

        Args:
            profile_url: LinkedIn profile URL

        Returns:
            Dict containing profile data

        """
        endpoint = "/get-profile-data-by-url"
        payload = {"url": profile_url}

        response = requests.post(
            f"{self.base_url}{endpoint}", json=payload, headers=self.headers, timeout=LINKEDIN_API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    def search_people(
        self,
        keywords: Optional[str] = None,
        start: Optional[str] = None,
        geo: Optional[str] = None,
        school_id: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        keyword_school: Optional[str] = None,
        keyword_title: Optional[str] = None,
        company: Optional[str] = None,
    ) -> dict:
        """
        Search for people on LinkedIn.

        Args:
            keywords: Search keywords (optional)
            start: Pagination start position - could be one of: 0, 10, 20, 30, etc. (optional)
            geo: Geographic location codes, comma-separated (e.g., "103644278,101165590") (optional)
            school_id: School identifier for education filter (optional)
            first_name: First name filter (optional)
            last_name: Last name filter (optional)
            keyword_school: School-related keywords (optional)
            keyword_title: Job title keywords (optional)
            company: Company filter (optional)

        Returns:
            Dict containing search results

        """
        endpoint = "/search-people"
        params = {}

        # Add parameters only if they are provided
        if keywords:
            params["keywords"] = keywords
        if start:
            params["start"] = start
        if geo:
            params["geo"] = geo
        if school_id:
            params["schoolId"] = school_id
        if first_name:
            params["firstName"] = first_name
        if last_name:
            params["lastName"] = last_name
        if keyword_school:
            params["keywordSchool"] = keyword_school
        if keyword_title:
            params["keywordTitle"] = keyword_title
        if company:
            params["company"] = company

        response = requests.get(
            f"{self.base_url}{endpoint}", headers=self.headers, params=params, timeout=LINKEDIN_API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    def search_people_by_url(self, search_url: str) -> dict:
        """
        Search people using a LinkedIn search URL.

        Args:
            search_url: LinkedIn search URL

        Returns:
            Dict containing search results

        Example Payload:
        {
            "url": "https://www.linkedin.com/search/results/people/?currentCompany=%5B%221035%22%5D&geoUrn=%5B%22103644278%22%5D&keywords=max&origin=FACETED_SEARCH&sid=%3AB5"
        }

        """
        endpoint = "/search-people-by-url"
        payload = {"url": search_url}

        response = requests.post(
            f"{self.base_url}{endpoint}", json=payload, headers=self.headers, timeout=LINKEDIN_API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    def get_company_details(self, username: str) -> dict:
        """
        Get company details by LinkedIn company username.

        Args:
            username: LinkedIn company username

        Returns:
            Dict containing company details

        """
        endpoint = "/get-company-details"
        params = {"username": username}

        response = requests.post(
            f"{self.base_url}{endpoint}", params=params, headers=self.headers, timeout=LINKEDIN_API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    def search_companies(
        self,
        keyword: Optional[str] = None,
        locations: Optional[list[int]] = None,
        company_sizes: Optional[list[str]] = None,
        has_jobs: Optional[bool] = None,
        industries: Optional[list[int]] = None,
        page: int = 1,
    ) -> dict:
        """
        Search for companies on LinkedIn.

        Args:
            keyword: Search keyword for company name/description
            locations: List of location codes (e.g., [103644278])
            company_sizes: List of company size codes (e.g., ["D", "E", "F", "G"])
                          where D=1001-5000, E=5001-10000, F=10001+, etc.
            has_jobs: Whether the company has active job postings
            industries: List of industry codes (e.g., [96, 4])
            page: Page number for pagination (default: 1)

        Returns:
            Dict containing search results

        """
        endpoint = "/search-companies"
        payload = {"keyword": keyword or "", "page": page}

        # Add optional parameters only if provided
        if locations:
            payload["locations"] = locations
        if company_sizes:
            payload["companySizes"] = company_sizes
        if has_jobs is not None:
            payload["hasJobs"] = has_jobs
        if industries:
            payload["industries"] = industries

        response = requests.post(
            f"{self.base_url}{endpoint}", json=payload, headers=self.headers, timeout=LINKEDIN_API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()


def initialize_linkedin_data_api_tool() -> Optional[LinkedInDataAPITool]:
    """
    Initialize the LinkedIn Data API tool if API key is available.

    Returns:
        LinkedInDataAPITool instance or None if API key not found.

    """
    api_key = os.getenv("RAPIDAPI_KEY")
    if api_key:
        logger.info(
            "RAPIDAPI_KEY found but LinkedInDataAPITool requires context parameter. Tool initialization deferred to agent."
        )
        return None  # Return None since we need context from agent
    logger.info("RAPIDAPI_KEY not found. LinkedIn Data API tool not initialized.")
    return None
