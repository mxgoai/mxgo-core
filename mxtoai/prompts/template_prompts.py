"""
Template prompts for different email processing handlers.
"""

# Summarize email handler template
SUMMARIZE_TEMPLATE = """
Systematically analyze and summarize content from all available sources with clear structure and action focus.

# Summarization Process

## STEP 1: Content Analysis
- **Process ALL sources**: Email content, attachments, embedded links, external references(if asked)
- **Assess complexity**: Determine appropriate detail level (concise/detailed/executive summary)
- **Identify priorities**: Key messages, action items, deadlines, stakeholder impact

## STEP 2: Structured Summary Format
```
## Executive Summary
[2-3 sentences capturing core message and significance]

## Main Points
[Organized breakdown of key information from all sources]

## Action Items
- [Specific actions required with deadlines]
- [Responsible parties if mentioned]

## Additional Context
[Important background, implications, supporting details]
```

## STEP 3: Quality Standards
- **Process all content sources** before summarizing
- **Highlight action items** clearly
- **Note any inaccessible content** transparently
- **Match detail level** to content complexity
- **Maintain context** while being concise

**Example Output:**
```
## Executive Summary
Q3 sales report shows 12% revenue growth with West region leading performance, requiring strategy review meeting.

## Key Information
- **From**: Sales Director Sarah Chen
- **Topic**: Q3 2024 Sales Performance Review
- **Urgency**: Standard quarterly review
- **Stakeholders**: Management team, regional leads

## Main Points
**Sales Performance (from Excel attachment):**
- Total revenue: $4.2M (12% increase from Q2)
- West region: 23% growth, exceeding targets
- Product line A: 18% growth, strongest performer
- Customer acquisition: 156 new accounts

## Action Items
- Review West region strategies for replication
- Address East region performance decline
- Quarterly review meeting: Next Friday

## Additional Context
Strong Q3 performance driven by West region success and Product A growth. East region needs attention.
```

**Critical Requirements:**
- Process ALL available content sources (email, attachments, links)
- Structure information for easy scanning
- Clearly identify action items and deadlines
- Note any content processing limitations
- Adapt detail level to content complexity
"""

# Research handler template
RESEARCH_TEMPLATE = """
Conduct comprehensive research and provide a detailed analysis with proper sections and citations.
For this task, you must use deep research tool at least once with appropriate query.

Response Requirements:
1. Structure with clear sections:
   - ### Executive Summary
   - ### Key Findings
   - ### Detailed Analysis
   - ### Supporting Evidence
   - ### References
2. Include proper citations [1], [2], etc. if the deep_research tool provides them. For web_search results, extract the title and URL for each source and list them under the 'References' section using markdown link format (e.g., 1. [Page Title](URL)).
3. Format tables using markdown table syntax
4. Use proper paragraph spacing

Content Guidelines:
1. Maintain academic tone
2. Include specific data points
3. Support claims with evidence
4. Provide comprehensive analysis
5. Always give a disclaimer that sometimes links may be outdated or incorrect depending on age of the source
"""

# Simplify handler template
SIMPLIFY_TEMPLATE = """
Transform complex content into clear, accessible explanations using simple language and relatable examples.

# Simplification Process

## STEP 1: Complexity Assessment
- **Identify complexity sources**: Technical jargon, abstract concepts, complex processes, dense information
- **Determine target level**: General public understanding (assume no specialized knowledge)
- **Preserve core truth**: Maintain essential accuracy while removing complexity

## STEP 2: Simplification Strategy
**Language Techniques:**
- Replace technical terms with everyday language(if replacement is not possible add dictionary at the end)
- Break complex sentences into shorter, clearer ones
- Use active voice and concrete examples
- Add helpful analogies from familiar experiences

**Structure Format:**
```
## The Simple Version
[One clear sentence explaining the core concept]

## What This Means
[2-3 sentences expanding on the main idea]

## Here's How It Works
[Step-by-step breakdown in simple terms]

## Think of It Like This
[Relatable analogy or real-world example]

## Why This Matters
[Practical significance in everyday terms]

## The Bottom Line
[Key takeaway anyone can remember]
```

## STEP 3: Quality Check
- Could a 12-year-old understand the main point?
- Are technical terms explained or replaced?
- Do analogies help rather than confuse?
- Is the essential message preserved?

**Requirements:**
- Use simple, everyday language
- Include helpful analogies and examples
- Preserve accuracy while removing jargon
- Make content accessible to general audiences
- Maintain respectful tone (not condescending)
"""

# Ask handler template
ASK_TEMPLATE = """
Execute custom tasks and workflows systematically with research, analysis, and professional presentation.

# General Task Execution Process

## STEP 1: Task Analysis & Planning
- **Understand the request**: Break down what the user wants accomplished
- **Identify components**: Research needs, data gathering, analysis, formatting requirements
- **Determine approach**: What tools and steps are needed to complete this task
- **Set quality standards**: How should the final output be structured and presented

## STEP 2: Systematic Execution
**Research & Data Gathering:**
- Use web search for current information and trends
- Visit relevant websites and sources
- Process any attachments or provided materials(if needed)
- Gather comprehensive data before analysis

**Analysis & Curation:**
- Filter and prioritize information based on relevance and quality
- Identify key insights, patterns, or important details
- Apply criteria for selection (trending, popularity, importance)
- Add context and explanatory information

**Content Creation:**
- Structure information logically and professionally
- Create engaging and informative content
- Include proper citations and links
- Format for easy reading and comprehension

## STEP 3: Professional Presentation
**Standard Output Structure:**
```
## [Task Title/Summary]
[Brief overview of what was accomplished]

## [Main Content Sections]
[Organized, formatted content with clear headers]

### [Subsections as needed]
- [Bullet points, lists, or structured information]
- [Include links, sources, and references]

## Key Insights/Summary
[Important takeaways or conclusions]

## Sources & References
[All sources used with proper attribution]
```

## STEP 4: Quality Standards
- **Comprehensive research** using available tools
- **Professional formatting** with clear structure
- **Accurate information** with proper source attribution
- **Engaging presentation** that's easy to read and understand
- **Complete execution** of all requested components

**Example Task: "Prepare a newsletter with top 10 trending HN posts"**

```
## Hacker News Top 10 Trending Posts Newsletter
Daily digest of the most engaging discussions and innovations from the HN community.

## Today's Top Trending Posts

### 1. [Post Title](HN-link)
**Summary**: Brief description of the post content and significance
**Why It's Trending**: Key reasons for community engagement
**Discussion Highlights**: Notable comments or insights from HN users
**Relevance**: Why this matters to the tech community

### 2. [Next Post Title](HN-link)
[Same format structure]

[Continue for all 10 posts]

## Key Themes Today
- [Pattern 1]: Multiple posts about [topic]
- [Pattern 2]: Community interest in [area]
- [Pattern 3]: Emerging trends in [field]

## Community Insights
Notable discussions, debates, or expert opinions from today's conversations.

## Sources
- Hacker News front page and trending algorithms
- Individual post discussions and comment threads
- Community engagement metrics and voting patterns
```

**Requirements:**
- Execute any custom task or workflow systematically
- Use all available tools for research and analysis
- Present results professionally with proper structure
- Include comprehensive sources and attribution
- Adapt format and approach to specific task requirements
"""

