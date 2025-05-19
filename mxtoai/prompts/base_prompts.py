"""Base prompts and common guidelines for email processing."""

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
- DO NOT add any signature - it will be added automatically
"""

# Formatting requirements for HTML conversion
LIST_FORMATTING_REQUIREMENTS = """
NESTED LIST OUTPUT FORMAT GUIDELINES (for Markdown to HTML conversion):

1. Always begin with a **numbered list** (use `1.`).
2. **Alternate between numbered and bullet lists** at each level of nesting:
   - Level 1: `1.`, `2.`, `3.` (numbered)
     1. Level 2: `-` (bullet)
       - Level 3: `1.`, `2.`, `3.` (numbered)
          1. Level 4: `-` (bullet)
            - And so on...
3. **Indent each nested level with two spaces.**
4. Use **blank lines** between paragraphs and between different list levels.

Example:

1. Main point
  - Sub-point
    1. Sub-sub-point
      - Sub-sub-sub-point

All list sections **must follow this structure exactly**. Improper nesting or use of list styles will break the HTML conversion.
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

def create_email_context(email_request, attachment_details=None):
    """Create the basic email context section."""
    return f"""Email Content:
Subject: {email_request.subject}
From: {email_request.from_email}
Email Date: {email_request.date}
Recipients: {', '.join(email_request.recipients) if email_request.recipients else 'N/A'}
CC: {email_request.cc or 'N/A'}
BCC: {email_request.bcc or 'N/A'}
Body: {email_request.textContent or email_request.htmlContent or ''}

{f'''Available Attachments:
{chr(10).join(attachment_details)}''' if attachment_details else 'No attachments provided.'}"""

def create_attachment_processing_task(attachment_details):
    """Create the attachment processing section."""
    if not attachment_details:
        return ""
    return f"""Process these attachments:
{chr(10).join(attachment_details)}"""

def create_task_template(
    handle: str,
    email_context: str,
    handle_specific_template: str = "",
    attachment_task: str = "",
    deep_research_mandatory: bool = False,
    output_template: str = "",
) -> str:
    """
    Create a complete task template with all necessary sections.

    Args:
        handle: The email handle being processed
        email_context: The email context section
        handle_specific_template: Optional handle-specific instructions
        research_instructions: Optional research-specific instructions
        attachment_task: Optional attachment processing instructions
        deep_research_mandatory: Whether deep research is required for this handle

    """
    sections = [
        f"Process this email according to the '{handle}' instruction type.\n",
        email_context
    ]

    # Add research guidelines based on handle requirements
    sections.append(
        RESEARCH_GUIDELINES["mandatory"] if deep_research_mandatory
        else RESEARCH_GUIDELINES["optional"]
    )

    if attachment_task:
        sections.append(attachment_task)

    # Add handle-specific template if provided
    if handle_specific_template:
        sections.append(handle_specific_template)

    # Add output template if provided
    if output_template:
        sections.append(output_template)

    # Add common processing steps
    sections.extend([
        RESPONSE_GUIDELINES,
        MARKDOWN_STYLE_GUIDE,
        LIST_FORMATTING_REQUIREMENTS
    ])

    return "\n".join(sections)
