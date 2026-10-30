---
name: browser-data-extraction
description: "Extract structured data from pages when web_extract fails."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [browser, data-extraction, scraping, tables, listings]
    related_skills: [blocked-page-recovery]
---

# Browser Data Extraction

Extract structured data (tables, listings, schedules, directories) from pages
that render content via JavaScript or serve data in non-standard DOM structures.

## When to use

- The page displays tabular/list data but `web_extract` returns a maintenance
  notice, blank body, or incomplete content.
- The data is loaded asynchronously (AJAX/fetch) after page load.
- The page structure is too irregular for simple CSS selectors.

## Procedure

### Step 1: Verify data is present in the DOM

Even when a page shows "service under maintenance" or blank content to the
user, the data may still be in the DOM as hidden rows or un-rendered cells.

```python
# Extract all row-like elements with their cell text
data = js("""
(() => {
  const rows = document.querySelectorAll('tr, [role="row"], .channel-row, .listing-row');
  const results = [];
  rows.forEach((row, i) => {
    const cells = row.querySelectorAll('td, th, [role="cell"]');
    const cellTexts = [];
    cells.forEach(c => cellTexts.push(c.innerText.trim()));
    if (cellTexts.length > 0 && cellTexts.join(' ').length > 0) {
      results.push({row: i, cells: cellTexts});
    }
  });
  return results;
})()
""")
```

If `data` is empty, the page truly has no data — the service may be down or
the content is loaded dynamically. Move to Step 4.

### Step 2: Check for the data as raw text

Some sites embed data as plain text in `body.innerText` rather than in
structured table rows. Extract the full body text and debug from there:

```python
body_text = js("document.body.innerText")
```

Then search for your target identifiers:

```python
# Find context around target identifiers
idx = body_text.find('TARGET_CHANNEL_OR_KEYWORD')
if idx >= 0:
    context = body_text[max(0, idx-100):idx+1000]
    print(repr(context))  # Use repr() to see \t, \n, \xa0 separators
```

**Use `repr()`** — it reveals tab (`\t`), newline (`\n`), and no-break space
(`\xa0`) characters that are invisible in normal output but are the actual
cell/content separators on the page.

### Step 3: Parse the discovered format

Once you see the raw text, identify the cell separator and content layout:

- **Tab-separated (`\t`)**: each cell is a tab-delimited block
- **No-break space (`\xa0`)**: often separates major sections (e.g. channel groups)
- **Newline (`\n`)**: separates lines within a cell (e.g. title, subtitle, time, category)

Common patterns:

| Pattern | Structure | Example |
|---------|-----------|--------|
| Table rows | `station\nX.Y\ttitle\ntime\nrating` | TV guide listings |
| Section blocks | `\xa0` separates groups | Channel listings |
| Multi-line cells | `title\nsubtitle\ntime\ncategory` | Each cell has multiple fields |

Parse by:
1. Splitting on section separators (\xa0)
2. For each section, extracting station name and channel number
3. Splitting remaining cells on tabs
4. Within each cell, extracting the time range and the title (first line)

### Step 4: Handle empty results

If `body.innerText` is also empty (the page truly renders nothing), the
data may be:
- Loaded by a JS framework that needs time to initialize → wait and re-check
- Behind a login wall → stop and ask the user
- Serving from an API endpoint → look for `/api/` or `/graphql` calls in the Network tab

### Step 5: Format and present

- Strip episode names, date suffixes, and subtitles from titles
- Convert time formats to consistent display (e.g. `7:00am` → `7 AM`)
- Present results as a markdown table
- Show the station name alongside the channel number for context

## Pitfalls

- **Don't assume CSS selectors work.** Pages that show "maintenance" messages
  often still have DOM rows with data — check `innerText` even when the page
  appears broken.
- **Always use `repr()` on raw text.** Invisible characters (`\t`, `\n`, `\xa0`)
  are the only reliable way to understand how a page structures its data.
- **Session state is not persistent across browser_exec calls.** Variables from
  previous calls do not carry over — put all extraction and parsing logic in a
  single `js()` call or re-extract each time.
- **Row 0 often contains column headers, not data.** When the page has a time
  header row, extract headers first and use them to map data columns correctly.
- **Multiple stations can share a channel number** (main + subchannels). Match
  by exact station call sign or file name, not just the channel number string,
  to avoid picking up subchannels like `2.2` when you want `2.1`.
- **`page_info()` summary truncates.** If the page is large, the summary from
  `page_info()` may cut off before the data. Use `js("document.body.innerText")`
  directly for full extraction.
- **`browser_exec` does not import `browser_helpers`** — that module name is wrong.
  The pre-imported browser helpers (`new_tab`, `goto_url`, `wait_for_load`,
  `page_info`, `js`, `fill_input`, `click_at_xy`, `capture_screenshot`) are
  available without any import statement. Writing `from browser_helpers import` raises
  `ModuleNotFoundError`. Always omit the import line.
- **`web_extract` returns empty content for Google Maps URLs.** Google Maps
  requires JavaScript rendering and returns no HTML body. Use the browser tool
  instead, or fall back to `web_search` with specific restaurant/POI queries
  that return indexable snippets.

## Time formatting reference

Convert the site's native time format to a clean display format:

| Native | Display | Rule |
|--------|---------|------|
| `7:00am` | `7 AM` | Drop `:00` minutes |
| `7:30am` | `7:30 AM` | Keep non-zero minutes |
| `10am` | `10 AM` | No colon in source → no colon in output |
| `10:30pm` | `10:30 PM` | Capitalize AM/PM |

## Title cleaning reference

Strip episode-specific content from show titles:

| Raw title | Cleaned | Rule |
|-----------|---------|------|
| `Cyberchase\nTrick or Treat` | `Cyberchase` | Take first line only |
| `Face the Nation\n10-18-2026` | `Face the Nation` | Remove trailing date pattern |
| `Skillsville\nTeacher; Allergist` | `Skillsville` | Remove everything after semicolon |
| `To the Contrary\nEpisode 21` | `To the Contrary` | Remove `Episode N` suffix |
| `Good Morning America Sunday\n10-18-2026` | `Good Morning America Sunday` | Remove trailing date |
