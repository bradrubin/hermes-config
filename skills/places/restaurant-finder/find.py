#!/usr/bin/env python3
"""restaurant-finder v1.3.0 -- one-call Hermes skill script.

Reads ONE line of key=value pairs (separated by ';') on stdin, e.g.
  address=709 Rosedale Rd, Glenview, IL; dates=2026-11-12..2026-11-16; miles=3;
  cuisine=american,chinese,italian,indian; min_rating=4; exclude=seafood;
  style=quick,casual; meal=lunch; min_reviews=20

Does everything in this one call: geocode, Places Nearby Search (tiled so the
20-result cap never hides places), filter, distance, hours check, CSV, reply.
ALWAYS prints a complete REPLY START ... REPLY END block, including on failure.
"""
import csv, datetime, json, math, os, re, sys, time, urllib.error, urllib.request

SKILL_DIR = os.environ.get("RF_SKILL_DIR", "/Users/hermes/.hermes/skills/places/restaurant-finder")
OUT_DIR = os.environ.get("RF_OUT_DIR", "/Users/hermes/.hermes/attachments")
KEY_SOURCES = ["/Users/hermes/.hermes/.env", os.path.expanduser("~/.hermes/.env"),
               "/Users/hermes/.hermes/secrets/google_places_api_key"]
NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join("places." + f for f in [
    "id", "displayName", "formattedAddress", "location", "types", "primaryType",
    "businessStatus", "googleMapsUri", "rating", "userRatingCount", "priceLevel",
    "regularOpeningHours", "nationalPhoneNumber"])
MAX_REQUESTS = 30          # hard cap on Nearby Search calls per run (project quota: 100/day)
CACHE_DAYS = 7             # API responses are reused for this long; re-runs with new filters are free
MAX_DEPTH = 2              # circle-splitting levels when a search hits the 20-result cap
REPLY_ROWS = 6            # rows listed in the chat reply; the CSV has all of them

# Cuisine word -> Places types that make a place that cuisine when they are its PRIMARY type
# (all from Table A, verified Oct 2026)
CUISINES = {
    "american": ["american_restaurant", "hamburger_restaurant", "diner", "sandwich_shop", "deli",
                 "barbecue_restaurant", "chicken_restaurant", "chicken_wings_restaurant",
                 "hot_dog_restaurant", "hot_dog_stand", "bar_and_grill", "soul_food_restaurant",
                 "southwestern_us_restaurant", "cajun_restaurant", "californian_restaurant",
                 "breakfast_restaurant", "brunch_restaurant"],
    "chinese": ["chinese_restaurant", "cantonese_restaurant", "dim_sum_restaurant",
                "chinese_noodle_restaurant"],
    "italian": ["italian_restaurant", "pizza_restaurant", "pizza_delivery"],
    "indian": ["indian_restaurant", "north_indian_restaurant", "south_indian_restaurant"],
    "mediterranean": ["mediterranean_restaurant", "middle_eastern_restaurant", "greek_restaurant",
                      "gyro_restaurant", "turkish_restaurant", "lebanese_restaurant", "israeli_restaurant",
                      "falafel_restaurant", "shawarma_restaurant", "kebab_shop", "moroccan_restaurant",
                      "persian_restaurant"],
    "middle eastern": ["middle_eastern_restaurant", "lebanese_restaurant", "persian_restaurant",
                       "israeli_restaurant", "turkish_restaurant", "falafel_restaurant",
                       "shawarma_restaurant", "kebab_shop"],
    "greek": ["greek_restaurant", "gyro_restaurant"],
    "mexican": ["mexican_restaurant", "taco_restaurant", "burrito_restaurant", "tex_mex_restaurant"],
    "thai": ["thai_restaurant"],
    "japanese": ["japanese_restaurant", "ramen_restaurant", "sushi_restaurant"],
    "korean": ["korean_restaurant", "korean_barbecue_restaurant"],
    "vietnamese": ["vietnamese_restaurant"],
}
# Primary types that say nothing about cuisine: for these, the cuisine comes from secondary types.
# Any other primary type (grocery store, bakery, butcher, a different cuisine) is dropped.
GENERIC_PRIMARY = {"restaurant", "fast_food_restaurant", "family_restaurant", "meal_takeaway",
                   "sports_bar", "pub", "gastropub", "food_court", "bistro"}
