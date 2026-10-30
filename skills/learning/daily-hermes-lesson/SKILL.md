---
name: daily-hermes-lesson
description: Teach one new Hermes tool or concept per day
version: 2.0.0
author: Brad Rubin
license: MIT
platforms: [macos]
---

# Daily Hermes Lesson

Use when the user asks for a Hermes lesson, a tutorial, "teach me something about Hermes", or when the daily lesson cron job runs. If the user names a topic ("teach me about cron"), pass their words to the script.

## Step 1: get today's topic (one terminal call)

```bash
python3 /Users/hermes/.hermes/skills/learning/daily-hermes-lesson/lesson.py
```

With a requested topic, add the user's words: `... lesson.py cron jobs`

The script picks a topic you have not taught recently, records it, and prints a block between `LESSON BRIEF START` and `LESSON BRIEF END`. The script decides the topic. Do not pick a different one, and do not check past sessions or memory for what was taught.

If the block says "failed", reply with that one line and stop.

## Step 2: write the lesson as your reply

Use only TOPIC, FACTS and EXAMPLE from the brief. Do not run any tools, search the web, or add tool names or parameters that are not in the brief. Under 250 words, this structure:

**<TOPIC>**

**Why it matters:** one sentence.

**Example:**
```
<EXAMPLE, copied exactly>
```

**What it does:** one or two sentences, from FACTS.

**Try it yourself:** one prompt the user can send to Hermes to try a variation.

Then a blank line and the FOOTER line copied exactly (it tracks progress and timing). If there is a NOTE line, put it first.

## Rules
- Exactly one terminal call (Step 1). No other tool calls.
- Never use execute_code, memory, read_file, or session_search for this skill.
- Never read, edit, or create files in the skill folder or the state folder.
