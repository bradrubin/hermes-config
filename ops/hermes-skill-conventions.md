# Hermes skill conventions (learned from building inbox-triage, tpaw-load, restaurant-finder and amazon-price-watch)

Read before writing any Hermes skill. The skill will be executed by a local Qwen model, so speed and reliability on a small model come first.

## Hermes constraints
- Frontmatter `description` must be under 60 characters. Put trigger phrases in the body instead.
- Skills live in `/Users/hermes/.hermes/skills/<category>/<skill-name>/` (e.g. `skills/email/inbox-triage`). Helper scripts go in that same folder, next to SKILL.md.
- MCP tools (e.g. Fastmail) load via `tool_search` -> `tool_describe` -> `tool_call`. They are NOT callable from `execute_code`; `hermes_tools` only exposes terminal, read_file, write_file, patch, search_files, web_search, web_extract.
- Fastmail `search_email` dates must be YYYY-MM-DD (`date -v-7d +%Y-%m-%d`), not slashes. Results use `receivedAt`, `isRead`, `isAnswered`, `threadId`, `preview`, `from[0].name/email`, `to`, `cc`, and paginate with `hasMore` + `nextCursor`.
- Deliver files with a `MEDIA:<path>` line printed by a script; write outputs under `/Users/hermes/.hermes/attachments` (hard-coded, not derived from the skill folder) with open(path, "x") unique names.

## Performance rules
- Scripts are INSTALLED FILES in the skill folder, not inline code in SKILL.md. Qwen regenerates inline code token by token on every run (a 100-line inline report script cost ~45s per run). SKILL.md runs one short command per step using the full script path. Scripts find their working files from their own location (`os.path.dirname(__file__)`, `$(dirname "$0")`).
- The model passes data to scripts as plain lines in a quoted heredoc (`<<'ROWS'`), pipe-separated, with the free-text field LAST so it can contain quotes, apostrophes or pipes (`split("|", N)`). No Python tuple syntax: fewer tokens, no quote-escaping failures. The script validates and prints SKIPPED for malformed lines.
- Python does anything deterministic: dedup, sorting, formatting, lookups against config files.
- The model writes the minimum: notes only where they add value; scripts truncate long fields.
- Never let the model copy raw tool JSON into code. Forbid execute_code explicitly.
- Keep user preferences (e.g. unsubscribe lists) in plain text files the scripts read.
- Setup script should fail loudly if missing; SKILL.md tells the model to stop and report that.
- The final script prints the model's entire reply between `REPLY START` / `REPLY END` markers, ending with the `MEDIA:` line; the model only copies that block. (Assembling the reply itself, Qwen dropped the `MEDIA:` prefix and Hermes showed no download button.)
- Keep SKILL.md short. Test in a fresh Hermes session so old skill versions in context don't leak in.
- Qwen will "improve" a reply that looks like data (restaurant-finder v1.2: it turned a list into a table, invented "all 89 open every day", turned a "not holiday hours" note into a false "Nov 12 is Thanksgiving", and dropped TIMING). Counter it: keep the REPLY block short prose with the hard facts pre-computed and stated outright (counts, holidays checked in Python), avoid long field-packed lines, never include vague caveats it can embellish, and tell it WHY it must copy exactly (counts and the attachment break).

## Stop the model improvising (learned from tpaw-load)
When one step failed, Qwen read the scripts, hand-wrote JSON, clicked around the web page, and edited the user's original data file. To prevent this:
- Use as few model calls as possible; ideally one. A script can do setup, work, and reporting in a single call, so there are no gaps between steps for the model to fill.
- The script ALWAYS prints a complete REPLY block, including on failure (`... failed: <reason>`). The model never has a reason to investigate.
- SKILL.md has an explicit Rules list: no other calls; send failures as-is; never read, edit, or create skill files or the user's data files; never click or type on web pages.
- Never modify the user's original files. Write copies to `<skill dir>/work/`. Suggest making originals read-only (`chmod a-w`).
- Ship a skill as the fewest possible files. Remove files a new version no longer uses (`git rm`), so old and new scripts can't mix. Delete superseded skills with similar names.
- The model passes input as one short string (e.g. `ARGS = "1468825"`), and the script parses and validates it.

