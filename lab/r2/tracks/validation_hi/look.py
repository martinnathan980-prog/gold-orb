"""validation_hi -- THE LOOK: one command, once, after it is declared in the protocol.

    LOOK_DECLARED=/home/user/gold-orb/lab/PROTOCOL_V3.md \\
    NUMBA_CACHE_DIR=/tmp/numba_validation_hi PYTHONDONTWRITEBYTECODE=1 \\
    python3 /home/user/gold-orb/lab/r2/tracks/validation_hi/look.py \\
        --spec /home/user/gold-orb/lab/r2/tracks/validation_hi/look_spec.json --cut 2026-01-01

What it does, in this order:
  1. vhi_guard.open_run(CUT): refuses CUT > 2026-01-01 always; refuses CUT > 2022-01-01 unless LOOK_DECLARED is the
     path of the protocol addendum and its text contains the word "declared"; for CUT > 2022-01-01 appends ONE line
     to lab/results/val_access.log (track "autopsy_HI_look", label "look:<spec name>:<spec sha256[:12]>") BEFORE any
     data is read; installs the read guard (every frame ts < CUT, every trades file entry_time < CUT).
  2. Runs the spec (vhi_run.run_spec) on the spec's "look" windows (entries 2022-01-01 .. 2025-12-31): every sleeve
     in FP costs and x1.5, as specified ("lab") and as the live program would ("live"), the portfolios as the plain
     sum of R x stake and through the capped account (6 positions, 2 per market), the comparisons at equal weekly
     swing, the official-trades check of the ten sleeves.
  3. Writes lab/results/r2/validation_hi/look/<name>__cut<YYYY-MM-DD>.json (all results, the spec and its sha256,
     the declared file and its sha256, whether the declared text quotes the spec's sha256, every read with its
     filter) and <name>__cut<YYYY-MM-DD>__trades.parquet (every simulated trade of every sleeve, mode, execution).
     It refuses to overwrite an existing look output (a look is run once).

With --cut 2022-01-01 (or earlier) the same command is an in-sample rehearsal: nothing is logged, and the output
goes to lab/results/r2/validation_hi/rehearsal/ instead.
"""
import argparse
import json
import os
import sys
import time

if not os.environ.get("NUMBA_CACHE_DIR", "").startswith("/tmp/"):
    raise SystemExit("set NUMBA_CACHE_DIR to a directory under /tmp")
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import vhi_guard as G  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", default=os.path.join(HERE, "look_spec.json"))
    ap.add_argument("--cut", default="2026-01-01")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    spec_path = os.path.abspath(a.spec)
    with open(spec_path, "rb") as f:
        raw = f.read()
    import hashlib
    sha = hashlib.sha256(raw).hexdigest()
    spec = json.loads(raw)
    label = f"look:{spec['name']}:{sha[:12]}"
    try:
        c0 = G.resolve_cut(a.cut)               # the CUT rules, checked before anything is written, read or logged
    except G.GuardError as e:
        raise SystemExit(f"REFUSED: {e}")
    look = G.is_look(c0)
    base = os.path.join(G.LAB, "results", "r2", "validation_hi", "look" if look else "rehearsal")
    stem = f"{spec['name']}__cut{c0.date()}"
    out = a.out or os.path.join(base, stem + ".json")
    if look and os.path.exists(out):
        raise SystemExit(f"REFUSED: {out} exists: the look is run once")
    cut = G.open_run(a.cut, label)              # for a look: the one access line, then the read guard
    os.makedirs(base, exist_ok=True)
    import pandas as pd
    import vhi_run as RUN
    t0 = time.time()
    res = RUN.run_spec(spec, cut)
    declared = os.environ.get("LOOK_DECLARED") if look else None
    meta = {"cut": str(cut), "is_look": look, "spec_path": spec_path, "spec_sha256": sha, "label": label,
            "declared_file": declared, "declared_sha256": RUN.sha256(declared) if declared else None,
            "declared_text_quotes_spec_sha256": (sha in open(declared, encoding="utf-8", errors="replace").read())
            if declared else None,
            "seconds": round(time.time() - t0, 1), "reads": G.reads(), "spec": spec}
    trades = res["_trades"]
    fr = []
    for (k, chain, mode, ex), t in trades.items():
        if len(t):
            fr.append(t.assign(sleeve=k, chain=chain, mode=mode, exec=ex))
    if fr:
        tp = out[:-5] + "__trades.parquet"
        allt = pd.concat(fr, ignore_index=True)
        for c in allt.columns:
            if allt[c].dtype == object and c not in ("sleeve", "chain", "mode", "exec", "reason"):
                allt[c] = allt[c].astype(str)
        allt.to_parquet(tp)
        meta["trades_file"] = tp
    body = RUN.strip_private(res)
    body["meta"] = meta
    RUN.jdump(body, out)
    print(f"written {out} [{meta['seconds']}s]; access logged: {look}")


if __name__ == "__main__":
    main()
