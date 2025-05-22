# Shamelessly stolen from Microsoft Autogen team: thanks to them for this great resource!
# https://github.com/microsoft/autogen/blob/gaia_multiagent_v01_march_1st/autogen/browser_utils.py
import mimetypes
import re
import time
from pathlib import Path
from typing import Any, ClassVar, Optional, Union
from urllib.parse import urljoin, urlparse

import requests

# Note: Requires 'google-search-results' package to be installed
import serpapi
from smolagents import Tool

from .cookies import COOKIES
from .mdconvert import FileConversionError, MarkdownConverter, UnsupportedFormatError

DEFAULT_REQUEST_TIMEOUT = 30
MAX_FILENAME_SUFFIX = 1000


class NoSearchResultsError(Exception):
    pass


class FileDownloadError(Exception):
    pass


class PageConversionError(Exception):
    pass


class WaybackError(Exception):
    pass


class SimpleTextBrowser:
    """(In preview) An extremely simple text-based web browser comparable to Lynx. Suitable for Agentic use."""

    def __init__(
        self,
        start_page: Optional[str] = None,
        viewport_size: Optional[int] = 1024 * 8,
        downloads_folder: Optional[Union[str, None]] = None,
        serpapi_key: Optional[Union[str, None]] = None,
        request_kwargs: Optional[Union[dict[str, Any], None]] = None,
    ):
        self.start_page: str = start_page if start_page else "about:blank"
        self.viewport_size = viewport_size  # Applies only to the standard uri types
        self.downloads_folder = downloads_folder
        self.history: list[tuple[str, float]] = []
        self.page_title: Optional[str] = None
        self.viewport_current_page = 0
        self.viewport_pages: list[tuple[int, int]] = []
        self.set_address(self.start_page)
        self.serpapi_key = serpapi_key
        self.request_kwargs = request_kwargs
        self.request_kwargs["cookies"] = COOKIES
        self._mdconvert = MarkdownConverter()
        self._page_content: str = ""

        self._find_on_page_query: Union[str, None] = None
        self._find_on_page_last_result: Union[int, None] = None  # Location of the last result

    @property
    def address(self) -> str:
        """Return the address of the current page."""
        return self.history[-1][0]

    def set_address(self, uri_or_path: str, filter_year: Optional[int] = None) -> None:
        # TODO: Handle anchors
        self.history.append((uri_or_path, time.time()))

        # Handle special URIs
        if uri_or_path == "about:blank":
            self._set_page_content("")
        elif uri_or_path.startswith("google:"):
            self._serpapi_search(uri_or_path[len("google:") :].strip(), filter_year=filter_year)
        else:
            if (
                not uri_or_path.startswith("http:")
                and not uri_or_path.startswith("https:")
                and not uri_or_path.startswith("file:")
            ) and len(self.history) > 1:
                prior_address = self.history[-2][0]
                uri_or_path = urljoin(prior_address, uri_or_path)
                # Update the address with the fully-qualified path
                self.history[-1] = (uri_or_path, self.history[-1][1])
            self.fetch_page(uri_or_path)

        self.viewport_current_page = 0
        self.find_on_page_query = None
        self.find_on_page_viewport = None

    @property
    def viewport(self) -> str:
        """Return the content of the current viewport."""
        bounds = self.viewport_pages[self.viewport_current_page]
        return self.page_content[bounds[0] : bounds[1]]

    @property
    def page_content(self) -> str:
        """Return the full contents of the current page."""
        return self._page_content

    def _set_page_content(self, content: str) -> None:
        """Sets the text content of the current page."""
        self._page_content = content
        self._split_pages()
        if self.viewport_current_page >= len(self.viewport_pages):
            self.viewport_current_page = len(self.viewport_pages) - 1

    def page_down(self) -> None:
        self.viewport_current_page = min(self.viewport_current_page + 1, len(self.viewport_pages) - 1)

    def page_up(self) -> None:
        self.viewport_current_page = max(self.viewport_current_page - 1, 0)

    def find_on_page(self, query: str) -> Union[str, None]:
        """Searches for the query from the current viewport forward, looping back to the start if necessary."""
        # Did we get here via a previous find_on_page search with the same query?
        # If so, map to find_next
        if query == self._find_on_page_query and self.viewport_current_page == self._find_on_page_last_result:
            return self.find_next()

        # Ok it's a new search start from the current viewport
        self._find_on_page_query = query
        viewport_match = self._find_next_viewport(query, self.viewport_current_page)
        if viewport_match is None:
            self._find_on_page_last_result = None
            return None
        self.viewport_current_page = viewport_match
        self._find_on_page_last_result = viewport_match
        return self.viewport

    def find_next(self) -> Union[str, None]:
        """Scroll to the next viewport that matches the query"""
        if self._find_on_page_query is None:
            return None

        starting_viewport = self._find_on_page_last_result
        if starting_viewport is None:
            starting_viewport = 0
        else:
            starting_viewport += 1
            if starting_viewport >= len(self.viewport_pages):
                starting_viewport = 0

        viewport_match = self._find_next_viewport(self._find_on_page_query, starting_viewport)
        if viewport_match is None:
            self._find_on_page_last_result = None
            return None
        self.viewport_current_page = viewport_match
        self._find_on_page_last_result = viewport_match
        return self.viewport

    def _find_next_viewport(self, query: str, starting_viewport: int) -> Union[int, None]:
        """Search for matches between the starting viewport looping when reaching the end."""
        if query is None:
            return None

        # Normalize the query, and convert to a regular expression
        nquery = re.sub(r"\*", "__STAR__", query)
        nquery = " " + (" ".join(re.split(r"\W+", nquery))).strip() + " "
        nquery = nquery.replace(" __STAR__ ", "__STAR__ ")  # Merge isolated stars with prior word
        nquery = nquery.replace("__STAR__", ".*").lower()

        if nquery.strip() == "":
            return None

        idxs = []
        idxs.extend(range(starting_viewport, len(self.viewport_pages)))
        idxs.extend(range(starting_viewport))

        for i in idxs:
            bounds = self.viewport_pages[i]
            content = self.page_content[bounds[0] : bounds[1]]

            # TODO: Remove markdown links and images
            ncontent = " " + (" ".join(re.split(r"\W+", content))).strip().lower() + " "
            if re.search(nquery, ncontent):
                return i

        return None

    def visit_page(self, path_or_uri: str, filter_year: Optional[int] = None) -> str:
        """Update the address, visit the page, and return the content of the viewport."""
        self.set_address(path_or_uri, filter_year=filter_year)
        return self.viewport

    def _split_pages(self) -> None:
        # Do not split search results
        if self.address.startswith("google:"):
            self.viewport_pages = [(0, len(self._page_content))]
            return

        # Handle empty pages
        if len(self._page_content) == 0:
            self.viewport_pages = [(0, 0)]
            return

        # Break the viewport into pages
        self.viewport_pages = []
        start_idx = 0
        while start_idx < len(self._page_content):
            end_idx = min(start_idx + self.viewport_size, len(self._page_content))  # type: ignore[operator]
            # Adjust to end on a space
            while end_idx < len(self._page_content) and self._page_content[end_idx - 1] not in [" ", "\t", "\r", "\n"]:
                end_idx += 1
            self.viewport_pages.append((start_idx, end_idx))
            start_idx = end_idx

    def _serpapi_search(self, query: str, filter_year: Optional[int] = None) -> None:
        if self.serpapi_key is None:
            msg = "Missing SerpAPI key."
            raise ValueError(msg)

        params = {
            "engine": "google",
            "q": query,
            "api_key": self.serpapi_key,
        }
        if filter_year is not None:
            params["tbs"] = f"cdr:1,cd_min:01/01/{filter_year},cd_max:12/31/{filter_year}"

        search = serpapi.GoogleSearch(params)
        results = search.get_dict()
        self.page_title = f"{query} - Search"
        if "organic_results" not in results:
            msg = f"No results found for query: '{query}'. Use a less specific query."
            raise NoSearchResultsError(msg)
        if len(results["organic_results"]) == 0:
            year_filter_message = f" with filter year={filter_year}" if filter_year is not None else ""
            self._set_page_content(
                f"No results found for '{query}'{year_filter_message}. Try with a more general query, or remove the year filter."
            )
            return

        def _prev_visit(url):
            for i in range(len(self.history) - 1, -1, -1):
                if self.history[i][0] == url:
                    return f"You previously visited this page {round(time.time() - self.history[i][1])} seconds ago.\n"
            return ""

        web_snippets: list[str] = []
        idx = 0
        if "organic_results" in results:
            for page in results["organic_results"]:
                idx += 1
                date_published = ""
                if "date" in page:
                    date_published = "\nDate published: " + page["date"]

                source = ""
                if "source" in page:
                    source = "\nSource: " + page["source"]

                snippet = ""
                if "snippet" in page:
                    snippet = "\n" + page["snippet"]

                redacted_version = f"{idx}. [{page['title']}]({page['link']}){date_published}{source}\n{_prev_visit(page['link'])}{snippet}"

                redacted_version = redacted_version.replace("Your browser can't play this video.", "")
                web_snippets.append(redacted_version)

        content = f"A Google search for '{query}' found {len(web_snippets)} results:\n\n## Web Results\n" + "\n\n".join(
            web_snippets
        )

        self._set_page_content(content)

    def fetch_page(self, url: str) -> None:
        # Check if the URL is a local file
        parsed_url = urlparse(url)
        if parsed_url.scheme == "file":
            file_path = Path(parsed_url.path)
            try:
                # Try to convert the local file to markdown
                result = self._mdconvert.convert(str(file_path))
                markdown_content = result.text_content
            except (UnsupportedFormatError, FileConversionError):
                # If conversion fails, try reading as plain text
                try:
                    markdown_content = file_path.read_text(encoding="utf-8")
                except Exception as read_error:
                    msg = f"Error reading file {file_path} as plain text after conversion failure: {read_error!s}"
                    raise PageConversionError(msg) from read_error
            except Exception as e:
                msg = f"Error converting file {file_path}: {e!s}"
                raise PageConversionError(msg) from e
            else:
                self._set_page_content(markdown_content)
        else:
            # It's a web URL, fetch with requests
            try:
                response = requests.get(url, timeout=DEFAULT_REQUEST_TIMEOUT, **self.request_kwargs)
                response.raise_for_status()  # Raise an exception for bad status codes
            except requests.exceptions.RequestException as e:
                msg = f"Error fetching URL {url}: {e!s}"
                raise PageConversionError(msg) from e

            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type:
                html_content = response.text
                try:
                    # Convert HTML to Markdown
                    markdown_content = self._mdconvert.convert_html_to_markdown(html_content, base_url=url)
                    self.page_title = self._mdconvert.get_title(html_content) or url
                except Exception:
                    # Fallback to plain text if conversion fails
                    markdown_content = self._mdconvert.extract_text_from_html(html_content)
                    self.page_title = url  # Use URL as title if extraction fails
                    # Optionally, log the conversion error or handle it more gracefully
                    # logger.warning(f"HTML to Markdown conversion failed for {url}, falling back to plain text: {e}")
            elif "text/plain" in content_type:
                markdown_content = response.text
                self.page_title = url
            elif any(ftype in content_type for ftype in [".pdf", ".docx", ".pptx"]):
                # For these file types, suggest using DownloadTool
                file_extension = mimetypes.guess_extension(content_type) or ".bin"
                markdown_content = (
                    "This page points to a "
                    + file_extension
                    + " file.\nPlease use the download_file tool to download it and then inspect it locally."
                )
                self.page_title = url
            else:
                # For other content types, provide a message indicating it's likely a binary file
                markdown_content = (
                    "This page has content type "
                    + content_type
                    + ".\nIt is likely a binary file or a format not suitable for direct viewing in the browser.\nConsider using the download_file tool if you wish to inspect its contents."
                )
                self.page_title = url
            self._set_page_content(markdown_content)

    def state(self) -> tuple[str, str]:
        """Return a tuple of the current address and viewport content."""
        header = f"Address: {self.address}\n"
        if self.page_title is not None:
            header += f"Title: {self.page_title}\n"

        current_page = self.viewport_current_page
        total_pages = len(self.viewport_pages)

        address = self.address
        for i in range(len(self.history) - 2, -1, -1):  # Start from the second last
            if self.history[i][0] == address:
                header += f"You previously visited this page {round(time.time() - self.history[i][1])} seconds ago.\n"
                break

        header += f"Viewport position: Showing page {current_page + 1} of {total_pages}.\n"
        return (header, self.viewport)