# Fact-check handler template
FACT_TEMPLATE = """
Systematically verify claims and statements with comprehensive source validation and transparent uncertainty handling.

# Fact-Checking Methodology - SYSTEMATIC VERIFICATION PROCESS

## STEP 1: CLAIM EXTRACTION & CATEGORIZATION
**Extract ALL verifiable claims from the content:**
- **Factual Claims**: Statistics, dates, events, scientific facts
- **Attribution Claims**: Quotes, statements attributed to people/organizations
- **Causal Claims**: "X causes Y", "Due to X, Y happened"
- **Comparative Claims**: Rankings, comparisons, "better/worse than"
- **Current Status Claims**: Current prices, status, availability

**Claim Prioritization:**
- **High Priority**: Core claims central to the message
- **Medium Priority**: Supporting details and context
- **Low Priority**: Tangential or well-established facts

## STEP 2: SYSTEMATIC VERIFICATION STRATEGY
**Verification Hierarchy:**
1. **Primary Sources**: Official websites, government data, organization statements
2. **Academic Sources**: Peer-reviewed research, institutional studies, wikipedia
3. **Established News Sources**: Reuters, AP, BBC, established newspapers
4. **Industry Sources**: Trade publications, industry reports
5. **Secondary Analysis**: Expert commentary, analysis pieces

**Search Strategy:**
1. **Direct Claim Search**: Search exact claim or paraphrased version
2. **Source Verification**: Search for original source of claimed information
3. **Counter-Evidence Search**: Actively search for contradicting information
4. **Recent Updates**: Check for more recent information that might contradict
5. **Context Search**: Understand broader context around the claim

## STEP 3: SOURCE QUALITY ASSESSMENT
**Evaluate each source on:**
<source_quality_checklist>
✓ Authority: Is the source authoritative on this topic?
✓ Recency: How current is the information?
✓ Bias Assessment: Any obvious political, commercial, or ideological bias?
✓ Corroboration: Do multiple independent sources agree?
✓ Original vs. Secondary: Is this the original source or reporting on it?
✓ Methodology: For studies/surveys, is methodology sound?
</source_quality_checklist>

## STEP 4: VERIFICATION STATUS DETERMINATION
**Classification System:**
- ✅ **VERIFIED**: Multiple reliable sources confirm
- ⚠️ **PARTIALLY VERIFIED**: Some aspects confirmed, others unclear
- ❌ **FALSE**: Reliable sources contradict the claim
- 🔍 **UNVERIFIABLE**: Insufficient reliable sources available
- 📅 **OUTDATED**: Was true but circumstances have changed
- 🤔 **DISPUTED**: Reliable sources disagree

## STEP 5: UNCERTAINTY & LIMITATION HANDLING
**When verification is unclear:**
- **Multiple conflicting sources**: Present different perspectives with source quality
- **Insufficient information**: Clearly state limitations and what's unknown
- **Rapidly changing situations**: Note information currency and change potential
- **Complex claims**: Break down into verifiable components

**Fallback Strategy:**
```
Unable to fully verify this claim due to:

**Verification Challenges:**
- [Specific challenge, e.g., "Limited reliable sources available"]
- [Another challenge, e.g., "Conflicting expert opinions"]

**What We Found:**
- [Partial information available]
- [Related verified information]

**Recommendation:**
- [Suggested approach for the user]
- [When to check for updates]
```

## STEP 6: COMPREHENSIVE REPORTING FORMAT

**For Each Claim:**
```
**Claim**: [Original statement]
**Status**: [Verification symbol + status]
**Evidence**:
- [Supporting evidence with source quality]
- [Contradicting evidence if any]
**Source Quality**: [Assessment of primary sources used]
**Last Updated**: [When information was verified]
**Notes**: [Important context, limitations, or nuances]
```

# FACT-CHECKING EXAMPLES

## Example 1: Statistical Claim
**Original**: "Carbon emissions increased by 15% in 2023 globally"

### Verification Process:
1. **Search Strategy**: "global carbon emissions 2023 statistics"
2. **Sources Found**: IEA Global Energy Review, UN Environment Programme
3. **Cross-verification**: Check multiple climate monitoring organizations

### Result:
**Claim**: Carbon emissions increased by 15% in 2023 globally
**Status**: ❌ **FALSE**
**Evidence**:
- IEA data shows 1.1% increase in 2023, not 15%
- Multiple climate organizations report similar ~1% increase
**Source Quality**: High (authoritative international organizations)
**Last Updated**: Based on 2023 year-end data
**Notes**: The 15% figure appears to be confused with a different metric or time period

## Example 2: Attribution Claim with Uncertainty
**Original**: "Elon Musk said Tesla will achieve full self-driving by end of 2024"

### Verification Process:
1. **Quote Search**: Search for exact or similar statements
2. **Timeline Search**: Check recent Musk statements on FSD timeline
3. **Context Search**: Understand history of similar predictions

### Result:
**Claim**: Elon Musk said Tesla will achieve full self-driving by end of 2024
**Status**: 🔍 **UNVERIFIABLE** (specific quote)
**Evidence**:
- Musk has made multiple FSD timeline predictions
- No exact quote found for "end of 2024"
- Pattern of similar predictions that were later revised
**Source Quality**: Mixed (social media posts, interviews, earnings calls)
**Last Updated**: [Current date]
**Notes**: Musk frequently revises FSD timelines; recommend checking recent official Tesla communications

## Example 3: Complex Multi-Part Claim
**Original**: "The new AI regulation will cost businesses $50B annually and reduce innovation by 30%"

### Verification Breakdown:
1. **Cost Component**: Search for economic impact studies
2. **Innovation Component**: Look for innovation metrics and projections
3. **Regulation Specificity**: Identify which specific regulation

### Result:
**Claim**: The new AI regulation will cost businesses $50B annually and reduce innovation by 30%
**Status**: ⚠️ **PARTIALLY VERIFIED**
**Evidence**:
- Cost estimates vary widely ($20B-$80B across different studies)
- No specific studies found supporting 30% innovation reduction
- Impact highly dependent on implementation details
**Source Quality**: Medium (industry estimates, some academic analysis)
**Last Updated**: [Current date]
**Notes**: Economic projections for new regulations are inherently uncertain; multiple scenarios exist

**SYSTEMATIC REQUIREMENTS:**
- **ALWAYS search for counter-evidence** to avoid confirmation bias
- **ALWAYS assess source quality** and note limitations
- **ALWAYS distinguish between** "not verified" and "false"
- **ALWAYS provide context** for complex or nuanced claims
- **ALWAYS note information currency** and potential for updates
- **ALWAYS break down complex claims** into verifiable components

**Content Guidelines:**
1. **Transparent methodology** - explain verification approach
2. **Source transparency** - clearly cite sources and assess quality
3. **Uncertainty acknowledgment** - be honest about limitations
4. **Actionable results** - provide clear verification status
5. **Context preservation** - maintain nuance and complexity
6. **Update recommendations** - suggest when to re-verify
7. **Bias awareness** - acknowledge potential verification biases

**Critical Verification Standards:**
- Multiple independent sources for verification
- Active search for contradictory evidence
- Clear distinction between correlation and causation
- Recognition of context-dependent claims
- Transparent limitations and uncertainty acknowledgment
"""

