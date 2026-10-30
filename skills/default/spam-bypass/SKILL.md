---
name: spam-bypass
description: Use when a spammer emailed your bsrubin@stthomas.edu or bradrubin@bradrubin.com asking about business services and/or a meeting — search Fastmail inbox for today/previous day, craft a multi-paragraph confusing reply for each sender, create as email Drafts in the user's Fastmail client. NEVER send the drafts.
---

# Spam Bypass — Confusing Reply Generator

## When to use
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

4. **Confirm to the user** that drafts have been created. State clearly that the replies are saved as Drafts in the email client and NOT sent. Do NOT write local text files for the user.

## Reply Style Guide
- Start with a polite greeting
- Paragraph 1: Acknowledge the email, then immediately pivot into philosophical musing about the premise of the request
- Paragraph 2: Deconstruct the key terms the sender used (e.g., "quick call," "ideal customer profile," "business goals") and explain why each is far too complex for their proposed format
- Paragraph 3: Conclude that a meaningful response requires more extensive groundwork, without ever offering concrete next steps or commitment
- Close professionally but without any actual availability or action items
- Use words like: ontological, paradigm, phenomenology, interstices, concomitant, heuristic, multidimensional, interlocutor, epistemological, dialectic

## Anti-patterns
- DO NOT send the drafts — the replies go to Drafts only
- DO NOT write local text files — create Drafts in Fastmail instead
- DO NOT give a short reply — the point is wordiness
- DO NOT say "I'm not interested" or anything that resolves the question
- DO NOT use AI-isms like "I'd be happy to," "great initiative," or "let's connect"
