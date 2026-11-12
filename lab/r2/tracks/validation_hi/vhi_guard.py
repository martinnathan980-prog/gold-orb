"""validation_hi -- the guard of the 2022-2025 look harness (PROTOCOL_V3 Addenda H and I).

Every run of the harness goes through `open_run(cut, label)` BEFORE any data is read. It decides what the process may
read and refuses everything else:

  * CUT is the first instant that may NOT be read. Every price frame is read with the parquet row filter `ts < CUT`
    and every trades file with `entry_time < CUT` (results realised at or after CUT are never needed in sample:
    see vhi_data.official_closed, which adds `exit_time < CUT`).
  * CUT <= 2022-01-01 is the in-sample harness (the only CUT this task uses).
  * 2022-01-01 < CUT <= 2026-01-01 is THE LOOK: refused unless the environment variable LOOK_DECLARED holds the path
    of the protocol addendum that declares it AND that file's text contains the word "declared". The run then
    appends ONE line to lab/results/val_access.log (track "autopsy_HI_look") before anything is read.
  * CUT > 2026-01-01 is refused whatever the environment says (the 2026 holdout is never read).
  * lab/holdout_raw, lab/data/holdout and any data file whose name carries "2026" are refused at every CUT.

The read guard is installed on pandas.read_parquet / read_csv and pyarrow.parquet.read_table for the whole process:
lens and strategy modules call them through their module attribute, so a read that would bypass the cut (for
example the nq_btc_follow default leader loader, which reads the research file to 2025 when no leader is set)
raises instead of reading. A frame or trades file read without a row filter strictly below CUT raises.
"""
import datetime as _dt
import json
import os
import re

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
IS_CUT = pd.Timestamp("2022-01-01", tz="UTC")           # the in-sample cut: the only one this task runs
LOOK_MAX = pd.Timestamp("2026-01-01", tz="UTC")         # never beyond: the 2026 holdout
VAL_LOG = os.path.join(LAB, "results", "val_access.log")
TRACK = "autopsy_HI_look"
DATA_DIR = os.path.join(LAB, "data")
OFFICIAL_DIR = os.path.join(LAB, "results", "r2", "recalc", "trades")
RESULTS_DIR = os.path.join(LAB, "results")
FORBIDDEN_DIRS = (os.path.join(LAB, "holdout_raw"), os.path.join(LAB, "data", "holdout"))

_STATE = {"cut": None, "label": None, "logged": False, "installed": False, "reads": []}


class GuardError(RuntimeError):
    """A read or a CUT the harness refuses."""


