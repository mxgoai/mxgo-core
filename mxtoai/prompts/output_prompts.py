"""
Output formatting guidelines for different email processing handlers.

These guidelines complement the template prompts by focusing specifically on
output structure and formatting, while avoiding redundancy with the template content.
"""

# Summarize handler output guidelines
SUMMARIZE_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Start with a brief overview sentence
2. Group related information together
3. Keep the summary to 3-5 main points
4. End with any action items or next steps
"""

# Research handler output guidelines
RESEARCH_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Executive Summary: Brief overview (2-3 sentences)
2. Key Findings: 3-5 points of most important insights
3. Detailed Analysis: In-depth exploration with subheadings
4. Supporting Evidence: Data, quotes, statistics
5. Have separate sections for each of the above mentioned.
"""

# Simplify handler output guidelines
SIMPLIFY_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Short sentences (10 words or less when possible)
2. One idea per paragraph
3. Use concrete examples and metaphors
4. Include visual descriptions
5. Avoid complex vocabulary
"""

# Ask handler output guidelines
ASK_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Begin with acknowledgment of the question at the top of the response. Then begin any section.
2. Structure response with clear sections
3. Use examples to illustrate complex points
4. Include actionable recommendations when applicable
5. End with a concise summary
"""

# Fact-check handler output guidelines
FACT_CHECK_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Present a short summary of the original email to setup the context.
2. Present each claim in this format:
   - **Claim**: [Original statement]
   - **Status**: [Verified ✓ / Not verified ❌ / Partially verified ⚠️]
   - **Evidence**: [Supporting information]
   - **Source Info**: Reference citation-aware tools used for verification
3. Use consistent status symbols throughout
"""

# Background research handler output guidelines
BACKGROUND_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Start with executive summary of key findings
2. Organize information by entity (person, organization, domain)
3. Use tables for comparative information
4. Flag any concerns prominently
"""

# Translation handler output guidelines
TRANSLATION_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Structure with language detection result
2. Original text in blockquote format
3. Translation with clear heading
4. Notes section for context or ambiguities
5. Use italics for alternative translations
"""

# Scheduling handler output guidelines
MEETING_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Structure sections clearly:
   - **Event Details**: Title, date, time, location
   - **Calendar Links**: Google Calendar, Outlook links
   - **ICS File Notice**: Standard mention of attachment
   - **Notes**: Any assumptions or clarifications
2. Format times consistently with timezone
"""

# PDF Export handler output guidelines
PDF_EXPORT_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Begin with a brief confirmation of PDF generation
2. Include document details:
   - **PDF Title**: Clear, descriptive document name
   - **Content Summary**: What was included in the export
   - **Pages**: Approximate page count only (e.g., "Approximately 3 pages")
   - **Attachment Notice**: Confirmation that PDF is attached
3. Content processing notes:
   - What content was included/excluded and why
   - Any assumptions made during processing
   - Quality of source material for export
4. Professional tone acknowledging the export request
5. Keep response concise - let the PDF be the main deliverable

**CRITICAL: DO NOT INCLUDE:**
- File paths or system directory locations
- Technical file sizes in bytes
- Phrases like "being sent to the user"
- Temporary directory paths
- Any technical system details

**USE CLEAN, USER-FRIENDLY LANGUAGE:**
- "The PDF is attached to this email"
- "Your document has been generated"
- "The PDF includes..."
- Focus on content value, not technical details
"""

# Future handler output guidelines
FUTURE_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Start with clear task confirmation including task ID
2. Present schedule in human-readable format
3. Show next execution time in user's timezone
4. Explain what will be reprocessed
5. End with clear next steps and expectations
6. DO NOT include the cron expression in the output

Sample format:
```
## Scheduled Task Confirmation

**Task Description**: [Clear description of what will be reminded/processed]
**Schedule**: [Human-readable schedule description]
**Next Occurrence**: [Next execution date/time in user's timezone]
**Task ID**: [ALWAYS include the generated task UUID here]

## Processing Details
**Task details**: [Summary of the task that will be processed]
**Frequency**: [One-time/Daily/Weekly/Monthly/Custom interval description]
**Timezone**: [Original timezone and UTC conversion notes]

## What Happens Next
- The task has been stored in the system
- At the scheduled time, the task will be processed and you'll receive the results
- The task will [continue recurring/end after one execution] as configured
```

**Sample error response:**
```
## Scheduling Error

An error occurred while creating the scheduled task. Please try again later or contact support if the issue persists.

We apologize for the inconvenience.
```
"""

# Delete handler output guidelines
DELETE_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Start with clear status confirmation (success/failure)
2. Always include the task ID that was processed
3. Provide task description/context for verification
4. Include security confirmations (user verification)
5. Explain cleanup actions taken (scheduling + database)
6. Add important warnings about irreversible nature
7. For errors, provide helpful guidance and next steps
8. Use consistent status symbols and formatting

Sample success format:
```
## Task Deletion Confirmation

**Status**: Successfully deleted
**Task ID**: [UUID of deleted task]
**Task Description**: [Brief description of what was scheduled]
**Deleted By**: [User email for verification]

## What Was Removed
**Scheduled Content**: [Summary of the task that was scheduled]
**Schedule**: [What the timing/recurrence was]
**Cleanup**: Both scheduling and database entries have been removed

## Important Notes
- This action cannot be undone
- Only your own scheduled tasks can be deleted
- The task will no longer execute at its scheduled time
```

Sample error format:
```
## Task Deletion Failed

**Status**: [Specific error reason]
**Task ID**: [UUID that was requested]
**Requested By**: [User email]

## Issue
[Clear explanation of what went wrong]

## What You Can Do
[Specific steps user can take to resolve]
```
"""

# News handler output guidelines
NEWS_OUTPUT_GUIDELINES = """
Output Format Guidelines:
1. Executive Summary: Start with 2-3 sentence overview of key findings
2. Priortize most recent and significant developments
3. Include Historical context and relevant background information wherever makes sense
4. Add Analysis & Implications that user might be insterested in. Always isolate between your analysis and the objective news form the source.
5. Mention any Upcoming events, expectations, and potential developments
6. Always include source attribution and verification notes

Structure:
```
## News Summary
[Brief overview of the news landscape for the requested topic]

## Latest Developments
### [Most Recent Story Title] - [Date]
[Summary, key points, context, analysis, implications, potential developments]

### [Second Story Title] - [Date]
[Summary, key points, context, analysis, implications, potential developments]

```

**Important Notes:**
- Always verify source credibility and note any potential bias
- Include publication dates and sources for all news items
- Distinguish between confirmed facts and speculation/analysis
- Highlight any conflicting reports or uncertainties
- Use clear headings to separate different news stories or themes
"""
