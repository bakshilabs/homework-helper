# Homework helper

A voice homework helper for Year 4 pupils, built on Oak National Academy lessons.

- **Phase 1 (now):** voice chat. The child talks, Oakley replies out loud, and helps them work the answer out rather than giving it.
- Phase 2: worked examples shown as text on screen.
- Phase 3: animated diagrams.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
echo 'ANTHROPIC_API_KEY=your-key-here' > app/.env
.venv/bin/python app/server.py
```

Open http://localhost:8000 in Chrome or Safari and allow the microphone.

## Lesson data

`data/year4-lessons.json` is built from the organised Oak download. It holds Year 4 plus Years 3 and 5, because schools teach some topics in a different year from Oak; Year 4 lessons rank first.

```bash
python3 scripts/build_lesson_index.py ~/Downloads/oak-full/oak-by-year data/year4-lessons.json \
  "Key Stage 2/Year 4" "Key Stage 2/Year 3" "Key Stage 2/Year 5"
```

Oak content is used under the Open Government Licence; the app credits the lessons it uses.

## Scripts

- `scripts/oak_download.py`, `scripts/oak_retry_curl.py`: download everything from Oak's API.
- `scripts/oak_organise.py`: organise the download by key stage, year, subject, unit and lesson.
- `scripts/build_lesson_index.py`: build the lesson index the helper searches.
