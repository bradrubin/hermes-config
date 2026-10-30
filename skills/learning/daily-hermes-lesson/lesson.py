#!/usr/bin/env python3
"""Pick today's Hermes lesson, record it, and print a brief for the model.

Usage: python3 lesson.py [topic words]
  No argument: the least-taught topic, in curriculum order (never the one taught last).
  With words:  the topic whose id or title matches them (e.g. "cron", "fastmail email").

The topic is recorded BEFORE the model writes the lesson, so the next run can
never repeat it, even if this session fails. History lives outside the skill
folder so a clean reinstall keeps it.
"""
import csv, datetime, os, sys, time

T0 = time.time()
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
CURRICULUM = os.path.join(SKILL_DIR, "curriculum.txt")
STATE_DIR = "/Users/hermes/.hermes/state/daily-hermes-lesson"
if not os.path.isdir("/Users/hermes"):  # local testing off the Mac Mini
    STATE_DIR = os.path.join(SKILL_DIR, "work")
HISTORY = os.path.join(STATE_DIR, "history.csv")
TIMING_HISTORY = os.path.join(STATE_DIR, "timing_history.csv")
FIELDS = ("id", "title", "facts", "example", "review")


def reply_fail(reason):
    print("LESSON BRIEF START")
    print(f"Daily Hermes lesson failed: {reason}")
    print("LESSON BRIEF END")
    sys.exit(0)


def load_curriculum():
    topics, cur = [], {}
    try:
        lines = open(CURRICULUM, encoding="utf-8").read().splitlines()
    except OSError as e:
        reply_fail(f"cannot read curriculum.txt ({e})")
    for line in lines + [""]:
        if not line.strip():
            if cur:
                missing = [f for f in FIELDS if f not in cur]
                if missing:
                    reply_fail(f"topic {cur.get('id', '?')} is missing {', '.join(missing)}")
                topics.append(cur)
                cur = {}
            continue
        if line.startswith("#"):
            continue
        key, _, val = line.partition(":")
        if key.strip() in FIELDS:
            cur[key.strip()] = val.strip()
    ids = [t["id"] for t in topics]
    if len(set(ids)) != len(ids):
        reply_fail("curriculum.txt has duplicate ids")
    if not topics:
        reply_fail("curriculum.txt has no topics")
    return topics


def load_history():
    if not os.path.exists(HISTORY):
        return []
    with open(HISTORY, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("id")]


def counts_for(topics, history):
    c = {t["id"]: 0 for t in topics}
    for r in history:
        if r["id"] in c:
            c[r["id"]] += 1
    return c


def next_topic(topics, counts, last_id):
    pool = [t for t in topics if t["id"] != last_id] or topics
    low = min(counts[t["id"]] for t in pool)
    return next(t for t in pool if counts[t["id"]] == low)  # curriculum order breaks ties


def match(topics, words):
    w = words.lower().strip()
    for t in topics:  # exact id first
        if t["id"].lower() == w:
            return t
    toks = [x for x in w.replace("_", " ").split() if len(x) > 2]
    best, score = None, 0
    for t in topics:
        hay = (t["id"].replace("_", " ") + " " + t["title"]).lower()
        s = sum(1 for x in toks if x in hay)
        if s > score:
            best, score = t, s
    return best


def main():
    os.makedirs(STATE_DIR, exist_ok=True)
    topics = load_curriculum()
    history = load_history()
    counts = counts_for(topics, history)
    last_id = history[-1]["id"] if history else None

    request = " ".join(sys.argv[1:]).strip()
    note = ""
    topic = match(topics, request) if request else None
    if request and not topic:
        note = f'No lesson matched "{request}", so here is the next one in the series. '
    if not topic:
        topic = next_topic(topics, counts, last_id)

    rnd = counts[topic["id"]] + 1
    example = topic["example"] if rnd == 1 else topic["review"]

    # Record now, before the model writes anything.
    today = datetime.date.today().isoformat()
    new = not os.path.exists(HISTORY)
    with open(HISTORY, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "id", "round"])
        w.writerow([today, topic["id"], rnd])

    counts[topic["id"]] += 1
    upcoming = next_topic(topics, counts, topic["id"])
    taught = sum(1 for t in topics if counts[t["id"]] > 0)
    secs = time.time() - T0

    new = not os.path.exists(TIMING_HISTORY)
    with open(TIMING_HISTORY, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["datetime", "id", "pick_seconds"])
        w.writerow([datetime.datetime.now().isoformat(timespec="seconds"), topic["id"], f"{secs:.3f}"])

    kind = "new topic" if rnd == 1 else f"review, round {rnd}"
    print("LESSON BRIEF START")
    if note:
        print(f"NOTE: {note}")
    print(f"TOPIC: {topic['title']}")
    print(f"FACTS: {topic['facts']}")
    print(f"EXAMPLE: {example}")
    print(f"FOOTER: Lesson {taught} of {len(topics)} ({kind}). Next: {upcoming['title']}. TIMING: pick {secs:.2f}s")
    print("LESSON BRIEF END")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # always give the model something to send
        reply_fail(f"{type(e).__name__}: {e}")