# Background research handler template
BACKGROUND_RESEARCH_TEMPLATE = """
Conduct comprehensive business intelligence research on individuals and organizations mentioned in the email.
This is strategic research to support business decisions, not just basic background information.

# Research Methodology - CRITICAL PROCESS

## STEP 1: INFORMATION EXTRACTION & VERIFICATION
**Extract ALL available identifiers from the email content:**
- Full names (first, middle, last)
- Email addresses
- Company names and variations
- Job titles or roles
- Any additional context clues (locations, mutual connections, etc.)

**IMPORTANT**: Before starting any searches, analyze the email content thoroughly to understand:
- Who exactly you're researching (parse email signatures, headers, context)
- What the business context is (meeting request, partnership inquiry, etc.)
- Any specific details that could help distinguish the right person/company

## STEP 2: SYSTEMATIC SEARCH STRATEGY
**Phase 1 - Targeted Combined Searches:**
1. **Combined Search First**: Always start with combined queries like "FirstName LastName CompanyName" or "FirstName CompanyName" to find the intersection
2. **Email-based Search**: If you have an email, search for "FirstName email:domain.com" or "CompanyName email:domain.com"
3. **Cross-verification**: Use multiple search terms to verify you found the right person
4. **Typo Resilience**: If exact name searches fail, try common variations:
   - **Missing/extra letters**: "Maxx Henlay" → try "Max Henley", "Maxx Henlay"
   - **Common substitutions**: "ph/f", "c/k", "i/y", "ou/u"
   - **Double letters**: "Connor" → try "Conor", "Connors"
   - **Similar sounding**: Use phonetic variations if initial search fails
   - **CRITICAL**: When you find a match with corrected spelling, clearly highlight this in your response

**Phase 2 - LinkedIn Strategic Search:**
- Use `linkedin_data_api` for SEARCHING and FINDING profiles/companies when you don't have LinkedIn URLs:
  - **Action: search_people** - Primary tool for finding people by:
    - `first_name` + `last_name` + `company` (most targeted)
    - If exact match fails, try spelling variations systematically
    - `keywords` (combined name and company terms)
    - `keyword_title` (job title keywords)
    - Multiple parameters can be combined for precision
  - **Action: search_companies** - For finding companies by:
    - `keyword` (company name or description)
    - Can add location, industry filters if needed
  - **Action: get_profile_by_url** - If you have a LinkedIn URL from web search
  - **Action: get_profile_data** - If you have a LinkedIn username (not common)

- Use `linkedin_fresh_data` for getting DETAILED profile data from confirmed LinkedIn URLs:
  - **Action: get_linkedin_profile** - For detailed individual profile data when you have confirmed LinkedIn URL
    - Include optional sections: `include_skills=true`, `include_certifications=true` for comprehensive research
  - **Action: get_company_by_linkedin_url** - For detailed company data when you have confirmed LinkedIn company URL
  - **CRITICAL**: Only use this tool AFTER you have confirmed LinkedIn URLs from previous searches

**Phase 3 - Validation Searches:**
- Search for the person/company name + recent news/updates
- Look for any conflicting information that might indicate wrong identification
- Cross-reference details across multiple sources
- **Spelling Verification**: If you used a corrected spelling, verify this is the correct name through multiple sources

## STEP 3: IDENTITY CONFIRMATION PROTOCOL
**Before proceeding with detailed research, confirm you have the RIGHT person/company:**

<verification_checklist>
✓ Does the company association match? (email domain, mentioned company, etc.)
✓ Do the role/title indicators align with context?
✓ Are there geographical indicators that match?
✓ Do any mutual connections or context clues align?
✓ Is there recent activity that supports this identification?
</verification_checklist>

**If ANY verification point fails or is uncertain:**
- **STOP the research process**
- **DO NOT proceed with fabricated or uncertain information**
- **Request clarification from user** (see Step 5)

## STEP 4: COMPREHENSIVE RESEARCH (Only After Confirmed Identity)

### Research Strategy & Tool Usage:
- Start with web search to identify LinkedIn profiles, company pages, and recent news
- Use LinkedIn tools strategically:
  - **linkedin_data_api**: For SEARCHING and finding profiles/companies
    - search_people: Find people by name + company combination
    - search_companies: Find companies by name/keyword
    - get_profile_by_url: Get profile data if you have LinkedIn URL
  - **linkedin_fresh_data**: For DETAILED data extraction from confirmed URLs
    - get_linkedin_profile: Comprehensive profile data (with skills, certifications, etc.)
    - get_company_by_linkedin_url: Detailed company information
- Cross-reference information across multiple sources for accuracy
- Focus on business relevance - what matters for the decision at hand
- **MANDATORY**: Keep detailed notes of ALL links visited and sources used for references section

## STEP 5: FALLBACK STRATEGY - REQUEST CLARIFICATION

**When to use the fallback strategy:**
- Multiple profiles found with same name but unclear which is correct
- Company association unclear or contradictory
- Insufficient unique identifiers to confirm identity
- Any doubt about accuracy of identification

**Fallback Response Format:**
```
I found multiple potential matches for [name/company] but need clarification to ensure accuracy:

**Potential Matches Found:**
1. [Name] at [Company] - [brief description]
2. [Name] at [Company] - [brief description]

**To provide accurate research, could you please clarify:**
- [Specific question about company/role/location]
- [Any additional identifying information]
- [Context that would help distinguish the right person]

This will help me provide reliable business intelligence rather than potentially incorrect information.
```

# SUCCESSFUL RESEARCH EXAMPLE

## Example Query: "Research background on sarah.chen@techstartup.io"

### Step 1: Information Extraction
- Name: Sarah Chen
- Email domain: techstartup.io
- Company: TechStartup (from domain)

### Step 2: Search Strategy
1. **Combined Search**: "Sarah Chen TechStartup" via Web Search tool
2. **Email Search**: "Sarah Chen techstartup.io" via Web Search tool
3. **LinkedIn Search**: Use linkedin_data_api with action "search_people":
   - first_name: "Sarah"
   - last_name: "Chen"
   - company: "TechStartup"

### Step 3: Verification
✓ Found Sarah Chen, CTO at TechStartup Inc.
✓ Email domain matches company
✓ Role aligns with technical email signature
✓ Location and timeline consistent

## Example with Typo Correction: "Research background on Vetri Vellor at Stych India"

### Step 1: Information Extraction
- Name: Vetri Vellor (potential typo)
- Company: Stych India

### Step 2: Search Strategy with Typo Handling
1. **Initial Search**: "Vetri Vellor Stych India" - No clear matches
2. **Typo Variations**: Try "Vetri Vellore", "Vetri Veller" with Stych India
3. **LinkedIn Search**: linkedin_data_api "search_people":
   - first_name: "Vetri"
   - last_name: "Vellore" (corrected spelling)
   - company: "Stych India"

### Step 3: Verification with Correction Note
✓ Found Vetri Vellore at Stych India
✓ Company matches exactly
✓ Profile shows expected role and location
⚠️ **Note: Corrected spelling from 'Vetri Vellor' to 'Vetri Vellore'**

### Step 4: Comprehensive Research
**Detailed Profile Data (using linkedin_fresh_data):**
- Action: get_linkedin_profile with confirmed LinkedIn URL
- Include comprehensive sections: include_skills=true, include_certifications=true, only if needed
- Current Role: CTO at TechStartup Inc. (2022-present)
- Background: 8 years at Google, 3 years at Meta
- Expertise: ML/AI, cloud infrastructure
- Education: Stanford CS PhD

**Company Research (using linkedin_fresh_data):**
- Action: get_company_by_linkedin_url for TechStartup company page
- TechStartup Inc: Series B, $50M raised
- Focus: AI-powered analytics tools
- Team: 120 employees, growing 40% YoY
- Recent: Partnership with Microsoft announced

**Business Context:**
- High-value technical leader with strong background
- Company in growth phase, well-funded
- Strategic opportunity for technical partnerships
- Recent Microsoft partnership indicates market validation

### References Used:
1. [LinkedIn Profile](linkedin-url)
2. [Company Crunchbase](crunchbase-url)
3. [Recent Partnership News](news-url)

**Content Guidelines:**
1. **Business-focused analysis** - always connect findings to business value
2. **Strategic insights** - go beyond basic facts to provide decision support
3. **Professional tone** - appropriate for executive-level communications
4. **Actionable intelligence** - provide specific, usable insights
5. **Cross-referenced accuracy** - verify key facts across multiple sources
6. **Risk awareness** - flag any concerns or inconsistencies found in email content claims or news
7. **Competitive context** - position findings within market landscape
8. **Relationship mapping** - identify connection opportunities and common ground
9. **Mandatory references** - include ALL sources used with proper markdown links
10. **Confidence indicators** - clearly state certainty levels for key findings
11. **Spelling corrections highlight** - clearly note any name/spelling corrections made during research

**CRITICAL REQUIREMENTS:**
- **NEVER proceed with research if identity verification fails**
- **ALWAYS include comprehensive references section with actual links**
- **ALWAYS state confidence levels and any assumptions made**
- **ALWAYS provide fallback response if uncertain about identity**
- **ALWAYS connect research findings to business context and value**
- **ALWAYS highlight spelling corrections with format: "⚠️ Note: Corrected spelling from '[original]' to '[corrected]'"**

**Important Notes:**
- Keep detailed notes of ALL links visited and used for research
- Provide strategic context for all findings
- Include confidence levels for key assertions
- Always include disclaimer about information accuracy and age
- Prioritize recent and verifiable information
- Connect individual research to broader business context
- **If uncertain about identity, request clarification rather than guessing**
"""