# Primary types that are never a lunch restaurant; excluded at the API so they don't use up results
JUNK_PRIMARY = ["grocery_store", "supermarket", "market", "convenience_store", "discount_store",
                "discount_supermarket", "warehouse_store", "department_store", "food_store",
                "hypermarket", "butcher_shop", "bakery", "pastry_shop", "cake_shop", "cafe",
                "coffee_shop", "juice_shop", "ice_cream_shop", "dessert_shop", "donut_shop",
                "acai_shop", "candy_store", "confectionery", "liquor_store", "gas_station",
                "catering_service", "golf_course", "hotel", "tea_house"]
# Primary types that don't pin down a cuisine (Korean BBQ and Korean fried chicken use them too).
# A place with one of these as its primary type is dropped if it also looks like an unrequested cuisine.
AMBIGUOUS_PRIMARY = {"barbecue_restaurant", "chicken_restaurant", "chicken_wings_restaurant",
                     "bar_and_grill", "sandwich_shop", "deli", "hamburger_restaurant", "diner",
                     "breakfast_restaurant", "brunch_restaurant", "hot_dog_restaurant"}
# Name words that mark a cuisine (used only to catch places whose types are ambiguous)
NAME_CUISINE = {"korean": ["korean", "kimchi", "bulgogi", "bibimbap"],
                "mexican": ["taco", "taqueria", "mexican", "burrito", "tapatio", "cantina"],
                "japanese": ["sushi", "ramen", "japanese", "hibachi", "teriyaki"],
                "thai": ["thai "], "vietnamese": ["pho ", "vietnamese", "banh mi"]}
JUNK_NAMES = ["smoothie", "juice", "jewel-osco", "mariano's", "walmart", "costco", "target "]
ALIASES = {"pizza": "italian", "burgers": "american", "burger": "american",
           "sandwiches": "american", "bbq": "american", "middle_eastern": "middle eastern",
           "mideast": "middle eastern", "turkish": "mediterranean", "lebanese": "middle eastern"}
# exclude word -> (Places types, name keywords)
EXCLUDES = {
    "seafood": (["seafood_restaurant", "sushi_restaurant", "oyster_bar_restaurant",
                 "fish_and_chips_restaurant"],
                ["seafood", "fish", "crab", "lobster", "oyster", "shrimp", "sushi", "poke"]),
    "sushi": (["sushi_restaurant"], ["sushi"]),
    "steak": (["steak_house"], ["steak"]),
    "bar": (["bar", "pub", "sports_bar", "cocktail_bar"], []),
    "pizza": (["pizza_restaurant", "pizza_delivery"], ["pizza"]),
}
# Counter-service primary types. A low price alone does NOT make a place quick service.
QUICK_PRIMARY = {"fast_food_restaurant", "sandwich_shop", "deli", "food_court", "hot_dog_restaurant",
                 "hot_dog_stand", "snack_bar", "cafeteria", "chicken_restaurant",
                 "chicken_wings_restaurant", "hamburger_restaurant", "burrito_restaurant",
                 "taco_restaurant", "gyro_restaurant", "kebab_shop", "falafel_restaurant",
                 "shawarma_restaurant", "salad_shop", "meal_takeaway", "pizza_delivery"}
PRICE = {"PRICE_LEVEL_FREE": "$", "PRICE_LEVEL_INEXPENSIVE": "$", "PRICE_LEVEL_MODERATE": "$$",
         "PRICE_LEVEL_EXPENSIVE": "$$$", "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$"}
MEALS = {"breakfast": (7 * 60 + 30, 9 * 60 + 30), "lunch": (11 * 60 + 30, 13 * 60 + 30),
         "dinner": (17 * 60 + 30, 19 * 60 + 30)}
MIN_OVERLAP = 60           # minutes the place must be open inside the meal window
DAYNAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


class Fail(Exception):
    pass


class QuotaOut(Fail):
    pass


def reply(lines):
    print("REPLY START")
    for line in lines:
        print(line)
    print("REPLY END")


# ---------- input ----------
def parse_date(s, today):
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    for fmt in ("%m/%d", "%b %d", "%B %d", "%m-%d"):
        try:
            d = datetime.datetime.strptime(f"{s} {today.year}", fmt + " %Y").date()
            return d if d >= today else datetime.datetime.strptime(f"{s} {today.year + 1}", fmt + " %Y").date()
        except ValueError:
            pass
    raise Fail(f"bad date '{s}' (use YYYY-MM-DD)")