def _utc(x):
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def declared_ok(path):
    """True when `path` is a readable file whose text contains the word 'declared' (any case)."""
    if not path or not os.path.isfile(path):
        return False
    check_path(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        return re.search(r"\bdeclared\b", f.read(), flags=re.IGNORECASE) is not None


def resolve_cut(cut, env=None):
    """The CUT of a run, checked. Raises GuardError when the run is not allowed."""
    env = os.environ if env is None else env
    c = _utc(cut)
    if c > LOOK_MAX:
        raise GuardError(f"CUT {c} is after 2026-01-01: the 2026 holdout is never read, whatever LOOK_DECLARED says")
    if c > IS_CUT:
        path = env.get("LOOK_DECLARED", "")
        if not path:
            raise GuardError(f"CUT {c} is after 2022-01-01: the look is refused until LOOK_DECLARED=<path of the "
                             "protocol addendum that declares it> is set")
        if not declared_ok(path):
            raise GuardError(f"CUT {c}: LOOK_DECLARED={path!r} is not a readable file containing the word 'declared'")
    return c


def is_look(cut):
    return _utc(cut) > IS_CUT


def check_path(path):
    """Refuse the holdout directories and any data file dated 2026, at every CUT."""
    p = os.path.abspath(str(path))
    for d in FORBIDDEN_DIRS:
        if p == d or p.startswith(d + os.sep):
            raise GuardError(f"refused: {p} is holdout data (never read by this harness)")
    if p.startswith(DATA_DIR + os.sep) and "2026" in os.path.basename(p):
        raise GuardError(f"refused: {p} is a data file dated 2026")
    return p


def _filter_bound(filters, col):
    """Largest t such that the filters contain (col, '<', t) at the top level (AND list), else None."""
    if not filters:
        return None
    flat = filters
    if isinstance(filters[0], list):            # DNF: [[...], [...]] -> only a single conjunction is accepted
        if len(filters) != 1:
            return None
        flat = filters[0]
    best = None
    for f in flat:
        if len(f) == 3 and f[0] == col and f[1] == "<":
            t = _utc(f[2])
            best = t if best is None else min(best, t)
    return best


def _check_read(path, filters, kind):
    p = check_path(path)
    cut = _STATE["cut"]
    if cut is None:
        raise GuardError(f"no run is open (vhi_guard.open_run) and {p} is read")
    if p.startswith(DATA_DIR + os.sep):
        b = _filter_bound(filters, "ts")
        if b is None or b > cut:
            raise GuardError(f"refused: {p} read without the row filter ts < CUT ({cut}); filters={filters!r}")
    elif p.startswith(RESULTS_DIR + os.sep) and kind in ("parquet", "read_table"):
        # every trades file (the official ones and any lens output) is read with entry_time < CUT
        b = _filter_bound(filters, "entry_time")
        if b is None or b > cut:
            raise GuardError(f"refused: {p} read without the row filter entry_time < CUT ({cut}); filters={filters!r}")
    _STATE["reads"].append({"path": os.path.relpath(p, LAB), "kind": kind, "filters": repr(filters)})
    return p


def install_read_guard():
    """Wrap pandas.read_parquet, pandas.read_csv and pyarrow.parquet.read_table (once per process)."""
    if _STATE["installed"]:
        return
    import pyarrow.parquet as pq

    orig_rp, orig_csv, orig_rt = pd.read_parquet, pd.read_csv, pq.read_table

    def read_parquet(path, *a, **kw):
        _check_read(path, kw.get("filters"), "parquet")
        return orig_rp(path, *a, **kw)

    def read_csv(path, *a, **kw):
        if isinstance(path, (str, os.PathLike)):
            p = check_path(path)
            if p.startswith(DATA_DIR + os.sep):
                raise GuardError(f"refused: raw data csv {p} (no row filter possible)")
        return orig_csv(path, *a, **kw)

    def read_table(source, *a, **kw):
        if isinstance(source, (str, os.PathLike)):
            _check_read(source, kw.get("filters"), "read_table")
        return orig_rt(source, *a, **kw)

    pd.read_parquet, pd.read_csv, pq.read_table = read_parquet, read_csv, read_table
    _STATE["installed"] = True


def log_access(label):
    """One line in results/val_access.log, same format as the existing lines. ONLY for a CUT after 2022-01-01."""
    cut = _STATE["cut"]
    if cut is None or not is_look(cut):
        raise GuardError("val_access.log is written only by a run whose CUT is after 2022-01-01")
    if _STATE["logged"]:
        return
    row = {"time": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"), "track": TRACK, "label": label,
           "period": "val"}
    with open(VAL_LOG, "a") as f:
        f.write(json.dumps(row) + "\n")
    _STATE["logged"] = True


def open_run(cut, label):
    """Check the CUT, install the read guard, and (for the look only) log the access BEFORE anything is read."""
    c = resolve_cut(cut)
    if _STATE["cut"] is not None and _STATE["cut"] != c:
        raise GuardError("one CUT per process")
    _STATE["cut"], _STATE["label"] = c, label
    install_read_guard()
    if is_look(c):
        log_access(label)
    return c


def current_cut():
    if _STATE["cut"] is None:
        raise GuardError("no run is open")
    return _STATE["cut"]


def reads():
    """Every guarded read of the process (path, kind, filters), for the run's own record."""
    return list(_STATE["reads"])


def self_test():
    """The refusals, checked without touching any data (no file is read, nothing is logged)."""
    out = {}
    env0 = {}
    for name, cut, env, want in (
            ("cut_2022_allowed", "2022-01-01", env0, True),
            ("cut_2021_allowed", "2021-06-30", env0, True),
            ("cut_2023_without_env_refused", "2023-01-01", env0, False),
            ("cut_2026_without_env_refused", "2026-01-01", env0, False),
            ("cut_2026_env_not_a_file_refused", "2026-01-01", {"LOOK_DECLARED": "/nonexistent/addendum.md"}, False),
            ("cut_2026_01_02_refused_even_with_env", "2026-01-02",
             {"LOOK_DECLARED": os.path.join(LAB, "PROTOCOL_V3.md")}, False),
            ("cut_2027_refused_even_with_env", "2027-01-01", {"LOOK_DECLARED": os.path.join(LAB, "PROTOCOL_V3.md")},
             False)):
        try:
            resolve_cut(cut, env)
            got = True
        except GuardError:
            got = False
        out[name] = {"expected_allowed": want, "allowed": got, "ok": got == want}
    # a file without the word: this module's own directory holds none; use a temporary text in memory
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, dir="/tmp") as f:
        f.write("an addendum that has not been written yet")
        tmp = f.name
    try:
        try:
            resolve_cut("2026-01-01", {"LOOK_DECLARED": tmp})
            got = True
        except GuardError:
            got = False
        out["cut_2026_env_file_without_word_refused"] = {"expected_allowed": False, "allowed": got, "ok": not got}
    finally:
        os.unlink(tmp)
    for name, path in (("holdout_raw_refused", os.path.join(LAB, "holdout_raw", "x.parquet")),
                       ("data_holdout_refused", os.path.join(LAB, "data", "holdout", "xauusd.parquet")),
                       ("data_file_dated_2026_refused", os.path.join(LAB, "data", "fp", "xauusd_2026_m1.parquet"))):
        try:
            check_path(path)
            got = True
        except GuardError:
            got = False
        out[name] = {"expected_allowed": False, "allowed": got, "ok": not got}
    for name, filters, want in (("frame_with_ts_filter_at_cut", [("ts", "<", IS_CUT)], True),
                                ("frame_without_filter", None, False),
                                ("frame_with_filter_after_cut", [("ts", "<", pd.Timestamp("2023-01-01", tz="UTC"))],
                                 False)):
        b = _filter_bound(filters, "ts")
        got = b is not None and b <= IS_CUT
        out[name] = {"expected_allowed": want, "allowed": got, "ok": got == want}
    out["all_ok"] = all(v["ok"] for v in out.values() if isinstance(v, dict))
    return out
