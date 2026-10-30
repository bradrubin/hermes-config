# amazon-price-watch: runs INSIDE Hermes browser_exec (needs its cdp() helper):
#   ARGS = "cron"; exec(open("/Users/hermes/.hermes/skills/shopping/amazon-price-watch/price_watch.py").read(), globals())
# ARGS = "cron" -> no drops gives a [SILENT] reply (Hermes suppresses delivery).
# ARGS = ""     -> chat run; no drops gives a one-line "no drops" reply.
# Do not run from the terminal.
#
# How it works: open ONE Amazon product page in the real browser, then fetch every
# /dp/<id> page from inside that page (same-origin fetch) and parse title + price
# there. Plain HTTP and headless page loads get blocked by Amazon; this did not.


def _pw_main():
    import json, os, re, time, datetime

    SKILL_DIR = "/Users/hermes/.hermes/skills/shopping/amazon-price-watch"  # exec() has no __file__
    STATE_DIR = globals().get("PW_STATE_DIR", "/Users/hermes/.hermes/state/amazon-price-watch")
    ITEMS = os.path.join(STATE_DIR, "items.txt")
    PRICES = os.path.join(STATE_DIR, "prices.json")
    HISTORY = os.path.join(STATE_DIR, "timing_history.csv")
    DEBUG = os.path.join(STATE_DIR, "last_run.json")
    DROP = 5.00          # alert when price <= baseline - DROP
    FAIL_DAYS = 3        # report an item after this many runs in a row without a price
    FETCH_TIMEOUT = 240  # seconds for the whole in-page fetch loop

    args = str(globals().get("ARGS", "") or "").strip().lower()
    cron = "cron" in args
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
                f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S},{'cron' if cron else 'chat'},"
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
        finish((["[CRON_FAILURE]"] if cron else []) + [f"Amazon price check failed: {reason}"], "failed")

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

    # ---------- items ----------
    def isbn13_to_10(s):
        core = s[3:12]
        tot = sum(int(c) * w for c, w in zip(core, range(10, 1, -1)))
        chk = (11 - tot % 11) % 11
        return core + ("X" if chk == 10 else str(chk))

    try:
        raw = open(ITEMS).read()
    except FileNotFoundError:
        return fail(f"item list missing ({ITEMS}). Re-run the installer.")
    ids, seen = [], set()
    for line in raw.splitlines():
        tok = line.split("#", 1)[0].strip().replace("-", "").upper()
        if not tok:
            continue
        if re.fullmatch(r"97[89]\d{10}", tok) and tok.startswith("978"):
            tok = isbn13_to_10(tok)
        if not re.fullmatch(r"[A-Z0-9]{10}", tok):
            continue  # malformed line; ignored
        if tok not in seen:
            seen.add(tok)
            ids.append(tok)
    if not ids:
        return fail("item list is empty")

    try:
        state = json.load(open(PRICES))
    except FileNotFoundError:
        state = {}
    except Exception as e:
        return fail(f"prices.json unreadable ({e})")

    # ---------- open one Amazon page ----------
    try:
        _cdp("Page.enable")
    except Exception:
        pass
    try:
        _cdp("Page.navigate", url=f"https://www.amazon.com/dp/{ids[0]}")
    except Exception as e:
        return fail(f"could not open Amazon ({e})")
    ready = False
    for _ in range(60):
        time.sleep(0.5)
        try:
            if _eval("location.host.endsWith('amazon.com') && document.readyState") in ("interactive", "complete"):
                ready = True
                break
        except Exception:
            pass
    if not ready:
        return fail("Amazon page did not load within 30s")
    try:
        blocked = _eval("/captcha|Type the characters|continue shopping/i.test(document.body.innerText.slice(0,3000))"
                        " && !document.querySelector('#productTitle')")
    except Exception:
        blocked = False
    if blocked:
        ua = ""
        try:
            ua = _eval("(navigator.userAgent.includes('HeadlessChrome') ? 'headless Chrome' : 'Chrome')"
                       " + (navigator.webdriver ? ', webdriver=true' : '')")
        except Exception:
            pass
        try:  # record what Amazon showed, so a block can be diagnosed from one run
            info = {"run_at": datetime.datetime.now().isoformat(timespec="seconds"), "robot_check": True,
                    "browser": ua,
                    "url": _eval("location.href"), "title": _eval("document.title"),
                    "text": _eval("document.body.innerText.slice(0, 600)")}
            try:
                import base64
                shot = _cdp("Page.captureScreenshot", format="png")
                for _ in range(3):
                    if isinstance(shot, dict) and "data" not in shot and "result" in shot:
                        shot = shot["result"]
                png = os.path.join(STATE_DIR, "robot_check.png")
                with open(png, "wb") as f:
                    f.write(base64.b64decode(shot["data"]))
                info["screenshot"] = png
            except Exception:
                pass
            with open(DEBUG, "w") as f:
                json.dump(info, f, indent=1)
        except Exception:
            pass
        return fail(f"Amazon showed a robot check page ({ua or 'browser unknown'}). "
                    "Check that Hermes is attached to the real Chrome (browser.cdp_url).")
    mark("page_load")

    # ---------- fetch + parse every item from inside the page ----------
    js = r"""
window.__pw = null;
(async (ids) => {
  const out = [];
  for (const id of ids) {
    const rec = {id};
    try {
      const r = await fetch("/dp/" + id, {credentials: "include"});
      rec.status = r.status;
      const h = await r.text();
      if (/validateCaptcha|Type the characters you see/i.test(h)) { rec.err = "captcha"; out.push(rec); continue; }
      const d = new DOMParser().parseFromString(h, "text/html");
      const t = d.querySelector("#productTitle");
      rec.title = t ? t.textContent.trim().replace(/\s+/g, " ") : null;
      let p = null, src = null;
      const m = h.match(/"priceAmount":\s*([\d.]+)/);
      if (m) { p = parseFloat(m[1]); src = "buybox"; }
      const sel = d.querySelector("[id^=tmm-grid-swatch].selected, .swatchElement.selected, #tmmSwatches .selected");
      if (sel) {
        const fm = sel.textContent.match(/^\s*([A-Za-z][A-Za-z ,]*?)\s*\$/);
        if (fm) rec.format = fm[1];
        if (p === null) { const sp = sel.textContent.match(/\$([\d,]+\.\d\d)/); if (sp) { p = parseFloat(sp[1].replace(/,/g, "")); src = "format"; } }
      }
      if (p === null) {
        for (const s of ["#corePrice_feature_div .a-offscreen", "#apex_desktop .a-offscreen", "#kindle-price"]) {
          const e = d.querySelector(s); const sp = e && e.textContent.match(/\$([\d,]+\.\d\d)/);
          if (sp) { p = parseFloat(sp[1].replace(/,/g, "")); src = "fallback"; break; }
        }
      }
      rec.price = p; rec.src = src;
      if (!rec.title) rec.err = "no title (HTTP " + r.status + ")";
    } catch (e) { rec.err = String(e).slice(0, 80); }
    out.push(rec);
    await new Promise(res => setTimeout(res, 400 + Math.random() * 800));
  }
  return JSON.stringify(out);
})(IDS).then(v => { window.__pw = v; }, e => { window.__pw = JSON.stringify({fatal: String(e)}); });
true
""".replace("IDS", json.dumps(ids))
    try:
        _eval(js)
    except Exception as e:
        return fail(f"could not start the price fetch ({e})")
    res = None
    deadline = time.time() + FETCH_TIMEOUT
    while time.time() < deadline:
        time.sleep(2)
        try:
            res = _eval("window.__pw")
        except Exception:
            res = None
        if res:
            break
    if not res:
        return fail(f"price fetch did not finish within {FETCH_TIMEOUT}s")
    try:
        recs = json.loads(res)
    except Exception:
        return fail("price fetch returned unreadable data")
    if isinstance(recs, dict):
        return fail(f"price fetch error ({recs.get('fatal')})")
    mark("fetch")
    try:
        with open(DEBUG, "w") as f:
            json.dump({"run_at": datetime.datetime.now().isoformat(timespec="seconds"), "items": recs}, f, indent=1)
    except Exception:
        pass

    # ---------- compare with baselines ----------
    bad = [r for r in recs if r.get("err") or r.get("price") is None]
    if any(r.get("err") == "captcha" for r in recs) or len(bad) * 2 > len(recs):
        return fail(f"Amazon blocked or broke the page reads ({len(bad)} of {len(recs)} items unreadable). "
                    f"Details in {DEBUG}.")

    today = datetime.date.today().isoformat()
    alerts, problems, new_items = [], [], []
    for r in recs:
        s = state.setdefault(r["id"], {})
        if r.get("title"):
            s["title"] = r["title"]
        if r.get("format"):
            s["format"] = r["format"]
        p = r.get("price")
        if r.get("err") or p is None:
            s["fails"] = s.get("fails", 0) + 1
            if s["fails"] == FAIL_DAYS:
                problems.append(r["id"])
            continue
        s["fails"] = 0
        if s.get("baseline") is None:
            s["baseline"], s["baseline_date"] = p, today
            new_items.append(r["id"])
        s["last"], s["last_date"] = p, today
        if p <= s["baseline"] - DROP + 0.004:
            if s.get("alerted") is None or p < s["alerted"] - 0.004:
                alerts.append(r["id"])
                s["alerted"] = p
        else:
            s["alerted"] = None  # back above the line: a later drop alerts again
    for k in [k for k in state if k not in seen]:
        del state[k]  # removed from items.txt: forget it, so a re-add starts a new baseline
    tmp = PRICES + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
    os.replace(tmp, PRICES)
    mark("compare")

    def name(i):
        s = state[i]
        t = s.get("title") or i
        t = t if len(t) <= 70 else t[:67].rstrip() + "..."
        return f"{t} ({s['format']})" if s.get("format") else t

    lines = []
    if alerts:
        lines.append(f"Amazon price drop{'s' if len(alerts) > 1 else ''} ({len(alerts)} of {len(recs)} items):")
        for i in alerts:
            s = state[i]
            lines.append(f"- {name(i)}: now ${s['last']:.2f}, was ${s['baseline']:.2f} on {s['baseline_date']} "
                         f"(down ${s['baseline'] - s['last']:.2f}) https://www.amazon.com/dp/{i}")
    for i in problems:
        lines.append(f"- No price for {FAIL_DAYS} runs in a row: {name(i)} https://www.amazon.com/dp/{i}")
    if not lines:
        if cron:
            lines = [f"[SILENT] No price drops. {len(recs)} items checked."]
        else:
            lines = [f"No price drops today. {len(recs)} items checked."]
            if new_items:
                lines[0] += f" Started tracking {len(new_items)} new item{'s' if len(new_items) > 1 else ''}."
    finish(lines, "drops" if alerts else ("problems" if problems else "no_drops"))


try:
    _pw_main()
except Exception as _e:  # last-resort: always give the model a complete reply
    print("REPLY START")
    if "cron" in str(globals().get("ARGS", "")).lower():
        print("[CRON_FAILURE]")
    print(f"Amazon price check failed: unexpected error ({type(_e).__name__}: {str(_e)[:150]})")
    print("REPLY END")