class SearchInformationTool(Tool):
    name = "web_search"
    description = "Perform a web search query (think a google search) and returns the search results."
    inputs: ClassVar[dict] = {
        "query": {"type": "string", "description": "The web search query to perform."},
        "filter_year": {
            "type": "string",
            "description": "[Optional parameter]: filter the search results to only include pages from a specific year. For example, '2020' will only include pages from 2020. Make sure to use this parameter if you're trying to search for articles from a specific date!",
            "nullable": True,
        },
    }
    output_type = "string"

    def __init__(self, browser):
        super().__init__()
        self.browser = browser

    def forward(self, query: str, filter_year: Optional[int] = None) -> str:
        self.browser.visit_page(f"google: {query}", filter_year=filter_year)
        header, content = self.browser.state()
        return header.strip() + "\n=======================\n" + content


class VisitTool(Tool):
    name = "visit_page"
    description = "Visit a webpage at a given URL and return its text. Given a url to a YouTube video, this returns the transcript."
    inputs: ClassVar[dict] = {
        "url": {"type": "string", "description": "The relative or absolute url of the webpage to visit."}
    }
    output_type = "string"

    def __init__(self, browser):
        super().__init__()
        self.browser = browser

    def forward(self, url: str) -> str:
        self.browser.visit_page(url)
        header, content = self.browser.state()
        return header.strip() + "\n=======================\n" + content


