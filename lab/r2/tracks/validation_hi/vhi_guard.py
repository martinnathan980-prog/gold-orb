"""validation_hi -- the guard of the 2022-2025 look harness (PROTOCOL_V3 Addenda H and I).

Every run of the harness goes through `open_run(cut, label, ...)` BEFORE any data is read. It decides what the process
may read and refuses everything else:

  * CUT is the first instant that may NOT be read. Every price frame is read with the parquet row filter `ts < CUT`
    and every trades file with `entry_time < CUT` (results realised at or after CUT are never needed in sample:
    see vhi_data.official_closed, which adds `exit_time < CUT`).
  * CUT <= 2022-01-01 is the in-sample harness (the only CUT this task uses).
  * 2022-01-01 < CUT <= 2026-01-01 is THE LOOK. It is refused unless (F1, the declaration bound to the spec)
    the environment variable LOOK_DECLARED names a readable file whose text contains the string "autopsy_HI_look"
    AND the full 64-hex sha256 of the spec file the run executes (look.py computes it from the very bytes it runs).
    It is also refused (F2, run once) when results/val_access.log already holds a line with track
    "autopsy_HI_look" or a '<stem>.started' marker exists, unless a second access is asked with its reason, which is
    then written into the label. The run appends ONE line to lab/results/val_access.log (track "autopsy_HI_look")
    and, right after it, the '<stem>.started' marker, before anything is read.
  * CUT > 2026-01-01 is refused whatever the environment says (the 2026 holdout is never read).
  * lab/holdout_raw, lab/data/holdout and any file whose name carries "2026" are refused at every CUT.

THE READ GUARD (F3), installed for the whole process by open_run:
  * pandas.read_parquet, pyarrow.parquet(.core).read_table / read_pandas / ParquetDataset: the source must be a str
    or os.PathLike path (file objects, bytes, buffers, lists, '~' and URIs such as 'file://...' are refused), resolved
    with os.path.realpath; EVERY parquet read, wherever the file is, must carry a top-level row filter
    (col, '<', t) with t <= CUT, col = 'ts' under lab/data, col in ('ts', 'entry_time', 't_dec') elsewhere; a
    `filesystem` argument is refused.
  * pyarrow.parquet(.core).ParquetFile, read_metadata and pyarrow.dataset.dataset cannot carry a row filter: refused
    (they work only inside a read that the guard has already checked, e.g. pandas -> pyarrow internals).
  * pandas.read_csv / read_table / read_fwf: path only (buffers refused); refused under lab/ except the allowlist
    CSV_ALLOW; every CSV read is recorded.
  * builtins.open and io.open (hence pathlib): refused on lab/data/** and the holdout directories (any mode), and on
    any file whose name carries "2026" (reading modes); every reading open of a file under lab/ is recorded.
  Lens and strategy modules call these through their module attribute, so they are covered too: a read that would
  bypass the cut (for example the nq_btc_follow default leader loader, which reads the research file to 2025 when no
  leader is set) raises instead of reading. What is not covered: pyarrow.fs file objects, os.open / mmap and other
  processes; nothing in the harness uses them.
"""
import builtins
import datetime as _dt
import functools
import glob
import hashlib
import io
import json
import os
import re
import threading

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
LAB_REAL = os.path.realpath(LAB)
IS_CUT = pd.Timestamp("2022-01-01", tz="UTC")           # the in-sample cut: the only one this task runs
LOOK_MAX = pd.Timestamp("2026-01-01", tz="UTC")         # never beyond: the 2026 holdout
VAL_LOG = os.path.join(LAB, "results", "val_access.log")
TRACK = "autopsy_HI_look"
DATA_DIR = os.path.join(LAB, "data")
OFFICIAL_DIR = os.path.join(LAB, "results", "r2", "recalc", "trades")
RESULTS_DIR = os.path.join(LAB, "results")
LOOK_DIR = os.path.join(LAB, "results", "r2", "validation_hi", "look")
FORBIDDEN_DIRS = (os.path.join(LAB, "holdout_raw"), os.path.join(LAB, "data", "holdout"))
DATA_REAL = os.path.realpath(DATA_DIR)
FORBIDDEN_REAL = tuple(os.path.realpath(d) for d in FORBIDDEN_DIRS)
TIME_COLS = ("ts", "entry_time", "t_dec")               # the row-filter columns a parquet read may be cut on
CSV_ALLOW = ("results/r2/autopsy/payoff/variants_table.csv",)   # the only CSV under lab/ the process may read
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
URI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")

