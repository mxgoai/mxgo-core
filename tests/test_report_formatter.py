import re

import pytest

from mxtoai.scripts.report_formatter import ReportFormatter


class TestReportFormatterMarkdownFixes:
    """Test all the markdown formatting fixes implemented in ReportFormatter."""

    @pytest.fixture
    def formatter(self):
        """Create a ReportFormatter instance for testing."""
        return ReportFormatter()

    def test_header_separation_from_lists(self, formatter):
        """Test that headers are properly separated from preceding lists."""
        markdown_content = """- Item 1
- Item 2
### Header Should Be Separated
Content after header"""

        fixed_markdown = formatter._fix_ai_markdown(markdown_content)

        # Should have a blank line before the header
        assert "\n\n### Header Should Be Separated" in fixed_markdown

        # Test HTML output - header should not be inside a list
        html_output = formatter._to_html(fixed_markdown)
        assert "<h3" in html_output
        # Header should not be nested inside <ul> tags
        assert not re.search(r"<ul>.*<h3.*</ul>", html_output, re.DOTALL)

    def test_bolded_links_in_lists(self, formatter):
        """Test that bolded links in list items render correctly."""
        markdown_content = """### Calendar Links
- **[Google Calendar](https://calendar.google.com)**
- **[Outlook Calendar](https://outlook.live.com)**"""

        fixed_markdown = formatter._fix_ai_markdown(markdown_content)

        # Should convert **[text](url)** to [**text**](url)
        assert "- [**Google Calendar**](https://calendar.google.com)" in fixed_markdown
        assert "- [**Outlook Calendar**](https://outlook.live.com)" in fixed_markdown

        # Test HTML output
        html_output = formatter._to_html(fixed_markdown)
        # Should have proper bold links in either order (both are valid)
        google_link_ok = (
            '<strong><a href="https://calendar.google.com">Google Calendar</a></strong>' in html_output
            or '<a href="https://calendar.google.com"><strong>Google Calendar</strong></a>' in html_output
        )
        outlook_link_ok = (
            '<strong><a href="https://outlook.live.com">Outlook Calendar</a></strong>' in html_output
            or '<a href="https://outlook.live.com"><strong>Outlook Calendar</strong></a>' in html_output
        )

        assert google_link_ok, "Google Calendar link should be bold"
        assert outlook_link_ok, "Outlook Calendar link should be bold"
        assert "**<a href" not in html_output  # Should not have malformed bold tags

    def test_letter_based_list_conversion(self, formatter):
        """Test that letter-based lists (a., b., c.) are converted to numbers."""
        markdown_content = """Steps to follow:
a. First step
b. Second step
c. Third step"""

        fixed_markdown = formatter._fix_ai_markdown(markdown_content)

        # Should convert a., b., c. to 1., 2., 3.
        assert "1. First step" in fixed_markdown
        assert "2. Second step" in fixed_markdown
        assert "3. Third step" in fixed_markdown
        assert "a. First step" not in fixed_markdown

    def test_mixed_list_formatting(self, formatter):
        """Test that mixed list formatting (- 1. Item) is cleaned up."""
        markdown_content = """- 1. First item
- 2. Second item
* 3. Third item"""

        fixed_markdown = formatter._fix_ai_markdown(markdown_content)

        # Should remove the bullet markers before numbered items
        assert "1. First item" in fixed_markdown
        assert "2. Second item" in fixed_markdown
        assert "3. Third item" in fixed_markdown
        assert "- 1." not in fixed_markdown
        assert "* 3." not in fixed_markdown

    def test_missing_spaces_after_list_markers(self, formatter):
        """Test that missing spaces after list markers are added."""
        markdown_content = """-Item without space
*Another item
1.Short item"""

        fixed_markdown = formatter._fix_ai_markdown(markdown_content)

        # Should add spaces after list markers
        assert "- Item without space" in fixed_markdown
        assert "* Another item" in fixed_markdown
        assert "1. Short item" in fixed_markdown

    def test_section_header_detection(self, formatter):
        """Test that numbered lines that are actually section headers are converted properly."""
        markdown_content = """1. Executive Summary and Key Findings
This is the summary content.

2. Detailed Analysis of Market Trends
This is the analysis content."""

        fixed_markdown = formatter._fix_ai_markdown(markdown_content)

        # Should convert section headers to proper markdown headers
        assert "## Executive Summary and Key Findings" in fixed_markdown
        assert "## Detailed Analysis of Market Trends" in fixed_markdown
        assert "1. Executive Summary" not in fixed_markdown

    def test_nested_lists(self, formatter):
        """Test that nested lists render correctly."""
        markdown_content = """- Main item
  - Sub item 1
  - Sub item 2
- Another main item"""

        fixed_markdown = formatter._fix_ai_markdown(markdown_content)
        html_output = formatter._to_html(fixed_markdown)

        # Should have nested <ul> structure
        assert "<ul>" in html_output
        assert re.search(r"<ul>.*<ul>.*</ul>.*</ul>", html_output, re.DOTALL)

    def test_complex_formatting_scenario(self, formatter):
        """Test a complex scenario combining multiple formatting issues."""
        markdown_content = """### Event Details
- **Title:** Important Meeting
- **Date:** Tomorrow
- **Participants:**
  - John Doe
  - Jane Smith
### Calendar Links
- **[Google Calendar](https://calendar.google.com)**
- **[Outlook Calendar](https://outlook.live.com)**
1. Acknowledgment of Meeting Details
This confirms all the details above.
a. First action item
b. Second action item"""

        fixed_markdown = formatter._fix_ai_markdown(markdown_content)
        html_output = formatter._to_html(fixed_markdown)

        # Headers should be properly separated
        assert "<h3" in html_output
        # Bold links should render correctly in either order
        google_link_ok = (
            '<strong><a href="https://calendar.google.com">Google Calendar</a></strong>' in html_output
            or '<a href="https://calendar.google.com"><strong>Google Calendar</strong></a>' in html_output
        )
        assert google_link_ok, "Google Calendar link should be bold"

        # Section headers should be converted
        assert "Acknowledgment of Meeting Details" in html_output
        # Letter lists should be converted
        assert "1. First action item" in fixed_markdown
        assert "2. Second action item" in fixed_markdown

    def test_preserve_normal_bold_text(self, formatter):
        """Test that normal bold text (not in links) is preserved."""
        markdown_content = """- **Important:** This is bold text
- **Note:** Another bold item"""

        fixed_markdown = formatter._fix_ai_markdown(markdown_content)
        html_output = formatter._to_html(fixed_markdown)

        # Should preserve normal bold formatting
        assert "**Important:**" in fixed_markdown
        assert "**Note:**" in fixed_markdown
        assert "<strong>Important:</strong>" in html_output
        assert "<strong>Note:</strong>" in html_output

    def test_edge_case_empty_links(self, formatter):
        """Test edge cases with empty or malformed links."""
        markdown_content = """- **[]()**
- Normal item
- **[Text only**"""

        # Should not crash and should handle gracefully
        fixed_markdown = formatter._fix_ai_markdown(markdown_content)
        html_output = formatter._to_html(fixed_markdown)

        assert "Normal item" in html_output  # Should still process other items

    def test_multiple_headers_in_sequence(self, formatter):
        """Test multiple headers appearing without content between them."""
        markdown_content = """- Last list item
### First Header
### Second Header
### Third Header
Content here."""

        fixed_markdown = formatter._fix_ai_markdown(markdown_content)

        # Should add blank line before first header only (others already separated)
        lines = fixed_markdown.split("\n")
        first_header_index = next(i for i, line in enumerate(lines) if line.strip() == "### First Header")
        assert lines[first_header_index - 1].strip() == ""  # Blank line before first header

    def test_indented_lists(self, formatter):
        """Test that indented lists maintain their structure."""
        markdown_content = """  - Indented item 1
  - Indented item 2
    - Double indented
- Normal item"""

        fixed_markdown = formatter._fix_ai_markdown(markdown_content)
        html_output = formatter._to_html(fixed_markdown)

        # Should maintain list structure
        assert "<li>Indented item 1</li>" in html_output
        assert "<li>Normal item</li>" in html_output

    def test_format_report_integration(self, formatter):
        """Test the full format_report method with our fixes."""
        content = """### Test Report
- **Summary:** This is a test
- **[Link](http://example.com)**
1. Executive Summary and Key Points
Content here.
a. Action item
b. Another action"""

        # Test HTML format
        html_result = formatter.format_report(content, format_type="html")

        assert "<h3" in html_result
        assert "<strong>Summary:</strong>" in html_result
        # Bold links should render correctly in either order
        link_ok = (
            '<strong><a href="http://example.com">Link</a></strong>' in html_result
            or '<a href="http://example.com"><strong>Link</strong></a>' in html_result
        )
        assert link_ok, "Link should be bold"
        assert "Executive Summary and Key Points" in html_result

        # Test markdown format (should include fixes)
        markdown_result = formatter.format_report(content, format_type="markdown")

        # This should be converted to a header because it contains "Executive Summary"
        assert "## Executive Summary and Key Points" in markdown_result
        assert "1. Action item" in markdown_result
        assert "2. Another action" in markdown_result

    def test_signature_preservation(self, formatter):
        """Test that the signature block is properly handled."""
        content = "Test content"

        result_with_signature = formatter.format_report(content, include_signature=True, format_type="html")
        result_without_signature = formatter.format_report(content, include_signature=False, format_type="html")

        assert "MXtoAI Assistant" in result_with_signature
        assert "MXtoAI Assistant" not in result_without_signature

    def test_real_world_calendar_example(self, formatter):
        """Test with the exact example from the user's original issue."""
        markdown_content = """### Event Details
- **Title:** 30-minute call: Enterprise use cases of MXtoAI with Founders
- **Date & Time:** June 12, 2025, 10:27 AM PDT (UTC-7) / 10:57 PM IST (UTC+5:30)
- **Duration:** 30 minutes
- **Location:** Virtual call
- **Description:** Discussion on enterprise use cases of MXtoAI with the
founders of the company.
- **Participants:**
  - Anisha (Organizer): 28gautam97@gmail.com
  - MXtoAI Founders: founders@mxtoai.com
### Calendar Links
- **[Google Calendar](https://www.google.com/calendar/render?action=TEMPLATE&text=30-minute+call)**
- **[Outlook Calendar](https://outlook.live.com/calendar/0/deeplink/compose)**
### ICS File Notice
- An .ics file is generated and can be attached to an email for calendar
scheduling.
### Notes
- The meeting is approved by Anisha and details have been confirmed."""

        fixed_markdown = formatter._fix_ai_markdown(markdown_content)
        html_output = formatter._to_html(fixed_markdown)

        # Should have proper structure with headers separated from lists
        assert "<h3" in html_output
        # Should have proper list structure
        assert "<ul>" in html_output
        assert "<li>" in html_output
        # Bold links should render correctly in either order
        google_link_ok = (
            '<strong><a href="https://www.google.com/calendar/render?action=TEMPLATE&text=30-minute+call">Google Calendar</a></strong>'
            in html_output
            or '<a href="https://www.google.com/calendar/render?action=TEMPLATE&text=30-minute+call"><strong>Google Calendar</strong></a>'
            in html_output
        )
        outlook_link_ok = (
            '<strong><a href="https://outlook.live.com/calendar/0/deeplink/compose">Outlook Calendar</a></strong>'
            in html_output
            or '<a href="https://outlook.live.com/calendar/0/deeplink/compose"><strong>Outlook Calendar</strong></a>'
            in html_output
        )

        assert google_link_ok, "Google Calendar link should be bold"
        assert outlook_link_ok, "Outlook Calendar link should be bold"
        # Should not have malformed bold tags
        assert "**<a href" not in html_output
