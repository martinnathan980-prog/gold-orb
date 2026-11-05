#!/bin/bash
# Audit every finalist of every track (needs lab/audit/cost_scenarios.json for broker scenarios).
cd "$(dirname "$0")/.."
for spec in "trend donch4h_stop" "orb orb_asia_2d_buf10" "pivots rn100_break_fresh" \
            "seasonality WKND_LIM" "seasonality FRI_PM_LIM" "meanrev meanrev-A-failedbreak-D5"; do
  set -- $spec
  python3 audit/audit.py "$1" "$2" > "results/audit/$1__$2.txt" 2>&1 && echo "done $1/$2" || echo "FAILED $1/$2"
done