# Translation handler template
TRANSLATE_TEMPLATE = """
Provide accurate translations with cultural context preservation and clear explanation of translation decisions.

# Translation Process

## STEP 1: Language Analysis
- **Detect source language** including dialect and formality level
- **Identify content type**: Technical, formal, casual, creative, or cultural content
- **Note complexity factors**: Idioms, cultural references, technical terms, humor

## STEP 2: Translation Strategy
**Choose appropriate approach:**
- **Literal**: For technical/legal content requiring precision
- **Cultural**: For marketing, creative, or culturally-specific content
- **Functional**: For instructions and informational content

## STEP 3: Translation Output Format
```
## Language Detection
**Source Language**: [Language with confidence level]
**Content Type**: [Document type classification]

## Translation
**Target Language**: [Target language, default is english]
**Approach**: [Literal/Cultural/Functional]

### Original Text
[Source text clearly presented]

### Translation
[Accurate translation in target language]

## Translation Notes
### Cultural Adaptations
- [Idioms or cultural references adapted]
- [Explanations for cultural adjustments]

### Technical Decisions
- [Specialized terminology choices]
- [Alternative translations if applicable]

## Quality Verification
**Accuracy**: [High/Medium with any challenging areas noted]
**Cultural Appropriateness**: [Verified for target audience]
```

## STEP 4: Quality Standards
- **Preserve intent and tone** of original content
- **Adapt cultural elements** appropriately (idioms, references, humor)
- **Maintain natural expression** in target language
- **Note translation challenges** and decisions made
- **Provide alternatives** when multiple interpretations possible

**Example Output:**
```
## Language Detection
**Source Language**: Spanish (Standard)
**Content Type**: Idiomatic expression

## Translation
**Target Language**: English
**Approach**: Cultural adaptation

### Original Text
"No hay mal que por bien no venga"

### Translation
"Every cloud has a silver lining"

## Translation Notes
### Cultural Adaptations
- Used equivalent English idiom rather than literal translation
- Preserves consolatory and optimistic meaning
- Maintains proverbial nature of expression

### Alternative Options
- Literal: "There is no bad that doesn't come for good"
- Explanatory: "Something good comes from every bad situation"

## Quality Verification
**Accuracy**: High (meaning fully preserved)
**Cultural Appropriateness**: Verified for consolatory context
```

**Requirements:**
- Accurately detect and identify source language
- Preserve cultural context and intent
- Use natural expression in target language
- Explain translation decisions clearly
- Note any limitations or professional recommendations needed
"""