## Browser skills (browser_exec)
- All browser logic goes in an installed script. The model's whole call is one line:
  `ARGS = "..."; exec(open("<skill dir>/<script>.py").read(), globals())`
  (`globals()` keeps the `cdp()` / `js()` helpers in scope; exec'd code has no `__file__`, so hard-code the skill dir.)
- Wrap the script body in one function, so it doesn't clutter the persistent browser session's globals. Don't import modules from the skill folder: the session caches imports across calls, so an updated file would be ignored.
- CDP file upload: `DOM.getDocument` (never assume nodeId=1, since IDs reset on every navigation) -> `DOM.querySelector` -> `DOM.setFileInputFiles(nodeId=...)`. Poll for elements and page titles instead of using fixed sleeps.
- Prefer editing the input data (e.g. the plan file) in Python over typing into web forms. If the app stores edits as a change history, reproduce the app's own diff method exactly (TPAW: fast-json-patch `compare`) and verify it against the existing history before writing a new entry.
- Reading numbers from a `<canvas>` chart without a vision model: install a hook with `Page.addScriptToEvaluateOnNewDocument` before navigating. The hook wraps `CanvasRenderingContext2D.prototype.fillText` / `strokeText` to record text with transformed coordinates, and clears the record on a full-canvas `clearRect`, so you keep the latest frame. Dedupe, then pick labels by position. Also record `textBaseline` and `globalAlpha`: apps often draw hidden duplicates at opacity 0, and the baseline or font can identify which component drew a label (TPAW point labels use 'bottom').
- Set a fixed viewport (`Emulation.setDeviceMetricsOverride`) so layouts and label positions are the same every run.
- If the web app is open source, read its UI code first. It shows exactly how values are drawn and what signals "still loading" (TPAW: "calculating..."), which beats guessing. Wait for values to stay unchanged over a window longer than the app's loading-indicator delay.
- Write a debug JSON of what the page showed on every run, so a "not found" can be fixed from one run's output.
- Scroll the key value into view (or clip to the chart), then capture a screenshot with `Page.captureScreenshot` and return it as MEDIA.
- Test against a mock page first, then against the real Chrome at 127.0.0.1:9222 in your own tab.
- See tpaw-load v3.2.0 (`tpaw.py`) for the reference implementation.

## Web API skills (learned from restaurant-finder)
- Qwen can't do geography by browsing or searching: Google Maps pages block scraping, `execute_code` has no network, and "distance calculator" searches return junk. Call a real API from an installed script via `terminal` (urllib, no extra packages).
- Google Maps Platform APIs (Places, Routes) use an API key, not the OAuth/scopes setup used for Workspace (Sheets, Drive). Scripts read `GOOGLE_PLACES_API_KEY` from the environment, falling back to `/Users/hermes/.hermes/.env`. Rules forbid the model from reading that file.
- Model input as one line of `key=value; key=value` in a `<<'ARGS'` heredoc: keys can be omitted, order doesn't matter, and addresses with commas or apostrophes are safe.
- Places Nearby Search returns at most 20 results and has no paging. Search once per category, and when a call returns 20, cover the circle with 7 circles of 0.55x radius (center + 6 at 0.866R), deduping by place id, with a hard request cap. Split breadth-first and round-robin across categories: in v1.0 a depth-first American search used the whole 40-request budget and Chinese/Indian/Mediterranean were never searched.
- Classify by `primaryType`; secondary types are loose (grocery stores carry `deli`, Korean BBQ carries `barbecue_restaurant`/`american_restaurant`). One search per category: `includedTypes` = the category's types, `excludedPrimaryTypes` = junk primaries (grocery, bakery, butcher, cafe...) plus other cuisines, so junk never uses up the 20 result slots. Then in Python, drop places whose primary type is ambiguous (barbecue, chicken, burger, diner...) but whose other types or name point to an unrequested cuisine.
- Don't infer service style from price ($ sports bars aren't quick service); use primary type. Require a minimum review count (a 4.0 from one review is noise).
- Only request the fields you need; the field mask sets the billing SKU (rating, priceLevel, regularOpeningHours = Enterprise; servesLunch, takeout = Enterprise + Atmosphere).
- Cache every API response on disk (`<skill dir>/work/cache/`, keyed by a hash of URL + body + field mask, ~7 days). Filters applied in Python then cost nothing to change, and a re-run is free. Count cached responses toward the per-run request cap so a re-run repeats exactly the same searches. Never cache errors.
- Projects can have small per-day quotas (Brad's Nearby Search: 100/day). On HTTP 429 or a quota message, stop searching and return what was found, marked PARTIAL; don't fail the whole run.
- Splitting experiments (mock with ~100-170 places in 3 mi): the plain 7-circle split found 99-100% within 30 requests; density-sized hex grids found less for the same budget. Keep the 7-split.
- Test with a fake `post()` that simulates the API from a list of places; no key needed.
- See restaurant-finder v1.3.0 (`find.py`) for the reference implementation.

## Timing (required in every skill)
- setup.sh writes `start <epoch>` to `<skill dir>/timing.log` (overwrite).
- `mark.sh <phase>` appends a phase boundary (use only for boundaries worth splitting, e.g. after a fetch).
- Each save script appends `save <epoch>`.
- The final script computes per-phase durations, prints a `TIMING:` line (included in the reply and at the bottom of the report), appends a row to `<skill dir>/timing_history.csv`, then renames timing.log to timing.log.last so stale marks can never be reused. If setup or save marks are missing it prints "TIMING: unavailable (... was not run this time)".
- Single-call skills keep the phase marks in memory and write the same `TIMING:` line and timing_history.csv row.
- See inbox-triage v1.4.2 (setup.sh, mark.sh, save.py, report.py) for the multi-step reference implementation.

## Scraping sites that block bots (learned from amazon-price-watch)
- Amazon blocks plain HTTP (curl, web_extract) and many headless loads. What works: open ONE normal product page in the real browser, then `fetch()` the other pages from inside it (same origin, cookies included) and parse them with `DOMParser` in page JS. 21 pages, 0 robot checks.
- Run a long in-page loop as a background promise that stores its result in `window.__x`, then poll it with short `Runtime.evaluate` calls. One long `awaitPromise` call can outlast the helper's timeout. A hidden tab throttles timers: 21 fetches took ~70s.
- Amazon prices: the buy box JSON (`"priceAmount":`) for print and physical items; the selected format swatch (`.swatchElement.selected`, `[id^=tmm-grid-swatch].selected`) for Kindle/eTextbook pages, which have no buy-box price. `/dp/` takes ISBN-10, so convert ISBN-13 (978 prefix) in Python.
- Hermes's default local browser is headless Chrome with `navigator.webdriver=true`; Amazon serves a robot check to it. Fix: real Google Chrome under user hermes (`ops/setup_hermes_chrome.sh`, see CLAUDE.md "Machine notes"). browser_exec then reports Chrome/156, webdriver=false.
- To see or click in the Mini's Chrome (no monitor, Screen Sharing off): from the Air, `ssh -N -L 9223:127.0.0.1:9222 hermes@homechat-llm`, then Air Chrome `chrome://inspect` -> Configure -> `localhost:9223` -> **inspect fallback** (the Mini's Chrome is newer). Open a tab from the Mini with `curl -s -X PUT "http://127.0.0.1:9222/json/new?<url>"`. Work in the Console tab; the page preview may be blank.
- On the monitorless Mini, real Chrome treats Hermes's tab as hidden and pauses rendering, so canvas-drawing skills (tpaw-load) hung until Chrome got `--disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows` (in setup_hermes_chrome.sh). Fetch-only skills (amazon-price-watch) weren't affected.
- Detect a blocked run (any captcha, or over half the items unreadable) and report it as one failure; don't change state on that run.

