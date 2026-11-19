"""Search over the Oak lesson index (BM25, no external dependencies)."""
import json
import math
import re
from collections import Counter

STOP = set("""a an and are as at be by can do does for from has have how i if in is it its
me my of on or so that the their them then there these this to was we what when where which
who why will with you your not no yes help homework question please""".split())

# How much each part of a lesson counts when matching a student's question.
WEIGHTS = {"title": 4, "keywords": 3, "outcome": 3, "unit": 2, "learningPoints": 2,
           "quiz": 1.5, "misconceptions": 1, "transcript": 0.3}


def tokens(text):
    out = []
    for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if w in STOP:
            continue
        if len(w) > 4 and w.endswith("s"):  # crude plural folding: fractions -> fraction
            w = w[:-1]
        out.append(w)
    return out


def _fields(l):
    return {
        "title": l["title"],
        "unit": l["unit"],
        "outcome": l.get("outcome"),
        "keywords": " ".join(f"{k['word']} {k['word']} {k.get('meaning') or ''}" for k in l["keywords"]),
        "learningPoints": " ".join(p or "" for p in l["learningPoints"]),
        "misconceptions": " ".join(m.get("mistake") or "" for m in l["misconceptions"]),
        "quiz": " ".join((q.get("question") or "") + " " + " ".join(a.get("text") or "" for a in q["answers"])
                         for q in l["quiz"]),
        "transcript": l.get("transcript", ""),
    }


class LessonIndex:
    def __init__(self, path):
        data = json.load(open(path))
        self.year = data["year"]
        self.lessons = data["lessons"]
        self.by_slug = {l["slug"]: l for l in self.lessons}
        self.subjects = sorted({l["subject"] for l in self.lessons})
        self.doc_tf = []
        df = Counter()
        lengths = []
        for l in self.lessons:
            tf = Counter()
            for field, text in _fields(l).items():
                for t in tokens(text):
                    tf[t] += WEIGHTS[field]
            self.doc_tf.append(tf)
            lengths.append(sum(tf.values()))
            df.update(tf.keys())
        n = len(self.lessons)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.avg_len = sum(lengths) / max(1, n)
        self.lengths = lengths

    def search(self, query, subject=None, k=3):
        q = tokens(query)
        if not q:
            return []
        k1, b = 1.2, 0.75
        scored = []
        for i, l in enumerate(self.lessons):
            if subject and l["subject"] != subject:
                continue
            tf, s = self.doc_tf[i], 0.0
            norm = k1 * (1 - b + b * self.lengths[i] / self.avg_len)
            for t in q:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (k1 + 1) / (f + norm)
            if s > 0:
                scored.append((s, l))
        scored.sort(key=lambda x: -x[0])
        return [l for _, l in scored[:k]]


def lesson_brief(l, quiz_items=4):
    """Compact text of one lesson for Claude's context (no transcript)."""
    lines = [f"## {l['subject']} - {l['unit']} - {l['title']}",
             f"Lesson goal: {l.get('outcome') or ''}"]
    if l["keywords"]:
        lines.append("Keywords: " + "; ".join(f"{k['word']}: {k.get('meaning') or ''}" for k in l["keywords"]))
    if l["learningPoints"]:
        lines.append("Key learning points:\n" + "\n".join(f"- {p}" for p in l["learningPoints"] if p))
    if l["misconceptions"]:
        lines.append("Common mistakes and how teachers help:\n" + "\n".join(
            f"- {m.get('mistake')} -> {m.get('help')}" for m in l["misconceptions"]))
    if l["teacherTips"]:
        lines.append("Teacher tips:\n" + "\n".join(f"- {t}" for t in l["teacherTips"] if t))
    qs = [q for q in l["quiz"] if q.get("question") and q["answers"]][:quiz_items]
    if qs:
        lines.append("Example practice questions from the lesson:\n" + "\n".join(
            f"- {q['question']} (answer: {', '.join(a['text'] for a in q['answers'] if a['correct'] and a['text'])})"
            for q in qs))
    if l.get("transcript"):
        lines.append("How the Oak teacher explains it (start of the video transcript):\n" + l["transcript"][:1500])
    return "\n".join(lines)