def parse_args(text, today):
    a = {}
    for part in text.replace("\n", ";").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            a[k.strip().lower()] = v.strip().strip('"').strip("'")
    if not a.get("address"):
        raise Fail("no address given")
    dates = a.get("dates", "")
    if not dates:
        raise Fail("no dates given")
    if ".." in dates:
        d1, d2 = dates.split("..", 1)
    elif " to " in dates:
        d1, d2 = dates.split(" to ", 1)
    else:
        d1 = d2 = dates
    start, end = parse_date(d1, today), parse_date(d2, today)
    if end < start or (end - start).days > 30:
        raise Fail(f"bad date range {start}..{end}")
    try:
        miles = float(a.get("miles", "3"))
        min_rating = float(a.get("min_rating", "0") or 0)
        min_reviews = int(float(a.get("min_reviews") or 20))
    except ValueError:
        raise Fail("miles, min_rating and min_reviews must be numbers")
    if not 0 < miles <= 30:
        raise Fail("miles must be between 0 and 30")
    words = [w.strip().lower() for w in re.split(r"[,/]", a.get("cuisine", "")) if w.strip()]
    words = [ALIASES.get(w, w) for w in words] or ["american", "chinese", "italian", "indian"]
    unknown = [w for w in words if w not in CUISINES]
    cuisines = [w for w in dict.fromkeys(words) if w in CUISINES]
    if not cuisines:
        raise Fail(f"no supported cuisine in '{a.get('cuisine')}' (supported: {', '.join(CUISINES)})")
    excl = [w.strip().lower() for w in a.get("exclude", "").split(",") if w.strip()]
    styles = [w.strip().lower() for w in a.get("style", "").split(",") if w.strip()] or ["any"]
    styles = ["quick" if s in ("fast", "quick service", "counter") else s for s in styles]
    meal = a.get("meal", "lunch").lower()
    if meal not in MEALS:
        meal = "lunch"
    return dict(address=a["address"], start=start, end=end, miles=miles, min_rating=min_rating,
                min_reviews=min_reviews, cuisines=cuisines, unknown=unknown, exclude=excl, styles=styles, meal=meal)


def api_key():
    k = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    if k:
        return k
    for p in KEY_SOURCES:
        try:
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GOOGLE_PLACES_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
                    if p.endswith("google_places_api_key") and line:
                        return line
        except OSError:
            pass
    raise Fail("no API key: add GOOGLE_PLACES_API_KEY=... to /Users/hermes/.hermes/.env")


