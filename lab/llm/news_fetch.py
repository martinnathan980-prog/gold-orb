"""Fetch the public archive of Donald Trump's Truth Social posts (trumpstruth.org, an independent
mirror; robots.txt allows crawling) for the period after the language model's knowledge cut-off, and
write one row per post: mirror id, original post id, creation time (UTC, to the second), text.

    python3 -I lab/llm/news_fetch.py fetch     # raw pages -> lab/data/llm/news/raw/ (git-ignored), 1 page / 2 s
    python3 -I lab/llm/news_fetch.py parse     # -> lab/results/llm/news/posts.parquet

The creation time is cross-checked against the original post id (Mastodon snowflake: id >> 16 = milliseconds
since 1970). Pages are untrusted input: they are only parsed with regular expressions.
"""
import base64
import html
import json
import os
import re
import subprocess
import sys
import time

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(LAB, "data", "llm", "news", "raw")
OUT = os.path.join(LAB, "results", "llm", "news")
START = "2026-06-28 00:00:00"          # a few days of context before 2026-07-01
BASE = "https://www.trumpstruth.org/?sort=desc&per_page=100"


def _blocks(s):
    parts = re.split(r'<div class="status" data-status-url="', s)[1:]
    for p in parts:
        mid = re.match(r'https://www\.trumpstruth\.org/statuses/(\d+)"', p)
        tm = re.search(r'<time datetime="([^"]+)"', p)
        orig = re.search(r'href="https://truthsocial\.com/@([^/"]+)/(\d+)"', p)
        body = re.search(r'<div class="status__content"[^>]*>(.*?)</div>\s*(?:<button|<div|</div>)', p, re.S)
        txt = ""
        if body:
            t = re.sub(r"<br\s*/?>|</p>", "\n", body.group(1))
            txt = html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
        yield {"mirror_id": int(mid.group(1)) if mid else -1, "time": tm.group(1) if tm else "",
               "account": orig.group(1) if orig else "", "orig_id": orig.group(2) if orig else "", "text": txt,
               "has_media": int("status__attachments" in p or "<video" in p or "status-attachment" in p),
               "is_quote": int("status__quote" in p or "ReTruth" in p)}


def fetch():
    os.makedirs(RAW, exist_ok=True)
    cursor, k = None, 0
    while True:
        url = BASE + (f"&cursor={cursor}" if cursor else "")
        path = os.path.join(RAW, f"page_{k:04d}.html")
        r = subprocess.run(["curl", "-sS", "-m", "60", "-A", "Mozilla/5.0 (research script)", url, "-o", path,
                            "-w", "%{http_code}"], capture_output=True, text=True)
        if r.stdout.strip() != "200":
            print("page", k, "HTTP", r.stdout, r.stderr[-200:])
            break
        s = open(path, encoding="utf-8", errors="replace").read()
        rows = list(_blocks(s))
        if not rows:
            print("page", k, "no posts: stop")
            break
        own = [x["time"] for x in rows if x["account"] == "realDonaldTrump" and x["time"]]   # re-posts carry the ORIGINAL author's date
        if not own:
            print("page", k, "no own post: stop")
            break
        last = own[-1]
        print(f"page {k}: {len(rows)} posts, {rows[0]['time']} -> {last}", flush=True)
        if last[:19].replace("T", " ") < START:
            break
        cursor = base64.b64encode(json.dumps({"status_created_at": last[:19].replace("T", " "),
                                              "_pointsToNextItems": True}, separators=(",", ":")).encode()).decode()
        k += 1
        time.sleep(2.0)


def parse():
    import pandas as pd
    rows = []
    for f in sorted(os.listdir(RAW)):
        if f.endswith(".html"):
            rows += list(_blocks(open(os.path.join(RAW, f), encoding="utf-8", errors="replace").read()))
    d = pd.DataFrame(rows)
    d["repost"] = (d.account != "realDonaldTrump").astype(int)       # shown with the original author's date: time unknown
    d = d.drop_duplicates("mirror_id")
    d["time"] = pd.to_datetime(d["time"], utc=True)
    d = d.sort_values("time").reset_index(drop=True)
    oid = pd.to_numeric(d.orig_id, errors="coerce")
    snow = pd.to_datetime((oid // 65536), unit="ms", utc=True, errors="coerce")
    d["id_time_diff_s"] = (d.time - snow).dt.total_seconds().round(1)
    d = d[(d.time >= pd.Timestamp(START, tz="UTC")) & (d.repost == 0)].reset_index(drop=True)
    os.makedirs(OUT, exist_ok=True)
    d.to_parquet(os.path.join(OUT, "posts.parquet"))
    print(len(d), "posts", d.time.min(), "->", d.time.max())
    print("re-posts of other accounts:", int(d.repost.sum()), "| own posts with text:", int(((d.repost == 0) & (d.text.str.len() > 0)).sum()))
    print("with text:", int((d.text.str.len() > 0).sum()), "| median length:", int(d.text.str.len().median()),
          "| per day:", round(len(d) / max((d.time.max() - d.time.min()).days, 1), 1))
    print("creation time vs original id (seconds): ", d.id_time_diff_s.describe().round(1).to_dict())
    print(d.groupby(d.time.dt.strftime("%Y-%m")).size().to_dict())


if __name__ == "__main__":
    {"fetch": fetch, "parse": parse}[sys.argv[1]]()