class DownloadTool(Tool):
    name = "download_file"
    description = """
Download a file at a given URL. The file should be of this format: [".xlsx", ".pptx", ".wav", ".mp3", ".m4a", ".png", ".docx"]
After using this tool, for further inspection of this page you should return the download path to your manager via final_answer, and they will be able to inspect it.
DO NOT use this tool for .pdf or .txt or .htm files: for these types of files use visit_page with the file url instead."""
    inputs: ClassVar[dict] = {
        "url": {"type": "string", "description": "The relative or absolute url of the file to be downloaded."}
    }
    output_type = "string"

    def __init__(self, browser):
        super().__init__()
        self.browser = browser

    def forward(self, url: str) -> str:
        if "arxiv" in url:
            url = url.replace("abs", "pdf")
        response = requests.get(url, timeout=DEFAULT_REQUEST_TIMEOUT)
        content_type = response.headers.get("content-type", "")
        extension = mimetypes.guess_extension(content_type)
        if extension is None:
            extension = ".object"  # default extension

        downloads_dir = Path("./downloads")
        downloads_dir.mkdir(parents=True, exist_ok=True)
        new_path = downloads_dir / f"file{extension}"

        with new_path.open("wb") as f:
            f.write(response.content)

        if "pdf" in extension or "txt" in extension or "htm" in extension:
            msg = "Do not use this tool for pdf or txt or html files: use visit_page instead."
            raise FileDownloadError(msg)

        return f"File was downloaded and saved under path {new_path}."


