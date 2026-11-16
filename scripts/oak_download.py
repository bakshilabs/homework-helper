#!/usr/bin/env python3
"""Download everything available from Oak National Academy's OpenAPI.

Resumable: run it again and it skips anything already downloaded.
Respects the per-key rate limit (1000 requests/hour) by sleeping until reset.

Usage:
    export OAK_API_KEY=...            # never commit the key
    python3 oak_download.py OUT_DIR [--no-video] [--only maths-primary,science-secondary]

Output layout:
    OUT_DIR/bulk/oak-bulk.zip                     curriculum + lesson text (bulk download)
    OUT_DIR/quizzes/<sequence>.json               quiz questions and answers per sequence
    OUT_DIR/manifests/<sequence>-assets.json      list of downloadable files per lesson
    OUT_DIR/assets/<sequence>/<lesson>/<type>.<ext>   the files themselves
    OUT_DIR/progress.log                          what happened, including failures
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://open-api.thenational.academy/api/v0"
BULK = "https://open-api.thenational.academy/api/bulk"
SEQUENCES = [
    "art-primary", "art-secondary", "citizenship-secondary",
    "computing-primary", "computing-secondary",
    "cooking-nutrition-primary", "cooking-nutrition-secondary",
    "design-technology-primary", "design-technology-secondary",
    "english-primary", "english-secondary", "french-primary", "french-secondary",
    "geography-primary", "geography-secondary", "german-secondary",
    "history-primary", "history-secondary", "maths-primary", "maths-secondary",
    "music-primary", "music-secondary",
    "physical-education-primary", "physical-education-secondary",
    "religious-education-primary", "religious-education-secondary",
    "rshe-pshe-primary", "rshe-pshe-secondary",
    "science-primary", "science-secondary", "spanish-primary", "spanish-secondary",
]
EXT = {
    "application/pdf": "pdf",
    "video/mp4": "mp4",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/zip": "zip",
    "audio/mpeg": "mp3",
}

KEY = os.environ.get("OAK_API_KEY")
OUT = None
_remaining = None
_reset_ms = 0


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print(line, flush=True)
    with open(os.path.join(OUT, "progress.log"), "a") as f:
        f.write(line + "\n")


def _wait_for_quota():
    global _remaining
    if _remaining is not None and _remaining <= 2:
        wait = max(5, _reset_ms / 1000 - time.time() + 5)
        log(f"rate limit reached; sleeping {wait/60:.1f} min")
        time.sleep(wait)
        _remaining = None


def request(url, data=None, dest=None, tries=6):
    """GET/POST url. If dest is given, stream body to dest; else return bytes.
    Returns (body_or_None, content_type) or raises after repeated failure."""
    global _remaining, _reset_ms
    for attempt in range(tries):
        _wait_for_quota()
        headers = {"Authorization": f"Bearer {KEY}", "User-Agent": "oak-downloader"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                if r.headers.get("x-ratelimit-remaining") is not None:
                    _remaining = int(r.headers["x-ratelimit-remaining"])
                    _reset_ms = int(r.headers.get("x-ratelimit-reset") or 0)
                ctype = (r.headers.get("content-type") or "").split(";")[0].strip()
                if dest is None:
                    return r.read(), ctype
                tmp = dest + ".part"
                with open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                return tmp, ctype
        except urllib.error.HTTPError as e:
            if e.code == 429:
                _remaining = 0
                _reset_ms = int(e.headers.get("x-ratelimit-reset") or (time.time() + 600) * 1000)
                continue
            if e.code in (400, 401, 403, 404):
                raise
            log(f"HTTP {e.code} on {url}; retry {attempt+1}")
        except Exception as e:  # network hiccup
            log(f"{type(e).__name__} on {url}: {e}; retry {attempt+1}")
        time.sleep(min(300, 10 * 2 ** attempt))
    raise RuntimeError(f"giving up on {url}")


def save_json(url, path):
    if os.path.exists(path):
        return json.load(open(path))
    body, _ = request(url)
    obj = json.loads(body)
    with open(path + ".part", "w") as f:
        json.dump(obj, f)
    os.replace(path + ".part", path)
    return obj


def main():
    global OUT
    args = sys.argv[1:]
    if not args or not KEY:
        sys.exit(__doc__)
    OUT = os.path.abspath(args[0])
    no_video = "--no-video" in args
    seqs = SEQUENCES
    if "--only" in args:
        seqs = args[args.index("--only") + 1].split(",")
    for d in ("bulk", "quizzes", "manifests", "assets"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)

    # 1. Bulk text download (does not count towards the API rate limit).
    bulk = os.path.join(OUT, "bulk", "oak-bulk.zip")
    if not os.path.exists(bulk):
        tmp, _ = request(BULK, data=json.dumps({"subjects": SEQUENCES}).encode(), dest=bulk)
        os.replace(tmp, bulk)
        log("bulk zip downloaded")

    # 2. Quizzes and asset manifests per sequence.
    for s in seqs:
        try:
            qpath = os.path.join(OUT, "quizzes", f"{s}.json")
            if not os.path.exists(qpath):
                # Paginated: max 300 lessons per page.
                allq, offset = [], 0
                while True:
                    body, _ = request(f"{BASE}/sequences/{s}/questions?limit=300&offset={offset}")
                    page = json.loads(body)
                    allq.extend(page)
                    if len(page) < 300:
                        break
                    offset += 300
                with open(qpath + ".part", "w") as f:
                    json.dump(allq, f)
                os.replace(qpath + ".part", qpath)
            save_json(f"{BASE}/sequences/{s}/assets", os.path.join(OUT, "manifests", f"{s}-assets.json"))
        except Exception as e:
            log(f"FAILED manifest/quiz for {s}: {e}")
    log("quizzes and manifests done")

    # 3. Asset files. Lessons can appear in several sequences; download each once.
    seen = set()
    jobs = []
    for s in seqs:
        path = os.path.join(OUT, "manifests", f"{s}-assets.json")
        if not os.path.exists(path):
            continue
        for lesson in json.load(open(path)):
            for a in lesson.get("assets", []):
                if no_video and a["type"] == "video":
                    continue
                k = (lesson["lessonSlug"], a["type"])
                if k in seen:
                    continue
                seen.add(k)
                jobs.append((s, lesson["lessonSlug"], a["type"], a["url"]))
    # Small files first so the useful material arrives early; videos last.
    jobs.sort(key=lambda j: j[2] == "video")
    log(f"{len(jobs)} files to fetch")

    done_marker = os.path.join(OUT, "assets", ".done")
    done = set(open(done_marker).read().split("\n")) if os.path.exists(done_marker) else set()
    failed = 0
    for i, (s, lesson, typ, url) in enumerate(jobs, 1):
        key = f"{lesson}/{typ}"
        if key in done:
            continue
        d = os.path.join(OUT, "assets", s, lesson)
        os.makedirs(d, exist_ok=True)
        try:
            tmp, ctype = request(url, dest=os.path.join(d, typ))
            os.replace(tmp, os.path.join(d, f"{typ}.{EXT.get(ctype, 'bin')}"))
            with open(done_marker, "a") as f:
                f.write(key + "\n")
        except Exception as e:
            failed += 1
            log(f"FAILED {key}: {e}")
        if i % 100 == 0:
            log(f"progress {i}/{len(jobs)} (failed {failed})")
    log(f"finished: {len(jobs)} files, {failed} failed")


if __name__ == "__main__":
    main()
