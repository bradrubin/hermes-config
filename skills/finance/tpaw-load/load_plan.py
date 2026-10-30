# TPAW plan loader. Runs INSIDE Hermes browser_exec (needs its cdp() and js() helpers):
#   exec(open("/Users/hermes/.hermes/skills/finance/tpaw-load/load_plan.py").read(), globals())
# Do not run from the terminal.
import base64, datetime, json, os, time

SKILL_DIR = "/Users/hermes/.hermes/skills/finance/tpaw-load"  # hard-coded: exec() has no __file__
ATTACH_DIR = "/Users/hermes/.hermes/attachments"
URL = "https://tpawplanner.com/guest"
TITLE_MARK = "(From File)"   # title becomes "Plan (From File) - TPAW Planner"
CLEAR_STORAGE = True         # start from a clean guest plan


def _mark(label):
    with open(os.path.join(SKILL_DIR, "timing.log"), "a") as f:
        f.write(f"{label} {time.time():.3f}\n")


def _cdp(method, **params):
    """Call a CDP method; tolerate either cdp(method, **kw) or cdp(method, dict)."""
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


def _wait(cond, timeout, step=0.25):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(step)
    return False


def _goto(url):
    _cdp("Page.navigate", url=url)
    time.sleep(0.5)  # let the previous document unload so readyState is the new page's
    return _wait(lambda: js("document.readyState") == "complete"
                 and "tpawplanner.com" in js("location.href"), 30)


def _screenshot():
    try:
        data = _cdp("Page.captureScreenshot", format="png").get("data")
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


def _expected():
    p = os.path.join(SKILL_DIR, "expect.txt")
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]


def _run(res):
    with open(os.path.join(SKILL_DIR, "current_plan.txt")) as f:
        plan = f.read().strip()
    res["plan"] = plan
    if not os.path.isfile(plan):
        raise RuntimeError(f"plan file not found: {plan}")

    # 1. Open the guest page (optionally wiping saved state first)
    if not _goto(URL):
        raise RuntimeError("tpawplanner.com/guest did not finish loading")
    if CLEAR_STORAGE:
        js("(localStorage.clear(), sessionStorage.clear(), true)")
        if not _goto(URL):
            raise RuntimeError("page did not reload after clearing storage")
    _mark("page_load")

    # 2. Find the hidden <input type=file> and hand it the file via CDP
    if not _wait(lambda: js("!!document.querySelector('input[type=file]')"), 20):
        raise RuntimeError("file input never appeared on the page")
    root = _cdp("DOM.getDocument", depth=0)["root"]["nodeId"]
    node = _cdp("DOM.querySelector", nodeId=root, selector='input[type="file"]').get("nodeId", 0)
    if not node:
        raise RuntimeError("DOM.querySelector found no file input")
    try:
        _cdp("DOM.setFileInputFiles", files=[plan], nodeId=node)
    except Exception:
        backend = _cdp("DOM.describeNode", nodeId=node)["node"]["backendNodeId"]
        _cdp("DOM.setFileInputFiles", files=[plan], backendNodeId=backend)
    _mark("file_set")

    # 3. Wait for the app to parse the file
    if not _wait(lambda: TITLE_MARK in (js("document.title") or ""), 30):
        raise RuntimeError(f"plan did not load (title is '{js('document.title')}')")
    res["title"] = js("document.title")
    _mark("plan_render")

    # 4. Content checks: requested balance (if any) + optional expect.txt values
    exp = _expected()
    bal_file = os.path.join(SKILL_DIR, "current_balance.json")
    bal = json.load(open(bal_file)) if os.path.exists(bal_file) else None
    if exp or bal:
        text = js("document.body.innerText") or ""
        if bal:
            res["balance_on_page"] = f"{bal['new']:,}" in text
        if exp:
            res["found"] = [e for e in exp if e in text]
            res["missing"] = [e for e in exp if e not in text]
    res["ok"] = True


_res = {"ok": False}
try:
    _run(_res)
except FileNotFoundError:
    _res["error"] = "setup.sh was not run first"
except Exception as _e:
    _res["error"] = str(_e)[:300]
finally:
    _res["screenshot"] = _screenshot()
    with open(os.path.join(SKILL_DIR, "last_result.json"), "w") as _f:
        json.dump(_res, _f)
    _mark("save")
    print("LOADED OK" if _res["ok"] else f"FAILED: {_res.get('error')}")
