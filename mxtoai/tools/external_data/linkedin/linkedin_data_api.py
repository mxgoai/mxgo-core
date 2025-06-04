"""
LinkedIn Data API implementation.
Provides access to LinkedIn data through the LinkedIn Data API (different from Fresh Data API).
"""

import logging
import os
from typing import Optional

import requests
from smolagents import Tool

logger = logging.getLogger(__name__)


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

    def __init__(self, api_key: str):
        """
        Initialize the LinkedIn Data API tool.

        Args:
            api_key: The RapidAPI key for authentication.

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

    def forward(
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
    ) -> dict:
        """
        Process LinkedIn data requests.

        Args:
            action: The type of search to perform
            username: LinkedIn username (for get_profile_data and get_company_details actions)
            profile_url: LinkedIn profile URL (for get_profile_by_url action)
            search_url: LinkedIn search URL (for search_people_by_url action)
            keywords: Search keywords for people search (optional)
            start: Pagination start position for people search (optional)
            geo: Geographic location codes for people search (optional)
            school_id: School identifier for education filter in people search (optional)
            first_name: First name filter for people search (optional)
            last_name: Last name filter for people search (optional)
            keyword_school: School-related keywords for people search (optional)
            keyword_title: Job title keywords for people search (optional)
            company: Company filter for people search (optional)
            keyword: Search keyword for company name/description in company search (optional)
            locations: List of location codes for company search (optional)
            company_sizes: List of company size codes for company search (optional)
            has_jobs: Whether the company has active job postings in company search (optional)
            industries: List of industry codes for company search (optional)
            page: Page number for pagination in company search (default: 1)

        Returns:
            Dict containing the search results

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
            if action == "get_profile_data":
                if not username:
                    msg = "username is required for get_profile_data action"
                    raise ValueError(msg)
                return actions[action](username=username)
            if action == "get_profile_by_url":
                if not profile_url:
                    msg = "profile_url is required for get_profile_by_url action"
                    raise ValueError(msg)
                return actions[action](profile_url=profile_url)
            if action == "search_people_by_url":
                if not search_url:
                    msg = "search_url is required for search_people_by_url action"
                    raise ValueError(msg)
                return actions[action](search_url=search_url)
            if action == "get_company_details":
                if not username:
                    msg = "username is required for get_company_details action"
                    raise ValueError(msg)
                return actions[action](username=username)
            if action == "search_people":
                return actions[action](
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
            if action == "search_companies":
                return actions[action](
                    keyword=keyword,
                    locations=locations,
                    company_sizes=company_sizes,
                    has_jobs=has_jobs,
                    industries=industries,
                    page=page,
                )
            msg = f"Action '{action}' not implemented in forward method"
            raise ValueError(msg)
        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn Data API request failed: {e}")
            msg = f"LinkedIn Data API request failed: {e}"
            raise Exception(msg) from e
        except Exception as e:
            logger.error(f"Error processing LinkedIn Data API request: {e}")
            msg = f"Failed to process LinkedIn Data API request: {e}"
            raise Exception(msg) from e

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
        response = requests.post(f"{self.base_url}{endpoint}", params=params, headers=self.headers)
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

        response = requests.post(f"{self.base_url}{endpoint}", json=payload, headers=self.headers)
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

        response = requests.get(f"{self.base_url}{endpoint}", headers=self.headers, params=params)
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

        response = requests.post(f"{self.base_url}{endpoint}", json=payload, headers=self.headers)
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

        response = requests.post(f"{self.base_url}{endpoint}", params=params, headers=self.headers)
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

        response = requests.post(f"{self.base_url}{endpoint}", json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()


def initialize_linkedin_data_api_tool() -> Optional[LinkedInDataAPITool]:
    """
    Initializes the LinkedInDataAPITool if the API key is available.

    Returns:
        Optional[LinkedInDataAPITool]: Initialized tool instance or None if initialization fails

    """
    api_key = os.getenv("RAPIDAPI_KEY")
    if api_key:
        try:
            tool = LinkedInDataAPITool(api_key=api_key)
            logger.debug("Initialized LinkedInDataAPITool.")
            return tool  # noqa: TRY300
        except ValueError as e:
            logger.warning(f"Failed to initialize LinkedInDataAPITool: {e}")
            return None
    else:
        logger.warning("LinkedInDataAPITool not initialized. Missing RAPIDAPI_KEY environment variable.")
        return None
