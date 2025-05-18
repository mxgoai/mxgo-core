class TOCGenerator:
    """Generate Table of Contents and structured research plans."""

    def __init__(self, model=None):
        """
        Initialize the TOC Generator.

        Args:
            model: LLM model to use for TOC generation (if None, will use the agent's model)

        """
        self.model = model

    def generate_toc_prompt(self, topic: str, context: str = "") -> str:
        """
        Generate a prompt for TOC generation.

        Args:
            topic: Research topic
            context: Additional context or requirements

        Returns:
            Prompt for generating a TOC

        """
        return f"""Given the research topic: "{topic}"
{context}

Please generate a comprehensive Table of Contents with 5-7 main sections and relevant subsections.
The TOC should cover all important aspects of the topic and follow a logical structure.

Format the TOC as follows:
# Table of Contents
1. Executive Summary
2. [Main Section 1]
   2.1. [Subsection 1]
   2.2. [Subsection 2]
3. [Main Section 2]
   ...
n. Conclusion
n+1. References

IMPORTANT: The sections should be specific to the topic, not generic placeholder names.
Focus on creating a structure that would facilitate a comprehensive, well-researched report.
"""

    def generate_section_research_prompt(self, section: str, context: str) -> str:
        """
        Generate a prompt for researching a specific section.

        Args:
            section: Section title
            context: Research context

        Returns:
            Prompt for section-specific research

        """
        return f"""I need thorough research for the following section of my report:

SECTION: {section}

CONTEXT: {context}

Please conduct comprehensive research on this specific section topic. Focus on:
1. Key facts, figures, and data relevant to this section
2. Latest developments and trends
3. Expert opinions and analysis
4. Relevant case studies or examples
5. Authoritative sources that can be cited

Provide a detailed response that's specifically focused on this section topic.
Include specific information that would be valuable for this section of the report.
"""

    def structure_report_from_toc(self, toc: str, research_results: dict[str, str]) -> str:
        """
        Structure a complete report based on TOC and section research results.

        Args:
            toc: Table of contents string
            research_results: Dictionary mapping section titles to research content

        Returns:
            Structured report

        """
        # Parse the TOC to identify sections
        sections = self._parse_toc(toc)

        # Build the report
        report = ["# Research Report\n"]
        report.append(toc)
        report.append("\n---\n")

        # Add executive summary
        report.append("# Executive Summary\n")
        summary = research_results.get("Executive Summary", "")
        report.append(summary)
        report.append("\n---\n")

        # Add each section
        for section in sections:
            if section in {"Executive Summary", "References"}:
                continue

            report.append(f"# {section}\n")
            content = research_results.get(section, "")
            report.append(content)
            report.append("\n---\n")

        # Add references
        report.append("# References\n")
        references = research_results.get("References", "")
        report.append(references)

        return "\n".join(report)

    def _parse_toc(self, toc: str) -> list[str]:
        """
        Parse a TOC string to extract section titles.

        Args:
            toc: Table of contents string

        Returns:
            List of section titles

        """
        import re

        sections = []

        # Extract section titles (lines that start with a number followed by a dot)
        lines = toc.split("\n")
        for line in lines:
            match = re.match(r"^\s*(\d+)\.?\s+([^\.]+)$", line)
            if match:
                sections.append(match.group(2).strip())

        return sections