class ArchiveSearchTool(Tool):
    name = "find_archived_url"
    description = "Given a url, searches the Wayback Machine and returns the archived version of the url that's closest in time to the desired date."
    inputs: ClassVar[dict] = {
        "url": {"type": "string", "description": "The url you need the archive for."},
        "date": {
            "type": "string",
            "description": "The date that you want to find the archive for. Give this date in the format 'YYYYMMDD', for instance '27 June 2008' is written as '20080627'.",
        },
    }
    output_type = "string"

    def __init__(self, browser):
        super().__init__()
        self.browser = browser

    def forward(self, url, date) -> str:
        no_timestamp_url = f"https://archive.org/wayback/available?url={url}"
        archive_url = no_timestamp_url + f"&timestamp={date}"
        response = requests.get(archive_url, timeout=DEFAULT_REQUEST_TIMEOUT).json()
        response_notimestamp = requests.get(no_timestamp_url, timeout=DEFAULT_REQUEST_TIMEOUT).json()
        if "archived_snapshots" in response and "closest" in response["archived_snapshots"]:
            closest = response["archived_snapshots"]["closest"]

        elif "archived_snapshots" in response_notimestamp and "closest" in response_notimestamp["archived_snapshots"]:
            closest = response_notimestamp["archived_snapshots"]["closest"]
        else:
            msg = f"Your {url=} was not archived on Wayback Machine, try a different url."
            raise WaybackError(msg)
        target_url = closest["url"]
        self.browser.visit_page(target_url)
        header, content = self.browser.state()
        return (
            f"Web archive for url {url}, snapshot taken at date {closest['timestamp'][:8]}:\n"
            + header.strip()
            + "\n=======================\n"
            + content
        )