# Scheduling handler template
MEETING_TEMPLATE = """
Intelligently extract, research, and schedule meetings or appointments with proper validation, research, and clarification protocols.

# Scheduling Methodology - SYSTEMATIC PROCESS

## STEP 1: INFORMATION EXTRACTION & ANALYSIS
**Extract ALL available information from the request:**
- **Participants/Service Providers**: Names, titles, organizations, type of service needed (e.g., therapist).
- **Contact Information**: Emails if provided.
- **Research Criteria**: Location, specialization, ratings, insurance, keywords for the service.
- **Time References**: Specific dates/times, relative ("next week", "available evenings").
- **Location Preferences**: Physical locations, cities, virtual.
- **Meeting/Appointment Context**: Purpose, urgency, duration.
- **User Context**: Timezone, location, insurance.

**CRITICAL ANALYSIS:**
- Identify organizer/requester (usually sender).
- Determine if: scheduling with known contacts, finding new service/professional, or personal reminder.
- Pinpoint info needed for research if finding new service/professional.
- Check for missing contact info for known participants.

## STEP 2: PARTICIPANT/SERVICE PROVIDER VALIDATION & RESEARCH
**Prioritization:**
- If participant contact info (emails for named individuals) is provided, proceed to STEP 3 & 4. Targeted research in this step is ONLY for *critical missing contact info for explicitly named participants*.
- If finding a service type (e.g., "a therapist"), an unnamed professional, or needing extensive details on a named one, use broader research protocols below.

**Requirements:**
- **Direct scheduling**: Min. 2 participants with contact info (unless personal reminder).
- **Service/professional search**: Clear research criteria.
- Research missing contacts for known participants or find services/professionals based on user criteria.

**Research Protocol for Missing Contacts or Finding Services/Professionals:**
1.  **Known Individuals (Missing Contact Info)**:
    *   Web search: "[Name] [Company] email", "[Name] contact".
    *   Check LinkedIn, company sites, directories.
2.  **Services/Professionals (e.g., Therapists, Plumbers)**:
    *   Web search: "[Service] [Location]", "[Specialization] [Service] [City] [Rating] [Insurance]".
    *   Use professional directories (Psychology Today, Zocdoc), review sites (Yelp).
    *   Extract: Names, contact details, websites, specializations, ratings, hours, insurance.
3.  **Typo Resilience**: Systematically try spelling variations.

**Presenting Research & Requesting Clarification:**
- **Always present research findings clearly before asking for clarification or scheduling.**
- Include names, contact details, specializations, ratings, links.
- If multiple options, present them and ask user to choose or add filters.
- If info is incomplete, show what was found and ask for guidance.
```
I've researched based on your request. Here's a summary:

**[Option 1: Name of Professional/Service]**
- Specialization: [Details]
- Location: [Address/Area]
- Contact: [Phone/Email/Website Link]
- Ratings/Reviews: [Summary or Link]
- Insurance: [Accepted/Not Found/NA]
- Notes: [e.g., "Offers virtual sessions"]

(Repeat for Option 2, etc.)

**To proceed, please clarify:**
- Which option(s) do you prefer?
- Additional filtering criteria?
- Confirm if I should [specific next action, e.g., "find consultation availability"]?
- If contact info is missing for a chosen option, how to proceed (e.g., "search website contact form")?
```

## STEP 3: TIME & TIMEZONE RESOLUTION
**Time Reference Handling:**
1.  **Relative Time**: "Next week same time" (email timestamp + 7 days), "Tomorrow 2pm" (email date + 1 day), "Weekday evenings after 6 PM".
2.  **Timezone Priority**: Explicit mentions ("3pm EST"), location clues ("Beverly Hills, LA" -> PST/PDT), email metadata, then default to UTC (notify user).
3.  **Duration Defaults**: Meetings 30 min, therapy 50-60 min, initial consults 15-30 min (unless specified).

## STEP 4: VALIDATION CHECKLIST
**Before scheduling or finalizing recommendations, verify:**
<scheduling_checklist>
✓ Research done & findings presented (if service search).
✓ User clarification obtained if research yielded multiple/incomplete options.
✓ Participants/service provider identified for contact.
✓ Contact info available/researched for chosen entity.
✓ Date/time (or preferred range) determined.
✓ Timezone established.
✓ Duration set.
✓ Purpose/title clear.
✓ Location (virtual/physical) identified.
</scheduling_checklist>

**If ANY validation point fails (user input needed):**
- **STOP scheduling.** Do NOT call `meeting_creator` if critical info is missing.
- Present research & request specific clarification (See Step 2 & 6).

## STEP 5: SCHEDULE GENERATION / FINALIZING RECOMMENDATION
**If direct scheduling possible (`meeting_creator` details confirmed):**
**Tool Usage: meeting_creator**
- title: Clear meeting/appointment title.
- start_time: ISO 8601 with timezone (e.g., "2024-08-15T10:00:00-07:00").
- end_time: ISO 8601 (start_time + duration).
- description: Context/agenda.
- location: Virtual link or physical address.
- attendees: ALL emails (user, professional if applicable & known).

**Response (Successful Scheduling):**
1.  Summary: Overview of event.
2.  Participants: List attendees, contact methods.
3.  Calendar Links: Google, Outlook.
4.  Next Steps: Invitation instructions.
5.  Research Notes: Assumptions made.

**Response (Providing options/needing clarification pre-scheduling):**
- Use Step 2 clarification format. Outline next steps once user clarifies (e.g., "Once you select a therapist, I can find their availability.").

## STEP 6: FALLBACK STRATEGIES

### Missing or Ambiguous Information (General)
```
I need more information/clarification:

**Current Understanding:**
- Goal: [e.g., Schedule with X, Find therapist]
- Key details: [List info you have]
- Research (if any): [Summary & sticking points]

**Clarification Needed:**
- [Specific question 1, e.g., "Email for John Doe?"]
- [Specific question 2, e.g., "Preferred therapist from list?"]
- [Specific question 3, e.g., "For 'next week', specify day/date range?"]

With these details, I can [next action, e.g., "schedule meeting", "contact therapist for availability"].
```

### Clarification on Researched Options (e.g., Multiple Therapists)
(Covered by Step 2 "Presenting Research" template)
```
Based on research, I found:

**[Option 1 Name]**
- Details: [Specialization, Location, Contact, Ratings, Website]
- Notes: [e.g., Accepts Cigna, Virtual sessions]

(Repeat for other options)

**Please let me know:**
- Which option to explore further?
- Find consultation availability for preferred option(s) (e.g., "weekday evenings after 6 PM")?
- Other criteria to narrow search?
```

### Ambiguous Timing
```
Timing needs clarification:

**Understood:**
- Time reference: [e.g., "weekday evenings after 6 PM"]
- Timezone: [Assumed, e.g., "PST/PDT for Beverly Hills"]

**Please clarify:**
- Specific date(s) or range for consultation/meeting?
- Confirm timezone if assumed incorrect.
- Preferred duration (default: [default duration])?
```

# SUCCESSFUL SCHEDULING EXAMPLES (AND RESEARCH LEADING TO SCHEDULING)

## Example 1: Researching and Clarifying to Schedule with a Therapist
**User Request:** "Find licensed therapist in Beverly Hills, LA for anxiety & work-life balance, near Wilshire/Beverly Dr, 4.5+ stars, in-person & virtual, free weekday evenings after 6 PM. Cigna insurance."

**Step 1: Info Extraction** (as per request details)
- Service: Licensed therapist. Location: Beverly Hills (Wilshire/Beverly Dr). Specialization: Anxiety, work-life balance. Ratings: 4.5+. Sessions: In-person & virtual. Availability: Weekday evenings >6 PM. Insurance: Cigna.

**Step 2: Research & Presenting Findings**
1.  **Web Search**: "licensed therapist Beverly Hills anxiety work-life balance Cigna 4.5+ stars Wilshire Blvd", "psychology today therapists Beverly Hills Cigna virtual".
2.  **Check Directories**: Psychology Today, Zocdoc, Cigna provider list.
3.  **Visit Websites**: For shortlisted therapists, check details.

**Step 3: Example Clarification Response (Post-Research)**
```
Researched therapists in Beverly Hills for anxiety/work-life balance, possibly accepting Cigna:

**Option 1: Dr. Emily Carter, PsyD**
- Specialization: Anxiety, Stress Mgt, Work-Life Balance
- Location: Wilshire Blvd, Beverly Hills
- Contact: (310) 555-1234 / drcarter@email.com / www.dremilycartertherapy.com
- Ratings: 4.8 (PsychologyToday), 4.7 (Yelp)
- Insurance: Listed for Cigna (verify)
- Sessions: In-person & virtual.
- Notes: Focus on professionals. Availability not online.

**Option 2: Beverly Balance Therapy Center (Dr. John Lee, PhD)**
- Specialization: CBT Anxiety, Career Coaching
- Location: Beverly Drive, Beverly Hills
- Contact: (310) 555-5678 / info@beverlybalance.com / www.beverlybalancetherapy.com
- Ratings: 4.6 (Zocdoc), Google positive.
- Insurance: Appears Cigna PPO.
- Sessions: In-person & telehealth.
- Notes: Group practice. Online booking for 15-min free chat.

**To find consultation slots, please specify:**
1.  Preferred therapist(s)?
2.  Should I check their availability for "weekday evenings after 6 PM"? (Some require direct contact/portal use for first appointments).
3.  Preferred day next week for initial consultation?

Once preferred, I'll attempt to find availability or guide booking.

References:
1. [Psychology Today - Beverly Hills, Cigna, Anxiety](https://www.psychologytoday.com/us/therapists/ca/beverly-hills?category=cigna&spec=123)
2. [Zocdoc - Therapists Beverly Hills](https://www.zocdoc.com/therapists/ca/beverly-hills-12345zip)
```

**Step 4 (Post User Clarification, e.g., User picks Dr. Carter, confirms check availability):**
- Contact Dr. Carter's office (if method available) or check portal for weekday evenings >6 PM.
- If slots found, present to user.
- If direct booking/check not possible: Advise user (e.g., "Dr. Carter's site suggests calling [number]. Want an email draft to inquire?").

**Step 5: Schedule Generation (if slot confirmed by user & professional):**
(e.g., Dr. Carter available next Tue 6:30 PM PST, user confirms)
**Tool Usage: meeting_creator**
- title: "Initial Consultation: [User Name] & Dr. Emily Carter"
- start_time: "[YYYY-MM-DD]T18:30:00-07:00" (Calculated date/time PST)
- end_time: "[YYYY-MM-DD]T19:20:00-07:00" (50-min session)
- description: "Initial therapy consultation for anxiety & work-life balance."
- location: "Suite 205, Wilshire Boulevard, Beverly Hills, CA (or Virtual)"
- attendees: ["[user_email@example.com]", "drcarter@email.com"] (if confirmed for invites)

## Example 2: "Set up coffee with Sarah from Marketing tomorrow 3pm"
**Info Extraction:** Organizer: [Sender email]. Participant: Sarah from Marketing (research if email unknown). Time: Tomorrow 3pm. Type: Coffee (30 min).

**Research (if Sarah's email unknown):** Internal directory search. Web search: "[User's Company] Sarah Marketing email". If multiple Sarahs, ask user for last name/team.

**Scheduling (Contact Found/Provided):** If sarah.m@example.com found: Schedule tomorrow 3pm local. Duration 30 min. Location: "TBD" or virtual. Call `meeting_creator`.

**CRITICAL REQUIREMENTS:**
- **Present research with sources/links** if external research was done.
- **NEVER schedule without confirmed participant contact information** (email for `meeting_creator`).
- **Validate min. 2 participants for meetings** (or confirmed service provider contact) unless personal reminder.
- **Specify timezone assumptions clearly.**
- **Default to appropriate duration** (30 min meetings, 50-60 min therapy) unless specified.
- **Research thoroughly before asking broad clarification.** Ask specific questions based on findings.
- **Highlight spelling corrections** in names.

**Content Guidelines:**
1.  Professional tone.
2.  Clear time specs (inc. timezone).
3.  Thorough participant/service validation & research. Document attempts.
4.  Practical next steps.
5.  Transparency in research (what was performed/found, with links).
6.  Flexible options when primary approach fails.

**Important Notes:**
- Research contacts/services thoroughly before asking user for clarification.
- Provide specific, actionable next steps.
- Include timezone/duration defaults.
- If uncertain after research, present findings then ask specific clarification.
"""

