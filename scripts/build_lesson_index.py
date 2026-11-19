#!/usr/bin/env python3
"""Build the lesson index the homework helper searches, from the organised Oak download.

Usage: python3 build_lesson_index.py OAK_BY_YEAR_DIR "Key Stage 2/Year 4" OUT.json

Walks <OAK_BY_YEAR_DIR>/<year path>/<Subject>/<NN Unit>/<NN Lesson>/ and keeps the text a
tutor needs from lesson-info.json and quiz.json (no videos, slides or worksheets).
"""
import json, os, re, sys

root, year_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
base = os.path.join(root, year_path)


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


lessons = []
for subject in sorted(os.listdir(base)):
    sdir = os.path.join(base, subject)
    if not os.path.isdir(sdir):
        continue
    for unit in sorted(os.listdir(sdir)):
        udir = os.path.join(sdir, unit)
        if not os.path.isdir(udir):
            continue
        for lesson in sorted(os.listdir(udir)):
            ldir = os.path.join(udir, lesson)
            info_p = os.path.join(ldir, "lesson-info.json")
            if not os.path.exists(info_p):
                continue
            info = json.load(open(info_p))
            quiz = {}
            if os.path.exists(os.path.join(ldir, "quiz.json")):
                quiz = json.load(open(os.path.join(ldir, "quiz.json")))
            lessons.append({
                "slug": info["lessonSlug"],
                "subject": subject,
                "unit": re.sub(r"^\d+ ", "", unit),
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
    json.dump({"year": year_path, "lessons": lessons}, f, ensure_ascii=False)
by_subject = {}
for l in lessons:
    by_subject[l["subject"]] = by_subject.get(l["subject"], 0) + 1
print(f"{len(lessons)} lessons -> {out} ({os.path.getsize(out)/1e6:.1f} MB)")
for s, n in by_subject.items():
    print(f"  {s}: {n}")