_STATE = {"cut": None, "label": None, "logged": False, "installed": False, "reads": [], "marker": None}
_TL = threading.local()
_ORIG = {}


class GuardError(RuntimeError):
    """A read or a CUT the harness refuses."""


def _utc(x):
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _under(p, d):
    return p == d or p.startswith(d + os.sep)


def _rel(p):
    return os.path.relpath(p, LAB_REAL) if _under(p, LAB_REAL) else p


# ------------------------------------------------------------------------------------------------- the declaration (F1)
def declaration_check(path, spec_sha):
    """What the declared file says about this look: readable, its sha256, whether its text contains the string
    'autopsy_HI_look' and the full 64-hex sha256 of the spec (any case). ok = both."""
    out = {"file": path or None, "readable": False, "sha256": None, "contains_track": False,
           "contains_spec_sha256": False, "spec_sha256": spec_sha, "ok": False}
    if not path or not os.path.isfile(path):
        return out
    check_holdout(path)                          # a protocol text, not data: its name may carry a 2026 date
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8", errors="replace")
    good_sha = isinstance(spec_sha, str) and SHA_RE.match(spec_sha) is not None
    out.update(readable=True, sha256=hashlib.sha256(raw).hexdigest(), contains_track=TRACK in text,
               contains_spec_sha256=bool(good_sha and spec_sha in text.lower()))
    out["ok"] = bool(out["contains_track"] and out["contains_spec_sha256"])
    return out


def resolve_cut(cut, env=None, spec_sha=None):
    """The CUT of a run, checked. Raises GuardError when the run is not allowed. For a CUT after 2022-01-01 the
    declared file (LOOK_DECLARED in `env`, default os.environ) must contain 'autopsy_HI_look' and `spec_sha`, the
    full sha256 of the spec file the run executes."""
    env = os.environ if env is None else env
    c = _utc(cut)
    if c > LOOK_MAX:
        raise GuardError(f"CUT {c} is after 2026-01-01: the 2026 holdout is never read, whatever LOOK_DECLARED says")
    if c > IS_CUT:
        if not (isinstance(spec_sha, str) and SHA_RE.match(spec_sha)):
            raise GuardError(f"CUT {c} is after 2022-01-01: the look needs the full sha256 of its spec file "
                             f"(look.py passes it); got {spec_sha!r}")
        path = env.get("LOOK_DECLARED", "")
        if not path:
            raise GuardError(f"CUT {c} is after 2022-01-01: the look is refused until LOOK_DECLARED=<path of the "
                             "protocol addendum that declares it> is set")
        d = declaration_check(path, spec_sha)
        if not d["readable"]:
            raise GuardError(f"CUT {c}: LOOK_DECLARED={path!r} is not a readable file")
        if not d["ok"]:
            raise GuardError(f"CUT {c}: the text of LOOK_DECLARED={path!r} must contain the string {TRACK!r} and the "
                             f"full sha256 of the spec ({spec_sha}); contains {TRACK!r}: {d['contains_track']}, "
                             f"contains the spec sha256: {d['contains_spec_sha256']}")
    return c


def is_look(cut):
    return _utc(cut) > IS_CUT


# ------------------------------------------------------------------------------------------------- run once (F2)
def prior_look_lines(log_path=None):
    """The lines of results/val_access.log whose track is 'autopsy_HI_look' (a line that is not JSON counts when it
    contains that name)."""
    p = VAL_LOG if log_path is None else log_path
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8", errors="replace") as f:
        for ln in f:
            s = ln.strip()
            if not s:
                continue
            try:
                d = json.loads(s)
                hit = isinstance(d, dict) and d.get("track") == TRACK
            except ValueError:
                hit = TRACK in s
            if hit:
                out.append(s)
    return out


def started_markers(look_dir=None):
    return sorted(glob.glob(os.path.join(LOOK_DIR if look_dir is None else look_dir, "*.started")))


