"""Base prompts and templates for email processing."""

FORMATTING_REQUIREMENTS = """
CRITICAL FORMATTING REQUIREMENTS:
1. ALWAYS use proper markdown syntax - this will be converted to HTML
2. Ensure proper spacing between paragraphs (use blank lines)
3. Use appropriate list formatting (- for bullets, 1. for numbered)
4. Format emphasis correctly (**bold**, _italic_)
5. Use proper heading levels (###) where specified
6. Keep the response focused and relevant
7. DO NOT add any signature - it will be added automatically"""

MARKDOWN_STYLE_GUIDE = """
Use proper markdown formatting:
- **bold** for emphasis
- _italics_ for quotes
- ### for section headers (if needed)
- Proper bullet points and numbered lists
- Clear paragraph spacing"""

RESPONSE_GUIDELINES = """
Generate Response:
- Write in proper markdown format
- Include only relevant information
- Maintain appropriate tone and style
- Use proper spacing and formatting
- DO NOT add any signature - it will be added automatically"""

RESEARCH_GUIDELINES = {
    "mandatory": """
RESEARCH REQUIREMENTS:
- You MUST use the deep_research tool to gather additional information
- Ensure comprehensive research before responding
- Include citations and sources in your response
- Synthesize findings with the email content""",
    
    "optional": """
RESEARCH GUIDELINES:
- Deep research is NOT allowed for this handle
- Only use basic tools and provided information
- Focus on addressing the direct content of the email""",
}

def create_email_context(email_request, attachment_details=None):
    """Create the basic email context section."""
    return f"""Email Content:
Subject: {email_request.subject}
From: {email_request.from_email}
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
    research_instructions: str = "",
    attachment_task: str = "",
    deep_research_mandatory: bool = False,
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

    if handle_specific_template:
        sections.append(handle_specific_template)

    if research_instructions and deep_research_mandatory:
        sections.append(research_instructions)

    if not handle_specific_template:
        # Add default processing steps if no specific template
        sections.extend([
            MARKDOWN_STYLE_GUIDE,
            RESPONSE_GUIDELINES
        ])

    # Always add formatting requirements at the end
    sections.append(FORMATTING_REQUIREMENTS)

    return "\n\n".join(sections) 