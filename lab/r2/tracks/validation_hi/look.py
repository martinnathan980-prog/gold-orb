"""validation_hi -- THE LOOK: one command, once, after it is declared in the protocol.

    LOOK_DECLARED=/home/user/gold-orb/lab/PROTOCOL_V3.md \\
    NUMBA_CACHE_DIR=/tmp/numba_validation_hi PYTHONDONTWRITEBYTECODE=1 \\
    python3 /home/user/gold-orb/lab/r2/tracks/validation_hi/look.py \\
        --spec /home/user/gold-orb/lab/r2/tracks/validation_hi/look_spec.json --cut 2026-01-01

What it does, in this order (plan(), then vhi_guard.open_run, both before any data is read):
  1. Reads the spec file once; its sha256 is computed on those very bytes, which are the spec that runs.
  2. The CUT rules: CUT > 2026-01-01 is always refused. CUT > 2022-01-01 (THE LOOK) is refused unless LOOK_DECLARED
     names a file whose text contains the string "autopsy_HI_look" AND the full 64-hex sha256 of the spec file
     (the declaration is bound to this exact spec, its list of changes included).
  3. Run once: a look is refused if results/val_access.log already holds a line with track "autopsy_HI_look" or a
     '<stem>.started' marker exists in results/r2/validation_hi/look/, unless --second-access "<reason>" is given
     (the reason is written into the access label; the output gets the suffix __access<N>). --out is refused for a
     look: its output path is fixed, results/r2/validation_hi/look/<name>__cut<YYYY-MM-DD>.json.
  4. For the look: appends ONE line to lab/results/val_access.log (track "autopsy_HI_look", label
     "look:<spec name>:<spec sha256[:12]>[:second_access:<reason>]"), then writes '<stem>.started' right after it,
     then installs the read guard (every parquet read cut at CUT, CSVs under lab/ refused, open() of lab/data and the
     holdout refused).
  5. Runs the spec (vhi_run.run_spec) on the spec's "look" windows (entries 2022-01-01 .. 2025-12-31) with the
     changes named in its "changes_in_look": every sleeve in FP costs and x1.5, as specified ("lab") and as the
     live program would ("live"), the portfolios as the plain sum of R x stake and through the capped account
     (6 positions, 2 per market), the comparisons at equal weekly swing (scale recomputed on the window), the
     official-trades check of the ten sleeves, and the declared criteria ("verdicts").
  6. Writes <stem>.json (all results, the spec and its sha256, the declared file and its sha256, the declaration
     check, every read with its filter) and <stem>__trades.parquet (every simulated trade).

With --cut 2022-01-01 (or earlier) the same command is an in-sample rehearsal: nothing is logged, no marker is
written, and the output goes to lab/results/r2/validation_hi/rehearsal/ (or --out).
"""
import argparse
import hashlib
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


def plan(cut, raw, out_arg=None, second_access=None, env=None, log_path=None, look_dir=None):
    """Everything look.py decides before it opens the run, checked; raises GuardError when refused. Pure: it reads
    the declared file (for a look) and the access log, and writes nothing. `raw` = the bytes of the spec file."""
    sha = hashlib.sha256(raw).hexdigest()
    spec = json.loads(raw)
    c0 = G.resolve_cut(cut, env=env, spec_sha=sha)
    look = G.is_look(c0)
    base = (look_dir or G.LOOK_DIR) if look else os.path.join(G.LAB, "results", "r2", "validation_hi", "rehearsal")
    stem = f"{spec['name']}__cut{c0.date()}"
    label = f"look:{spec['name']}:{sha[:12]}"
    declaration = None
    if look:
        if out_arg:
            raise G.GuardError("--out is refused for a look: its output path is fixed "
                               f"({os.path.join(base, stem + '.json')})")
        prior, started = G.check_run_once(second_access, log_path=log_path, look_dir=base)
        if second_access is not None:
            reason = str(second_access).strip()
            stem = f"{stem}__access{max(len(prior), len(started)) + 1}"
            label = f"{label}:second_access:{reason}"
        envd = os.environ if env is None else env
        declaration = G.declaration_check(envd.get("LOOK_DECLARED"), sha)
        out = os.path.join(base, stem + ".json")
        marker = os.path.join(base, stem + ".started")
        for p in (out, marker):
            if os.path.exists(p):
                raise G.GuardError(f"{p} exists: the look is run once")
    else:
        if second_access is not None:
            raise G.GuardError("--second-access is for a look only (CUT after 2022-01-01)")
        out = os.path.abspath(out_arg) if out_arg else os.path.join(base, stem + ".json")
        marker = None
    return {"cut": c0, "is_look": look, "sha": sha, "spec": spec, "label": label, "base": base, "stem": stem,
            "out": out, "marker": marker, "second_access": second_access, "declaration": declaration}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", default=os.path.join(HERE, "look_spec.json"))
    ap.add_argument("--cut", default="2026-01-01")
    ap.add_argument("--out", default=None, help="rehearsals only (CUT <= 2022-01-01); refused for a look")
    ap.add_argument("--second-access", default=None, metavar="REASON",
                    help="only after a first access of the look was logged: the reason, written into the label")
    a = ap.parse_args()
    spec_path = os.path.abspath(a.spec)
    with open(spec_path, "rb") as f:
        raw = f.read()
    try:
        P = plan(a.cut, raw, a.out, a.second_access)
        cut = G.open_run(a.cut, P["label"], spec_sha=P["sha"], second_access=P["second_access"], marker=P["marker"])
    except G.GuardError as e:
        raise SystemExit(f"REFUSED: {e}")
    look = P["is_look"]
    os.makedirs(os.path.dirname(P["out"]), exist_ok=True)
    import pandas as pd
    import vhi_run as RUN
    t0 = time.time()
    res = RUN.run_spec(P["spec"], cut)
    d = P["declaration"] or {}
    meta = {"cut": str(cut), "is_look": look, "spec_path": spec_path, "spec_sha256": P["sha"], "label": P["label"],
            "second_access": P["second_access"], "marker": P["marker"],
            "declared_file": d.get("file"), "declared_sha256": d.get("sha256"),
            "declared_text_quotes_spec_sha256": d.get("contains_spec_sha256") if look else None,
            "declaration_check": P["declaration"],
            "seconds": round(time.time() - t0, 1), "reads": G.reads(), "spec": P["spec"]}
    trades = res["_trades"]
    fr = []
    for (k, chain, mode, ex), t in trades.items():
        if len(t):
            fr.append(t.assign(sleeve=k, chain=chain, mode=mode, exec=ex))
    out = P["out"]
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
