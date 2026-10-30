# tpaw-load v3: the whole skill in one browser_exec call.
#   ARGS = "1468825"; exec(open("/Users/hermes/.hermes/skills/finance/tpaw-load/tpaw.py").read(), globals())
# ARGS (optional): a dollar amount for the new portfolio balance and/or a plan .txt path.
# Always ends by printing a REPLY START / REPLY END block, even on failure.
# Everything lives inside one function so it doesn't clutter the browser session's globals,
# and nothing is imported from the skill folder (the session caches imports across calls).

def _tpaw_main(args):
    import base64, copy, csv, datetime, json, os, re, time, uuid

    SKILL_DIR = "/Users/hermes/.hermes/skills/finance/tpaw-load"   # exec() has no __file__
    ATTACH_DIR = "/Users/hermes/.hermes/attachments"
    URL = "https://tpawplanner.com/guest"
    TITLE_MARK = "(From File)"
    MARKER = "---- PLAN DATA STARTS HERE ----"

    class Stop(Exception):
        pass

    marks = [("start", time.time())]
    def mark(label):
        marks.append((label, time.time()))

    # ---------- setup ----------
    def parse_args(s):
        plan, bal = "", ""
        for tok in re.findall(r'"[^"]*"|\'[^\']*\'|\S+', s or ""):
            tok = tok.strip("\"'")
            if tok.lower().endswith(".txt") or "/" in tok:
                plan = tok
            elif tok:
                bal = tok
        return plan, bal

    def default_plan():
        p = os.path.join(SKILL_DIR, "plan_path.txt")
        if not os.path.exists(p):
            raise Stop(f"missing {p}")
        with open(p) as f:
            for line in f:
                line = line.strip().rstrip("\r")
                if line and not line.startswith("#"):
                    return line
        raise Stop("no plan file set in plan_path.txt")

    def parse_amount(s):
        t = s.strip().lower().replace("$", "").replace(",", "").replace("_", "")
        m = re.fullmatch(r"(\d+(?:\.\d+)?)([km]?)", t)
        if not m:
            raise Stop(f"not a dollar amount: {s}")
        v = int(round(float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6}[m.group(2)]))
        if not 1 <= v <= 10_000_000_000:
            raise Stop(f"balance out of range: {v}")
        return v

    # ---------- plan file patching ----------
    def apply(doc, ops):
        for op in ops:
            parts = [p.replace("~1", "/").replace("~0", "~") for p in op["path"].split("/")[1:]]
            if not parts:
                doc = copy.deepcopy(op["value"])
                continue
            c = doc
            for p in parts[:-1]:
                c = c[int(p)] if isinstance(c, list) else c[p]
            k = parts[-1]
            if isinstance(c, list):
                k = len(c) if k == "-" else int(k)
                if op["op"] == "add":
                    c.insert(k, copy.deepcopy(op["value"]))
                elif op["op"] == "remove":
                    c.pop(k)
                else:
                    c[k] = copy.deepcopy(op["value"])
            elif op["op"] == "remove":
                del c[k]
            else:
                c[k] = copy.deepcopy(op["value"])
        return doc

    def replay(hist):
        doc = {}
        for e in hist:
            doc = apply(doc, e["diff"])
        return doc

    def compare(old, new):
        """Port of fast-json-patch compare(), which TPAW uses to record each change.
        Reproduces all 212 recorded diffs in Brad's 2026 plan exactly (key order included)."""
        out = []
        esc = lambda k: str(k).replace("~", "~0").replace("/", "~1")
        keys = lambda o: [str(i) for i in range(len(o))] if isinstance(o, list) else list(o)
        get = lambda o, k: o[int(k)] if isinstance(o, list) else o[k]
        has = lambda o, k: (0 <= int(k) < len(o)) if isinstance(o, list) else k in o
        def same(a, b):
            if isinstance(a, bool) or isinstance(b, bool):
                return type(a) is type(b) and a == b
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                return a == b
            return type(a) is type(b) and a == b
        def gen(m, o, path):
            if m is o:
                return
            nk, ok, deleted = keys(o), keys(m), False
            for key in reversed(ok):
                ov = get(m, key)
                if has(o, key):
                    nv = get(o, key)
                    if (isinstance(ov, (dict, list)) and isinstance(nv, (dict, list))
                            and isinstance(ov, list) == isinstance(nv, list)):
                        gen(ov, nv, path + "/" + esc(key))
                    elif not same(ov, nv):
                        out.append({"op": "replace", "path": path + "/" + esc(key), "value": copy.deepcopy(nv)})
                elif isinstance(m, list) == isinstance(o, list):
                    out.append({"op": "remove", "path": path + "/" + esc(key)})
                    deleted = True
                else:
                    out.append({"op": "replace", "path": path, "value": copy.deepcopy(o)})
            if not deleted and len(nk) == len(ok):
                return
            for key in nk:
                if not has(m, key):
                    out.append({"op": "add", "path": path + "/" + esc(key), "value": copy.deepcopy(get(o, key))})
        gen(old, new, "")
        return out

    def roll_months(o, ym):
        """Like the app: the first change in a new month moves every 'now' monthOfEntry to that month."""
        if isinstance(o, dict):
            moe = o.get("monthOfEntry")
            if isinstance(moe, dict) and isinstance(moe.get("calendarMonth"), dict):
                moe["calendarMonth"]["year"], moe["calendarMonth"]["month"] = ym
            for v in o.values():
                roll_months(v, ym)
        elif isinstance(o, list):
            for v in o:
                roll_months(v, ym)

    def read_plan(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if MARKER not in text:
            raise Stop(f"{os.path.basename(path)} is not a TPAW plan file (restore it from a backup)")
        head, body = text.split(MARKER, 1)
        try:
            plan = json.loads(body)
            hist = plan["planParamsHistory"]
            state = replay(hist[: len(hist) - int(plan.get("reverseHeadIndex", 0) or 0)])
            state["wealth"]["portfolioBalance"]
        except Stop:
            raise
        except Exception:
            raise Stop(f"{os.path.basename(path)} is damaged (restore it from a backup)")
        return head, body[: len(body) - len(body.lstrip())], plan, state

    def patch(src, amount):
        head, lead, plan, state = read_plan(src)
        hist = plan["planParamsHistory"]
        rhi = int(plan.get("reverseHeadIndex", 0) or 0)
        if rhi:  # drop undone entries, as the app does on a new change
            hist = hist[: len(hist) - rhi]
        # Build the new state the way the app does, then record it with the app's diff method.
        pb = state["wealth"]["portfolioBalance"]
        if pb.get("updatedHere"):
            old, old_ts = pb.get("amount"), state.get("timestamp")
        else:
            old, old_ts = pb.get("updatedTo"), pb.get("updatedAtTimestamp")
        new = copy.deepcopy(state)
        now = datetime.datetime.now()
        roll_months(new, (now.year, now.month))
        npb = new["wealth"]["portfolioBalance"]
        for k in ("updatedAtTimestamp", "updatedTo", "updatedAtId"):
            npb.pop(k, None)
        npb["updatedHere"] = True
        npb["amount"] = amount
        now_ms = max(int(time.time() * 1000), int(state.get("timestamp", 0)) + 1)
        new["timestamp"] = now_ms
        hist.append({"id": str(uuid.uuid4()),
                     "change": {"type": "setCurrentPortfolioBalance", "value": amount},
                     "diff": compare(state, new)})
        plan["planParamsHistory"] = hist
        plan["reverseHeadIndex"] = 0
        plan["lastSavedTimestamp"] = now_ms
        if replay(hist) != new:
            raise Stop("balance patch failed verification")
        out_dir = os.path.join(SKILL_DIR, "work")
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, os.path.basename(src))
        with open(out, "w", encoding="utf-8") as f:
            f.write(head + MARKER + lead + json.dumps(plan, separators=(",", ":"), ensure_ascii=False))
        return out, old, old_ts

    # ---------- browser ----------
    def C(method, **params):
        try:
            r = cdp(method, **params)
        except TypeError:
            r = cdp(method, params)
        if isinstance(r, dict):
            if r.get("error"):
                raise RuntimeError(f"{method}: {r['error']}")
            if isinstance(r.get("result"), dict):
                r = r["result"]
        return r if r is not None else {}

    def wait(cond, timeout, step=0.25):
        end = time.time() + timeout
        while time.time() < end:
            try:
                if cond():
                    return True
            except Exception:
                pass
            time.sleep(step)
        return False

    def goto(url):
        C("Page.navigate", url=url)
        time.sleep(0.5)
        return wait(lambda: js("document.readyState") == "complete"
                    and "tpawplanner.com" in js("location.href"), 30)

    def scroll_to(text):
        t = json.dumps(text)
        try:
            return bool(js("(() => { const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);"
                           " let n; while ((n = w.nextNode())) { if (n.textContent.includes(" + t + ")) {"
                           " n.parentElement.scrollIntoView({block: 'center'}); return true; } } return false; })()"))
        except Exception:
            return False

    def screenshot(clip=None):
        try:
            p = {"format": "png"}
            if clip:
                p["clip"] = clip
            data = C("Page.captureScreenshot", **p).get("data")
            if not data:
                return ""
            os.makedirs(ATTACH_DIR, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
            n = 1
            while True:
                path = f"{ATTACH_DIR}/tpaw_plan_{stamp}_{n}.png"
                try:
                    f = open(path, "xb")
                    break
                except FileExistsError:
                    n += 1
            with f:
                f.write(base64.b64decode(data))
            return path
        except Exception:
            return ""

    # Installed before the page loads: records every number the page draws on a <canvas>, with
    # its position, opacity and text baseline, on canvas.__ft. In TPAW (github.com/bengmathew/tpaw,
    # ChartSalientPoints.ts) the chart's point labels are the only text drawn with
    # textBaseline 'bottom' (y-axis: 'middle', x-axis: 'top', hover box: 'alphabetic'), and
    # duplicate or overlapping labels are drawn with opacity 0.
    HOOK_JS = r"""(() => {
      if (window.__tpawHook) return; window.__tpawHook = 1;
      const P = CanvasRenderingContext2D.prototype;
      const rec = (ctx, a) => {
        const t = String(a[0]); if (!/\d/.test(t)) return;
        let x = a[1], y = a[2];
        try { const m = ctx.getTransform(); x = m.a*a[1] + m.c*a[2] + m.e; y = m.b*a[1] + m.d*a[2] + m.f; } catch (e) {}
        const c = ctx.canvas; if (!c.__ft) c.__ft = [];
        c.__ft.push({t, x, y, b: ctx.textBaseline, al: ctx.globalAlpha, ts: performance.now()});
        if (c.__ft.length > 4000) c.__ft.splice(0, 2000);
      };
      for (const k of ['fillText', 'strokeText']) {
        const o = P[k];
        P[k] = function (...a) { try { rec(this, a); } catch (e) {} return o.apply(this, a); };
      }
      const cr = P.clearRect;  // TPAW's Chart.draw() clears the whole canvas: a new frame starts
      P.clearRect = function (x, y, w, h) {
        try { const m = this.getTransform();
          if (w * m.a >= this.canvas.width - 1 && h * m.d >= this.canvas.height - 1) this.canvas.__ft = []; } catch (e) {}
        return cr.apply(this, arguments);
      };
    })();"""

    # Each canvas: position, nearest label text, and the numbers drawn in its latest frame.
    CANVAS_JS = r"""JSON.stringify([...document.querySelectorAll('canvas')].map((c, i) => {
      const r = c.getBoundingClientRect(); let p = c.parentElement, lab = '';
      for (let k = 0; k < 10 && p; k++, p = p.parentElement) {
        const t = (p.innerText || '').trim(); if (t) { lab = t.slice(0, 300); break; } }
      const f = c.__ft || [], last = f.length ? f[f.length - 1].ts : 0;
      const sx = r.width / (c.width || 1), sy = r.height / (c.height || 1);
      return {i, x: r.left, y: r.top, w: r.width, h: r.height, sx: window.scrollX, sy: window.scrollY,
              label: lab, n: f.length,
              recs: [...new Map(f.filter(e => e.ts >= last - 100)
                .map(e => ({t: e.t, x: Math.round(e.x * sx), y: Math.round(e.y * sy), b: e.b, al: e.al}))
                .map(e => [e.t + '|' + e.x + '|' + e.y + '|' + (e.al > 0.01), e])).values()]};
    }))"""

    def canvases():
        try:
            return json.loads(js(CANVAS_JS) or "[]")
        except Exception:
            return []

    def monies(t):
        """Every dollar amount in a piece of text."""
        out = []
        for m in re.finditer(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s?([KkMm](?![a-z]))?", t):
            v = float(m.group(1).replace(",", "")) * {"": 1, "k": 1e3, "m": 1e6}[(m.group(2) or "").lower()]
            out.append({"text": m.group(0).strip(), "value": int(round(v)), "exact": not m.group(2)})
        return out

    def first_point(c):
        """Leftmost visible point label(s); if the 5th/50th/95th labels differ, the median."""
        pts = [dict(m, x=r["x"], y=r["y"]) for r in c["recs"]
               if r.get("b") == "bottom" and (r.get("al") or 0) > 0.01 for m in monies(r["t"])]
        if not pts:
            return None, []
        x0 = min(p["x"] for p in pts)
        left = sorted([p for p in pts if p["x"] <= x0 + 3], key=lambda p: p["value"])
        return left[len(left) // 2], left

    def read_chart(dbg):
        """First-point value of the 'Monthly Spending During Retirement' chart."""
        cs = canvases()
        if not cs:
            dbg["canvases"] = []
            return None, None
        pick = [c for c in cs if "spending" in c["label"].lower()] or cs
        ci = max(pick, key=lambda c: c["w"] * c["h"])["i"]
        dbg["chart_canvas"] = ci
        js(f"(document.querySelectorAll('canvas')[{ci}].scrollIntoView({{block: 'center'}}), true)")
        # Wait for the simulation and animations to settle: the same value for ~2.4 s (6 polls).
        hist, c, val, left = [], None, None, []
        end = time.time() + 25
        while time.time() < end:
            time.sleep(0.4)
            c = next((d for d in canvases() if d["i"] == ci), None)
            if not c:
                continue
            val, left = first_point(c)
            # TPAW shows "calculating..." (PlanResultsLoading.tsx) once a run passes 750 ms,
            # so a stale value can't survive this 2.4 s window.
            busy = "calculating..." in (js("document.body.innerText") or "")
            hist.append("busy" if busy else (val["value"] if val else None))
            if len(hist) >= 6 and hist[-1] not in (None, "busy") and len(set(hist[-6:])) == 1:
                break
        dbg["canvases"] = [{k: d[k] for k in ("i", "x", "y", "w", "h", "n")} | {"label": d["label"][:80],
                           "recs": d["recs"][:80]} for d in canvases()]
        dbg["first_point_labels"] = left
        dbg["poll_values"] = hist
        if val and (len(hist) < 6 or len(set(hist[-6:])) != 1):
            val = dict(val, unsettled=True)
        return val, c

    def read_tasks(dbg):
        """Stocks / bonds % from the Tasks card (PlanResultsSidePanelTasksCard.tsx):
        'Rebalance' / 'Stocks' / '34%' / 'Bonds' / '66%', each on its own line."""
        text = js("document.body.innerText") or ""
        i = text.find("Rebalance")
        seg = text[i:i + 300] if i >= 0 else ""
        dbg["tasks_text"] = seg or text[:1500]
        def pct(word):
            m = re.search(word + r"\s*:?\s*(\d{1,3}(?:\.\d+)?)\s*%", seg, re.I)
            return m.group(1) if m else None
        return pct("stocks"), pct("bonds")

    def load(plan_file, expect_text):
        try:  # fixed desktop layout so the chart labels render the same every time
            C("Emulation.setDeviceMetricsOverride", width=1400, height=1000, deviceScaleFactor=1, mobile=False)
        except Exception:
            pass
        try:
            C("Page.enable")
        except Exception:
            pass
        C("Page.addScriptToEvaluateOnNewDocument", source=HOOK_JS)
        if not goto(URL):
            raise Stop("tpawplanner.com/guest did not finish loading")
        js("(localStorage.clear(), sessionStorage.clear(), true)")
        if not goto(URL):
            raise Stop("page did not reload after clearing storage")
        mark("page_load")
        if not wait(lambda: js("!!document.querySelector('input[type=file]')"), 20):
            raise Stop("file input never appeared on the page")
        root = C("DOM.getDocument", depth=0)["root"]["nodeId"]
        node = C("DOM.querySelector", nodeId=root, selector='input[type="file"]').get("nodeId", 0)
        if not node:
            raise Stop("DOM.querySelector found no file input")
        try:
            C("DOM.setFileInputFiles", files=[plan_file], nodeId=node)
        except Exception:
            backend = C("DOM.describeNode", nodeId=node)["node"]["backendNodeId"]
            C("DOM.setFileInputFiles", files=[plan_file], backendNodeId=backend)
        mark("file_set")
        state = {}
        def done():
            if TITLE_MARK in (js("document.title") or ""):
                return True
            if "Not a valid" in (js("document.body.innerText") or ""):
                state["invalid"] = True
                return True
            return False
        if not wait(done, 30):
            raise Stop(f"plan did not load (page title is '{js('document.title')}')")
        if state.get("invalid"):
            which = "the copy with the new balance" if "/work/" in plan_file else "your original plan file"
            raise Stop(f"TPAW says {which} is not a valid plan")
        mark("plan_render")
        text = js("document.body.innerText") or ""
        return js("document.title"), text

    # ---------- balance from Google Sheets (used when no amount is given) ----------
    def sheet_config():
        p = os.path.join(SKILL_DIR, "balance_source.txt")
        if not os.path.exists(p):
            raise Stop(f"no amount given and {p} is missing")
        cfg = {}
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip().lower()] = v.strip()
        for k in ("sheet_id", "sheet", "cell"):
            if not cfg.get(k):
                raise Stop(f"balance_source.txt is missing '{k} = ...'")
        return cfg

    def find_google_api(cfg):
        p = os.path.expanduser(cfg.get("google_api", ""))
        if p and os.path.isfile(p):
            return p
        import glob
        hits = sorted(glob.glob(os.path.expanduser("~/.hermes/skills/**/google_api.py"), recursive=True))
        if not hits:
            raise Stop("couldn't find the Google Workspace skill's google_api.py "
                       "(set google_api = <path> in balance_source.txt)")
        return hits[0]

    def first_value(d):
        """First cell value in a Sheets API values.get response (or whatever the wrapper prints)."""
        if isinstance(d, dict):
            for k in ("values", "value", "result", "data"):
                if k in d:
                    v = first_value(d[k])
                    if v is not None:
                        return v
            return None
        if isinstance(d, list):
            for x in d:
                v = first_value(x)
                if v is not None:
                    return v
            return None
        return d if str(d).strip() else None

    def balance_from_sheet():
        """Read the balance cell with the Hermes Google Workspace skill's CLI:
        python google_api.py sheets get <sheet_id> "AA!D20"  (Sheets API spreadsheets.values.get)."""
        import subprocess
        cfg = sheet_config()
        tool = find_google_api(cfg)
        rng = f"{cfg['sheet']}!{cfg['cell']}"
        cmd = [cfg.get("python") or "python3", tool, "sheets", "get", cfg["sheet_id"], rng]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=45, cwd=os.path.dirname(tool))
        except Exception as e:
            raise Stop(f"couldn't run google_api.py: {type(e).__name__}: {e}")
        out = (r.stdout or "").strip()
        if r.returncode != 0:
            err = ((r.stderr or out).strip().splitlines() or ["no output"])[-1]
            raise Stop(f"Google Sheets read failed: {err[:200]}")
        try:
            v = first_value(json.loads(out))
        except ValueError:
            v = out   # not JSON: use the printed text as-is
        if v is None:
            raise Stop(f"the Google Sheet cell {rng} is empty")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            amount = int(round(v))
            if not 1 <= amount <= 10_000_000_000:
                raise Stop(f"balance out of range: {amount}")
        else:
            m = re.search(r"\$?\s?\d[\d,]*(?:\.\d+)?", str(v))
            if not m:
                raise Stop(f"the Google Sheet cell {rng} isn't a dollar amount: {str(v)[:60]}")
            amount = parse_amount(m.group(0))   # e.g. "$1,468,825.00" -> 1468825
        return amount, rng, "google_api.py"

    # ---------- run ----------
    lines, shot, ok, browser_used = [], "", False, False
    try:
        plan_arg, bal_arg = parse_args(args)
        plan = os.path.expanduser(plan_arg or default_plan())
        if not os.path.isfile(plan):
            raise Stop(f"plan file not found: {plan}")
        if not plan.lower().endswith(".txt"):
            raise Stop(f"plan file must be a TPAW .txt export: {plan}")
        try:  # fail fast, before the sheet read
            with open(plan, "rb") as f:
                f.read(1)
        except PermissionError as e:
            if e.errno == 1:  # EPERM = macOS privacy (TCC) block, not file permissions
                raise Stop(f"macOS blocked reading {plan} (privacy protection on Documents/Desktop/"
                           "Downloads for scheduled jobs). Move the plan out of those folders and "
                           "update plan_path.txt")
            raise Stop(f"no permission to read {plan}")
        bal_source = None
        if bal_arg:
            bal = parse_amount(bal_arg)
        else:
            bal, cell, how = balance_from_sheet()
            bal_source = f"Google Sheet {cell}"
            mark("sheet")
        to_load, old, old_ts = patch(plan, bal)
        mark("patch")

        browser_used = True
        title, text = load(to_load, bal)
        lines.append(f"TPAW plan loaded: {os.path.basename(plan)}")
        lines.append(f"Page: {title}")
        if bal is not None:
            fmt = f"{bal:,}"
            line = f"Portfolio balance set to ${fmt}" + (f" (from {bal_source})" if bal_source else "")
            if old is not None:
                when = (" on " + datetime.date.fromtimestamp(old_ts / 1000).isoformat()) if old_ts else ""
                line += f" (last entered ${old:,}{when})"
            line += "; shown on page" if fmt in text else "; NOT found on page, check the screenshot"
            lines.append(line)

        # Results: monthly spending (chart, first point), then stocks % (Tasks card).
        dbg = {}
        try:
            spend, c = read_chart(dbg)
        except Exception as e:
            spend, c = None, None
            dbg["chart_error"] = repr(e)
        dbg["spending"] = spend
        if spend:
            lines.append(f"Monthly spending (first point): ${spend['value']:,}"
                         + ("" if spend["exact"] else f" (chart shows {spend['text']})")
                         + (" (chart was still changing, check the screenshot)" if spend.get("unsettled") else ""))
        else:
            lines.append("Monthly spending (first point): not found (see work/extract_debug.json)")
        if c:
            pad = 30
            shot = screenshot({"x": max(0, c["x"] + c["sx"] - pad), "y": max(0, c["y"] + c["sy"] - pad),
                               "width": c["w"] + 2 * pad, "height": c["h"] + 2 * pad, "scale": 1})
        mark("chart")
        try:
            stocks, bonds = read_tasks(dbg)
        except Exception as e:
            stocks, bonds = None, None
            dbg["tasks_error"] = repr(e)
        if stocks:
            lines.append(f"Stocks: {stocks}%" + (f" (bonds {bonds}%)" if bonds else ""))
        else:
            lines.append("Stocks: not found (see work/extract_debug.json)")
        mark("tasks")
        try:
            os.makedirs(os.path.join(SKILL_DIR, "work"), exist_ok=True)
            with open(os.path.join(SKILL_DIR, "work", "extract_debug.json"), "w") as f:
                json.dump(dbg, f, indent=1, default=str)
        except Exception:
            pass
        exp_file = os.path.join(SKILL_DIR, "expect.txt")
        if os.path.exists(exp_file):
            with open(exp_file) as f:
                exp = [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]
            missing = [e for e in exp if e not in text]
            if missing:
                lines.append("Missing expected values: " + ", ".join(missing))
            elif exp:
                lines.append(f"Checks: all {len(exp)} expected values found")
        ok = True
    except Stop as e:
        lines = [f"TPAW plan load failed: {e}"]
    except Exception as e:
        lines = [f"TPAW plan load failed: {type(e).__name__}: {str(e)[:250]}"]
    if browser_used and not shot:
        time.sleep(0.3)
        shot = screenshot()
    mark("verify")

    # ---------- timing ----------
    phases = [(marks[i][0], marks[i][1] - marks[i - 1][1]) for i in range(1, len(marks))]
    total = marks[-1][1] - marks[0][1]
    lines.append(f"TIMING: total {total:.1f}s (" + ", ".join(f"{n} {s:.1f}s" for n, s in phases) + ")")
    try:
        hist = os.path.join(SKILL_DIR, "timing_history.csv")
        new = not os.path.exists(hist)
        with open(hist, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["timestamp", "ok", "total_s", "phases"])
            w.writerow([datetime.datetime.now().isoformat(timespec="seconds"), ok,
                        f"{total:.1f}", "; ".join(f"{n}={s:.1f}" for n, s in phases)])
    except Exception:
        pass
    if shot:
        lines += ["", f"MEDIA:{shot}"]

    print("REPLY START")
    print("\n".join(lines))
    print("REPLY END")


_tpaw_main(globals().get("ARGS", ""))
