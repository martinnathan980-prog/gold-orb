"""validation_hi -- THE LOOK: one command, once, after it is declared in the protocol.

    LOOK_DECLARED=/home/user/gold-orb/lab/PROTOCOL_V3.md \\
    NUMBA_CACHE_DIR=/tmp/numba_validation_hi PYTHONDONTWRITEBYTECODE=1 \\
    python3 /home/user/gold-orb/lab/r2/tracks/validation_hi/look.py \\
        --spec /home/user/gold-orb/lab/r2/tracks/validation_hi/look_spec.json --cut 2026-01-01

What it does, in this order (plan(), then vhi_guard.open_run, both before any data is read):
  1. Reads the spec file once; its sha256 is computed on those very bytes, which are the spec that runs.
  2. The CUT rules: CUT > 2026-01-01 is always refused. A look (2022-01-01 < CUT <= 2026-01-01) runs only at the
     end of the spec's look window, windows.look.eval = [2022-01-01, 2026-01-01], so CUT = 2026-01-01: any other look
     CUT (2024-01-01, 2025-12-31, ...) is refused first, before the declared file is read and before anything is
     logged (a mistyped --cut cannot use up the single access). CUT > 2022-01-01 (THE LOOK) is refused unless
     LOOK_DECLARED is the protocol itself -- its real path must be exactly /home/user/gold-orb/lab/PROTOCOL_V3.md
     (A1: any other file is refused before it is read, the harness's own outputs, copies and links elsewhere
     included), and the file opened once must be that same file (st_dev and st_ino), its text read from that open
     file -- and the protocol's text contains the string "autopsy_HI_look" AND the full 64-hex sha256 of the spec
     file (the declaration is bound to this exact spec, its list of changes included).
  3. Run once: a look is refused if results/val_access.log already holds a line with track "autopsy_HI_look" or a
     '<stem>.started' marker exists in results/r2/validation_hi/look/, unless --second-access "<reason>" is given
     (the reason is written into the access label; the output gets the suffix __access<N>). --out is refused for a
     look: its output path is fixed, results/r2/validation_hi/look/<name>__cut<YYYY-MM-DD>.json.
  3b. synthesis A's FROZEN files: every file synthesis A froze that the look uses (goldlab sim / r2 / data / split,
     r2/recalc.py, r2/fp_costs.json, the strategy files, the F1 model, synthesis A's portfolio.py) must still have the
     sha256 that results/r2/autopsy/synthesis_A.json ('frozen_files_sha256', and its proposed_validation_look text)
     gives it. A look is refused otherwise, before anything is logged (checked in plan and again in open_run). At an
     in-sample CUT the check is recorded in the output's meta, not refused.
  4. For the look: appends ONE line to lab/results/val_access.log (track "autopsy_HI_look", label
     "look:<spec name>:<spec sha256[:12]>[:second_access:<reason>]"), then writes '<stem>.started' right after it,
     then installs the read guard (every parquet read cut at CUT, CSVs under lab/ refused, open() of lab/data and the
     holdout refused).
  5. Runs the spec (vhi_run.run_spec) on the spec's "look" windows (entries 2022-01-01 .. 2025-12-31) with the
     changes named in its "changes_in_look": every sleeve in FP costs and x1.5, as specified ("lab") and as the
     live program would ("live"), the portfolios as the plain sum of R x stake and through the capped account
     (6 positions, 2 per market), the comparisons at equal weekly swing (scale recomputed on the window), the
     official-trades check of the ten sleeves (synthesis A's CHECK FIRST: "check_first", the first key of the
     output; a failure is printed loudly and synthesis A's changes are then not judged), the declared criteria
     ("verdicts": synthesis_B's for K1, K2, K3; synthesis A's V1-V5 at the frozen factors for its five changes) and
     synthesis A's report ("synthesis_A": the passing changes together against the unchanged portfolio, item 6).
  6. Writes <stem>.json (all results, the spec and its sha256, the declared file and its sha256, the declaration
     check, synthesis A's frozen files check, every read with its filter, the sha256 of every harness, lens and
     strategy file the run imported and of every configuration file it opened) and <stem>__trades.parquet (every
     simulated trade). The check first's WARNING lines (an '@payoff' reference not identical to its P0 sleeve inside
     the window: a warning, not a failure) are printed after the output is written.
  7. Exit status: 0 when the run is written and the check first passed; 3 (EXIT_CHECK_FIRST_FAILED) when the output
     is written but the check first failed ("stop and report"); 1 with "REFUSED: ..." when the run is refused before
     anything is read.

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

EXIT_CHECK_FIRST_FAILED = 3     # the output is written, but synthesis A's check first failed: "stop and report"


def plan(cut, raw, out_arg=None, second_access=None, env=None, log_path=None, look_dir=None):
    """Everything look.py decides before it opens the run, checked; raises GuardError when refused. Pure: it reads
    the declared file (for a look; once, the very read that is judged and recorded), the access log, synthesis A's
    synthesis_A.json and the files it froze, and writes nothing. `raw` = the bytes of the spec file."""
    sha = hashlib.sha256(raw).hexdigest()
    spec = json.loads(raw)
    window_end = G.look_cut_check(cut, spec)              # a look runs only at the end of its look window (fix 2)
    c0, declaration = G.resolve_cut_declared(cut, env=env, spec_sha=sha)
    look = G.is_look(c0)
    base = (look_dir or G.LOOK_DIR) if look else os.path.join(G.LAB, "results", "r2", "validation_hi", "rehearsal")
    stem = f"{spec['name']}__cut{c0.date()}"
    label = f"look:{spec['name']}:{sha[:12]}"
    if look:
        if out_arg:
            raise G.GuardError("--out is refused for a look: its output path is fixed "
                               f"({os.path.join(base, stem + '.json')})")
        prior, started = G.check_run_once(second_access, log_path=log_path, look_dir=base)
        if second_access is not None:
            reason = str(second_access).strip()
            stem = f"{stem}__access{max(len(prior), len(started)) + 1}"
            label = f"{label}:second_access:{reason}"
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
    frozen = G.frozen_files_check()                       # synthesis A's frozen files (fix 5)
    if look and not frozen["ok"]:
        raise G.GuardError(G.frozen_refusal(frozen))      # a look: refused; a rehearsal: recorded only
    return {"cut": c0, "is_look": look, "sha": sha, "spec": spec, "label": label, "base": base, "stem": stem,
            "out": out, "marker": marker, "second_access": second_access, "declaration": declaration,
            "frozen_check": frozen, "look_window_end": None if window_end is None else str(window_end)}


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
    if not P["frozen_check"]["ok"]:                      # a rehearsal (a look was refused in plan): recorded only
        print("WARNING: synthesis A's frozen files differ (recorded in the meta, not refused at an in-sample CUT): "
              + "; ".join(P["frozen_check"]["problems"][:6]), file=sys.stderr)
    os.makedirs(os.path.dirname(P["out"]), exist_ok=True)
    import pandas as pd
    import vhi_run as RUN
    t0 = time.time()
    res = RUN.run_spec(P["spec"], cut)
    d = P["declaration"] or {}
    rec = G.open_run_record()
    reads = G.reads()                                    # the run's reads (before the code files are read to hash)
    meta = {"cut": str(cut), "is_look": look, "spec_path": spec_path, "spec_sha256": P["sha"], "label": P["label"],
            "second_access": P["second_access"], "marker": P["marker"],
            "declared_file": d.get("file"), "declared_real_path": d.get("real_path"),
            "declared_is_the_protocol": d.get("is_the_protocol") if look else None,
            "declared_same_file_as_the_protocol": d.get("same_file_as_the_protocol") if look else None,
            "declared_sha256": d.get("sha256"),
            "declared_text_quotes_spec_sha256": d.get("contains_spec_sha256") if look else None,
            "declaration_check": P["declaration"], "declaration_check_at_open_run": rec["declaration"],
            "look_window_end": P["look_window_end"],
            "frozen_files_check": P["frozen_check"], "frozen_files_check_at_open_run": rec["frozen_check"],
            "seconds": round(time.time() - t0, 1), "reads": reads, "spec": P["spec"]}
    # A5: the code the run executed, tied to the reviewed files (sha256 of every lab file imported, and of every
    # non-data file under lab/ opened for reading, e.g. r2/fp_costs.json and the F1 model)
    try:
        meta["code_sha256"] = RUN.imported_code_sha256([p["path"] for p in res.get("plugins") or []])
        meta["files_opened_sha256"] = RUN.opened_files_sha256(reads)
    except Exception as e:  # noqa: BLE001 -- the look's output is written whatever happens here
        meta["code_sha256_error"] = repr(e)[:300]
    meta["versions"] = {"python": sys.version.split()[0], "numpy": __import__("numpy").__version__,
                        "pandas": pd.__version__, "pyarrow": __import__("pyarrow").__version__}
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
    cf = res.get("check_first") or {}
    for w in cf.get("warnings") or []:                  # an '@payoff' reference not identical to its P0 sleeve
        print(w)
    if not cf.get("passed"):
        RUN.loud(print, [cf.get("status", "CHECK FIRST NOT COMPUTED"), f"see 'check_first' at the top of {out}"])
        print(f"CHECK FIRST FAILED: {cf.get('status', 'not computed')}", file=sys.stderr)
        sys.exit(EXIT_CHECK_FIRST_FAILED)


if __name__ == "__main__":
    main()