## Cron delivery
- In the final reply, `[SILENT]` suppresses delivery (output is still saved locally). `[CRON_FAILURE]` alone on line 1 marks the run failed, and failed runs always deliver. The script prints these markers; ARGS tells it whether it's a cron or chat run, so chat runs never show the marker.
- Script-only jobs (`no_agent`) use no model and stay silent on empty stdout, but scripts must live in `$HERMES_HOME/scripts/` and can't use browser_exec.
- Keep user-edited lists and long-lived state in `/Users/hermes/.hermes/state/<skill>/`, not the skill folder. A skill seeds those files only if they're missing.
- `[SILENT]` and `[CRON_FAILURE]` only work as the very first thing in the reply (cron/scheduler.py, gateway/response_filters.py: `[SILENT]` must start the reply or be its own first/last line; `[CRON_FAILURE]` must be line 1). Qwen copied the literal `REPLY START` / `REPLY END` lines from "exactly the lines between", which would deliver every quiet night. SKILL.md must say "Do NOT write the REPLY START or REPLY END lines; the first character of your reply is the first character after REPLY START". Test with `hermes -z "This is a scheduled cron run. Run the <skill> skill."` and check the first characters of the output (`cat -v`).
- Qwen drops a separate TIMING line from a `[SILENT]` reply; the script puts the TIMING on the same line as `[SILENT]`.
- See amazon-price-watch v1.0.0 (`price_watch.py`) for the reference implementation.