# ---------- Places API ----------
def post(url, body, key, mask):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json", "X-Goog-Api-Key": key, "X-Goog-FieldMask": mask})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode())["error"]["message"]
        except Exception:
            msg = str(e)
        if e.code == 429 or "quota" in msg.lower():
            raise QuotaOut(f"Google's daily request quota is used up ({msg[:120]})")
        raise Fail(f"Places API error {e.code}: {msg[:200]}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise Fail(f"network error reaching Google: {e}")


def cache_dir():
    d = os.path.join(SKILL_DIR, "work", "cache")
    os.makedirs(d, exist_ok=True)
    return d


def prune_cache():
    try:
        d, cutoff = cache_dir(), time.time() - CACHE_DAYS * 86400
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if os.path.getmtime(p) < cutoff:
                os.remove(p)
    except OSError:
        pass


def cached_post(url, body, key, mask, state=None):
    """post() with a week-long disk cache keyed by the exact request. Errors are never cached."""
    import hashlib
    h = hashlib.sha256(json.dumps([url, body, mask], sort_keys=True).encode()).hexdigest()[:32]
    path = None
    try:
        path = os.path.join(cache_dir(), h + ".json")
        with open(path) as f:
            if state is not None:
                state["cached"] += 1
            return json.load(f)
    except (OSError, ValueError):
        pass
    r = post(url, body, key, mask)
    if state is not None:
        state["requests"] += 1
    try:
        with open(path, "w") as f:
            json.dump(r, f)
    except (OSError, TypeError):
        pass
    return r


def geocode(address, key):
    r = cached_post(TEXT_URL, {"textQuery": address}, key, "places.location,places.formattedAddress")
    if not r.get("places"):
        raise Fail(f"could not find the address '{address}'")
    p = r["places"][0]
    return p["location"]["latitude"], p["location"]["longitude"], p.get("formattedAddress", address)


def offset(lat, lng, dist_m, bearing_deg):
    b = math.radians(bearing_deg)
    dlat = dist_m * math.cos(b) / 111320.0
    dlng = dist_m * math.sin(b) / (111320.0 * math.cos(math.radians(lat)))
    return lat + dlat, lng + dlng


def run_searches(olat, olng, radius_m, cuisines, excl_types, key, state):
    """ONE Nearby Search per cuisine: any place with a cuisine type, minus junk primaries and
    other cuisines (excluded at the API). Searches are breadth-first: every cuisine gets its first
    search before any circle is split, and splits are taken round-robin across cuisines, nearest
    sub-circles first, so the request cap trims the far edges, never a whole cuisine."""
    requested = {t for c in cuisines for t in CUISINES[c]}
    other = sorted({t for c, ts in CUISINES.items() if c not in cuisines for t in ts} - requested)
    excl_primary = (JUNK_PRIMARY + other)[:50]
    jobs = []
    for c in cuisines:
        ctypes = [t for t in CUISINES[c] if t not in excl_types]
        if not ctypes:
            continue
        body = {"includedTypes": ctypes, "excludedPrimaryTypes": excl_primary}
        excl = sorted(set(excl_types) - set(ctypes))
        if excl:
            body["excludedTypes"] = excl
        jobs.append((c, body))
    km = lambda a, b, c, d: miles_between(a, b, c, d) * 1609.344
    level = [(j, olat, olng, radius_m) for j in range(len(jobs))]
    depth = 0
    while level:
        nxt = {}
        for idx, (j, lat, lng, r) in enumerate(level):
            c, tmpl = jobs[j]
            if state["requests"] + state["cached"] >= MAX_REQUESTS:   # cached count too: re-runs repeat exactly
                for jj, *_ in level[idx:]:
                    state["truncated"].add(jobs[jj][0])
                return
            body = dict(tmpl, maxResultCount=20, rankPreference="DISTANCE",
                        locationRestriction={"circle": {"center": {"latitude": round(lat, 6),
                                                                   "longitude": round(lng, 6)},
                                                        "radius": round(min(r, 50000.0), 1)}})
            try:
                places = cached_post(NEARBY_URL, body, key, FIELDS, state).get("places", [])
            except QuotaOut:
                state["quota_out"] = True
                for jj, *_ in level[idx:]:
                    state["truncated"].add(jobs[jj][0])
                return
            state["log"].append([c, depth, round(r), len(places)])
            for p in places:
                state["places"].setdefault(p["id"], p)
            if len(places) < 20:
                continue
            if depth >= MAX_DEPTH:
                state["truncated"].add(c)
                continue
            # Results are sorted by distance, so everything closer than the 20th is already found.
            loc = places[-1].get("location", {})
            known = km(lat, lng, loc.get("latitude", lat), loc.get("longitude", lng))
            r2 = r * 0.55          # 7 circles of radius >= R/2 cover a circle of radius R
            subs = [(lat, lng)] + [offset(lat, lng, r * 0.866, b) for b in range(0, 360, 60)]
            keep = []
            for slat, slng in subs:
                if km(lat, lng, slat, slng) + r2 <= known:        # fully inside the found area
                    continue
                if km(olat, olng, slat, slng) - r2 >= radius_m:    # entirely outside the search area
                    continue
                keep.append((km(olat, olng, slat, slng), (j, slat, slng, r2)))
            nxt.setdefault(j, []).extend(item for _, item in sorted(keep))
        queues = list(nxt.values())
        level = []
        while any(queues):                 # round-robin across cuisines
            for q in queues:
                if q:
                    level.append(q.pop(0))
        depth += 1


# ---------- filtering ----------
def miles_between(lat1, lng1, lat2, lng2):
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def open_intervals(hours):
    """Week-minute intervals [start, end) from regularOpeningHours.periods (day 0 = Sunday)."""
    out = []
    for per in hours.get("periods", []):
        o = per.get("open")
        if not o:
            continue
        c = per.get("close")
        s = o.get("day", 0) * 1440 + o.get("hour", 0) * 60 + o.get("minute", 0)
        if not c:                     # open 24 hours
            return [(0, 2 * 10080)]
        e = c.get("day", 0) * 1440 + c.get("hour", 0) * 60 + c.get("minute", 0)
        if e <= s:
            e += 10080
        out += [(s, e), (s + 10080, e + 10080)]
    return out


def meal_ok(intervals, gday, window):
    ws, we = gday * 1440 + window[0], gday * 1440 + window[1]
    need = min(MIN_OVERLAP, window[1] - window[0])
    for base in (0, 10080):
        for s, e in intervals:
            if min(e, we + base) - max(s, ws + base) >= need:
                return True
    return False


def style_of(p):
    types = set(p.get("types", []))
    prim = p.get("primaryType", "")
    price = p.get("priceLevel", "")
    if "fine_dining_restaurant" in types or price in ("PRICE_LEVEL_EXPENSIVE", "PRICE_LEVEL_VERY_EXPENSIVE"):
        return "upscale", "Upscale"
    if prim in QUICK_PRIMARY or "fast_food_restaurant" in types:
        return "quick", "Quick service"
    return "casual", "Casual"


def cuisine_of(p, wanted):
    """Cuisine from the PRIMARY type. A generic primary ("restaurant") falls back to secondary
    types. Anything else (grocery store, bakery, Korean BBQ when Korean wasn't asked) is dropped."""
    prim = p.get("primaryType", "")
    for c in wanted:
        if prim in CUISINES[c]:
            return c
    if not prim or prim in GENERIC_PRIMARY:
        types = set(p.get("types", []))
        for c in wanted:
            if types & set(CUISINES[c]):
                return c
    return None


def build_rows(state, args, olat, olng):
    excl_names = [kw for w in args["exclude"] for kw in EXCLUDES.get(w, ([], [w]))[1]]
    excl_types = {t for w in args["exclude"] for t in EXCLUDES.get(w, ([], []))[0]}
    requested = {t for c in args["cuisines"] for t in CUISINES[c]}
    other_types = {t for c, ts in CUISINES.items() if c not in args["cuisines"] for t in ts} - requested
    other_names = [w for c, ws in NAME_CUISINE.items() if c not in args["cuisines"] for w in ws]
    window = MEALS[args["meal"]]
    days = [args["start"] + datetime.timedelta(days=i) for i in range((args["end"] - args["start"]).days + 1)]
    rows, dropped = [], {"distance": 0, "rating": 0, "reviews": 0, "style": 0, "excluded": 0,
                         "closed": 0, "cuisine": 0}
    for p in state["places"].values():
        name = p.get("displayName", {}).get("text", "?")
        if p.get("businessStatus", "OPERATIONAL") != "OPERATIONAL":
            dropped["closed"] += 1
            continue
        loc = p.get("location", {})
        dist = miles_between(olat, olng, loc.get("latitude", 0), loc.get("longitude", 0))
        if dist > args["miles"]:
            dropped["distance"] += 1
            continue
        if set(p.get("types", [])) & excl_types or any(k in name.lower() for k in excl_names):
            dropped["excluded"] += 1
            continue
        lname = name.lower() + " "
        if any(k in lname for k in JUNK_NAMES):
            dropped["cuisine"] += 1
            continue
        prim = p.get("primaryType", "")
        if prim in AMBIGUOUS_PRIMARY or prim in GENERIC_PRIMARY or not prim:
            if set(p.get("types", [])) & other_types or any(k in lname for k in other_names):
                dropped["cuisine"] += 1          # e.g. Korean BBQ listed as barbecue_restaurant
                continue
        cuisine = cuisine_of(p, args["cuisines"])
        if not cuisine:
            dropped["cuisine"] += 1
            continue
        rating = p.get("rating")
        if args["min_rating"] and (rating is None or rating < args["min_rating"]):
            dropped["rating"] += 1
            continue
        if p.get("userRatingCount", 0) < args["min_reviews"]:
            dropped["reviews"] += 1
            continue
        skey, slabel = style_of(p)
        if "any" not in args["styles"] and skey not in args["styles"]:
            dropped["style"] += 1
            continue
        hours = p.get("regularOpeningHours")
        if hours and hours.get("periods"):
            iv = open_intervals(hours)
            closed = [d for d in days if not meal_ok(iv, (d.weekday() + 1) % 7, window)]
            if len(closed) == len(days):      # never open for this meal on any requested day
                dropped["closed"] += 1
                continue
            closed_txt = "none" if not closed else ", ".join(d.strftime("%a %b %-d") for d in closed)
            n_closed = len(closed)
        else:
            closed_txt, n_closed = "hours unknown", 99
        rows.append(dict(name=name, cuisine=cuisine.title(), style=slabel, dist=dist, rating=rating,
                         count=p.get("userRatingCount", 0), price=PRICE.get(p.get("priceLevel", ""), ""),
                         closed=closed_txt, n_closed=n_closed, addr=p.get("formattedAddress", ""),
                         phone=p.get("nationalPhoneNumber", ""), url=p.get("googleMapsUri", "")))
    rows.sort(key=lambda r: (min(r["n_closed"], 1), r["dist"]))
    return rows, dropped, days


def us_holidays(year):
    """Major US holidays when many restaurants change hours."""
    def nth(month, weekday, n):            # weekday: Mon=0; n=-1 means last
        if n > 0:
            d = datetime.date(year, month, 1)
            d += datetime.timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))
            return d
        d = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1) if month < 12 else datetime.date(year, 12, 31)
        return d - datetime.timedelta(days=(d.weekday() - weekday) % 7)
    return {datetime.date(year, 1, 1): "New Year's Day", nth(1, 0, 3): "Martin Luther King Jr. Day",
            datetime.date(year, 6, 19): "Juneteenth", datetime.date(year, 11, 11): "Veterans Day",
            nth(10, 0, 2): "Columbus Day", nth(5, 0, -1): "Memorial Day",
            datetime.date(year, 7, 4): "Independence Day", nth(9, 0, 1): "Labor Day",
            nth(11, 3, 4): "Thanksgiving", nth(11, 3, 4) + datetime.timedelta(days=1): "the day after Thanksgiving",
            datetime.date(year, 12, 24): "Christmas Eve", datetime.date(year, 12, 25): "Christmas",
            datetime.date(year, 12, 31): "New Year's Eve", nth(2, 0, 3): "Presidents' Day"}


