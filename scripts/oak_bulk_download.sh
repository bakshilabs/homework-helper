#!/usr/bin/env bash
# Bulk-download Oak National Academy curriculum + lesson data (JSON, one file per subject/phase).
#
# Usage:
#   export OAK_API_KEY=...            # never commit this
#   scripts/oak_bulk_download.sh                      # everything
#   scripts/oak_bulk_download.sh maths-primary science-secondary
#
# Output: data/oak/<timestamp>.zip, extracted into data/oak/json/
# Data is provided under the Open Government Licence; see
# https://www.thenational.academy/legal/terms-and-conditions-api-version
set -euo pipefail

: "${OAK_API_KEY:?Set OAK_API_KEY to your Oak OpenAPI key}"
OUT_DIR="${OUT_DIR:-data/oak}"

ALL_SUBJECTS=(
  art-primary art-secondary
  citizenship-secondary
  computing-primary computing-secondary
  cooking-nutrition-primary cooking-nutrition-secondary
  design-technology-primary design-technology-secondary
  english-primary english-secondary
  french-primary french-secondary
  geography-primary geography-secondary
  german-secondary
  history-primary history-secondary
  maths-primary maths-secondary
  music-primary music-secondary
  physical-education-primary physical-education-secondary
  religious-education-primary religious-education-secondary
  rshe-pshe-primary rshe-pshe-secondary
  science-primary science-secondary
  spanish-primary spanish-secondary
)

if [ "$#" -gt 0 ]; then SUBJECTS=("$@"); else SUBJECTS=("${ALL_SUBJECTS[@]}"); fi

body=$(printf '%s\n' "${SUBJECTS[@]}" | python3 -c 'import json,sys; print(json.dumps({"subjects":[l.strip() for l in sys.stdin if l.strip()]}))')

mkdir -p "$OUT_DIR"
zip="$OUT_DIR/oak-bulk-$(date -u +%Y%m%dT%H%M%SZ).zip"
echo "Requesting ${#SUBJECTS[@]} subject/phase file(s)..." >&2

status=$(curl -sS --retry 3 -X POST "https://open-api.thenational.academy/api/bulk" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${OAK_API_KEY}" \
  --data "$body" -o "$zip" -w '%{http_code}')

if [ "$status" != "200" ]; then
  echo "Download failed (HTTP $status):" >&2; head -c 500 "$zip" >&2; echo >&2
  rm -f "$zip"; exit 1
fi

mkdir -p "$OUT_DIR/json"
unzip -oq "$zip" -d "$OUT_DIR/json"
echo "Saved $zip ($(du -h "$zip" | cut -f1)), extracted to $OUT_DIR/json" >&2
