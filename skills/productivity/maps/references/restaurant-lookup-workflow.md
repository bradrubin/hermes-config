# Restaurant Lookup Workflow

When the user wants to find restaurants near a specific location with filters
(cuisine type, rating, distance, hours), use this procedure.

## Procedure

### Step 1: Identify the anchor address

Get the exact address. If the user gives an address, use it directly with the
`maps` skill's `nearby` command.

```bash
MAPS=~/.hermes/skills/maps/scripts/maps_client.py
python $MAPS nearby --near "709 Rosedale Rd, Glenview, IL" --category restaurant --radius 4800 --limit 30
```

Radius 4800m ≈ 3 miles. Adjust as needed.

### Step 2: Filter by cuisine

The `nearby` command returns `cuisine` tags when available. Filter results
manually by checking the `cuisine` field. If cuisine is not in the tags, use
`web_search` to verify:

```
web_search "restaurant_name cuisine_type address hours rating"
```

### Step 3: Verify distance for candidates

For candidates that pass the cuisine filter, verify driving distance from the
anchor address using the `maps` skill's `distance` command:

```bash
python $MAPS distance "709 Rosedale Rd, Glenview, IL" --to "1827 Waukegan Rd, Glenview, IL" --mode driving
```

**Important:** The `maps_client.py` script uses OSRM for driving distance.
OSRM can be slow or fail in some areas. If it times out, fall back to
`web_search` with the specific route query.

### Step 4: Check rating

Use `web_search` to verify the Google/ Yelp rating for each candidate:

```
web_search "\"restaurant name\" address rating Google review stars"
```

### Step 5: Check hours for all relevant days

Use `web_search` to verify the restaurant is open on the required days during
lunch hours (typically 11am–3pm):

```
web_search "\"restaurant name\" hours lunch Thursday Friday Saturday Sunday Monday"
```

### Step 6: Present results

Format as a table:

| Restaurant | Cuisine | Distance | Rating | Open Thu-Mon? | Notes |

Include the `maps_url` field for each restaurant so the user can tap to open
directions.

## Pitfalls

- **`web_search` has a 50-call per-turn limit.** Plan queries efficiently —
  batch multiple lookups into one search when possible. If you hit the limit,
  stop and summarize what you have so far.
- **Nominatim geocoding accuracy is limited in dense suburban areas.** Two
  addresses in the same zip code with different street names may resolve to
  the same OSM node. Verify critical distance calculations with the `maps`
  skill's `distance` command.
- **`web_extract` does not work on Google Maps.** Google Maps requires JS
  rendering. Use `web_search` for Google rating data.
- **Restaurant hours change seasonally.** Holiday hours (Thanksgiving, etc.)
  are not reflected in standard data. Note this caveat when presenting results.
- **Some restaurants are "closed lunch" on certain days.** Always verify
  hours for every day the user needs, not just "open daily."