class PageUpTool(Tool):
    name = "page_up"
    description = "Scroll the viewport UP one page-length in the current webpage and return the new viewport content."
    inputs: ClassVar[dict] = {}
    output_type = "string"

    def __init__(self, browser):
        super().__init__()
        self.browser = browser

    def forward(self) -> str:
        self.browser.page_up()
        header, content = self.browser.state()
        return header.strip() + "\n=======================\n" + content


class PageDownTool(Tool):
    name = "page_down"
    description = "Scroll the viewport DOWN one page-length in the current webpage and return the new viewport content."
    inputs: ClassVar[dict] = {}
    output_type = "string"

    def __init__(self, browser):
        super().__init__()
        self.browser = browser

    def forward(self) -> str:
        self.browser.page_down()
        header, content = self.browser.state()
        return header.strip() + "\n=======================\n" + content


class FinderTool(Tool):
    name = "find_on_page_ctrl_f"
    description = "Scroll the viewport to the first occurrence of the search string. This is equivalent to Ctrl+F."
    inputs: ClassVar[dict] = {
        "search_string": {
            "type": "string",
            "description": "The string to search for on the page. This search string supports wildcards like '*'",
        }
    }
    output_type = "string"

    def __init__(self, browser):
        super().__init__()
        self.browser = browser

    def forward(self, search_string: str) -> str:
        find_result = self.browser.find_on_page(search_string)
        header, content = self.browser.state()

        if find_result is None:
            return (
                header.strip()
                + f"\n=======================\nThe search string '{search_string}' was not found on this page."
            )
        return header.strip() + "\n=======================\n" + content


class FindNextTool(Tool):
    name = "find_next"
    description = "Scroll the viewport to next occurrence of the search string. This is equivalent to finding the next match in a Ctrl+F search."
    inputs: ClassVar[dict] = {}
    output_type = "string"

    def __init__(self, browser):
        super().__init__()
        self.browser = browser

    def forward(self) -> str:
        find_result = self.browser.find_next()
        header, content = self.browser.state()

        if find_result is None:
            return header.strip() + "\n=======================\nThe search string was not found on this page."
        return header.strip() + "\n=======================\n" + content
