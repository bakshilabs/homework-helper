#!/usr/bin/env python3
"""Build the lesson index the homework helper searches, from the organised Oak download.

Usage: python3 build_lesson_index.py OAK_BY_YEAR_DIR OUT.json "Key Stage 2/Year 4" ["Key Stage 2/Year 3" ...]

The first year is the main year; the others are included so topics that Oak teaches a year
earlier or later than the child's school still have a lesson to draw on.
Walks <OAK_BY_YEAR_DIR>/<year path>/<Subject>/<NN Unit>/<NN Lesson>/ and keeps the text a
tutor needs from lesson-info.json and quiz.json (no videos, slides or worksheets).
"""
import json, os, re, sys

root, out, years = sys.argv[1], sys.argv[2], sys.argv[3:]


def quiz_items(qs):
    items = []
    for q in qs or []:
        answers = []
        for a in q.get("answers") or []:
            if isinstance(a, dict) and a.get("type") == "text":
                answers.append({"text": a.get("content"), "correct": not a.get("distractor", False)})
        items.append({
            "question": q.get("question"),
            "type": q.get("questionType"),
            "answers": answers,
            "image": (q.get("questionImage") or {}).get("url"),
        })
    return items


def lesson_dirs(base):
    for subject in sorted(os.listdir(base)):
        sdir = os.path.join(base, subject)
        for unit in sorted(os.listdir(sdir)) if os.path.isdir(sdir) else []:
            udir = os.path.join(sdir, unit)
            for lesson in sorted(os.listdir(udir)) if os.path.isdir(udir) else []:
                ldir = os.path.join(udir, lesson)
                if os.path.exists(os.path.join(ldir, "lesson-info.json")):
                    yield subject, re.sub(r"^\d+ ", "", unit), ldir


lessons = []
for year_path in years:
    for subject, unit, ldir in lesson_dirs(os.path.join(root, year_path)):
        info = json.load(open(os.path.join(ldir, "lesson-info.json")))
        quiz = {}
        if os.path.exists(os.path.join(ldir, "quiz.json")):
            quiz = json.load(open(os.path.join(ldir, "quiz.json")))
        lessons.append({
            "slug": info["lessonSlug"],
            "year": os.path.basename(year_path),
            "subject": subject,
            "unit": unit,
            "title": info.get("lessonTitle"),
            "outcome": info.get("pupilLessonOutcome"),
            "keywords": [{"word": k.get("keyword"), "meaning": k.get("description")}
                         for k in info.get("lessonKeywords") or []],
            "learningPoints": [k.get("keyLearningPoint") for k in info.get("keyLearningPoints") or []],
            "misconceptions": [{"mistake": m.get("misconception"), "help": m.get("response")}
                               for m in info.get("misconceptionsAndCommonMistakes") or []],
            "teacherTips": [t.get("teacherTip") for t in info.get("teacherTips") or []],
            "quiz": quiz_items(quiz.get("starterQuiz")) + quiz_items(quiz.get("exitQuiz")),
            "transcript": (info.get("transcript_sentences") or "").strip(),
            "url": info.get("oakUrl"),
        })

os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
with open(out, "w") as f:
    json.dump({"year": os.path.basename(years[0]), "lessons": lessons}, f, ensure_ascii=False)
counts = {}
for l in lessons:
    counts[(l["year"], l["subject"])] = counts.get((l["year"], l["subject"]), 0) + 1
print(f"{len(lessons)} lessons -> {out} ({os.path.getsize(out)/1e6:.1f} MB)")
for (y, s), n in sorted(counts.items()):
    print(f"  {y} {s}: {n}")
