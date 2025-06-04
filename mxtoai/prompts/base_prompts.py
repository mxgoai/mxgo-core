"""
Base prompts and common guidelines for email processing.
"""

MARKDOWN_STYLE_GUIDE = """
MARKDOWN FORMATTING REQUIREMENTS:
- **bold** for emphasis
- _italics_ for quotes
- Strictly use `###` for section headers
- Proper bullet points and numbered lists
- Clear paragraph spacing
"""

# Common response guidelines
RESPONSE_GUIDELINES = """
GENERAL RESPONSE REQUIREMENTS:
- Write in proper markdown format
- Include only relevant information
- Maintain appropriate tone and style
- Use proper spacing and formatting
- Try to maintain visual hierarchy of the response using section headers and lists
- NEVER add numbers to section headers
- DO NOT add any signature - it will be added automatically
- If web search tools were used, create a 'References' section at the end of your response. List the titles and URLs of the web pages used, formatted as markdown links (e.g., `1. [Page Title](URL)`).
"""

# Formatting requirements for HTML conversion
# Not needed anymore, still keeping it for a while just in case
# LIST_FORMATTING_REQUIREMENTS = """
# NESTED LIST OUTPUT FORMAT GUIDELINES (for Markdown to HTML conversion):

# 1. Always begin with a **numbered list** (use `1.`).
# 2. **Alternate between numbered and bullet lists** at each level of nesting:
#    - Level 1: `1.`, `2.`, `3.` (numbered)
#      1. Level 2: `-` (bullet)
#        - Level 3: `1.`, `2.`, `3.` (numbered)
#           1. Level 4: `-` (bullet)
#             - And so on...
# 3. Use **blank lines** between paragraphs and between different list levels.

# Example:

# 1. Main point
#   - Sub-point
#     1. Sub-sub-point
#       - Sub-sub-sub-point

# All list sections **must follow this structure exactly**. Improper nesting or use of list styles will break the HTML conversion.
# """

# Research guidelines
RESEARCH_GUIDELINES = {
    "mandatory": """
RESEARCH REQUIREMENTS:
- You MUST use the deep_research tool to gather additional information
- Ensure comprehensive research before responding
- Include citations and sources in your response
- Synthesize findings with the email content
""",
    "optional": """
RESEARCH GUIDELINES:
- Only use basic tools and provided information
- Focus on addressing the direct content of the email
""",
}
