#!/usr/bin/env python3
"""Reorganise an Oak download into Key Stage / Year / Subject / Unit / Lesson.

Usage: python3 oak_organise.py OAK_DIR [--apply]
Without --apply it only prints the plan (dry run).

Reads OAK_DIR/bulk/extracted/*.json (unzipped bulk download), OAK_DIR/quizzes/*.json
and moves files from OAK_DIR/assets/<sequence>/<lesson>/ into OAK_DIR/oak-by-year/.
Each lesson is stored once (in its earliest year; ties keep Oak's sequence order); any
other unit it belongs to gets a "<NN Lesson> - see <where>.txt" pointer file.
Every lesson folder also gets lesson-info.json (bulk text) and quiz.json when available.
All moves are logged to OAK_DIR/oak-by-year/_moves.csv so they can be undone.
"""
import csv, glob, json, os, re, sys

ROOT = os.path.abspath(sys.argv[1])
APPLY = "--apply" in sys.argv
OUT = os.path.join(ROOT, "oak-by-year")

SUBJECT = {
    "art": "Art and design", "citizenship": "Citizenship", "computing": "Computing",
    "cooking-nutrition": "Cooking and nutrition", "design-technology": "Design and technology",
    "english": "English", "french": "French", "geography": "Geography", "german": "German",
    "history": "History", "maths": "Maths", "music": "Music", "physical-education": "Physical education",
    "religious-education": "Religious education", "rshe-pshe": "RSHE (PSHE)", "science": "Science",
    "biology": "Biology", "chemistry": "Chemistry", "physics": "Physics",
    "combined-science": "Combined science", "spanish": "Spanish",
}
SEQ_ORDER = [
    "art-primary", "art-secondary", "citizenship-secondary", "computing-primary", "computing-secondary",
    "cooking-nutrition-primary", "cooking-nutrition-secondary", "design-technology-primary",
    "design-technology-secondary", "english-primary", "english-secondary", "french-primary",
    "french-secondary", "geography-primary", "geography-secondary", "german-secondary",
    "history-primary", "history-secondary", "maths-primary", "maths-secondary", "music-primary",
    "music-secondary", "physical-education-primary", "physical-education-secondary",
    "religious-education-primary", "religious-education-secondary", "rshe-pshe-primary",
    "rshe-pshe-secondary", "science-primary", "science-secondary", "spanish-primary", "spanish-secondary",
]


def clean(s, n=90):
    s = str(s).replace(": ", " - ")
    s = re.sub(r"[/:\\\x00-\x1f]", "-", s).strip().strip(".")
    s = re.sub(r"\s+", " ", s)
    return s[:n].rstrip()


def title_of(x):
    if isinstance(x, dict):
        for k in ("title", "tierTitle", "pathwayTitle", "examBoardTitle"):
            if x.get(k):
                return x[k]
        for k, v in x.items():
            if k.lower().endswith("title") and v:
                return v
        return None
    return x or None


def year_folder(u):
    y = u.get("yearSlug") or ""
    if y.startswith("year-"):
        return "Year " + y[5:]
    return {"reception": "Reception", "all-years": "All years"}.get(y, clean(y) or "Unknown year")


def ks_folder(u):
    k = u.get("keyStageSlug") or ""
    return "Key Stage " + k[2:] if k.startswith("ks") else (k or "Unknown key stage")


def subject_folder(u):
    name = SUBJECT.get(u.get("subjectSlug"), clean(u.get("subjectSlug") or "Unknown"))
    extras = [title_of(u.get("examBoard")), title_of(u.get("pathway")), title_of(u.get("tier"))]
    extras = [clean(e, 40) for e in extras if e]
    return " - ".join([name] + extras)


# ---- Load bulk data ----
lessons_info, units_in_order = {}, []
for seq in SEQ_ORDER:
    p = os.path.join(ROOT, "bulk", "extracted", f"{seq}.json")
    if not os.path.exists(p):
        continue
    d = json.load(open(p))
    for l in d["lessons"]:
        lessons_info.setdefault(l["lessonSlug"], l)
    for u in d["sequence"]:
        units_in_order.append((seq, u))

quiz = {}
for p in glob.glob(os.path.join(ROOT, "quizzes", "*.json")):
    for q in json.load(open(p)):
        quiz.setdefault(q["lessonSlug"], q)

downloaded = {}  # lesson -> source dir
for seq in os.listdir(os.path.join(ROOT, "assets")):
    sd = os.path.join(ROOT, "assets", seq)
    if os.path.isdir(sd):
        for lesson in os.listdir(sd):
            if os.path.isdir(os.path.join(sd, lesson)):
                downloaded.setdefault(lesson, os.path.join(sd, lesson))

