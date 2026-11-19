#!/usr/bin/env python3
"""Fetch any asset not yet in assets/.done using curl (works where urllib gets HTTP 400).
Usage: OAK_API_KEY=... python3 oak_retry_curl.py OUT_DIR"""
import glob, json, os, subprocess, sys, time

OUT = os.path.abspath(sys.argv[1])
KEY = os.environ["OAK_API_KEY"]
EXT = {"video": "mp4", "slideDeck": "pptx"}
done_path = os.path.join(OUT, "assets", ".done")
done = set(open(done_path).read().split("\n"))
log_path = os.path.join(OUT, "progress.log")


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + "[curl] " + msg
    print(line, flush=True)
    open(log_path, "a").write(line + "\n")


jobs, seen = [], set()
for m in sorted(glob.glob(os.path.join(OUT, "manifests", "*-assets.json"))):
    seq = os.path.basename(m)[: -len("-assets.json")]
    for lesson in json.load(open(m)):
        for a in lesson.get("assets", []):
            k = f"{lesson['lessonSlug']}/{a['type']}"
            if k in done or k in seen:
                continue
            seen.add(k)
            jobs.append((seq, lesson["lessonSlug"], a["type"], a["url"]))
log(f"{len(jobs)} missing files to retry")

ok = gone = bad = 0
for i, (seq, slug, typ, url) in enumerate(jobs, 1):
    d = os.path.join(OUT, "assets", seq, slug)
    os.makedirs(d, exist_ok=True)
    part = os.path.join(d, typ + ".part")
    for attempt in range(4):
        r = subprocess.run(
            ["curl", "-sS", "-L", "--retry", "3", "-o", part, "-w", "%{http_code} %{content_type}",
             "-H", f"Authorization: Bearer {KEY}", url],
            capture_output=True, text=True)
        code, _, ctype = r.stdout.partition(" ")
        if code == "429":
            log("rate limited; sleeping 10 min")
            time.sleep(600)
            continue
        break
    if code in ("200", "206") and r.returncode == 0:
        ext = "pdf" if "pdf" in ctype else EXT.get(typ, "bin")
        if "presentation" in ctype:
            ext = "pptx"
        elif "mp4" in ctype:
            ext = "mp4"
        os.replace(part, os.path.join(d, f"{typ}.{ext}"))
        open(done_path, "a").write(f"{slug}/{typ}\n")
        ok += 1
    else:
        if os.path.exists(part):
            os.remove(part)
        if code == "404":
            gone += 1
        else:
            bad += 1
        log(f"FAILED {slug}/{typ}: HTTP {code} {r.stderr.strip()[:120]}")
    if i % 25 == 0:
        log(f"progress {i}/{len(jobs)} ok={ok} gone={gone} failed={bad}")
log(f"retry finished: {len(jobs)} tried, ok={ok}, removed-by-Oak={gone}, failed={bad}")
