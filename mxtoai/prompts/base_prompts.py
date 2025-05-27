"""
Base prompts and common guidelines for email processing.
"""

MARKDOWN_STYLE_GUIDE = """
MARKDOWN FORMATTING REQUIREMENTS:
- **bold** for emphasis
- _italics_ for quotes
- ### for section headers (if needed)
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
- ALWAYS Indent each nested level with two spaces
- DO NOT add any signature - it will be added automatically
"""

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
- Deep research is NOT allowed for this handle
- Only use basic tools and provided information
- Focus on addressing the direct content of the email
""",
}