def check_run_once(second_access=None, log_path=None, look_dir=None):
    """Raise GuardError unless this look is the first access (no 'autopsy_HI_look' line in val_access.log, no
    '.started' marker), or a second access asked with a non-empty reason after an earlier access. Returns
    (earlier access lines, markers)."""
    prior, started = prior_look_lines(log_path), started_markers(look_dir)
    if second_access is not None:
        if not str(second_access).strip():
            raise GuardError("--second-access needs a reason (it is written into the access label)")
        if not prior and not started:
            raise GuardError("--second-access is for a look whose first access is already logged; there is none")
    elif prior or started:
        raise GuardError(f"the look is run once: val_access.log already holds {len(prior)} line(s) with track "
                         f"{TRACK!r} and {len(started)} '.started' marker(s) exist; a second access needs "
                         "--second-access '<reason>'")
    return prior, started


def write_marker(path, body):
    """The '<stem>.started' marker of a look, written right after its access line (exclusive create)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "x") as f:
            json.dump(body, f, indent=1, default=str)
    except FileExistsError as e:
        raise GuardError(f"{path} exists: the look is run once") from e
    _STATE["marker"] = path


# ------------------------------------------------------------------------------------------------- paths and filters
def check_holdout(path):
    """Refuse the holdout directories (real path). Returns the real path."""
    s = os.fspath(path)
    if isinstance(s, bytes):
        s = os.fsdecode(s)
    p = os.path.realpath(s)
    for d in FORBIDDEN_REAL:
        if _under(p, d):
            raise GuardError(f"refused: {p} is holdout data (never read by this harness)")
    return p


def check_path(path):
    """Refuse the holdout directories and any file whose name carries '2026', at every CUT. Returns the real path."""
    p = check_holdout(path)
    if "2026" in os.path.basename(p):
        raise GuardError(f"refused: {p} is dated 2026")
    return p


def source_path(src, what="read"):
    """The real path of a read's source. Only a str or os.PathLike path is accepted: file objects, bytes, buffers,
    lists, '~' and URIs ('file://...', 's3:...') are refused."""
    if isinstance(src, os.PathLike):
        s = os.fspath(src)
    elif isinstance(src, str):
        s = src
    else:
        raise GuardError(f"refused: {what} of a {type(src).__name__} (only a str or os.PathLike path is accepted)")
    if not isinstance(s, str):
        raise GuardError(f"refused: {what} of a bytes path {s!r}")
    if "://" in s or URI_RE.match(s):
        raise GuardError(f"refused: {what} of a URI {s!r}")
    if "~" in s:
        raise GuardError(f"refused: {what} of a path with '~' {s!r}")
    return os.path.realpath(s)


def _filter_bound(filters, col):
    """Largest t such that the filters contain (c, '<', t) for c in `col` (a name or a tuple of names) at the top
    level (AND list), else None. A DNF with more than one conjunction gives None."""
    if not filters:
        return None
    cols = (col,) if isinstance(col, str) else tuple(col)
    flat = filters
    if isinstance(filters[0], list):            # DNF: [[...], [...]] -> only a single conjunction is accepted
        if len(filters) != 1:
            return None
        flat = filters[0]
    best = None
    for f in flat:
        if isinstance(f, (tuple, list)) and len(f) == 3 and f[0] in cols and f[1] == "<":
            t = _utc(f[2])
            best = t if best is None else min(best, t)
    return best


def _record(p, kind, filters=None, bound=None):
    _STATE["reads"].append({"path": _rel(p), "kind": kind, "filters": repr(filters),
                            "bound": None if bound is None else str(bound)})


def _check_read(path, filters, kind, filesystem=None):
    """A parquet read: path only, real path, not holdout / 2026, a row filter at or before CUT. Recorded."""
    p = check_path(source_path(path, kind))
    cut = _STATE["cut"]
    if cut is None:
        raise GuardError(f"no run is open (vhi_guard.open_run) and {p} is read")
    if filesystem is not None:
        raise GuardError(f"refused: {kind} of {p} with a filesystem argument")
    cols = ("ts",) if _under(p, DATA_REAL) else TIME_COLS
    b = _filter_bound(filters, cols)
    if b is None or b > cut:
        raise GuardError(f"refused: {p} read without a row filter ({' | '.join(cols)}) < t with t <= CUT ({cut}); "
                         f"filters={filters!r}")
    _record(p, kind, filters, b)
    return p


def _check_csv(path, kind):
    p = check_path(source_path(path, kind))
    if _under(p, LAB_REAL) and _rel(p) not in CSV_ALLOW:
        raise GuardError(f"refused: csv {_rel(p)} under lab/ (allowed: {', '.join(CSV_ALLOW)})")
    _record(p, kind)
    return p


def _open_check(file, args, kwargs):
    """builtins.open / io.open: refuse lab/data/** and the holdout (any mode), files dated 2026 (reading modes);
    record every reading open under lab/."""
    if isinstance(file, int):
        return
    try:
        s = os.fspath(file)
    except TypeError:
        return                                   # not a path: open() raises its own error
    if isinstance(s, bytes):
        s = os.fsdecode(s)
    p = os.path.realpath(s)
    mode = args[0] if args else kwargs.get("mode", "r")
    for d in FORBIDDEN_REAL:
        if _under(p, d):
            raise GuardError(f"refused: open() of {p} (holdout data)")
    if _under(p, DATA_REAL):
        raise GuardError(f"refused: open() of {p}: lab/data is read only through the guarded parquet readers, with "
                         "a row filter")
    reading = ("r" in mode) or ("+" in mode)
    if reading and "2026" in os.path.basename(p):
        raise GuardError(f"refused: open() of {p}: dated 2026")
    if reading and _under(p, LAB_REAL):
        _record(p, "open")


# ------------------------------------------------------------------------------------------------- the read guard
def _inside():
    return getattr(_TL, "depth", 0) > 0


class _Inside:
    """Inside a read the guard has checked: the library's own nested calls (pandas -> pyarrow, pandas -> open,
    ParquetDataset -> pyarrow.dataset) pass without a second check and are not recorded twice."""

    def __enter__(self):
        _TL.depth = getattr(_TL, "depth", 0) + 1

    def __exit__(self, *exc):
        _TL.depth -= 1


def _only_source_positional(name, a):
    if len(a) > 1:
        raise GuardError(f"refused: {name} with positional arguments after the source (pass filters=... by keyword)")


def _wrap(fn, check):
    @functools.wraps(fn)
    def w(*a, **kw):
        if _inside():
            return fn(*a, **kw)
        check(a, kw)
        with _Inside():
            return fn(*a, **kw)
    w.__vhi_guarded__ = True
    return w


def _refuse_always(name, why):
    def check(a, kw):
        raise GuardError(f"refused: {name} {why}")
    return check


def install_read_guard():
    """Wrap the parquet, CSV and open() entry points (once per process). See the module docstring."""
    if _STATE["installed"]:
        return
    import pandas.io.parquet as pdpq
    import pandas.io.parsers as pdparsers
    import pandas.io.parsers.readers as pdreaders
    import pyarrow.dataset as pads
    import pyarrow.parquet as pq
    import pyarrow.parquet.core as pqc

    def chk_parquet(name):
        def check(a, kw):
            _only_source_positional(name, a)
            src = a[0] if a else kw.get("path", kw.get("source"))
            _check_read(src, kw.get("filters"), name, kw.get("filesystem"))
        return check

    def chk_csv(name):
        def check(a, kw):
            _only_source_positional(name, a)
            _check_csv(a[0] if a else kw.get("filepath_or_buffer"), name)
        return check

    _ORIG.update(read_parquet=pd.read_parquet, read_csv=pd.read_csv, read_table_pd=pd.read_table, read_fwf=pd.read_fwf,
                 read_table=pqc.read_table, read_pandas=pqc.read_pandas, ParquetFile=pqc.ParquetFile,
                 ParquetDataset=pqc.ParquetDataset, read_metadata=pqc.read_metadata, dataset=pads.dataset,
                 parquet_dataset=pads.parquet_dataset, open=builtins.open, io_open=io.open)

    rp = _wrap(_ORIG["read_parquet"], chk_parquet("pandas.read_parquet"))
    pd.read_parquet = pdpq.read_parquet = rp
    for nm, orig in (("read_csv", _ORIG["read_csv"]), ("read_table", _ORIG["read_table_pd"]), ("read_fwf", _ORIG["read_fwf"])):
        w = _wrap(orig, chk_csv(f"pandas.{nm}"))
        setattr(pd, nm, w)
        for mod in (pdparsers, pdreaders):
            if getattr(mod, nm, None) is orig:
                setattr(mod, nm, w)
    rt = _wrap(_ORIG["read_table"], chk_parquet("pyarrow.parquet.read_table"))
    rpd = _wrap(_ORIG["read_pandas"], chk_parquet("pyarrow.parquet.read_pandas"))
    rmd = _wrap(_ORIG["read_metadata"], _refuse_always("pyarrow.parquet.read_metadata", "(row-group statistics "
                                                                                          "cannot be cut at CUT)"))
    dsf = _wrap(_ORIG["dataset"], _refuse_always("pyarrow.dataset.dataset", "(no row filter can be checked at its "
                                                                             "creation: use pandas.read_parquet with filters)"))
    pdsf = _wrap(_ORIG["parquet_dataset"], _refuse_always("pyarrow.dataset.parquet_dataset", "(no row filter can be "
                                                                                              "checked at its creation)"))
    PF0, PD0 = _ORIG["ParquetFile"], _ORIG["ParquetDataset"]

    class ParquetFile(PF0):
        """pyarrow.parquet.ParquetFile, guarded: it reads row groups without a row filter, so it is refused outside a
        read the guard has already checked."""

        def __init__(self, source, *a, **kw):
            if not _inside():
                raise GuardError("refused: pyarrow.parquet.ParquetFile (no row filter; use pandas.read_parquet / "
                                 "pyarrow.parquet.read_table with filters)")
            super().__init__(source, *a, **kw)

    class ParquetDataset(PD0):
        """pyarrow.parquet.ParquetDataset, guarded: a single path and a row filter at or before CUT."""

        def __init__(self, path_or_paths, *a, **kw):
            if _inside():
                super().__init__(path_or_paths, *a, **kw)
                return
            fs = a[0] if a else kw.get("filesystem")
            _check_read(path_or_paths, kw.get("filters"), "pyarrow.parquet.ParquetDataset", fs)
            with _Inside():
                super().__init__(path_or_paths, *a, **kw)

    for mod in (pq, pqc):
        mod.read_table, mod.read_pandas, mod.read_metadata = rt, rpd, rmd
        mod.ParquetFile, mod.ParquetDataset = ParquetFile, ParquetDataset
    pads.dataset, pads.parquet_dataset = dsf, pdsf

    orig_open = _ORIG["open"]

    @functools.wraps(orig_open)
    def guarded_open(file, *args, **kwargs):
        if not _inside():
            _open_check(file, args, kwargs)
        return orig_open(file, *args, **kwargs)

    guarded_open.__vhi_guarded__ = True
    builtins.open = io.open = guarded_open
    _STATE["installed"] = True


# ------------------------------------------------------------------------------------------------- the run
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


def open_run(cut, label, spec_sha=None, second_access=None, marker=None):
    """Check the CUT (and, for a look, the declaration bound to the spec and the run-once rule), then (for the look
    only) log the access and write the '.started' marker, then install the read guard -- all BEFORE anything is
    read."""
    c = resolve_cut(cut, spec_sha=spec_sha)
    if _STATE["cut"] is not None and _STATE["cut"] != c:
        raise GuardError("one CUT per process")
    look = is_look(c)
    if look:
        if _STATE["logged"]:
            raise GuardError("this process has already logged its access")
        if not marker:
            raise GuardError("a look writes its '<stem>.started' marker: no marker path given")
        check_run_once(second_access, look_dir=os.path.dirname(marker))
        if os.path.exists(marker):
            raise GuardError(f"{marker} exists: the look is run once")
        if second_access is not None and str(second_access).strip() not in label:
            raise GuardError("the second-access reason must be written into the access label")
    _STATE["cut"], _STATE["label"] = c, label
    if look:
        log_access(label)
        write_marker(marker, {"time": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                              "track": TRACK, "label": label, "cut": str(c), "spec_sha256": spec_sha,
                              "declared_file": os.environ.get("LOOK_DECLARED"), "second_access": second_access,
                              "pid": os.getpid()})
    install_read_guard()
    return c


def current_cut():
    if _STATE["cut"] is None:
        raise GuardError("no run is open")
    return _STATE["cut"]


def reads():
    """Every guarded read of the process (path, kind, filters, bound), for the run's own record."""
    return list(_STATE["reads"])


def self_test(spec_sha=None, protocol=None):
    """The CUT rules checked on SIMULATED environments (dicts: the process environment is never set) with temporary
    addendum texts; only resolve_cut is called (it returns a timestamp: nothing is opened, read or logged).
    The temporary texts quote a DUMMY spec sha256 (never the real one), so no file written here could serve as the
    declaration of the real look. `spec_sha` (the real spec's sha256) and `protocol` (lab/PROTOCOL_V3.md) check that
    the protocol as it stands is refused."""
    import tempfile
    out = {}
    env0 = {}
    dummy = hashlib.sha256(b"vhi_guard self_test: a dummy spec, not the look's").hexdigest()
    other = hashlib.sha256(b"another dummy spec").hexdigest()
    texts = {"full": f"Addendum (test text): the look {TRACK} is declared; spec sha256 {dummy}.",
             "full_upper": f"Addendum (test text): {TRACK}, spec sha256 {dummy.upper()}.",
             "word_declared_only": "Addendum J (test text): the look is declared here.",
             "track_only": f"Addendum (test text): the look {TRACK} is declared.",
             "sha_only": f"Addendum (test text): spec sha256 {dummy}.",
             "track_and_sha12": f"Addendum (test text): {TRACK}, spec {dummy[:12]}.",
             "track_and_other_sha": f"Addendum (test text): {TRACK}, spec sha256 {other}.",
             "unwritten": "an addendum that has not been written yet"}
    files = {}
    tmpd = tempfile.mkdtemp(prefix="vhi_selftest_")
    try:
        for k, t in texts.items():
            files[k] = os.path.join(tmpd, f"addendum_{k}.txt")
            with open(files[k], "w") as f:
                f.write(t)
        cases = [("cut_2022_allowed", "2022-01-01", env0, None, True),
                 ("cut_2021_allowed", "2021-06-30", env0, None, True),
                 ("cut_2023_without_env_refused", "2023-01-01", env0, dummy, False),
                 ("cut_2026_without_env_refused", "2026-01-01", env0, dummy, False),
                 ("cut_2026_env_not_a_file_refused", "2026-01-01", {"LOOK_DECLARED": "/nonexistent/addendum.md"}, dummy, False),
                 ("cut_2026_text_with_word_declared_only_refused (the old gate)", "2026-01-01",
                  {"LOOK_DECLARED": files["word_declared_only"]}, dummy, False),
                 ("cut_2026_text_with_track_only_refused", "2026-01-01", {"LOOK_DECLARED": files["track_only"]}, dummy, False),
                 ("cut_2026_text_with_sha_only_refused", "2026-01-01", {"LOOK_DECLARED": files["sha_only"]}, dummy, False),
                 ("cut_2026_text_with_track_and_sha12_refused", "2026-01-01", {"LOOK_DECLARED": files["track_and_sha12"]},
                  dummy, False),
                 ("cut_2026_text_with_track_and_another_specs_sha_refused", "2026-01-01",
                  {"LOOK_DECLARED": files["track_and_other_sha"]}, dummy, False),
                 ("cut_2026_text_unwritten_refused", "2026-01-01", {"LOOK_DECLARED": files["unwritten"]}, dummy, False),
                 ("cut_2026_full_declaration_but_no_spec_sha_refused", "2026-01-01", {"LOOK_DECLARED": files["full"]},
                  None, False),
                 ("cut_2026_full_declaration_but_short_spec_sha_refused", "2026-01-01", {"LOOK_DECLARED": files["full"]},
                  dummy[:12], False),
                 ("cut_2026_text_with_track_and_full_sha_allowed (resolve only, nothing opened)", "2026-01-01",
                  {"LOOK_DECLARED": files["full"]}, dummy, True),
                 ("cut_2026_text_with_track_and_full_sha_in_capitals_allowed (resolve only)", "2026-01-01",
                  {"LOOK_DECLARED": files["full_upper"]}, dummy, True),
                 ("cut_2026_01_02_refused_even_with_full_declaration", "2026-01-02", {"LOOK_DECLARED": files["full"]},
                  dummy, False),
                 ("cut_2027_refused_even_with_full_declaration", "2027-01-01", {"LOOK_DECLARED": files["full"]}, dummy, False)]
        if spec_sha and protocol:
            cases.append(("cut_2026_LOOK_DECLARED_PROTOCOL_V3.md_as_it_stands_refused", "2026-01-01",
                          {"LOOK_DECLARED": protocol}, spec_sha, False))
        for name, cut, env, sha, want in cases:
            try:
                resolve_cut(cut, env, spec_sha=sha)
                got, why = True, None
            except GuardError as e:
                got, why = False, str(e)[:300]
            out[name] = {"expected_allowed": want, "allowed": got, "ok": got == want, "why": why}
    finally:
        for p in files.values():
            if os.path.exists(p):
                os.unlink(p)
        os.rmdir(tmpd)
    if spec_sha and protocol:
        d = declaration_check(protocol, spec_sha)
        out["PROTOCOL_V3.md_as_it_stands"] = {"expected_allowed": False, "allowed": d["ok"], "ok": not d["ok"],
                                              "sha256": d["sha256"], "contains_track": d["contains_track"],
                                              "contains_spec_sha256": d["contains_spec_sha256"]}
    for name, path in (("holdout_raw_refused", os.path.join(LAB, "holdout_raw", "x.parquet")),
                       ("data_holdout_refused", os.path.join(LAB, "data", "holdout", "xauusd.parquet")),
                       ("data_file_dated_2026_refused", os.path.join(LAB, "data", "fp", "xauusd_2026_m1.parquet")),
                       ("any_file_dated_2026_refused", os.path.join(LAB, "results", "live", "brain_maps_2026-11-11.json"))):
        try:
            check_path(path)
            got = True
        except GuardError:
            got = False
        out[name] = {"expected_allowed": False, "allowed": got, "ok": not got}
    for name, src, want in (("source_str_path_accepted", os.path.join(LAB, "data", "fp", "ethusd_m1.parquet"), True),
                            ("source_bytes_refused", os.fsencode(os.path.join(LAB, "data", "fp", "ethusd_m1.parquet")), False),
                            ("source_file_uri_refused", "file://" + os.path.join(LAB, "data", "fp", "ethusd_m1.parquet"), False),
                            ("source_scheme_refused", "file:" + os.path.join(LAB, "data", "fp", "ethusd_m1.parquet"), False),
                            ("source_buffer_refused", io.BytesIO(b""), False),
                            ("source_list_refused", [os.path.join(LAB, "data", "fp", "ethusd_m1.parquet")], False),
                            ("source_tilde_refused", "~/gold-orb/lab/data/fp/ethusd_m1.parquet", False)):
        try:
            source_path(src)
            got = True
        except GuardError:
            got = False
        out[name] = {"expected_allowed": want, "allowed": got, "ok": got == want}
    for name, filters, cols, want in (("frame_with_ts_filter_at_cut", [("ts", "<", IS_CUT)], ("ts",), True),
                                      ("frame_without_filter", None, ("ts",), False),
                                      ("frame_with_entry_time_filter_refused (lab/data needs ts)",
                                       [("entry_time", "<", IS_CUT)], ("ts",), False),
                                      ("frame_with_filter_after_cut", [("ts", "<", pd.Timestamp("2023-01-01", tz="UTC"))],
                                       ("ts",), False),
                                      ("frame_with_le_filter_refused", [("ts", "<=", IS_CUT)], ("ts",), False),
                                      ("trades_with_t_dec_filter_at_cut", [("t_dec", "<", IS_CUT)], TIME_COLS, True),
                                      ("dnf_with_two_conjunctions_refused", [[("ts", "<", IS_CUT)], [("ts", ">", IS_CUT)]],
                                       ("ts",), False)):
        b = _filter_bound(filters, cols)
        got = b is not None and b <= IS_CUT
        out[name] = {"expected_allowed": want, "allowed": got, "ok": got == want}
    out["all_ok"] = all(v["ok"] for v in out.values() if isinstance(v, dict))
    return out
