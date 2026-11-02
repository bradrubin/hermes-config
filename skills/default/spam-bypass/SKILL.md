---
name: spam-bypass
description: Draft confusing replies to business-spam emails
version: 1.1.1
---

# Spam Bypass — Confusing Reply Generator

## When to use
Triggers: "run spam-bypass", a spammer emailed bsrubin@stthomas.edu or bradrubin@bradrubin.com about business services or a meeting. Search the Fastmail inbox for today and the previous day, draft a reply per sender, NEVER send.

A spammer emailed `bsrubin@stthomas.edu` or `bradrubin@bradrubin.com` asking about business services and/or asking to schedule a meeting. The goal is to waste their time so they have an economic incentive to remove the address from their mailing list.

## Procedure

1. **Search Fastmail inbox ONLY** for spam emails to either address for today or the previous day. Crucially, the search MUST only return emails in the **Inbox** folder (id `P-F`, role `inbox`), NOT emails in Trash, Spam, Archive, or any other folder. After getting results, verify the folder field of each result is `"role":"inbox"` before proceeding.
   ```
   mcp__fastmail__search_email with query: "to:bsrubin@stthomas.edu after:today-1d"
   mcp__fastmail__search_email with query: "to:bradrubin@bradrubin.com after:today-1d"
   ```
   (If date parsing fails, use `after:7d` or search more broadly, then filter by date manually.)
   Read each candidate email with `mcp__fastmail__read_email` to confirm it's a business solicitation / meeting request.
   - IMPORTANT: If an email appears in the search results but has been deleted (folder is Trash), SKIP IT. The user has already handled deleted emails. Only act on emails that are currently in the Inbox.

2. **For each spam email found:**
   - Identify the sender's name, email, and what they're asking for
   - Craft a multi-paragraph (3+ paragraphs) reply that:
     - Is very verbose and uses lots of words to say almost nothing
     - Is philosophically circular and conceptually dense
     - Never commits to anything, never answers the actual question directly
     - Sounds professional but is completely unactionable
     - Is several hundred words per reply

3. **Create each reply as a Draft** in Fastmail using `mcp__fastmail__draft_email`:
   ```
   mode: "new"
   to: [{ "email": "<sender_email>", "name": "<sender_name>" }]
   body: "<the confusing reply text>"
   format: "text"
   ```
   Each spammer gets their own draft in the Drafts folder. The subject defaults to "Re: ..." for replies — for new drafts, set the subject to match the spammer's original subject prefixed with "Re: ".

4. **Final reply (this is what reaches the user on Telegram on cron runs).** Count the drafts you actually created in this run (each `draft_email` call that succeeded). Do not count anything already in Drafts.
   - **One or more drafts created:** reply with exactly this, nothing before or after it:
     ```
     Spam bypass: N reply draft(s) added to Fastmail Drafts (not sent):
     - <sender name or email>: Re: <original subject>
     ```
     One `-` line per draft. Use `draft` for 1 and `drafts` for more.
   - **No drafts created** (nothing found, or everything found was already handled): reply with exactly `[SILENT]` and nothing else. No explanation, no summary of what was searched.
   - **A `draft_email` call failed:** put `[CRON_FAILURE]` alone on line 1, then say which sender failed. Still list any drafts that did succeed.
   Do NOT write local text files for the user.

## Reply Style Guide
- Start with a polite greeting
- Paragraph 1: Acknowledge the email, then immediately pivot into philosophical musing about the premise of the request
- Paragraph 2: Deconstruct the key terms the sender used (e.g., "quick call," "ideal customer profile," "business goals") and explain why each is far too complex for their proposed format
- Paragraph 3: Conclude that a meaningful response requires more extensive groundwork, without ever offering concrete next steps or commitment
- Close professionally but without any actual availability or action items
- Use words like: ontological, paradigm, phenomenology, interstices, concomitant, heuristic, multidimensional, interlocutor, epistemological, dialectic

## Anti-patterns
- DO NOT send the drafts — the replies go to Drafts only
- DO NOT add text to the final reply beyond the formats in step 4; `[SILENT]` is never combined with other text
- DO NOT write local text files — create Drafts in Fastmail instead
- DO NOT give a short reply — the point is wordiness
- DO NOT say "I'm not interested" or anything that resolves the question
- DO NOT use AI-isms like "I'd be happy to," "great initiative," or "let's connect"
