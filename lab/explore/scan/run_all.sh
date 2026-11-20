#!/usr/bin/env bash
# DIRECTION4 scan on the real bars: discovery (3 processes) -> selection -> confirmation -> report.
# Logs to $SCAN_DIR/run.log (default ~/explore_data/scan). Safe to start again after a restart: discovery skips the
# markets already done, selection refuses to overwrite a different frozen list, confirmation runs once per list (a
# second run of the same list must reproduce confirmation.json; another list is refused; every run is appended to
# confirmation_runs.log) and the report is recomputed identically.
#   EXPECT_RULES_SHA=<committed hash> bash lab/explore/scan/run_all.sh discover   # then select
#   (the lead commits frozen_candidates.json and its sha256)
#   EXPECT_RULES_SHA=<..> FROZEN_SHA=<committed hash of frozen_candidates.json> bash ... confirm   # then report
# Stages: discover | select | confirm | report | all. The confirm stage (and 'all' after select) refuses to start
# without FROZEN_SHA: the hash is never read from the frozen_candidates.sha256 that select writes.
#   EXPECT_RULES_SHA=<committed hash> bash ...   # refuse to start if scan/rules.csv is not the committed list
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPLORE="$(cd "$HERE/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$EXPLORE"
export SCAN_DIR="${SCAN_DIR:-$HOME/explore_data/scan}"
mkdir -p "$SCAN_DIR"
LOG="$SCAN_DIR/run.log"
PROCS="${PROCS:-3}"
STAGE="${1:-all}"
cd "$EXPLORE"
py() { python3 -B "$@" 2>&1 | tee -a "$LOG"; return "${PIPESTATUS[0]}"; }
echo "=== $(date -u +%FT%TZ) run_all.sh stage=$STAGE procs=$PROCS dir=$SCAN_DIR" | tee -a "$LOG"

SHA_NOW="$(sha256sum "$HERE/rules.csv" | cut -d' ' -f1)"
echo "rules.csv sha256 $SHA_NOW" | tee -a "$LOG"
if [[ -n "${EXPECT_RULES_SHA:-}" && "$SHA_NOW" != "$EXPECT_RULES_SHA" ]]; then
  echo "refused: rules.csv sha256 is not EXPECT_RULES_SHA=$EXPECT_RULES_SHA" | tee -a "$LOG"; exit 2
fi

if [[ "$STAGE" == all || "$STAGE" == discover ]]; then
  py -m scan.discover --procs "$PROCS" --out "$SCAN_DIR/discovery"
fi
if [[ "$STAGE" == all || "$STAGE" == select ]]; then
  py -m scan.select --discovery "$SCAN_DIR/discovery" --out "$SCAN_DIR"
fi
if [[ "$STAGE" == all || "$STAGE" == confirm ]]; then
  if [[ -z "${FROZEN_SHA:-}" ]]; then
    echo "stopped before confirmation: commit frozen_candidates.json, then run the confirm stage with" \
         "FROZEN_SHA=<its committed sha256> (never taken from frozen_candidates.sha256)" | tee -a "$LOG"; exit 3
  fi
  echo "confirmation of the frozen list sha256 $FROZEN_SHA (given by FROZEN_SHA)" | tee -a "$LOG"
  py -m scan.confirm --candidates "$SCAN_DIR/frozen_candidates.json" --sha256 "$FROZEN_SHA" \
     --discovery "$SCAN_DIR/discovery" --out "$SCAN_DIR"
fi
if [[ "$STAGE" == all || "$STAGE" == report ]]; then
  py -m scan.report --dir "$SCAN_DIR"
fi
echo "=== $(date -u +%FT%TZ) done stage=$STAGE" | tee -a "$LOG"