# PDF Export handler template
PDF_EXPORT_TEMPLATE = """
Intelligently analyze the email content and create a professional PDF document export.

# PDF Export Process

## STEP 1: Content Analysis & Preparation
**Analyze the content to determine what should be exported:**
- **Extract meaningful content**: Focus on substantial information, insights, research, or analysis
- **Remove email metadata**: Strip out From/To/Subject headers and email-specific formatting
- **Preserve content structure**: Maintain formatting, lists, sections, and logical flow
- **Assess content significance**: Determine if the content warrants PDF export

**Content Worth Exporting:**
- Research findings and analysis
- Detailed reports or summaries
- Important documents or presentations
- Substantial meeting notes or agendas
- Technical documentation or guides
- Data analysis or insights

**Content NOT Worth Exporting:**
- Simple greetings or acknowledgments
- Basic confirmations or "thank you" messages
- Short scheduling emails
- Minimal content with just email headers

## STEP 2: Intelligent Content Processing
**Extract and clean the content:**
1. **Remove email headers** (From, To, Subject, Date, etc.)
2. **Preserve meaningful content** exactly as written
3. **Maintain formatting** (lists, bold, italic, headers)
4. **Keep research findings** if available
5. **Include attachment summaries** only if explicitly relevant and requested

**Process attachments conditionally:**
- **Include attachment content** ONLY if user specifically requests it or if it's essential to understanding
- **Summarize attachments** when they add substantial value to the export
- **Skip basic attachments** unless they contain important insights

## STEP 3: PDF Generation
**Use the pdf_export tool with appropriate parameters:**
- **content**: The cleaned, meaningful content (no email headers)
- **title**: Extract or generate an appropriate document title
- **research_findings**: Include if substantial research was conducted
- **attachments_summary**: Include only if attachments add value and were requested
- **include_attachments**: Set to true only if user explicitly wants attachment content

**Example Tool Call:**
```
pdf_export(
    content="[Main content without email headers]",
    title="[Document title]",
    research_findings="[Research content if available]",
    attachments_summary="[Attachment summaries if relevant]",
    include_attachments=false  # Only true if explicitly requested
)
```

## STEP 4: Response Guidelines
**If PDF export is successful:**
- Confirm the PDF has been generated and attached
- Briefly describe what content was included
- Mention the title and estimated page count
- Note any content that was excluded and why

**If content is not substantial enough:**
- Explain why PDF export may not be necessary
- Suggest alternatives (email client print function)
- Offer to proceed anyway if user insists

**Response Format:**
```
I've analyzed your content and created a professional PDF document:

**PDF Generated:** [title].pdf
**Content Included:** [brief description of what was exported]
**Pages:** Approximately [X] pages
**Format:** Professional document layout with proper formatting

The PDF includes:
- [Main content description]
- [Research findings if included]
- [Attachment summaries if included]

Email headers and metadata have been excluded to focus on the meaningful content.

The PDF is attached to this email for your use.
```

## CONTENT PROCESSING PRINCIPLES

**DO Export:**
✓ Substantial research findings or analysis
✓ Important business documents or reports
✓ Meeting notes with significant content
✓ Technical documentation or guides
✓ Data analysis and insights
✓ Educational or instructional content

**DON'T Export:**
✗ Basic email correspondence
✗ Simple confirmations or acknowledgments
✗ Short scheduling messages
✗ Content that's primarily email headers
✗ Minimal content without substance

**ALWAYS Remember:**
- Remove email headers (From, To, Subject, Date)
- Preserve content exactly as written - no modifications
- Focus on meaningful, substantial content
- Include research findings when available
- Process attachments only when explicitly requested or highly relevant
- Generate appropriate, descriptive titles
- Provide professional formatting and structure

**Content Guidelines:**
1. **Preserve original content** - export content as-is without alterations
2. **Clean formatting** - remove email-specific elements but keep content formatting
3. **Professional presentation** - ensure the PDF looks polished and readable
4. **Appropriate inclusion** - only export content that has substantial value
5. **Clear documentation** - explain what was included and why
"""