## Salesforce PWA Kit storefronts (learned from duluth-price-watch)
- duluthtrading.com is Akamai-protected: curl and urllib get 403 on every path, including `/api/` and `/mobify/proxy/ocapi/`. So, as with Amazon, a no_agent script cannot do it; use browser_exec in Hermes's real Chrome and `fetch()` from inside the page.
- Find the price endpoint by recording `Network.requestWillBeSent` (XHR/Fetch) while the page loads. PWA Kit sites call `POST /api/ShopperProducts/getProducts` with body `[{"parameters":{"locale":"default","ids":"81316,76015","allImages":false,"perPricebook":true},"headers":{"Authorization":<token>}}]`. The guest token is in `localStorage.authToken` (already "Bearer ..."). One call prices many products: `variants[].price`, `.orderable`, `.variationValues {size,color}`, `variationAttributes[]` (color codes and names).
- Variants that are not `orderable` (sold out) keep clearance prices (a $9.79 that cannot be bought). Always require `orderable`.
- The API has no solid/pattern flag. Judge colors from swatch images (`imageGroups` with `viewType: "swatch"`): fetch them in-page as data URLs, build a contact sheet with PIL, and look at it. Keep the verdicts in a state file the script reads; unlisted colors are reported as "not sure" instead of guessed.
- A dev harness for driving a tab of the Mini's Chrome from the terminal needs `websockets`: use the venv under `~/.hermes/installs/*/environments/*/venv/bin/python3`. Open your own tab with `PUT /json/new`, close it after.
- The guest token in `localStorage.authToken` persists in Chrome between runs and expires in ~30 min. An expired one makes the API return HTTP 200 with an "Unauthorized" JSON body (no `data`), not a 401. Check the JWT `exp`; if expired, `removeItem('authToken')` and `Page.navigate` to the product page (in Hermes's tab `Page.reload` did not mint a new token, navigate did).
- See duluth-price-watch v1.0.1 (`duluth.py`) for the reference implementation.
