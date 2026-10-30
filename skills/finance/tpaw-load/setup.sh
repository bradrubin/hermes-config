#!/bin/bash
# Usage: setup.sh ["/full/path/to/plan.txt"]
# With no argument, uses the first non-comment line of plan_path.txt.
D="$(cd "$(dirname "$0")" && pwd)"
fail() { echo "SETUP FAILED: $1"; exit 1; }

for f in load_plan.py report.py plan_path.txt; do
  [ -f "$D/$f" ] || fail "missing $D/$f"
done

PLAN="$1"
if [ -z "$PLAN" ]; then
  PLAN="$(grep -v '^[[:space:]]*#' "$D/plan_path.txt" | grep -v '^[[:space:]]*$' | head -n 1 | tr -d '\r')"
fi
PLAN="${PLAN/#\~/$HOME}"
[ -n "$PLAN" ] || fail "no plan file set in $D/plan_path.txt"
[ -f "$PLAN" ] || fail "plan file not found: $PLAN"
case "$PLAN" in
  *.txt) ;;
  *) fail "plan file must be a TPAW .txt export: $PLAN" ;;
esac

rm -f "$D/last_result.json"
printf '%s\n' "$PLAN" > "$D/current_plan.txt"
python3 -c 'import time; print("start %.3f" % time.time())' > "$D/timing.log"
echo "SETUP OK: $(basename "$PLAN")"
