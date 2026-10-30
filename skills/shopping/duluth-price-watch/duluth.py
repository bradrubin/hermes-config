# duluth-price-watch: runs INSIDE Hermes browser_exec (needs its cdp() helper):
#   ARGS = "cron"; exec(open("/Users/hermes/.hermes/skills/shopping/duluth-price-watch/duluth.py").read(), globals())
# ARGS words: "cron"           -> nothing to report gives a [SILENT] reply (Hermes suppresses delivery)
#             "threshold=NN"   -> test run with a different price limit; never changes saved state
# Do not run from the terminal.
#
# How it works: duluthtrading.com (Salesforce PWA Kit) blocks plain HTTP (Akamai), so open one product page in
# the real browser and call the site's own /api/ShopperProducts/getProducts from inside it, with the guest
# token the page keeps in localStorage. One call prices every color and size of both products.


def _dl_main():
    import json, os, re, time, datetime

    STATE_DIR = globals().get("DL_STATE_DIR", "/Users/hermes/.hermes/state/duluth-price-watch")
    COLORS = os.path.join(STATE_DIR, "solid_colors.txt")
    PRICES = os.path.join(STATE_DIR, "prices.json")
    HISTORY = os.path.join(STATE_DIR, "timing_history.csv")
    DEBUG = os.path.join(STATE_DIR, "last_run.json")
    START_URL = "https://www.duluthtrading.com/mens-buck-naked-boxers-81316.html?color=BAH"
    LIMIT = 15.00        # alert when one pair is at or under this
    FETCH_TIMEOUT = 60   # seconds for the in-page API call
    # id, name used in the reply, product page (the API's slugUrl must match), words the API name must contain
    PRODUCTS = [
        ("81316", "Men's Buck Naked Performance Boxers",
         "https://www.duluthtrading.com/mens-buck-naked-boxers-81316.html", "Buck Naked Boxers"),
        ("76015", "Men's Buck Naked Performance Boxer Briefs",
         "https://www.duluthtrading.com/mens-buck-naked-boxer-briefs-76015.html", "Buck Naked Boxer Briefs"),
    ]
    SEED = """# One color per line: solid|<color name>  or  pattern|<color name>  (names match case-insensitively).
# solid = a plain color. pattern = a print or graphic. A color that is not listed here is reported
# as "not sure" if it reaches the price limit, so a new color can never be missed.
solid|Black
solid|Graphite
solid|Dark Cobalt
solid|Blue Mercury
solid|Burgundy
solid|Brilliant Orange
solid|Pine Green
pattern|Fowl Language
pattern|Holiday Train
pattern|Honey Badger
pattern|Knotty
pattern|Balsam Green Cabin Wall
pattern|Cosmic Bowl
pattern|Miller High Life
pattern|Movie Theater
pattern|Venus Fly Trap
pattern|WD-40
"""

    args = str(globals().get("ARGS", "") or "").strip().lower()
    cron = bool(re.search(r"\bcron\b", args))
    test = False
    m = re.search(r"threshold\s*=\s*\$?(\d+(?:\.\d+)?)", args)
    if m:
        LIMIT, test = float(m.group(1)), True
    t0 = time.time()
    marks = []

    def mark(name):
        marks.append((name, time.time()))

    def timing_line():
        prev, parts = t0, []
        for name, t in marks:
            parts.append(f"{name} {t - prev:.1f}s")
            prev = t
        total = (marks[-1][1] if marks else time.time()) - t0
        return f"TIMING: total {total:.1f}s ({', '.join(parts)})", total, parts

    def finish(lines, status):
        tl, total, parts = timing_line()
        try:
            new = not os.path.exists(HISTORY)
            with open(HISTORY, "a") as f:
                if new:
                    f.write("run_at,mode,status,total_s,phases\n")
                f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S},{'test' if test else 'cron' if cron else 'chat'},"
                        f"{status},{total:.1f},\"{'; '.join(parts)}\"\n")
        except Exception:
            pass
        print("REPLY START")
        if lines and lines[0].startswith("[SILENT]"):
            lines = [f"{lines[0]} {tl}"]  # one line: Qwen drops a separate TIMING line from a silent reply
        else:
            lines = lines + [tl]
        for ln in lines:
            print(ln)
        print("REPLY END")

    def fail(reason):
        # Failures always reach Telegram: [CRON_FAILURE] alone on line 1 marks the run failed.
        mark("failed")
        finish((["[CRON_FAILURE]"] if cron else []) + [f"Duluth price check failed: {reason}"], "failed")

    # ---------- CDP helpers (tolerate either cdp(method, **kw) or cdp(method, dict)) ----------
    def _cdp(method, **params):
        try:
            return cdp(method, **params)
        except TypeError:
            return cdp(method, params)

    def _eval(expr):
        r = _cdp("Runtime.evaluate", expression=expr, returnByValue=True)
        for _ in range(4):  # unwrap {"result": {"result": {"value": ...}}} envelopes
            if not isinstance(r, dict):
                return r
            if "exceptionDetails" in r:
                raise RuntimeError(str(r["exceptionDetails"])[:200])
            if "value" in r:
                return r["value"]
            if "result" in r:
                r = r["result"]
            else:
                return None
        return None

    # ---------- color list (user-edited) ----------
    os.makedirs(STATE_DIR, exist_ok=True)
    if not os.path.exists(COLORS):
        with open(COLORS, "w") as f:
            f.write(SEED)
    kind = {}
    for line in open(COLORS).read().splitlines():
        if line.strip().startswith("#") or "|" not in line:
            continue
        k, name = line.split("|", 1)
        if k.strip().lower() in ("solid", "pattern") and name.strip():
            kind[name.strip().lower()] = k.strip().lower()
    try:
        state = json.load(open(PRICES))
    except FileNotFoundError:
        state = {}
    except Exception as e:
        return fail(f"prices.json unreadable ({e})")
    alerted = state.setdefault("alerted", {})

    # ---------- open one Duluth page ----------
    try:
        _cdp("Page.enable")
    except Exception:
        pass
    try:
        _cdp("Page.navigate", url=START_URL)
    except Exception as e:
        return fail(f"could not open duluthtrading.com ({e})")
    ready = False
    for _ in range(80):
        time.sleep(0.5)
        try:
            if _eval("location.host.endsWith('duluthtrading.com') && document.readyState === 'complete'"
                     " && !!localStorage.getItem('authToken')"):
                ready = True
                break
        except Exception:
            pass
    if not ready:
        try:
            title = _eval("document.title")
            where = _eval("location.href")
        except Exception:
            title, where = "?", "?"
        why = "the site blocked the page (Access Denied)" if "denied" in str(title).lower() else \
            f"the page did not finish loading within 40s (title: {str(title)[:60]})"
        try:
            with open(DEBUG, "w") as f:
                json.dump({"run_at": datetime.datetime.now().isoformat(timespec="seconds"), "load_failed": True,
                           "url": where, "title": title}, f, indent=1)
        except Exception:
            pass
        return fail(why)
    mark("page_load")

    # ---------- one in-page API call for both products ----------
    ids = ",".join(p[0] for p in PRODUCTS)
    js = r"""
window.__dl = null;
(async () => {
  const call = () => fetch("/api/ShopperProducts/getProducts", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify([{parameters: {locale: "default", ids: IDS, allImages: false, perPricebook: true},
                           headers: {Authorization: localStorage.getItem("authToken")}}])});
  let r = await call();
  if (r.status === 401) { await new Promise(x => setTimeout(x, 3000)); r = await call(); }
  return JSON.stringify({status: r.status, body: await r.text()});
})().then(v => { window.__dl = v; }, e => { window.__dl = JSON.stringify({status: 0, body: String(e).slice(0, 100)}); });
true
""".replace("IDS", json.dumps(ids))
    try:
        _eval(js)
    except Exception as e:
        return fail(f"could not start the price call ({e})")
    res = None
    deadline = time.time() + FETCH_TIMEOUT
    while time.time() < deadline:
        time.sleep(0.5)
        try:
            res = _eval("window.__dl")
        except Exception:
            res = None
        if res:
            break
    if not res:
        return fail(f"the price call did not finish within {FETCH_TIMEOUT}s")
    try:
        r = json.loads(res)
        if r.get("status") != 200:
            return fail(f"the price call returned HTTP {r.get('status')} ({str(r.get('body'))[:80]})")
        data = json.loads(r["body"])["data"]
    except Exception:
        return fail("the price call returned data that could not be read")
    mark("fetch")

    # ---------- per product, per color: lowest price among sizes that can be bought ----------
    table = []  # one dict per (product, color)
    byid = {str(d.get("id")): d for d in data}
    for pid, pname, purl, must in PRODUCTS:
        p = byid.get(pid)
        if not p:
            return fail(f"{pname} ({pid}) was missing from the price data")
        if must.lower() not in str(p.get("name", "")).lower():
            return fail(f"product {pid} is now called '{p.get('name')}', not {pname}. The site may have changed.")
        attrs = {a["id"]: {v["value"]: v["name"] for v in a["values"]} for a in p.get("variationAttributes", [])}
        cnames, sizes = attrs.get("color", {}), list(attrs.get("size", {}))
        best = {}  # color code -> {price: [sizes]}
        for v in p.get("variants", []):
            vv = v.get("variationValues", {})
            code, price = vv.get("color"), v.get("price")
            if not code or not isinstance(price, (int, float)) or not v.get("orderable"):
                continue  # sold-out sizes can show clearance prices; they cannot be bought
            best.setdefault(code, {}).setdefault(round(float(price), 2), []).append(vv.get("size"))
        if not best:
            return fail(f"no purchasable prices found for {pname}")
        for code, name in cnames.items():
            row = {"pid": pid, "product": pname, "code": code, "color": name,
                   "kind": kind.get(name.lower(), "unknown"), "price": None, "sizes": [],
                   "url": f"{purl}?color={code}"}
            if code in best:
                row["price"] = min(best[code])
                row["sizes"] = [s for s in sizes if s in best[code][row["price"]]]
                row["all_sizes"] = len(row["sizes"]) == len(sizes)
            table.append(row)
    priced = [r for r in table if r["price"] is not None]
    if any(not (1 <= r["price"] <= 500) for r in priced):
        return fail("a price outside $1 to $500 was returned, so the data looks wrong")
    try:
        with open(DEBUG, "w") as f:
            json.dump({"run_at": datetime.datetime.now().isoformat(timespec="seconds"), "limit": LIMIT, "test": test,
                       "colors": table}, f, indent=1)
    except Exception:
        pass

    # ---------- compare ----------
    hits = [r for r in priced if r["price"] <= LIMIT + 0.004 and r["kind"] != "pattern"]
    new_hits = []
    for r in hits:
        key = f"{r['pid']}|{r['code']}"
        a = alerted.get(key)
        if a is None or r["price"] < a - 0.004:
            new_hits.append(r)
    if not test:  # a test run must not mark anything as already alerted
        hit_keys = {f"{r['pid']}|{r['code']}": r["price"] for r in hits}
        for r in new_hits:
            alerted[f"{r['pid']}|{r['code']}"] = r["price"]
        for k in list(alerted):
            if k not in hit_keys:
                del alerted[k]  # back above the line or sold out: a later drop alerts again
        state["last_run"] = datetime.datetime.now().isoformat(timespec="seconds")
        tmp = PRICES + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=1, sort_keys=True)
        os.replace(tmp, PRICES)
    mark("compare")

    def line(r):
        sz = " (all sizes)" if r.get("all_sizes") else f" (sizes: {', '.join(r['sizes'])})" if r["sizes"] else ""
        return f"- {r['product']}: {r['color']} ${r['price']:.2f}{sz} {r['url']}"

    solid_hits = [r for r in new_hits if r["kind"] == "solid"]
    unsure = [r for r in new_hits if r["kind"] == "unknown"]
    lines = []
    if solid_hits:
        n = len(solid_hits)
        lines.append(f"Duluth price alert: {n} solid color{'s' if n > 1 else ''} at or under ${LIMIT:.2f} for one pair.")
        lines += [line(r) for r in solid_hits]
    if unsure:
        lines.append("Not sure if these colors are solid or patterned. Reply solid or pattern for each and I will record it:")
        lines += [line(r) for r in unsure]
    if lines:
        if test:
            lines.insert(0, f"(TEST RUN with limit ${LIMIT:.2f}. These are not real deals.)")
        status = "alert"
    else:
        solids = [r for r in priced if r["kind"] == "solid"]
        low = min(solids, key=lambda r: r["price"]) if solids else None
        msg = (f"No solid color is at or under ${LIMIT:.2f} for one pair. "
               f"{len(priced)} colors in stock across {len(PRODUCTS)} products were checked.")
        if low:
            msg += f" Lowest solid price: ${low['price']:.2f} ({low['product']}, {low['color']})."
        lines = [("[SILENT] " + msg) if cron else msg]
        status = "no_deal"
    finish(lines, status)


try:
    _dl_main()
except Exception as _e:  # last-resort: always give the model a complete reply
    print("REPLY START")
    if "cron" in str(globals().get("ARGS", "")).lower():
        print("[CRON_FAILURE]")
    print(f"Duluth price check failed: unexpected error ({type(_e).__name__}: {str(_e)[:150]})")
    print("REPLY END")
