"""Condition 1 of this idea (IDEAS.md, LEDGER.md note of 2026-11-20): the MAIN rule's trades entered in 2019-2021 ALONE
against the scan's confirmation bars (DIRECTION4 section 5), computed with the scan's own confirm_one() on the scan's
own rule (scan/rules.csv, frozen), so the trades are the scan's. One configuration, no neighbour, no validation bar.
Run from the repository root:  PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/ideas/<folder>/gate.py"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))          # lab/explore
from scan import confirm as CF, grammar as G                                   # noqa: E402

raw = open(os.path.join(HERE, "gate_declared.json"), "rb").read()
want = open(os.path.join(HERE, "gate_declared.sha256")).read().split()[0]
if hashlib.sha256(raw).hexdigest() != want:
    sys.exit("gate_declared.json is not the declared file: refused")
decl = json.loads(raw)
if G.sha256_text(G.csv_text()) != decl["rules_sha256"]:
    sys.exit("scan/rules.csv is not the frozen rule list: refused")
if list(G.UNITS[decl["unit"]]) != decl["markets"]:
    sys.exit("the unit's markets are not the declared ones: refused")
cand = {"rule": decl["main"], "unit": decl["unit"], "markets": decl["markets"], "order": 1, "stage": "basket"}
res = CF.confirm_one(cand, None, 0, {})
res["condition_1_passed"] = bool(res["confirmed"])
with open(os.path.join(HERE, "fresh_years.json"), "w") as f:
    json.dump(res, f, indent=1, sort_keys=True)
print(json.dumps(res, indent=1, sort_keys=True))