# ---------- output ----------
def write_csv(rows, args):
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    n = 1
    while True:
        path = f"{OUT_DIR}/restaurants_{stamp}_{n}.csv"
        try:
            f = open(path, "x", newline="")
            break
        except FileExistsError:
            n += 1
    meal = args["meal"].title()
    with f:
        w = csv.writer(f)
        w.writerow(["Name", "Cuisine", "Style", "Miles (straight line)", "Rating", "Reviews", "Price",
                    f"Closed for {meal} (of requested days)", "Address", "Phone", "Google Maps"])
        for r in rows:
            w.writerow([r["name"], r["cuisine"], r["style"], f"{r['dist']:.1f}",
                        r["rating"] if r["rating"] is not None else "", r["count"], r["price"],
                        r["closed"], r["addr"], r["phone"], r["url"]])
    return path


def timing_line(marks):
    names = [m[0] for m in marks[1:]]
    parts = [f"{n} {marks[i + 1][1] - marks[i][1]:.1f}s" for i, n in enumerate(names)]
    total = marks[-1][1] - marks[0][1]
    return f"TIMING: {', '.join(parts)}, total {total:.1f}s", parts, total


def log_timing(marks, nreq, nrows):
    line, parts, total = timing_line(marks)
    try:
        p = os.path.join(SKILL_DIR, "timing_history.csv")
        new = not os.path.exists(p)
        with open(p, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["run_at"] + [m[0] for m in marks[1:]] + ["total_s", "api_requests", "results"])
            w.writerow([datetime.datetime.now().isoformat(timespec="seconds")]
                       + [f"{marks[i + 1][1] - marks[i][1]:.2f}" for i in range(len(marks) - 1)]
                       + [f"{total:.2f}", nreq, nrows])
    except OSError:
        pass
    return line