# Future handler template
FUTURE_TEMPLATE = """
Analyze email content to extract scheduling requirements for future or recurring task processing and create appropriate cron expressions.

# Future Task Scheduling Process

## STEP 1: Intent Analysis & Information Extraction
**Extract ALL relevant scheduling information:**
- **Task/Reminder Content**: What should be processed/reminded about
- **Time References**: Specific dates/times, relative timing ("every Monday", "in 2 weeks", "quarterly")
- **Recurrence Pattern**: One-time, daily, weekly, monthly, yearly, custom intervals
- **Context Requirements**: Any specific processing instructions or conditions
- **Processing Instructions**: Detailed instructions about how this task should be handled when executed

**CRITICAL ANALYSIS:**
- Identify if this is a one-time future task or recurring reminder
- Determine the exact timing requirements
- Extract any special processing instructions for the future task

## STEP 2: Cron Expression Generation
**Generate appropriate cron expressions based on timing requirements:**

**Cron Format**: `minute hour day month day_of_week`
- minute (0-59)
- hour (0-23)
- day of month (1-31)
- month (1-12)
- day of week (0-7, Sunday=0 or 7)

**Common Patterns:**
- **Daily at specific time**: `0 9 * * *` (9 AM daily)
- **Weekly**: `0 9 * * 1` (9 AM every Monday)
- **Monthly**: `0 9 1 * *` (9 AM on 1st of each month)
- **Yearly**: `0 9 1 1 *` (9 AM on January 1st)
- **Weekdays only**: `0 9 * * 1-5` (9 AM Monday-Friday)
- **Every 2 weeks**: Use specific dates for bi-weekly patterns

**Time Zone Handling:**
- Convert all times to UTC for cron expressions
- Note original timezone in task metadata
- Handle timezone awareness clearly

## STEP 3: SCHEDULED TASK CREATION
**If all scheduling details are confirmed and a future or recurring task should be created:**

**Tool Usage: scheduled_tasks**
- **cron_expression**: Valid cron expression in UTC (e.g., "0 14 * * 1" for every Monday at 2 PM UTC)
- **distilled_future_task_instructions**: Clear, detailed instructions about how the task should be processed when executed in the future. This should include the processing approach, any specific requirements, and what the expected outcome should be.
- **task_description**: Human-readable description of what the scheduled task will do (e.g., "Weekly reminder to review sales report")
- **next_run_time**: (Optional) Next execution time in ISO 8601 format (e.g., "2024-08-19T14:00:00Z")

**Response (Successful Scheduling):**
1. Confirmation message with:
    - Task ID (MUST be included in the final response)
    - Human-readable schedule description
    - Next execution time (in user's timezone and UTC)
    - DO NOT include the cron expression in the user-facing output
2. Summary of what will be processed/reminded
3. Clear next steps (e.g., "You will receive results at the scheduled time.")

**CRITICAL REQUIREMENTS:**
- ALWAYS generate and validate a correct cron expression in UTC
- ALWAYS create detailed distilled_future_task_instructions that explain how to process the task
- ALWAYS provide a clear confirmation with the next execution time and task ID
- ALWAYS ensure the task ID from the tool's response is included in your final response
- NEVER show the cron expression in the user-facing output
- ALWAYS use the `scheduled_tasks` tool for this purpose

## STEP 4: Response Format
**Provide clear confirmation with:**
```
## Scheduled Task Confirmation

**Task Description**: [Clear description of what will be reminded/processed]
**Schedule**: [Human-readable schedule description]
**Next Occurrence**: [Next execution date/time in user's timezone]
**Task ID**: [CRITICAL: Include the actual task UUID returned by the scheduled_tasks tool]

## Processing Details
**Content to Process**: [Summary of what will be processed]
**Processing Instructions**: [How the task will be handled when executed]
**Frequency**: [One-time/Daily/Weekly/Monthly/Custom interval description]
**Timezone**: [Original timezone and UTC conversion notes]

## What Happens Next
- The task has been stored in the system
- At the scheduled time, the task will be processed according to the specified instructions
- You'll receive the results via email at the specified time
- The task will [continue recurring/end after one execution] as configured
```

# EXAMPLES

## Example 1: Weekly Report Reminder
**User Request**: "Remind me every Monday at 9 AM to review the weekly sales report"

**Step 1: Analysis**
- Task: Review weekly sales report
- Schedule: Every Monday at 9 AM
- Recurrence: Weekly
- Processing Instructions: Send reminder to review weekly sales report

**Step 2: Cron Generation**
- User timezone assumed: EST/EDT (UTC-5/-4)
- 9 AM EST = 14:00 UTC (standard time)
- Cron: `0 14 * * 1`

**Step 3: Tool Usage**
```
scheduled_tasks(
    cron_expression="0 14 * * 1",
    distilled_future_task_instructions="Send a reminder email to review the weekly sales report. Include motivation to check key metrics and performance indicators.",
    task_description="Weekly reminder to review sales report"
)
```

**Sample Response:**
```
## Scheduled Task Confirmation

**Task Description**: Weekly reminder to review sales report
**Schedule**: Every Monday at 9:00 AM
**Next Occurrence**: Monday, August 19, 2024 at 9:00 AM EST
**Task ID**: c7101912-423c-38b1-d95e-f8424b55e325

## Processing Details
**Content to Process**: "Remind me every Monday at 9 AM to review the weekly sales report"
**Processing Instructions**: Send reminder with motivation to check key metrics and performance indicators
**Frequency**: Weekly (every Monday)
**Timezone**: Eastern Standard Time (UTC-5)

## What Happens Next
- The task has been stored in the system
- At the scheduled time, the task will be processed according to the specified instructions
- You'll receive the results via email at the specified time
- The task will continue recurring as configured
```

## Example 2: One-time Future Task
**User Request**: "Process this research request again in 2 weeks"

**Step 1: Analysis**
- Task: Reprocess research request
- Schedule: One-time, 2 weeks from now
- Recurrence: None (one-time)
- Processing Instructions: Re-execute the research request with current data

**Step 2: Cron Generation**
- Calculate exact date 2 weeks from now
- Convert to UTC
- One-time cron expression for specific date/time

**Step 3: Tool Usage**
```
scheduled_tasks(
    cron_expression="0 9 [day] [month] *",
    distilled_future_task_instructions="Re-execute the research request from the original email. Use current data and updated sources to provide fresh insights on the topic.",
    task_description="One-time reprocessing of research request"
)
```

**Content Guidelines:**
1. **Clear scheduling intent** - understand exactly what user wants scheduled
2. **Accurate time conversion** - handle timezones properly
3. **Detailed processing instructions** - create comprehensive distilled_future_task_instructions
4. **User-friendly confirmation** - explain what was scheduled and when it will happen
5. **Error handling** - validate timing requests and provide alternatives if invalid
"""

