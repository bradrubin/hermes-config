---
name: jama-email-scan
description: Scan JAMA emails for topic-relevant articles monthly.
version: 0.1.0
author: Brad Rubin, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [jama, email, scanning, medical-literature, fastmail, mcp]
    related_skills: [email-inbox-triage]
---

# JAMA Email Scan Skill

Scans the JAMA email folder in Fastmail for articles matching user-defined topics, compiles a categorized monthly index, and supports automated overnight scanning via cron.

## When to Use

- User wants a monthly scan of JAMA emails for specific medical topics
- User wants to batch-scan multiple months of historical JAMA emails
- Cron job needs to run nightly scanning one month of JAMA emails
- Topics include: hormone-sensitive breast cancer, prostate cancer screening, family medicine overviews, calcium score (and any custom topics the user specifies)

## Prerequisites

- Fastmail MCP server configured with `mcp__fastmail__search_email` and `mcp__fastmail__read_email` tools
- Output directory: `~/Documents/JAMA/` (create if missing)
- File naming convention: `JAMA_<MonthYear>.md` (e.g., `JAMA_September_2026.md`)

## How to Run

Use the `mcp__fastmail__search_email` and `mcp__fastmail__read_email` tools from the Fastmail MCP server. Do NOT use raw shell or API calls.

## Procedure

1. **Search for emails** in the JAMA folder for the target date range.
   - Query format: `in:JAMA after:<YYYY-MM-DD> before:<YYYY-MM-DD>`
   - Set limit to 50 (JAMA sends ~30-40 emails per month)
   - If `hasMore` is true, paginate using the `nextCursor` from the previous response
   - Store all email IDs, subjects, and dates in a temporary list

2. **Build the index file** with category headers for the current month.
   - Categories: Hormone-Sensitive Breast Cancer, Prostate Cancer Screening, General Medical Overviews for Family Medicine, Calcium Score and Cardiovascular Risk Assessment
   - Add a "Related but Not Core Matches" section for tangential articles
   - Output file: `~/Documents/JAMA/JAMA_<MonthYear>.md`
   - If the file already exists (from a prior run), append new matches rather than overwriting

3. **Read ALL emails sequentially** — never parallelize reads (rate limits).
   - Process New Issue emails first (higher priority), then Online First, then Med News
   - **For JAMA Oncology (and JAMA Cardiology/IM) Online First emails, ALWAYS read the full body text** — the subject line is always just "Online First" and reveals nothing about article content. The individual article titles, authors, and links are listed in the body under section headers (*Original Investigation*, *Research Letter*, *Viewpoint*, etc.).
   - If you skip any email without reading it, you will miss articles whose titles appear only in the body.
   - For each email: read the full content, check title/abstract/preview for topic matches
   - If a match is found, append a structured entry:
     ```
     ### [Article Title]
     - **Journal:** Journal name
     - **Date:** Month DD, YYYY (Issue type)
     - **Authors:** [if available]
     - **Reason:** Brief relevance explanation
     - **Link:** [JAMA click link]
     ```
   - Omit `Source email` lines from the output (kept for internal tracking only)

4. **Compile and finalize** the index:
   - Sort entries within each category by date (newest first)
   - Remove duplicate entries
   - Add a summary header with scanning date and topic list
   - Write final file to `~/Documents/JAMA/JAMA_<MonthYear>.md`

## Pitfalls

- **Rate limits:** MCP server rejects concurrent `read_email` calls. Always read one email at a time.
- **Context bloat:** Reading many emails at once can overflow the context window. Process sequentially.
- **Email ID validation:** Some email IDs from searches may be invalid. If `read_email` fails, verify the ID against the compiled list.
- **Overlapping date ranges:** October "New Issue" emails sometimes appear in September searches. Include them if they fall within the search window.
- **Tangential matches:** Articles that touch on a topic secondarily (e.g., breast cancer risk in a hormone therapy study) belong in the "Related" section, not core matches.
- **Source email IDs:** Internal tracking IDs (`Stm...`) are used during scanning but should NOT appear in the final output file.
- **Online First emails hide article titles in the body:** JAMA Oncology (and JAMA Cardiology, JAMA Internal Medicine) emails with subject "Online First" list article titles in the body only — the subject line contains zero article-specific information. Always read the full body of *every* email before deciding there is no match; filtering or skipping on subject alone misses core-match content entirely.

## Verification

- Confirm the output file exists at `~/Documents/JAMA/JAMA_<MonthYear>.md`
- Verify each category section has at least one entry or is empty (not missing)
- Ensure no `Source email` lines appear in the final markdown
- Cross-check the article count against manual scan of email subjects

## Cron Scheduling

Two cron jobs manage the automated scanning:

1. **Monthly retrospective** — runs at midnight on the 1st of each month, scanning the previous month's JAMA emails.
   - Schedule: `0 0 1 * *`
   - Prompt: "Scan JAMA emails for the previous month. Create/update the index file at ~/Documents/JAMA/JAMA_<MonthYear>.md using the topics: hormone-sensitive breast cancer, prostate cancer screening, family medicine overviews, calcium score."

2. **Backlog sweep** — runs at midnight nightly, scanning one month per night going backwards from the most recent unscanned month until caught up.
   - Schedule: `0 0 * * *` (daily at midnight)
   - Prompt: "Scan JAMA emails for one month going backwards from the current date. Check ~/Documents/JAMA/ for existing monthly files. Pick the most recent unscanned month. Create the index file at ~/Documents/JAMA/JAMA_<MonthYear>.md using the topics: hormone-sensitive breast cancer, prostate cancer screening, family medicine overviews, calcium score. If all months through today are caught up, report that."

For the backlog sweep, the prompt must be self-contained since cron jobs run with no chat context.