def save_debug(state, args, origin):
    try:
        d = os.path.join(SKILL_DIR, "work")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "last_run.json"), "w") as f:
            json.dump({"args": {k: str(v) for k, v in args.items()}, "origin": origin,
                       "requests": state["requests"], "truncated": sorted(state["truncated"]),
                       "cached": state["cached"], "quota_out": state["quota_out"],
                       "search_log [cuisine, depth, radius_m, results]": state["log"],
                       "places": list(state["places"].values())}, f, indent=1)
    except OSError:
        pass


def main(stdin_text, today=None, post_fn=None):
    global post
    if post_fn:
        post = post_fn
    marks = [("start", time.time())]
    today = today or datetime.date.today()
    try:
        args = parse_args(stdin_text, today)
        key = api_key()
        olat, olng, oaddr = geocode(args["address"], key)
        marks.append(("geocode", time.time()))
        prune_cache()
        state = {"places": {}, "requests": 0, "cached": 0, "truncated": set(), "log": [],
                 "quota_out": False}
        excl_types = {t for w in args["exclude"] for t in EXCLUDES.get(w, ([], []))[0]}
        run_searches(olat, olng, args["miles"] * 1609.344, args["cuisines"], excl_types, key, state)
        marks.append(("search", time.time()))
        save_debug(state, args, [olat, olng, oaddr])
        rows, dropped, days = build_rows(state, args, olat, olng)
        path = write_csv(rows, args)
        marks.append(("filter+write", time.time()))
    except Fail as e:
        marks.append(("failed", time.time()))
        reply([f"Restaurant search failed: {e}", timing_line(marks)[0]])
        return
    except Exception as e:  # never leave the model without a reply
        marks.append(("failed", time.time()))
        reply([f"Restaurant search failed: unexpected error {type(e).__name__}: {e}", timing_line(marks)[0]])
        return

    tline = (log_timing(marks, state["requests"], len(rows))
             + f" ({state['requests']} new API requests, {state['cached']} from cache)")
    span = f"{days[0].strftime('%a %b %-d')}" + (f" - {days[-1].strftime('%a %b %-d')}" if len(days) > 1 else "")
    crit = [", ".join(c.title() for c in args["cuisines"])]
    if args["min_rating"]:
        crit.append(f"rating {args['min_rating']:g}+")
    if args["min_reviews"]:
        crit.append(f"{args['min_reviews']}+ reviews")
    if "any" not in args["styles"]:
        crit.append("/".join(args["styles"]))
    if args["exclude"]:
        crit.append("no " + ", ".join(args["exclude"]))
    open_all = [r for r in rows if r["n_closed"] == 0]
    some_closed = [r for r in rows if 0 < r["n_closed"] < 99]
    unknown = [r for r in rows if r["n_closed"] == 99]
    counts = {}
    for r in rows:
        counts[r["cuisine"]] = counts.get(r["cuisine"], 0) + 1
    ndays = len(days)
    lines = [f"{args['meal'].title()} near {oaddr}, {span}",
             f"Filters: {'; '.join(crit)}; within {args['miles']:g} mi.",
             f"Found {len(rows)}: {len(open_all)} open all {ndays} days, "
             f"{len(some_closed)} closed on some days" + (f", {len(unknown)} with no hours listed." if unknown else "."),
             "By cuisine: " + ", ".join(f"{c.title()} {counts.get(c.title(), 0)}" for c in args["cuisines"]) + ".",
             "", f"Nearest open all {ndays} days:"]
    for i, r in enumerate(open_all[:REPLY_ROWS], 1):
        rt = f"{r['rating']:.1f}" if r["rating"] is not None else "n/a"
        lines.append(f"{i}. {r['name'][:38]} ({r['cuisine']}, {r['dist']:.1f} mi, {rt} stars)")
    if not open_all:
        lines.append("(none)")
    lines += ["", "The attached CSV lists all of them, with the days each one is closed."]
    notes = []
    if args["unknown"]:
        notes.append(f"Skipped unsupported cuisine: {', '.join(args['unknown'])}.")
    if state["quota_out"]:
        notes.append("PARTIAL RESULTS: Google's daily search quota ran out during this search. "
                     "Run it again after 2 a.m. Central; what was already found is reused for free.")
    elif state["truncated"]:
        notes.append("Dense area: the search hit its request cap for "
                     f"{', '.join(c.title() for c in sorted(state['truncated']))}, "
                     "so a few of those farthest away may be missing.")
    hol = {**us_holidays(days[0].year), **us_holidays(days[-1].year)}
    hits = [f"{hol[d]} ({d.strftime('%a %b %-d')})" for d in days if d in hol]
    notes.append("Holiday in these dates: " + ", ".join(hits) + (". Hours may differ that day." if len(hits) == 1 else ". Hours may differ those days.")
                 if hits else "No major holidays fall in these dates.")
    notes.append("Distances are straight-line.")
    lines += [""] + notes + [tline, "", f"MEDIA:{path}"]
    reply(lines)


if __name__ == "__main__":
    main(sys.stdin.read())
