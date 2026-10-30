---
name: restaurant-finder
description: Find restaurants near an address via Google Places
version: 1.3.0
author: Hermes Agent
---

# Restaurant finder

Use when the user asks for restaurants, lunch spots, dinner places, or places to eat near an address, within some distance, on certain dates, with cuisine, rating, price or style filters.

## Step 1: write ONE terminal call

Fill in the line from the user's request and run it exactly like this. Do nothing else first.

```bash
python3 /Users/hermes/.hermes/skills/places/restaurant-finder/find.py <<'ARGS'
address=709 Rosedale Rd, Glenview, IL; dates=2026-11-12..2026-11-16; miles=3; cuisine=american,chinese,italian,indian; min_rating=4; exclude=seafood; style=quick,casual; meal=lunch
ARGS
```

Keys (separate with `;`, leave out any the user did not mention):
- `address` (required): the address or place as the user wrote it.
- `dates` (required): `YYYY-MM-DD..YYYY-MM-DD`, or one date. If you don't know the year, write `11/12..11/16`.
- `miles`: number, default 3.
- `cuisine`: comma list. Supported: american, chinese, italian, indian, mediterranean (includes Middle Eastern, Greek, Turkish), middle eastern, greek, mexican, thai, japanese, korean, vietnamese.
- `min_rating`: e.g. `4` for "4 stars or better".
- `min_reviews`: default 20. Use `0` only if the user asks for places with few reviews.
- `exclude`: comma list, e.g. `seafood`, `sushi`, `steak`, `bar`, `pizza`.
- `style`: `quick` (fast food, counter service), `casual`, or both. Leave out for any style.
- `meal`: `breakfast`, `lunch` or `dinner`. Default lunch.

## Step 2: reply

The command prints a block between `REPLY START` and `REPLY END`. Send the lines between those two markers as your whole reply, exactly as printed. Do not send the marker lines themselves.

Why exact: the script already counted the open and closed days, checked holidays, and wrote the `MEDIA:` line that attaches the CSV. If you reword it, the counts and the attachment break, and the user gets wrong information.

- Do not make a table. Do not add a summary, notes, or advice.
- Do not change any number, name, or date.
- Keep the `TIMING:` line and the `MEDIA:` line exactly as printed. The `MEDIA:` line is last.

## Rules

- Make exactly one terminal call. No web_search, web_extract, browser, execute_code or vision calls.
- If the block says the search failed, send it as-is. Do not retry or investigate.
- Never read, edit or create any file in the skill folder or in `/Users/hermes/.hermes/.env`.
- Never paste CSV rows into the chat. The CSV file is the deliverable.