# ---- Build placements ----
unit_dirs = {}       # (ks, year, subj, unitSlug) -> unit dir
unit_counter = {}    # (ks, year, subj) -> next number
unit_by_slug = {}    # unitSlug -> first unit dir
placements = {}      # lesson -> [lesson_dir, ...] in order
for seq, u in units_in_order:
    key = (ks_folder(u), year_folder(u), subject_folder(u), u["unitSlug"])
    if key not in unit_dirs:
        grp = key[:3]
        unit_counter[grp] = unit_counter.get(grp, 0) + 1
        unit_dirs[key] = os.path.join(OUT, *grp, f"{unit_counter[grp]:02d} {clean(u['unitTitle'])}")
        unit_by_slug.setdefault(u["unitSlug"], unit_dirs[key])
    udir = unit_dirs[key]
    for ul in sorted(u.get("unitLessons", []), key=lambda x: x.get("lessonOrder") or 0):
        if ul.get("state") != "published":
            continue
        ldir = os.path.join(udir, f"{(ul.get('lessonOrder') or 0):02d} {clean(ul['lessonTitle'])}")
        lst = placements.setdefault(ul["lessonSlug"], [])
        if ldir not in lst:
            lst.append(ldir)

# Lessons missing from unit lists: place by their own unitSlug, numbered after the unit's lessons.
extra_n = {}
for slug, info in lessons_info.items():
    if slug in placements:
        continue
    udir = unit_by_slug.get(info.get("unitSlug"))
    if not udir:
        udir = os.path.join(OUT, "Unplaced", clean(info.get("subjectTitle") or "Unknown"))
    extra_n[udir] = extra_n.get(udir, 90) + 1
    placements[slug] = [os.path.join(udir, f"{extra_n[udir]:02d} {clean(info['lessonTitle'])}")]
for slug in downloaded:
    if slug not in placements:
        placements[slug] = [os.path.join(OUT, "Unplaced", slug)]

# Main copy goes in the earliest year (stable: ties keep Oak's sequence order).
def _year_rank(d):
    y = os.path.relpath(d, OUT).split(os.sep)[1]
    if y == "Reception":
        return 0
    if y.startswith("Year "):
        return int(y[5:])
    return 99
for slug in placements:
    placements[slug].sort(key=_year_rank)

# ---- Report / apply ----
primary_dirs = [v[0] for v in placements.values()]
assert len(primary_dirs) == len(set(primary_dirs)), "duplicate lesson folder names"
multi = sum(1 for v in placements.values() if len(v) > 1)
files = sum(len(os.listdir(d)) for d in downloaded.values())
print(f"lessons with folders: {len(placements)}  (with downloaded files: {len(downloaded)})")
print(f"files to move: {files}   lessons in >1 place (pointer files): {multi}")
print(f"unplaced: {sum(1 for v in placements.values() if '/Unplaced/' in v[0])}")
for slug in list(downloaded)[:3] + [s for s, v in placements.items() if len(v) > 1][:2]:
    print(" ", slug, "->", os.path.relpath(placements[slug][0], ROOT),
          *("\n      also: " + os.path.relpath(p, ROOT) for p in placements[slug][1:]))
if not APPLY:
    print("dry run only; re-run with --apply")
    sys.exit()

os.makedirs(OUT, exist_ok=True)
moves = csv.writer(open(os.path.join(OUT, "_moves.csv"), "a", newline=""))
index = csv.writer(open(os.path.join(OUT, "_index.csv"), "w", newline=""))
index.writerow(["lessonSlug", "folder", "also_in"])
for slug, dirs in placements.items():
    main = dirs[0]
    os.makedirs(main, exist_ok=True)
    src = downloaded.get(slug)
    if src:
        for f in sorted(os.listdir(src)):
            dst = os.path.join(main, f)
            if os.path.exists(dst):
                continue
            os.rename(os.path.join(src, f), dst)
            moves.writerow([os.path.join(src, f), dst])
        try:
            os.rmdir(src)
        except OSError:
            pass
    if slug in lessons_info:
        json.dump(lessons_info[slug], open(os.path.join(main, "lesson-info.json"), "w"), indent=1)
    if slug in quiz:
        json.dump(quiz[slug], open(os.path.join(main, "quiz.json"), "w"), indent=1)
    for other in dirs[1:]:
        os.makedirs(os.path.dirname(other), exist_ok=True)
        rel = os.path.relpath(main, OUT)
        where = " - ".join(rel.split(os.sep)[2:3])  # subject folder of the main copy
        with open(f"{other} - see {clean(where, 60)}.txt", "w") as fh:
            fh.write(f"This lesson is stored in:\noak-by-year/{rel}\n")
    index.writerow([slug, os.path.relpath(main, OUT), " | ".join(os.path.relpath(d, OUT) for d in dirs[1:])])
print("done")