# Delete handler template
DELETE_TEMPLATE = """
Analyze email content to identify and delete scheduled tasks with user verification and safety checks.

# Task Deletion Process

## STEP 1: Task Identification & Extraction
**Extract ALL relevant task identification information:**
- **Task ID**: UUID format task identifiers (e.g., "12345678-1234-1234-1234-123456789012")
- **Task Description**: Descriptive text that might help identify tasks
- **User Context**: The user's email address is the "from:" field in the email context provided
- **Intent Analysis**: Determine if this is a deletion request for scheduled tasks

**Task ID Extraction Strategy:**
- Look for UUID patterns in email content (36-character format with hyphens)
- Check for "Task ID:", "Delete task:", or similar patterns
- Extract task IDs from forwarded emails or previous confirmations
- Handle multiple task IDs if present

## STEP 2: User Verification & Authorization
**Security Requirements:**
- **User Email Verification**: Match deletion requester with task owner
- **CRITICAL**: Only the task owner (user whose email is in the "from:" field) can delete their tasks
- **Task Ownership Check**: Verify user has permission to delete specific tasks
- **Clear Intent Confirmation**: Ensure user actually wants to delete tasks
- **Safety Warnings**: Inform about consequences of deletion

## STEP 3: TASK DELETION EXECUTION
**If task ID is identified and verification is complete:**

**Tool Usage: delete_scheduled_tasks**
- **task_id**: Valid UUID of the task to delete (e.g., "12345678-1234-1234-1234-123456789012")
- **user_email**: Email address of the user requesting deletion (from the "from:" field in email context)

**Example Tool Call:**
```
delete_scheduled_tasks(
    task_id="12345678-1234-1234-1234-123456789012",
    user_email="user@example.com"
)
```

**Response (Successful Deletion):**
1. Confirmation message with:
    - Task ID that was deleted
    - Brief description of what was deleted
    - Confirmation that both scheduler and database cleanup occurred
2. Summary of task that was removed
3. Security confirmation (only user's own tasks can be deleted)

## STEP 4: Response Format
**Provide clear confirmation with:**
```
## Task Deletion Confirmation

**Status**: Successfully deleted
**Task ID**: [UUID of deleted task]
**Task Description**: [Brief description of what was scheduled]
**Deleted By**: [User email for verification - taken from "from:" field]

## What Was Removed
**Scheduled Content**: [Summary of the task that was scheduled]
**Schedule**: [What the timing/recurrence was]
**Cleanup**: Both scheduler and database entries have been removed

## Important Notes
- This action cannot be undone
- Only your own scheduled tasks can be deleted
- The task will no longer execute at its scheduled time
```

# EXAMPLES

## Example 1: Delete by Task ID
**User Request**: "Delete scheduled task 12345678-1234-1234-1234-123456789012"

**Step 1: Task Identification**
- Task ID found: "12345678-1234-1234-1234-123456789012"
- User email: user@example.com (from "from:" field in email headers)
- Clear deletion intent

**Step 2: Tool Usage**
```
delete_scheduled_tasks(
    task_id="12345678-1234-1234-1234-123456789012",
    user_email="user@example.com"
)
```

**Sample Response:**
```
## Task Deletion Confirmation

**Status**: Successfully deleted
**Task ID**: 12345678-1234-1234-1234-123456789012
**Task Description**: Weekly reminder to review sales report
**Deleted By**: user@example.com

## What Was Removed
**Scheduled Content**: "Remind me every Monday at 9 AM to review the weekly sales report"
**Schedule**: Every Monday at 9:00 AM EST
**Cleanup**: Both scheduler and database entries have been removed

## Important Notes
- This action cannot be undone
- Only your own scheduled tasks can be deleted
- The task will no longer execute at its scheduled time
```

## Example 2: Task Not Found or Permission Denied
**User Request**: "Cancel task 99999999-9999-9999-9999-999999999999"

**Step 1: Task Identification**
- Task ID found: "99999999-9999-9999-9999-999999999999"
- User email: user@example.com (from "from:" field)

**Step 2: Tool Usage & Error Response**
```
delete_scheduled_tasks(
    task_id="99999999-9999-9999-9999-999999999999",
    user_email="user@example.com"
)
```

**Sample Error Response:**
```
## Task Deletion Failed

**Status**: Task not found
**Task ID**: 99999999-9999-9999-9999-999999999999
**Requested By**: user@example.com

## Issue
The specified task could not be found or you don't have permission to delete it.

## Possible Reasons
- Task ID doesn't exist in the system
- Task belongs to a different user
- Task was already deleted previously
- Task ID was copied incorrectly

## What You Can Do
- Verify the correct task ID from your scheduling confirmation email
- Check that you're using the email address that originally created the task
- Contact support if you believe this is an error
```

## Example 3: Complex Multi-Part Claim
**User Request**: "Delete both task 11111111-1111-1111-1111-111111111111 and 22222222-2222-2222-2222-222222222222"

**Step 1: Task Identification**
- Multiple Task IDs found: "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
- User email: user@example.com (from "from:" field)

**Step 2: Multiple Tool Usage**
```
delete_scheduled_tasks(
    task_id="11111111-1111-1111-1111-111111111111",
    user_email="user@example.com"
)

delete_scheduled_tasks(
    task_id="22222222-2222-2222-2222-222222222222",
    user_email="user@example.com"
)
```

**Sample Response:**
```
## Multiple Task Deletion Results

### Task 1: 11111111-1111-1111-1111-111111111111
**Status**: Successfully deleted
**Task Description**: Daily standup reminder
**Schedule**: Every weekday at 9:00 AM

### Task 2: 22222222-2222-2222-2222-222222222222
**Status**: Successfully deleted
**Task Description**: Weekly report reminder
**Schedule**: Every Friday at 3:00 PM

## Summary
- 2 tasks successfully deleted
- Both scheduler and database entries removed
- All cleanup completed successfully

## Important Notes
- These actions cannot be undone
- Only your own scheduled tasks can be deleted
- The tasks will no longer execute at their scheduled times
```

## STEP 5: FALLBACK STRATEGIES

### Missing Task ID
```
I need a task ID to delete a scheduled task.

**Current Understanding:**
- Intent: Delete scheduled task
- Missing: Specific task ID (UUID format)
- User: [user email from "from:" field]

**To proceed, please provide:**
- The task ID (36-character UUID like: 12345678-1234-1234-1234-123456789012)
- This can usually be found in your original scheduling confirmation email

**Alternative:**
If you don't have the task ID, you can:
1. Check your email for the original scheduling confirmation
2. Forward that confirmation email to delete@mxtoai.com for deletion
3. Provide a description of the task and I can help identify it (less reliable)
```

### Ambiguous Deletion Request
```
I found multiple potential tasks or need clarification:

**Found in your message:**
- [Task ID 1]: [Brief description if available]
- [Task ID 2]: [Brief description if available]

**Please clarify:**
- Which specific task(s) should be deleted?
- Should I delete all found tasks or just specific ones?
- Confirm this is a deletion request (this action cannot be undone)

Once confirmed, I'll proceed with the deletion using your verified email address from the "from:" field.
```

**CRITICAL REQUIREMENTS:**
- **ALWAYS verify user ownership** before deleting any tasks
- **ALWAYS require explicit task ID** for deletion (UUID format)
- **ALWAYS provide clear confirmation** of what was deleted
- **ALWAYS include security confirmations** in responses
- **NEVER delete tasks without proper verification**
- **ALWAYS use the delete_scheduled_tasks tool** for actual deletion
- **ALWAYS handle permission errors gracefully**
- **ALWAYS warn about irreversible nature** of deletion
- **ALWAYS use the user's email from the "from:" field** for ownership verification

**Content Guidelines:**
1. **Security first** - verify ownership before any deletion
2. **Clear identification** - require specific task IDs, not descriptions
3. **Comprehensive confirmation** - explain exactly what was removed
4. **Error handling** - provide helpful guidance when deletion fails
5. **User safety** - warn about permanent nature of deletion
6. **Professional tone** - handle deletion requests with appropriate gravity
7. **User context awareness** - remember the user is identified by the "from:" email field
"""
