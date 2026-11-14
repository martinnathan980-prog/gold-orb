"""Read what ReleveFP.mq5 and SondeFP.mq5 wrote on the Mac and set the robot's and the lab's assumptions against the
broker's real values, symbol by symbol.

    python3 -I lab/robot/demo/read_mac_files.py <folder with the files> [--out DIR]

Any of these files may be missing (the folder is MQL5/Files/claude/releve on the Mac, copied here):
  fiches.csv     ReleveFP.mq5 FicheHeader() and Fiche() (lines 92-134): one line per market asked for, 31 fields:
                 base,name,path,description,digits,point,tick_size,tick_value,tick_value_loss,contract_size,vol_min,
                 vol_step,vol_max,calc_mode,exe_mode,spread_float,spread_points,stops_level,swap_mode,swap_long,
                 swap_short,swap_3days,margin_initial,margin_1lot,ccy_base,ccy_profit,ccy_margin,bid,ask,tick_time,
                 sessions; "base,INTROUVABLE,,,..." when the market is not found. Commas are taken out of path and
                 description (Clean, :67-73), so a plain split is exact. sessions = "dw:from-to|..." in minutes of the
                 server day, dw 0 = Sunday (Sessions, :76-87). margin_1lot = OrderCalcMargin(buy, 1 lot, ask) in the
                 account currency, 0 when it failed (:107-108).
  tous.csv       ReleveFP.mq5 AllSymbols() (:139-162): name,path,description,digits,contract_size,vol_min,vol_step,
                 calc_mode,swap_long,swap_short,ccy_profit,trade_mode, every symbol of the server in its own order.
  fini.txt       ReleveFP.mq5 OnStart() (:308-332): key=value lines (version, server, company, currency, leverage, demo,
                 server_time, server_minus_gmt_sec, all_symbols, one "BASE=NAME jours=.. minutes=.. ticks=.. du=..
                 au=.. derniere_erreur=.. jours_incomplets=.." line per market or "BASE=INTROUVABLE", stopped,
                 seconds). The server name is masked at once and never written or printed.
  m1_<BASE>.csv  ReleveFP.mq5 Minutes() and Row() (:167-271): time,bo,bh,bl,bc,ao,ah,al,ac,n,sp_mean,sp_max; time =
                 the minute's start, server seconds; bid and ask O/H/L/C of the ticks of the minute (COPY_TICKS_INFO,
                 ticks with bid and ask > 0), prices with the symbol's digits, n ticks, sp_mean = mean of ask - bid
                 (digits + 2 decimals), sp_max = largest ask - bid (price units, not points). Days are written newest
                 first, minutes in order inside a day.
  sonde.csv      SondeFP.mq5 OnStart() and Probe() (:77-197, 228, 247): base,name,status,volume,bid_before,
                 ask_before,buy_price,bid_at_close,ask_at_close,sell_price,deals,commission,fee,profit,swap,tick_size,
                 tick_value,contract_size,position (19 fields; a probe that stopped early writes "base,name,<why>",
                 "base,,INTROUVABLE" when not found); commission, fee, profit and swap are the sums over the position's
                 deals (DEAL_COMMISSION etc., account currency) for `volume` lots; status "ok" only when both deals
                 were read back. Last line "#currency=..,server=..,server_time=.." (server masked).
What is set against what (robot = the shipped EA's constants and SPEC; lab = lab/r2/fp_costs.json and the harness,
check/mock_replay.h): names (CR_Broker.mqh BrkResolve on tous.csv), digits and point (the harness rounds to 2
digits), contract size, volume min / step / max, EUR tick value (harness 0.89 x tick size x units), stops level
(mock 0), freeze level and filling (not in the files: UNKNOWN), margin mode (hedging: SondeFP refuses to trade on
another mode), margin (effective leverage from margin_1lot against fp_costs.json and the mock: gold 1:500, US100
1:200, crypto 1:50; the T7b reading at 1:2), commission (SondeFP against the robot's 6-point gold commission and
none on the others), swaps (annual % of the price against fp_costs.json), spreads (m1 files against fp_costs.json),
sessions (SPEC 10.5: the Friday gold session to 23:46 server, crypto at weekends, holiday sessions against the
robot's built-in closures of SPEC 2.1) and the server clock (SPEC 10.4: New York + 7 h).
A holiday session counts as complete when the m1 file covers its start and either holds a later bar or ReleveFP ran
after the session's end (fini.txt server_time: the ticks up to then are in the file), so a weekend run judges the
Friday after Thanksgiving. A suggested InpExtraClosures window is written in absolute New York dates and times, as
ClkInit takes it ('XAU 2021.11.24 23:00-2021.11.25 18:00'). The gold all-in spread adds the model's 0.06 USD per oz
when SondeFP's commission agrees with it within the probe's cent rounding (at 0.01 lot the cents alone count 6.98
points for a true 6), the measured one otherwise. A robot market whose fiches.csv line is missing or cut short still
gets its commission and spread checks from sonde.csv and its m1 file. The gold digits check says that the robot's
paper commission is 6 points x 0.5 x point (CR_Registry.mqh RegSetPoint): another number of digits makes it wrong.
Every check says OK, DIFFERENT or UNKNOWN with both values. Output in --out (default: the session scratchpad; a
folder inside the repository is refused): summary.json, summary_fr.txt; a short French summary on stdout.
"""
import argparse
import datetime as dt
import os
import re
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import demo_common as C  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

FICHE_COLS = ["base", "name", "path", "description", "digits", "point", "tick_size", "tick_value", "tick_value_loss",
              "contract_size", "vol_min", "vol_step", "vol_max", "calc_mode", "exe_mode", "spread_float", "spread_points",
              "stops_level", "swap_mode", "swap_long", "swap_short", "swap_3days", "margin_initial", "margin_1lot",
              "ccy_base", "ccy_profit", "ccy_margin", "bid", "ask", "tick_time", "sessions"]
TOUS_COLS = ["name", "path", "description", "digits", "contract_size", "vol_min", "vol_step", "calc_mode", "swap_long",
             "swap_short", "ccy_profit", "trade_mode"]
SONDE_COLS = ["base", "name", "status", "volume", "bid_before", "ask_before", "buy_price", "bid_at_close", "ask_at_close",
              "sell_price", "deals", "commission", "fee", "profit", "swap", "tick_size", "tick_value", "contract_size",
              "position"]
M1_COLS = ["time", "bo", "bh", "bl", "bc", "ao", "ah", "al", "ac", "n", "sp_mean", "sp_max"]   # ReleveFP 1.00; 1.10 adds sp_min
R1_COLS = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]       # ReleveFP 1.10 r1_<BASE>.csv
FINI_KEYS = {"version", "server", "company", "currency", "leverage", "demo", "server_time", "server_minus_gmt_sec",
             "all_symbols", "stopped", "seconds"}
TEXT_FIELDS = {"base", "name", "path", "description", "ccy_base", "ccy_profit", "ccy_margin", "sessions", "status"}
# MQL5 documentation order of the enumerations written as integers
SWAP_MODE = ["disabled", "points", "currency_symbol", "currency_margin", "currency_deposit", "interest_current",
             "interest_open", "reopen_current", "reopen_bid"]
CALC_MODE = {0: "forex", 1: "futures", 2: "cfd", 3: "cfd_index", 4: "cfd_leverage", 5: "forex_no_leverage",
             32: "exch_stocks", 33: "exch_futures", 34: "exch_futures_forts", 35: "exch_options", 36: "exch_options_margin",
             37: "exch_bonds", 38: "exch_stocks_moex", 39: "exch_bonds_moex", 64: "serv_collateral"}
EXE_MODE = {0: "request", 1: "instant", 2: "market", 3: "exchange"}
TRADE_MODE = {0: "disabled", 1: "long only", 2: "short only", 3: "close only", 4: "full"}
# BrkResolve's aliases (CR_Broker.mqh:148-168) and ReleveFP's (ReleveFP.mq5:42-65, more markets)
ROBOT_ALIASES = {"US100": ["NAS100", "USTEC", "US100.cash", "NDX100"], "XAUUSD": ["GOLD"]}
RELEVE_ALIASES = dict(ROBOT_ALIASES, US500=["SPX500", "SP500", "US500.cash"], GER40=["DE40", "DAX40", "GER30", "DE30"],
                      JP225=["JPN225", "JP225.cash", "NIKKEI225", "NI225", "JAP225"])
# harness and lab assumptions not in fp_costs.json (check/mock_replay.h main(): defaults; export_frames.py DIGITS)
MOCK_USDEUR = 0.89
MOCK_VMAX = 100.0
HARNESS_DIGITS = 2
T7B_TEXT = ("lecture T7b (ACCEPTANCE.md, section T7b) : a 1:2, le controle de marge (MARGIN) aurait saute 462 demandes de "
            "D2 en 2018-2021 (S7 : 250), surtout des trades crypto (NQB 165, F1B 90, F1E 78, BKB 68, BKE 43)")


# ---------------------------------------------------------------------------------------------- readers
def read_fiches(path):
    text = C.read_text(path).splitlines()
    rows, problems = {}, []
    if not text:
        return rows, ["fiches.csv est vide"]
    head = text[0].strip().split(",")
    if head != FICHE_COLS:
        problems.append("l'en-tete de fiches.csv n'est pas celui de ReleveFP 1.00 (colonnes lues par leur nom)")
    idx = {c: head.index(c) for c in FICHE_COLS if c in head}
    for no, ln in enumerate(text[1:], 2):
        if not ln.strip():
            continue
        f = ln.rstrip("\r\n").split(",")
        if len(f) != len(head):
            problems.append(f"fiches.csv ligne {no} : {len(f)} champs au lieu de {len(head)} (ligne ignoree)")
            continue
        base = f[idx["base"]].strip()
        if f[idx["name"]].strip() == "INTROUVABLE":
            rows[base] = {"base": base, "found": False}
            continue
        r = {"base": base, "found": True}
        for c, i in idx.items():
            r[c] = f[i].strip() if c in TEXT_FIELDS else C.fnum(f[i])
        rows[base] = r
    return rows, problems


def read_tous(path):
    text = C.read_text(path).splitlines()
    out, problems = [], []
    if not text:
        return out, ["tous.csv est vide"]
    head = text[0].strip().split(",")
    if head != TOUS_COLS:
        problems.append("l'en-tete de tous.csv n'est pas celui de ReleveFP 1.00")
    idx = {c: head.index(c) for c in TOUS_COLS if c in head}
    for no, ln in enumerate(text[1:], 2):
        if not ln.strip():
            continue
        f = ln.rstrip("\r\n").split(",")
        if len(f) != len(head):
            problems.append(f"tous.csv ligne {no} : {len(f)} champs (ignoree)")
            continue
        r = {c: (f[i].strip() if c in TEXT_FIELDS else C.fnum(f[i])) for c, i in idx.items()}
        out.append(r)
    return out, problems


def read_fini(path, scrub):
    out, markets = {}, {}
    for ln in C.read_text(path).splitlines():
        if "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        k, v = k.strip(), v.strip()
        if k == "server":
            scrub.add(v)
            out["server_present"] = bool(v)
            out["server_looks_demo"] = "demo" in v.lower()
            continue
        if k in FINI_KEYS:
            out[k] = C.fnum(v) if C.fnum(v) is not None else v
            continue
        if v == "INTROUVABLE":
            markets[k] = {"found": False}
            continue
        parts = v.split(" ", 1)
        m = {"found": True, "name": parts[0], "info": parts[1] if len(parts) > 1 else ""}
        info = m["info"]
        # ReleveFP 1.10 adds barres, jours_barres and erreur_barres at the end of the line (1.00 files have none)
        for key in ("jours", "minutes", "ticks", "derniere_erreur", "jours_incomplets", "barres", "jours_barres", "erreur_barres"):
            mm = re.search(r"(?:^|\s)" + key + r"=(\S*)", info)
            if mm:
                m[key] = C.fnum(mm.group(1))
        for key in ("du", "au"):
            j = info.find(key + "=")
            if j >= 0:
                m[key] = " ".join(info[j + len(key) + 1:].split(" ")[:2])
        markets[k] = m
    out["markets"] = markets
    return out


def read_sonde(path, scrub):
    text = C.read_text(path).splitlines()
    rows, meta, problems = {}, {}, []
    if not text:
        return rows, meta, ["sonde.csv est vide"]
    head = text[0].strip().split(",")
    if head != SONDE_COLS:
        problems.append("l'en-tete de sonde.csv n'est pas celui de SondeFP 1.10")
    for no, ln in enumerate(text[1:], 2):
        ln = ln.rstrip("\r\n")
        if not ln.strip():
            continue
        if ln.startswith("#"):
            for kv in ln[1:].split(","):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    if k.strip() == "server":
                        scrub.add(v.strip())
                        meta["server_present"] = True
                    else:
                        meta[k.strip()] = C.fnum(v) if C.fnum(v) is not None else v.strip()
            continue
        f = ln.split(",")
        if len(f) < 3:
            problems.append(f"sonde.csv ligne {no} : trop courte (ignoree)")
            continue
        base = f[0].strip()
        if len(f) == len(SONDE_COLS) and len(f) == len(head):
            r = {c: (f[i].strip() if c in TEXT_FIELDS else C.fnum(f[i])) for i, c in enumerate(head)}
            r["full"] = True
        elif len(f) < len(SONDE_COLS):
            r = {"base": base, "name": f[1].strip(), "status": ",".join(f[2:]).strip(), "full": False}
        else:
            problems.append(f"sonde.csv ligne {no} : {len(f)} champs (ignoree)")
            continue
        rows[base] = r
    return rows, meta, problems


def m1_digits(path):
    """digits of the prices of an m1 file: ReleveFP writes them with DoubleToString(x, digits) (Row, :172-173), so the
    decimals of the bo field are the digits exactly"""
    with open(path, "rb") as h:
        h.readline()
        first = h.readline().decode("cp1252", errors="replace").strip()
    if not first:
        return None
    bo = first.split(",")[1]
    return len(bo.split(".")[1]) if "." in bo else 0


def read_m1(path):
    """an m1 file, columns read by name (sp_min kept when there, ReleveFP 1.10)"""
    df = pd.read_csv(path, encoding="cp1252")
    missing = [c for c in M1_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"{os.path.basename(path)} : colonnes absentes {missing}")
    df = df[M1_COLS + (["sp_min"] if "sp_min" in df.columns else [])].dropna()
    df["time"] = df["time"].astype(np.int64)
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    return df


def read_r1(path):
    """ReleveFP 1.10's r1 file: the terminal's own M1 bars (MqlRates as CopyRates gives them, what the robot reads),
    days newest first: time (server seconds), bid open/high/low/close, tick_volume, spread (points), real_volume"""
    df = pd.read_csv(path, encoding="cp1252")
    need = ["time", "open", "high", "low", "close", "spread"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"{os.path.basename(path)} : colonnes absentes {missing}")
    df = df[need].dropna()
    df["time"] = df["time"].astype(np.int64)
    df["spread"] = df["spread"].astype(np.int64)
    return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def data_rows(path):
    """lines of data of a ReleveFP file (the header aside): each line is one minute (m1) or one bar (r1)"""
    with open(path, "rb") as h:
        return max(sum(1 for ln in h if ln.strip()) - 1, 0)


# ---------------------------------------------------------------------------------------------- helpers
def resolve(base, tous, aliases):
    """BrkResolve (CR_Broker.mqh:148-168) on tous.csv: base + '.r', base, the aliases (alias.r, alias), else the first
    symbol of the server's list that starts with base; tradable = SYMBOL_TRADE_MODE not disabled"""
    if not tous:
        return None
    tradable = {r["name"]: (r.get("trade_mode") or 0) != 0 for r in tous}
    if tradable.get(base + ".r"):
        return base + ".r"
    if tradable.get(base):
        return base
    for a in aliases.get(base, []):
        if tradable.get(a + ".r"):
            return a + ".r"
        if tradable.get(a):
            return a
    for r in tous:
        if r["name"].startswith(base) and tradable.get(r["name"]):
            return r["name"]
    return ""


def sessions_parse(s):
    """'dw:from-to|...' (minutes of the server day) -> {dw: [(from, to)]}"""
    out = {}
    for part in (s or "").split("|"):
        if ":" not in part or "-" not in part:
            continue
        d, rng = part.split(":", 1)
        a, b = rng.split("-", 1)
        try:
            out.setdefault(int(d), []).append((int(a), int(b)))
        except ValueError:
            continue
    return out


def sess_txt(ss, dws=range(7)):
    def m(x):
        return f"{x // 60:02d}:{x % 60:02d}"
    parts = []
    for d in dws:
        if d in ss:
            parts.append(C.DOW_EN3[d] + " " + ",".join(f"{m(a)}-{m(b)}" for a, b in ss[d]))
    return "; ".join(parts) if parts else "aucune"


def gold_friday(ss):
    """CR_Rule_GoldFri.mqh GfpSessionShort: a Friday session must hold 13:30 New York (20:30 server) and run to 16:46
    New York (23:46 server) or later; an end at or before the start runs to midnight. Returns (ok, latest end in
    minutes of a session holding 20:30, or None)"""
    a, b = 20 * 60 + 30, 23 * 60 + 46
    if 5 not in ss:
        return None, None
    best = None
    for f, t in ss[5]:
        f %= 1440
        t = t % 1440 if t != 1440 else 1440
        if t <= f:
            t = 1440
        if f <= a < t:
            best = t if best is None else max(best, t)
            if t >= b:
                return True, t
    return False, best


def eur_per_usd(fiche):
    """EUR (account currency) per unit of the profit currency, from the tick value: tick_value = tick_size x contract
    x rate"""
    tv, ts, cs = fiche.get("tick_value"), fiche.get("tick_size"), fiche.get("contract_size")
    if not tv or not ts or not cs:
        return None
    return tv / (ts * cs)


def eff_leverage(fiche):
    """notional of one lot in the account currency / margin of one lot: price / tick_size x tick_value / margin"""
    m, ask, tv, ts = fiche.get("margin_1lot"), fiche.get("ask"), fiche.get("tick_value"), fiche.get("tick_size")
    if not m or m <= 0 or not ask or not tv or not ts:
        return None
    return ask / ts * tv / m


def swap_cost(fiche, value):
    """a broker swap as an annual cost in fraction of the price (positive = the trader pays), 360-day basis like
    fp_costs.json; None when the mode cannot be converted"""
    mode = fiche.get("swap_mode")
    price = ((fiche.get("bid") or 0) + (fiche.get("ask") or 0)) / 2
    pt, cs, tv, ts = fiche.get("point"), fiche.get("contract_size"), fiche.get("tick_value"), fiche.get("tick_size")
    if value is None or mode is None:
        return None
    if mode == 0:
        return 0.0
    if not price:
        return None
    if mode == 1 and pt:                                         # points per lot and day
        return -value * pt / price * 360
    if mode == 4 and tv and ts:                                  # account currency per lot and day
        return -value / (price / ts * tv) * 360
    if mode == 3 and cs and fiche.get("ccy_margin") == fiche.get("ccy_profit"):
        return -value / (price * cs) * 360
    if mode == 2 and cs:                                         # base currency per lot and day
        return -value / cs * 360
    if mode in (5, 6):                                           # annual interest in %
        return -value / 100.0
    return None


class Report:
    def __init__(self):
        self.checks = []

    def add(self, market, item, label, status, broker, assumed, note="", source=""):
        self.checks.append({"market": market, "item": item, "label": label, "status": status, "broker": broker,
                            "assumed": assumed, "assumed_source": source, "note": note})


def fmtv(x, nd=4, unit=""):
    if x is None:
        return "?"
    if isinstance(x, (int, np.integer)) and not isinstance(x, bool):
        return f"{int(x)}" + (" " + unit if unit else "")
    if isinstance(x, float):
        s = f"{x:.{nd}f}".rstrip("0").rstrip(".") if nd > 0 else f"{x:.0f}"
        return s.replace(".", ",") + (" " + unit if unit else "")
    return str(x) + (" " + unit if unit else "")


# ---------------------------------------------------------------------------------------------- m1 statistics
def m1_stats(df, base, digits, run_srv=None):
    """statistics of one m1 file; run_srv = fini.txt's server_time (when ReleveFP ran): the ticks up to then are in
    the file, so a session that ended before it is complete even when no later bar exists (a weekend run)"""
    sc = 10 ** digits
    bo, ao, bc, ac = (np.rint(df[c].to_numpy() * sc) for c in ("bo", "ao", "bc", "ac"))
    mid = (df.bo.to_numpy() + df.ao.to_numpy()) / 2
    sp_open, sp_close = ao - bo, ac - bc
    sp_bp = ((sp_open + sp_close) / 2 / sc) / mid * 1e4
    t = df.time.to_numpy()
    days = np.unique(t // 86400)
    dw = ((t // 86400) + 4) % 7
    hour = (t % 86400) // 3600
    st = {"rows": int(len(df)), "first_srv": int(t[0]), "last_srv": int(t[-1]), "first": C.ymdhm(t[0]) + " serveur",
          "last": C.ymdhm(t[-1]) + " serveur", "days_with_bars": int(len(days)),
          "spread_bp_median": float(np.median(sp_bp)), "spread_bp_mean": float(np.mean(sp_bp)),
          "spread_bp_p90": float(np.quantile(sp_bp, 0.9)), "spread_points_open_median": float(np.median(sp_open)),
          "spread_points_max_median": float(np.median(np.rint(df.sp_max.to_numpy() * sc))),
          "mid_last": float(mid[-1]), "weekend_bars": int(((dw == 0) | (dw == 6)).sum()),
          "weekend_days": sorted({C.ymd(x) for x in t[(dw == 0) | (dw == 6)]})[:20]}
    # bars per server hour on Tuesday-Thursday (the daily break of gold is 00:00-00:59 server = 17:00 New York)
    st["bars_per_server_hour_tue_thu"] = {int(h): int(((hour == h) & (dw >= 2) & (dw <= 4)).sum()) for h in range(24)}
    # summer-time switch inside the window: the same count on each side
    sw = [u for u in range(int(srv_to_utc0(t[0])), int(srv_to_utc0(t[-1])), 3600) if C.us_dst(u) != C.us_dst(u + 3600)]
    if sw:
        cut = C.utc_to_srv(sw[0] + 3600)
        st["us_dst_switch_utc"] = C.utc_txt(sw[0] + 3600)
        for side, mask in (("before", t < cut), ("after", t >= cut)):
            wk = mask & (dw >= 1) & (dw <= 5)
            st[f"days_{side}"] = int(len(np.unique(t[wk] // 86400)))
            st[f"bars_per_server_hour_{side}"] = {int(h): int(((hour == h) & wk).sum()) for h in range(24)}
    # NYSE holidays and half days inside the window: the bars of that date's trading session, [d-1 18:00, d 18:00)
    # New York, in minutes from d's midnight (negative = the evening before)
    ny = t - 7 * 3600
    hol = []
    d_first, d_last = int(ny.min() // 86400), int(ny.max() // 86400)
    for d0 in range(d_first, d_last + 1):
        d = dt.date(1970, 1, 1) + dt.timedelta(days=d0)
        k = C.nyse_kind(d)
        if k is None or d.weekday() >= 5:
            continue
        rel = (ny - d0 * 86400) // 60
        sel = rel[(rel >= -360) & (rel < 18 * 60)]
        w_end = d0 * 86400 + 18 * 3600
        by_bars = w_end <= ny.max()
        by_run = run_srv is not None and int(run_srv) - 7 * 3600 >= w_end
        rec = {"date": d.isoformat(), "kind": k, "bars": int(len(sel)),
               "window_complete": bool(d0 * 86400 - 360 * 60 >= ny.min() and (by_bars or by_run)),
               "complete_by_run_time": bool(by_run and not by_bars)}
        if len(sel):
            rec["first_rel_min"] = int(sel.min())
            rec["last_rel_min"] = int(sel.max())
            rec["first_ny"] = rel_txt(int(sel.min()))
            rec["last_ny"] = rel_txt(int(sel.max()))
        hol.append(rec)
    st["nyse_days"] = hol
    return st


def srv_to_utc0(s):
    return C.srv_to_utc(int(s))


def rel_txt(m):
    """minutes from a date's midnight (negative = the evening before) as text"""
    if m < 0:
        m += 1440
        return f"veille {m // 60:02d}:{m % 60:02d}"
    return f"{m // 60:02d}:{m % 60:02d}"


# ---------------------------------------------------------------------------------------------- the checks
FX = {"EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURJPY"}
NO_COMMISSION = {"US100", "BTCUSD", "ETHUSD", "US500", "US30", "GER40", "JP225"}
INFO = "information : ni le robot ni le labo n'ont d'hypothese pour ce marche"


def market_checks(rep, base, fiche, tous, costs, sonde, m1, fini_m, is_robot, usd_rate):
    lab = costs.get(C.LAB_SYM.get(base, ""), {})
    src_lab = "fp_costs.json" if lab else ""
    # 1. name (BrkResolve on tous.csv for the robot's markets, ReleveFP's Resolve for the others)
    expected = base + ".r"
    robot_pick = resolve(base, tous, ROBOT_ALIASES if is_robot else RELEVE_ALIASES)
    if fiche and fiche.get("found"):
        name = fiche["name"]
        st = "OK" if name == expected and (robot_pick in (None, name)) else "DIFFERENT"
        note = ""
        if robot_pick not in (None, name):
            note = f"le robot choisirait {robot_pick or 'rien'} (regles de BrkResolve sur tous.csv)"
        elif name != expected:
            note = "le compte Raw devrait montrer le nom en .r ; le robot prend ce nom-ci (BrkResolve)"
        rep.add(base, "name", "nom chez le courtier", st, name, expected + (f" (BrkResolve : {robot_pick})" if robot_pick else ""),
                note, "SPEC 1 (comptes Raw, symboles .r), CR_Broker.mqh BrkResolve")
    elif fiche is not None and not fiche.get("found"):
        rep.add(base, "name", "nom chez le courtier", "DIFFERENT", "introuvable", expected,
                "le robot refuse de demarrer sans ses quatre marches" if is_robot else "", "SPEC 1")
        return
    elif robot_pick:
        rep.add(base, "name", "nom chez le courtier", "OK" if robot_pick == expected else "DIFFERENT", robot_pick, expected,
                "d'apres tous.csv seulement", "SPEC 1")
    else:
        rep.add(base, "name", "nom chez le courtier", "UNKNOWN", None, expected, "pas de fiche pour ce marche", "SPEC 1")
    if not fiche or not fiche.get("found"):
        # no fiche line (missing, or cut short): the probe and the minutes still say what they can
        if (sonde and sonde.get(base)) or m1.get(base):
            comm_price, comm_ok = commission_check(rep, base, None, sonde.get(base) if sonde else None, is_robot, usd_rate)
            spread_check(rep, base, None, m1.get(base), lab, comm_price, is_robot, comm_ok)
        return
    name = fiche["name"]
    tm = next((r.get("trade_mode") for r in tous if r["name"] == name), None) if tous else None
    if tm is not None:
        rep.add(base, "trade_mode", "trading autorise", "OK" if tm == 4 else "DIFFERENT", TRADE_MODE.get(tm, str(tm)), "full",
                "" if tm == 4 else "le robot n'ouvre que sur un marche en mode full (CR_Broker.mqh BrkOpen)", "CR_Broker.mqh")
    # 2. digits, point, tick size
    dg, pt, ts = fiche.get("digits"), fiche.get("point"), fiche.get("tick_size")
    if is_robot:
        note = ""
        if dg != HARNESS_DIGITS:
            note = "le robot lit les decimales en direct ; le banc d'essai arrondit a 2 decimales"
            if base == "XAUUSD" and isinstance(pt, (int, float)) and pt > 0:
                note += (f" ; ET la commission du papier de l'or vaut 6 points x 0,5 x point (CR_Registry.mqh RegSetPoint) : avec un point "
                         f"de {fmtv(float(pt), 8)} elle ferait {fmtv(6 * pt, 4)} USD par once aller-retour au lieu de 0,06 "
                         f"({fmtv(0.06 / (6 * pt), 2)} fois trop {'petite' if 6 * pt < 0.06 else 'grande'}) : le papier de l'or serait faux, "
                         "a corriger dans le robot avant la demo (CR_XAU_COMM_PTS) ; la ligne commission le montre aussi")
        rep.add(base, "digits", "decimales", "OK" if dg == HARNESS_DIGITS else "DIFFERENT", dg, HARNESS_DIGITS, note,
                "check/export_frames.py DIGITS, CR_Registry.mqh RegSetPoint")
        rep.add(base, "point", "point", "OK" if pt is not None and abs(pt - 0.01) < 1e-12 else "DIFFERENT", fmtv(pt, 8), "0,01",
                "", "check/export_frames.py")
    else:
        rep.add(base, "digits", "decimales", "UNKNOWN", dg, None, INFO, "")
        rep.add(base, "point", "point", "UNKNOWN", fmtv(pt, 8), None, INFO, "")
    if ts is not None and pt is not None:
        same = abs(ts - pt) < 1e-12
        rep.add(base, "tick_size", "pas de cotation", "OK" if same else "DIFFERENT", fmtv(ts, 8), fmtv(pt, 8) + " (= le point)",
                "" if same else "le robot pose ses stops sur ce pas (GridStop) ; le banc d'essai prend pas = point",
                "check/mock_replay.h (pas = point)")
    # 3. contract size, volumes
    cs = fiche.get("contract_size")
    if lab.get("units_per_lot") is not None:
        ok = cs is not None and abs(cs - lab["units_per_lot"]) < 1e-9
        rep.add(base, "contract_size", "taille du contrat", "OK" if ok else "DIFFERENT", fmtv(cs, 4),
                fmtv(float(lab["units_per_lot"]), 4), "" if ok else "les lots du robot suivent la vraie taille (lue en direct)", src_lab)
    else:
        rep.add(base, "contract_size", "taille du contrat", "UNKNOWN", fmtv(cs, 4), None, INFO, "")
    for key, lk, label in (("vol_min", "min_lot", "lot minimum"), ("vol_step", "lot_step", "pas du lot")):
        v = fiche.get(key)
        if lk in lab:
            ok = v is not None and abs(v - lab[lk]) < 1e-9
            note = ""
            if base == "US100" and key == "vol_min":
                note = ("lot minimum US100 confirme (fp_costs.json le donnait a lire chez l'utilisateur)" if ok else
                        "lot minimum US100 different : un petit compte saute plus de trades N30/OC4 (MIN_LOT)")
            rep.add(base, key, label, "OK" if ok else "DIFFERENT", fmtv(v, 4, "lot"), fmtv(float(lab[lk]), 4, "lot"), note, src_lab)
        else:
            rep.add(base, key, label, "UNKNOWN", fmtv(v, 4, "lot"), None, INFO, "")
    vmax = fiche.get("vol_max")
    if is_robot:
        st = "OK" if vmax is not None and vmax >= MOCK_VMAX else "DIFFERENT"
        rep.add(base, "vol_max", "lot maximum", st, fmtv(vmax, 2, "lots"), fmtv(MOCK_VMAX, 2, "lots") + " (mock)",
                "au-dela le robot coupe l'ordre (SEND cut=vmax) ; D2 demanderait plus de 100 lots sur 1 500 demandes de 2018-2021 "
                "(ACCEPTANCE.md 10.6), quand le compte depasse le million d'euros", "check/mock_replay.h MOCK_VMAX")
    else:
        rep.add(base, "vol_max", "lot maximum", "UNKNOWN", fmtv(vmax, 2, "lots"), None, INFO, "")
    # 4. EUR tick value
    rate = eur_per_usd(fiche) if fiche.get("ccy_profit") == "USD" else None
    if rate is not None:
        st = "OK" if abs(rate - MOCK_USDEUR) <= 0.10 else "DIFFERENT"
        rep.add(base, "tick_value_eur", "valeur du pas en EUR", st,
                f"{fmtv(fiche.get('tick_value'), 6)} EUR par pas et par lot (1 USD = {fmtv(rate, 4)} EUR)",
                f"pas x contrat x {fmtv(MOCK_USDEUR, 2)} (1 USD = {fmtv(MOCK_USDEUR, 2)} EUR)",
                "le robot lit la valeur en direct (SPEC 9.6) ; 0,89 ne sert qu'au banc d'essai", "check/mock_replay.h MOCK_USDEUR")
    else:
        rep.add(base, "tick_value_eur", "valeur du pas", "UNKNOWN",
                f"{fmtv(fiche.get('tick_value'), 6)} EUR par pas et par lot (gain en {fiche.get('ccy_profit')})",
                None, "pas de gain en USD : pas de comparaison avec 0,89" if is_robot else INFO, "")
    tvl, tv = fiche.get("tick_value_loss"), fiche.get("tick_value")
    if tvl and tv and abs(tvl / tv - 1) > 0.01:
        rep.add(base, "tick_value_loss", "valeur du pas en perte", "DIFFERENT", fmtv(tvl, 6), fmtv(tv, 6) + " (valeur du pas)",
                "le robot dimensionne avec la valeur en perte (CR_Sizing.mqh)", "CR_Sizing.mqh")
    # 5. stops level, freeze level, filling
    sl_ = fiche.get("stops_level")
    if is_robot:
        rep.add(base, "stops_level", "distance minimale des stops", "OK" if sl_ == 0 else ("UNKNOWN" if sl_ is None else "DIFFERENT"),
                fmtv(sl_, 0, "points"), "0 point (mock)",
                "" if not sl_ else "le robot n'envoie pas un stop plus pres (BrkOpen stop_side) ; un deplacement refuse est retente toutes les 10 s",
                "check/mock_replay.h MOCK_STOPS")
        rep.add(base, "freeze_level", "niveau de gel", "UNKNOWN", "absent des fichiers", "0 point (mock)",
                "ReleveFP ne l'ecrit pas ; le journal du robot le montre (SLMOD rc=10029, voir check_demo.py)", "check/mock_replay.h MOCK_FREEZE")
        rep.add(base, "filling", "modes de remplissage", "UNKNOWN",
                f"absent des fichiers (mode d'execution : {EXE_MODE.get(fiche.get('exe_mode'), fiche.get('exe_mode'))})", "IOC (mock)",
                "le robot prend le mode du symbole (SetTypeFillingBySymbol) ; un refus se verrait dans SEND rc=10030", "check/mock_replay.h")
    else:
        rep.add(base, "stops_level", "distance minimale des stops", "UNKNOWN", fmtv(sl_, 0, "points"), None, INFO, "")
    # 6. margin
    lev = eff_leverage(fiche)
    lab_lev = lab.get("leverage")
    if lev is None:
        rep.add(base, "margin", "marge (levier effectif)", "UNKNOWN", f"marge d'un lot {fmtv(fiche.get('margin_1lot'), 2)}",
                f"1:{lab_lev}" if lab_lev else None, "marge d'un lot absente (OrderCalcMargin a echoue ?)", src_lab)
    else:
        broker = (f"1:{fmtv(lev, 1)} (marge d'un lot {fmtv(fiche.get('margin_1lot'), 2)} EUR, marge initiale "
                  f"{fmtv(fiche.get('margin_initial'), 4)}, calcul {CALC_MODE.get(fiche.get('calc_mode'), fiche.get('calc_mode'))})")
        crypto = base in ("BTCUSD", "ETHUSD")
        if lab_lev:
            if lev >= 0.8 * lab_lev:
                st, note = "OK", ("comme le mock (1:50) : la marge ne bloque pas plus que dans les essais (0 saut MARGIN en T7a et T7b)"
                                  if crypto else "")
            else:
                st = "DIFFERENT"
                if crypto and lev <= 2.5:
                    note = "c'est le cas 1:2 de SPEC 10.6 : " + T7B_TEXT
                elif crypto:
                    note = ("entre 1:2 et 1:50 : le controle de marge bloquera plus que dans le mock (0 saut a 1:50) et moins "
                            "qu'a 1:2 (" + T7B_TEXT.split(" : ", 1)[1] + ")")
                else:
                    note = "moins de levier que le mock : le controle de marge (MARGIN) peut sauter des trades"
            rep.add(base, "margin", "marge (levier effectif)", st, broker, f"1:{lab_lev} (fp_costs.json et mock)", note, src_lab)
        else:
            rep.add(base, "margin", "marge (levier effectif)", "UNKNOWN", broker, None, INFO, "")
    # 7. commission (SondeFP)
    comm_price, comm_ok = commission_check(rep, base, fiche, sonde.get(base) if sonde else None, is_robot, usd_rate)
    # 8. swaps
    for side in ("long", "short"):
        v = fiche.get(f"swap_{side}")
        cost = swap_cost(fiche, v)
        lab_cost = lab.get(f"swap_{side}")
        mode = fiche.get("swap_mode")
        bt = f"{fmtv(v, 4)} (mode {SWAP_MODE[mode] if isinstance(mode, int) and 0 <= mode < len(SWAP_MODE) else mode})"
        if cost is not None:
            bt += f" = cout de {fmtv(cost * 100, 2)} % par an"
        if lab_cost is None:
            rep.add(base, f"swap_{side}", f"swap {side}", "UNKNOWN", bt, None, INFO, "")
            continue
        at = f"cout de {fmtv(lab_cost * 100, 2)} % par an (credits ignores)"
        if cost is None:
            rep.add(base, f"swap_{side}", f"swap {side}", "UNKNOWN", bt, at, "mode de swap non converti", src_lab)
            continue
        if cost <= 0 and lab_cost == 0:
            st, note = "OK", ("credit ou zero ; le labo l'ignore" if cost < 0 else "")
        elif abs(cost - lab_cost) <= max(0.25 * lab_cost, 0.01):
            st, note = "OK", ""
        else:
            st = "DIFFERENT"
            note = ("plus cher que le labo" if cost > lab_cost else "moins cher que le labo") + \
                   (" ; le papier du robot ne compte aucun swap (SPEC 2.5) : D4H, ORX, F1E+H2, BKB et BKE gardent des positions la nuit"
                    if is_robot else "")
        rep.add(base, f"swap_{side}", f"swap {side}", st, bt, at, note, src_lab)
    s3 = fiche.get("swap_3days")
    if lab.get("swap_triple") and s3 is not None:
        b3 = C.DOW_EN3[int(s3)] if 0 <= int(s3) <= 6 else str(s3)
        rep.add(base, "swap_triple", "jour du swap triple", "OK" if b3 == lab["swap_triple"] else "DIFFERENT", b3, lab["swap_triple"],
                "", src_lab)
    # 9. spread
    spread_check(rep, base, fiche, m1.get(base), lab, comm_price, is_robot, comm_ok)


def releve_checks(rep, base, fini_m, m1_path, r1_path, m1_df, r1_df, digits):
    """ReleveFP's own read of one market's history, whatever its fiche line (a cut or missing fiche keeps these):
    the tick history (fini.txt), the m1 file's rows against minutes= (ReleveFP writes the newest day first, so a file
    cut short loses its oldest days, review2 N9 b), the terminal's bars (r1_<BASE>.csv, ReleveFP 1.10) against
    barres= and the days they cover, and SPEC 10.3 from the minutes present in both (information only)"""
    found = bool(fini_m and fini_m.get("found"))
    if found:
        inc = fini_m.get("jours_incomplets")
        err = fini_m.get("derniere_erreur")
        st = "OK" if (inc == 0 and err in (0, None) and (fini_m.get("minutes") or 0) > 0) else "DIFFERENT"
        if not fini_m.get("minutes"):
            note = f"aucune minute lue (derniere erreur {err}) : relancer ReleveFP pour ce marche"
        else:
            note = "" if st == "OK" else f"{inc} jour(s) incomplet(s), derniere erreur {err} : des minutes peuvent manquer"
        rep.add(base, "releve_days", "historique de ticks lu", st,
                f"{fini_m.get('jours')} jours, {fini_m.get('minutes')} minutes, du {fini_m.get('du')} au {fini_m.get('au')}",
                "jours complets, derniere erreur 0", note, "ReleveFP.mq5")
    if m1_path is not None:
        rows = data_rows(m1_path)
        mins = fini_m.get("minutes") if found else None
        if isinstance(mins, int) and mins > 0:
            st = "OK" if rows == mins else "DIFFERENT"
            note = "" if st == "OK" else (
                f"fichier coupe : {mins - rows} minute(s) manquent ; ReleveFP ecrit le jour le plus recent d'abord, ce sont donc les jours "
                "les plus anciens : recopier le fichier" if rows < mins else "plus de lignes que fini.txt n'en compte : fichier d'un autre releve ?")
            rep.add(base, "m1_rows", "minutes du fichier m1", st, f"{rows} lignes dans m1_{base}.csv", f"minutes={mins} (fini.txt)", note,
                    "ReleveFP.mq5 Minutes")
        else:
            rep.add(base, "m1_rows", "minutes du fichier m1", "UNKNOWN", f"{rows} lignes dans m1_{base}.csv", "fini.txt absent ou sans minutes=",
                    "", "ReleveFP.mq5 Minutes")
    bars_f = fini_m.get("barres") if found else None
    if r1_path is not None:
        rows = data_rows(r1_path)
        if r1_df is not None and len(r1_df):
            t = r1_df.time.to_numpy()
            days = int(len(np.unique(t // 86400)))
            broker = f"{rows} barres sur {days} jours, du {C.ymd(t[0])} au {C.ymd(t[-1])}"
        else:
            days, broker = 0, f"{rows} barres"
        notes = []
        if isinstance(bars_f, int) and bars_f >= 0:
            st = "OK" if rows == bars_f else "DIFFERENT"
            if rows < bars_f:
                notes.append(f"fichier coupe : {bars_f - rows} barre(s) manquent (les jours les plus anciens) : recopier le fichier")
            elif rows > bars_f:
                notes.append("plus de lignes que fini.txt n'en compte : fichier d'un autre releve ?")
            err = fini_m.get("erreur_barres")
            if isinstance(err, int) and err > 0:
                st = "DIFFERENT"
                notes.append(f"{err} jour(s) de barres illisibles (erreur_barres) : relancer ReleveFP")
            assumed = f"barres={bars_f} (fini.txt)"
        else:
            st, assumed = "UNKNOWN", "fini.txt absent ou sans barres= (ReleveFP 1.00 ?)"
        if days and days < 150:
            notes.append(f"{days} jours : moins que les 150 qu'il faut pour comparer D4H (120 jours d'echauffement) sur toute la demo")
        rep.add(base, "r1_rows", "barres M1 du terminal (r1)", st, broker, assumed, " ; ".join(notes), "ReleveFP.mq5 Rates")
    elif isinstance(bars_f, int) and bars_f > 0:
        rep.add(base, "r1_rows", "barres M1 du terminal (r1)", "DIFFERENT", f"r1_{base}.csv absent", f"barres={bars_f} (fini.txt)",
                "copier aussi les fichiers r1_<marche>.csv de ReleveFP", "ReleveFP.mq5 Rates")
    if m1_df is not None and r1_df is not None and digits is not None:
        bar_spread_check(rep, base, m1_df, r1_df, digits)


def bar_spread_check(rep, base, m1_df, r1_df, digits):
    """SPEC 10.3 (information only, never a difference): on the minutes in both the m1 file (built from ticks) and the r1
    file (the terminal's bars), how often MqlRates.spread equals the smallest spread of the minute's ticks (sp_min,
    ReleveFP 1.10), the first tick's (open), the last tick's (close) and the rounded mean"""
    j = m1_df.merge(r1_df[["time", "spread"]], on="time", how="inner")
    if not len(j):
        rep.add(base, "bar_spread", "ecart des barres du terminal (SPEC 10.3)", "UNKNOWN", "aucune minute commune aux fichiers m1 et r1",
                "ask = bid + MqlRates.spread (le robot)", "information", "SPEC 10.3")
        return
    sc = 10 ** int(digits)
    sp = j["spread"].to_numpy()

    def share(x):
        return 100.0 * float(np.mean(sp == x))
    o = np.rint(j.ao.to_numpy() * sc) - np.rint(j.bo.to_numpy() * sc)
    c = np.rint(j.ac.to_numpy() * sc) - np.rint(j.bc.to_numpy() * sc)
    mean_ = np.floor(j.sp_mean.to_numpy() * sc + 0.5)
    parts = [f"minimum {fmtv(share(np.rint(j.sp_min.to_numpy() * sc)), 1)} %" if "sp_min" in j.columns else
             "minimum ? (m1 sans sp_min : ReleveFP 1.00)",
             f"ouverture {fmtv(share(o), 1)} %", f"fermeture {fmtv(share(c), 1)} %", f"moyenne arrondie {fmtv(share(mean_), 1)} %"]
    rep.add(base, "bar_spread", "ecart des barres du terminal (SPEC 10.3)", "OK",
            "MqlRates.spread egal a l'ecart des ticks de la minute : " + ", ".join(parts) + f" ({len(j)} minutes communes)",
            "ask = bid + MqlRates.spread (le robot)", "information : l'ecart que MT5 garde dans ses barres M1 ; check_demo rejoue les "
            "barres r1 telles quelles", "SPEC 10.3")


def commission_check(rep, base, fiche, s, is_robot, usd_rate):
    """SondeFP's round trip against the model: gold and FX pay 3 USD per lot and per side on Raw (gold: the robot's
    6-point constant; FX: fp_costs.json _fx_note), indices and crypto pay nothing (SPEC 2.2). Returns the measured round
    trip in price units per unit of size (None when unknown) and whether it agrees with the model within the probe's
    rounding (each deal's commission is rounded to the cent: at 0.01 lot that is up to 16 % of a gold commission)"""
    if base == "XAUUSD" or base in FX:
        model_side_usd = 3.0
    elif base in NO_COMMISSION:
        model_side_usd = 0.0
    else:
        model_side_usd = None
    src = ("CR_Types.mqh CR_XAU_COMM_PTS = 6 (aller-retour) ; fp_costs.json 0,19 = 0,13 d'ecart + 0,06 de commission" if base == "XAUUSD"
           else ("SPEC 2.2 : pas de commission sur US100, BTC, ETH (compte Raw)" if base in NO_COMMISSION else "fp_costs.json _fx_note"))
    model_txt = None
    if base == "XAUUSD":
        model_txt = "6 points aller-retour = 0,06 USD par once = 3 USD par lot et par cote"
    elif model_side_usd == 0.0:
        model_txt = "aucune"
    elif model_side_usd:
        model_txt = "3 USD par lot et par cote"
    if s is None:
        rep.add(base, "commission", "commission", "UNKNOWN", "pas de sonde pour ce marche", model_txt, "lancer SondeFP sur le compte demo", src)
        return None, False
    if not s.get("full") or s.get("status") != "ok" or not s.get("volume") or not (s.get("deals") or 0) >= 2:
        rep.add(base, "commission", "commission", "UNKNOWN", f"sonde : {s.get('status')}", model_txt,
                "la sonde n'a pas relu l'achat et la revente", src)
        return None, False
    vol = s["volume"]
    com = -((s.get("commission") or 0) + (s.get("fee") or 0))           # account currency, for vol lots, round trip
    deals = int(s["deals"])
    margin_lot = 0.005 * deals / vol if com > 0 else 0.0                # each deal's commission is rounded to the cent
    rt_lot = com / vol
    ts, tv = s.get("tick_size"), s.get("tick_value")
    pt = (fiche.get("point") if fiche else None) or ts
    if not ts or not tv or not pt:
        rep.add(base, "commission", "commission", "UNKNOWN", f"{fmtv(rt_lot / 2, 3)} EUR par lot et par cote", model_txt,
                "fiche de la sonde incomplete", src)
        return None, False
    price_units = rt_lot * ts / tv                                      # money per lot -> price units per unit of size
    rt_pts = price_units / pt
    margin_pts = margin_lot * ts / tv / pt
    broker = (f"{fmtv(rt_lot / 2, 3)} EUR par lot et par cote = {fmtv(rt_pts, 2)} points aller-retour"
              f" (a {fmtv(margin_lot / 2, 3)} EUR pres : centimes arrondis sur {fmtv(vol, 2)} lot)")
    if model_side_usd is None:
        rep.add(base, "commission", "commission", "UNKNOWN", broker, None, INFO, src)
        return price_units, False
    if base == "XAUUSD":
        st = "OK" if abs(rt_pts - C.XAU_COMM_PTS) <= max(1.0, margin_pts) else "DIFFERENT"
        rate = eur_per_usd(fiche) if fiche and fiche.get("ccy_profit") == "USD" else usd_rate
        note = f"le modele vaut 3 USD = {fmtv(3 * rate, 2)} EUR par lot et par cote au taux du jour" if rate else ""
        if st == "DIFFERENT":
            note += (" ; le robot alerte (COST) au-dela d'1 point d'ecart et garde 6 points tant que le labo ne change pas "
                     "la constante CR_XAU_COMM_PTS")
    elif model_side_usd == 0.0:
        st = "OK" if rt_lot / 2 <= max(margin_lot / 2, 1e-9) else "DIFFERENT"
        note = "" if st == "OK" else "le papier du robot ne compte pas de commission sur ce marche : chaque trade coute ce montant de plus"
    else:
        rate = usd_rate
        if not rate:
            rep.add(base, "commission", "commission", "UNKNOWN", broker, model_txt, "taux USD/EUR inconnu (pas de fiche en USD)", src)
            return price_units, False
        model_side_eur = model_side_usd * rate
        st = "OK" if abs(rt_lot / 2 - model_side_eur) <= max(0.25, margin_lot / 2) else "DIFFERENT"
        note = f"modele {fmtv(model_side_eur, 2)} EUR par lot et par cote au taux du jour"
    rep.add(base, "commission", "commission", st, broker, model_txt, note, src)
    return price_units, st == "OK"


def spread_check(rep, base, fiche, st, lab, comm_price, is_robot, comm_ok=False):
    """the median minute spread of the m1 file (mean of the opening and closing spreads, in bp of the mid, as
    live_ai/releve.py) plus the commission where the lab's figure holds one (gold, FX), against fp_costs.json. When the
    probe agrees with the model within its cent rounding (comm_ok), the model's commission is added, not the probe's
    rounded one (at 0.01 lot of gold the cents count 6.98 points for a true 6)"""
    if lab.get("spread") is None:
        if st:
            rep.add(base, "spread", "ecart achat-vente observe", "UNKNOWN", f"mediane {fmtv(st['spread_bp_median'], 3)} pb", None, INFO, "")
        return
    if st is None:
        cur = fiche.get("spread_points") if fiche else None
        rep.add(base, "spread", "ecart achat-vente observe", "UNKNOWN",
                f"pas de fichier m1 (ecart instantane de la fiche : {fmtv(cur, 0, 'points')})", f"{lab['spread']} en prix",
                "ReleveFP ecrit m1_<marche>.csv", "fp_costs.json")
        return
    mid = st["mid_last"]
    ref_px = lab.get("spread_ref_price") or mid
    model_bp = lab["spread"] / ref_px * 1e4
    meas = st["spread_bp_median"]
    extra = ""
    meas_all = meas
    if base == "XAUUSD" or base in FX:                                  # the lab's figure holds the commission
        model_px = 0.06 if base == "XAUUSD" else (6.0 / (lab.get("units_per_lot") or 100000)
                                                   if base in ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD") else None)
        if comm_price is not None and comm_ok and model_px is not None:
            com_bp, how = model_px / mid * 1e4, "du modele (la sonde le confirme aux centimes arrondis pres)"
        elif comm_price is not None:
            com_bp, how = comm_price / mid * 1e4, "mesuree par la sonde"
        else:
            com_bp, how = (0.06 if base == "XAUUSD" else 6.0 / (lab.get("units_per_lot") or 100000)) / mid * 1e4, "du modele"
            if base not in ("XAUUSD", "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"):
                com_bp = None
        if com_bp is not None:
            meas_all = meas + com_bp
            extra = f" + commission {how} {fmtv(com_bp, 3)} pb = {fmtv(meas_all, 3)} pb tout compris"
    ratio = meas_all / model_bp
    status = "OK" if ratio <= 1.5 else "DIFFERENT"
    note = f"rapport {fmtv(ratio, 2)} ; les regles ont ete testees avec des frais x1,5"
    if ratio > 1.5:
        note += (" : au-dela, le robot alerte (COST, 1,5 x le modele)" if is_robot else "")
    elif ratio < 0.5:
        note += " ; bien moins cher que le modele"
    rep.add(base, "spread", "ecart achat-vente observe (mediane des minutes)", status,
            f"{fmtv(meas, 3)} pb{extra} (moyenne {fmtv(st['spread_bp_mean'], 3)}, 9e decile {fmtv(st['spread_bp_p90'], 3)}) sur {st['rows']} minutes",
            f"{fmtv(model_bp, 3)} pb ({lab['spread']} a {fmtv(float(ref_px), 2)})", note, "fp_costs.json, CR_Registry.mqh model_bp")


CLOSURE_RX = r"^(XAU|IDX|CRY) (\d{4})\.(\d{2})\.(\d{2}) (\d{2}):(\d{2})-(\d{4})\.(\d{2})\.(\d{2}) (\d{2}):(\d{2})$"


def closure_window(kind, d, start_rel_min, end_rel_min=18 * 60):
    """an InpExtraClosures window as ClkInit takes it (CR_Clock.mqh: 'XAU yyyy.mm.dd hh:mm-yyyy.mm.dd hh:mm', New York
    wall clock, ending after it starts, at most 7 days): the start and end given in minutes from the New York midnight
    of date d (negative = the evening before), written as absolute dates and times"""
    base = dt.datetime(d.year, d.month, d.day)
    a = base + dt.timedelta(minutes=int(start_rel_min))
    z = base + dt.timedelta(minutes=int(end_rel_min))
    return f"{kind} {a:%Y.%m.%d %H:%M}-{z:%Y.%m.%d %H:%M}"


def session_checks(rep, fiches, m1):
    # gold: the Friday session must hold 20:30 server and run to 23:46 server (SPEC 10.5, CR_Rule_GoldFri.mqh)
    f = fiches.get("XAUUSD")
    if not (f and f.get("found")):                                     # no usable gold fiche: the key check stays (review2 N9 a)
        rep.add("XAUUSD", "friday_session", "seance or du vendredi", "UNKNOWN",
                "pas de fiche de l'or (ligne absente, coupee ou introuvable dans fiches.csv)", "13:30-16:46 New York = 20:30-23:46 serveur",
                "relancer ReleveFP et recopier fiches.csv en entier", "SPEC 10.5")
    if f and f.get("found"):
        ss = sessions_parse(f.get("sessions"))
        ok, end = gold_friday(ss)
        if ok is None:
            rep.add("XAUUSD", "friday_session", "seance or du vendredi", "UNKNOWN", "aucune seance listee le vendredi",
                    "13:30-16:46 New York = 20:30-23:46 serveur", "le robot ne saute alors aucun vendredi (pas d'information)", "SPEC 10.5")
        else:
            endt = f"fin {end // 60:02d}:{end % 60:02d} serveur" if end is not None else "aucune seance ne tient 20:30"
            rep.add("XAUUSD", "friday_session", "seance or du vendredi", "OK" if ok else "DIFFERENT", f"{sess_txt(ss, [5])} ({endt})",
                    "tient 20:30 et va jusqu'a 23:46 serveur (13:30-16:46 New York)",
                    "" if ok else "GFP saute alors chaque vendredi et le pousse (F7)", "SPEC 10.5, CR_Rule_GoldFri.mqh")
        rep.add("XAUUSD", "sessions", "seances de l'or (serveur)", "OK", sess_txt(ss), "pause 17:00-18:00 New York = 00:00-01:00 serveur",
                "information", "SPEC 2.1")
    f = fiches.get("US100")
    if f and f.get("found"):
        rep.add("US100", "sessions", "seances du US100 (serveur)", "OK", sess_txt(sessions_parse(f.get("sessions"))),
                "fermeture 16:15-18:00 New York = 23:15-01:00 serveur", "information", "SPEC 2.1")
    # crypto at weekends
    for b in ("BTCUSD", "ETHUSD"):
        f = fiches.get(b)
        if not f or not f.get("found"):
            continue
        ss = sessions_parse(f.get("sessions"))
        wk = bool(ss.get(0) or ss.get(6))
        bars = m1[b].get("weekend_bars") if b in m1 else None
        broker = f"seances le week-end : {'oui' if wk else 'non'} ({sess_txt(ss, [6, 0])})"
        if bars is not None:
            broker += f" ; minutes cotees le week-end dans m1_{b}.csv : {bars}"
        quoted = wk or bool(bars)
        rep.add(b, "weekend", "cotation le week-end", "DIFFERENT" if quoted else "OK", broker,
                "ferme du vendredi 23:55 au lundi 00:00 serveur (fp_costs.json weekdays_only)",
                "sans effet sur le robot : aucun ordre dans une minute masquee (SPEC 4.1, F2)" if quoted else "", "fp_costs.json, SPEC 2.2")
    # NYSE holidays and half days of the m1 files against the robot's built-in closures (SPEC 2.1)
    for b in ("XAUUSD", "US100"):
        st = m1.get(b)
        if not st:
            continue
        days = st.get("nyse_days", [])
        if not days:
            rep.add(b, "holidays", "jours feries NYSE dans la periode", "UNKNOWN", "aucun jour ferie ni demi-journee dans le releve",
                    "fermetures integrees (SPEC 2.1)", "", "SPEC 2.1")
            continue
        for h in days:
            d = dt.date.fromisoformat(h["date"])
            label = f"{'jour ferie' if h['kind'] == 'full' else 'demi-journee'} NYSE {h['date']}"
            last, lm = h.get("last_ny"), h.get("last_rel_min")
            seen = f"{h['bars']} minutes de la seance (veille 18:00 - 18:00), derniere {last or 'aucune'} New York"
            if not h.get("window_complete"):
                rep.add(b, "holiday_" + h["date"], label, "UNKNOWN", seen + " (seance coupee par le debut ou la fin du releve)",
                        "fermetures integrees (SPEC 2.1)", "", "SPEC 2.1")
                continue
            if b == "US100":
                if h["kind"] == "half":
                    late = lm is not None and lm > 13 * 60 + 15
                    rep.add(b, "holiday_" + h["date"], label, "OK", seen, "le robot masque 13:16-17:59 New York (P6)",
                            "cote apres 13:15 : ces minutes sont masquees" if late else "", "SPEC 2.2")
                else:
                    rep.add(b, "holiday_" + h["date"], label, "OK", seen, "N30 et OC4 ne tradent pas un jour ferie", "information", "SPEC 3")
                continue
            clo = C.gold_holiday_closure(d)
            if clo is None:
                rep.add(b, "holiday_" + h["date"], label, "OK", seen, "journee normale pour l'or", "", "SPEC 2.1")
                continue
            c0, _ = clo
            c0t = "17:00 la veille" if c0 < 0 else f"{c0 // 60:02d}:{c0 % 60:02d}"
            want = f"fermeture integree a partir de {c0t} New York jusqu'a 18:00"
            if c0 < 0:
                ok = h["bars"] == 0
                rep.add(b, "holiday_" + h["date"], label, "OK", seen, want,
                        "" if ok else "FP cote pendant la fermeture du robot : il n'y trade pas, le papier si (SPEC 9.2)", "SPEC 2.1")
            elif lm is None:
                rep.add(b, "holiday_" + h["date"], label, "DIFFERENT", seen, want,
                        f"FP ferme toute la seance ; ajouter '{closure_window('XAU', d, -7 * 60)}' dans InpExtraClosures",
                        "SPEC 2.1, 10.5")
            elif lm + 1 < c0 - 30:
                rep.add(b, "holiday_" + h["date"], label, "DIFFERENT", seen, want,
                        f"FP ferme plus tot que le robot ne le croit : ajouter '{closure_window('XAU', d, lm + 1)}' dans InpExtraClosures",
                        "SPEC 2.1, 10.5")
            else:
                rep.add(b, "holiday_" + h["date"], label, "OK", seen, want,
                        "FP cote encore pendant la fermeture du robot (il n'y trade pas)" if lm >= c0 else "", "SPEC 2.1")


def account_checks(rep, fini, sonde_rows, sonde_meta, m1):
    if fini:
        cur = fini.get("currency")
        rep.add("compte", "currency", "devise du compte", "OK" if cur == "EUR" else ("UNKNOWN" if cur is None else "DIFFERENT"),
                cur, "EUR", "" if cur in ("EUR", None) else "les montants du robot et des essais sont en EUR", "check/mock_replay.h")
        lev = fini.get("leverage")
        rep.add("compte", "leverage", "levier du compte", "OK" if lev == 500 else ("UNKNOWN" if lev is None else "DIFFERENT"),
                f"1:{lev}" if lev else None, "1:500", "", "SPEC (FP Raw 1:500)")
        demo = fini.get("demo")
        rep.add("compte", "demo", "compte de demonstration", "OK" if demo == 1 else ("UNKNOWN" if demo is None else "DIFFERENT"),
                {1: "oui", 0: "non (REEL)"}.get(demo, demo), "oui (deux semaines en demo)",
                "" if demo != 0 else "ReleveFP a tourne sur un compte REEL", "")
        if fini.get("stopped") == 1:
            rep.add("compte", "releve_stopped", "releve complet", "DIFFERENT", "interrompu", "termine", "relancer ReleveFP jusqu'au bout", "")
    # hedging: SondeFP stops before any order on another margin mode (SondeFP.mq5:206-210)
    probes = [r for r in sonde_rows.values() if r.get("status") not in ("INTROUVABLE", None)]
    traded = [r for r in probes if r.get("full")]
    if traded:
        same = True
        if fini and fini.get("server_time") and sonde_meta.get("server_time"):
            same = abs(int(fini["server_time"]) - int(sonde_meta["server_time"])) <= 30 * 86400
        rep.add("compte", "margin_mode", "mode de marge (hedging)", "OK" if same else "UNKNOWN",
                "hedging (SondeFP a passe ses allers-retours ; il refuse tout autre mode)", "hedging requis (SPEC 4.3)",
                "" if same else "sonde et releve a plus de 30 jours d'ecart : est-ce le meme compte ?", "SondeFP.mq5:206-210")
    else:
        rep.add("compte", "margin_mode", "mode de marge (hedging)", "UNKNOWN", "pas d'aller-retour de la sonde",
                "hedging requis (SPEC 4.3)", "ACCOUNT_MARGIN_MODE n'est dans aucun fichier ; le journal du robot le montre (check_demo.py)", "")
    left = [b for b, r in sonde_rows.items() if "RESTEE OUVERTE" in (r.get("status") or "")]
    if left:
        rep.add("compte", "probe_left_open", "position de la sonde restee ouverte", "DIFFERENT", ", ".join(left), "aucune",
                "la fermer a la main (magic 20261112) avant de lancer le robot", "SondeFP.mq5")
    # server clock = New York + 7 h (SPEC 10.4)
    if fini and fini.get("server_time") is not None and fini.get("server_minus_gmt_sec") is not None:
        srv, meas = int(fini["server_time"]), int(fini["server_minus_gmt_sec"])
        rule = C.rule_offset(srv - meas)
        st = "OK" if abs(meas - rule) <= 120 else "DIFFERENT"
        rep.add("compte", "server_clock", "heure du serveur = New York + 7 h", st,
                f"serveur - GMT = {meas} s le {C.ymdhm(srv)} (serveur)", f"{rule} s (New York + 7 h a cette date)",
                "" if st == "OK" else "ecart de plus de 120 s : le robot bloquerait les entrees (CLOCK)", "SPEC 2.1, 6.5, 10.4")
    else:
        rep.add("compte", "server_clock", "heure du serveur = New York + 7 h", "UNKNOWN", "fini.txt absent", "New York + 7 h", "", "SPEC 10.4")
    st = m1.get("XAUUSD")
    if st:
        def gap_hour(counts):
            vals = [counts[h] for h in range(24)]
            med = float(np.median(vals)) or 1.0
            h0 = int(np.argmin(vals))
            return h0, vals[h0] <= 0.05 * med
        parts, ok = [], True
        for side in ("before", "after", None):
            key = f"bars_per_server_hour_{side}" if side else "bars_per_server_hour_tue_thu"
            if key not in st or (side is None and "bars_per_server_hour_before" in st):
                continue
            if side and st.get(f"days_{side}", 0) < 3:                  # too few weekdays on that side of the switch
                continue
            h0, clear = gap_hour(st[key])
            ok &= (h0 == 0 and clear)
            parts.append((f"{'avant le changement' if side == 'before' else 'apres'} : " if side else "") + f"{h0:02d}:00-{h0:02d}:59")
        txt = "pause quotidienne de l'or " + ", ".join(parts) + " serveur"
        if "us_dst_switch_utc" in st:
            txt += f" (changement d'heure americain le {st['us_dst_switch_utc']})"
        rep.add("compte", "server_clock_bars", "heure du serveur d'apres les minutes d'or", "OK" if ok else "DIFFERENT", txt,
                "00:00-00:59 serveur (17:00 New York), avant et apres le changement d'heure", "" if ok else
                "la pause de l'or n'est pas a minuit serveur : serveur different de New York + 7 h ?", "SPEC 2.1, 10.4")


# ---------------------------------------------------------------------------------------------- main
def run(folder, out_dir):
    scrub = C.Scrubber()
    out = C.safe_out(out_dir)
    present = {n: os.path.exists(os.path.join(folder, n)) for n in ("fiches.csv", "tous.csv", "fini.txt", "sonde.csv")}
    m1_files = sorted(f for f in os.listdir(folder) if f.startswith("m1_") and f.endswith(".csv"))
    r1_files = sorted(f for f in os.listdir(folder) if f.startswith("r1_") and f.endswith(".csv"))
    problems = []
    fini = read_fini(os.path.join(folder, "fini.txt"), scrub) if present["fini.txt"] else {}
    fiches, p = read_fiches(os.path.join(folder, "fiches.csv")) if present["fiches.csv"] else ({}, [])
    problems += p
    tous, p = read_tous(os.path.join(folder, "tous.csv")) if present["tous.csv"] else ([], [])
    problems += p
    sonde_rows, sonde_meta, p = read_sonde(os.path.join(folder, "sonde.csv"), scrub) if present["sonde.csv"] else ({}, {}, [])
    problems += p
    costs = C.load_fp_costs()
    m1, m1_df, r1_df, digits_of = {}, {}, {}, {}
    for fn in m1_files:
        base = fn[3:-4]
        try:
            df = read_m1(os.path.join(folder, fn))
            dg = fiches.get(base, {}).get("digits") if fiches.get(base, {}).get("found") else None
            dg = dg if dg is not None else m1_digits(os.path.join(folder, fn))
            if len(df):
                rs = fini.get("server_time") if fini and isinstance(fini.get("server_time"), int) else None
                m1[base] = m1_stats(df, base, int(dg or 0), rs)
                m1[base]["digits"] = int(dg or 0)
                m1_df[base] = df
                digits_of[base] = int(dg or 0)
        except Exception as e:                                          # one bad file never stops the others
            problems.append(f"{fn} illisible : {str(e)[:120]}")
    for fn in r1_files:                                                 # ReleveFP 1.10: the terminal's own M1 bars
        base = fn[3:-4]
        try:
            df = read_r1(os.path.join(folder, fn))
            r1_df[base] = df
            if base not in digits_of:
                dg = fiches.get(base, {}).get("digits") if fiches.get(base, {}).get("found") else None
                digits_of[base] = int(dg) if dg is not None else m1_digits(os.path.join(folder, fn))
        except Exception as e:                                          # noqa: BLE001
            problems.append(f"{fn} illisible : {str(e)[:120]}")
    rep = Report()
    account_checks(rep, fini, sonde_rows, sonde_meta, m1)
    bases = list(C.ROBOT_BASES) + sorted((set(fiches) | set(sonde_rows) | set(m1) | set(r1_df)) - set(C.ROBOT_BASES))
    usd_rate = next((eur_per_usd(f) for f in fiches.values() if f.get("found") and f.get("ccy_profit") == "USD"
                     and eur_per_usd(f)), None)
    for b in bases:
        if b == "":
            continue
        fini_m = fini.get("markets", {}).get(b) if fini else None
        market_checks(rep, b, fiches.get(b) if fiches else None, tous, costs, sonde_rows, m1, fini_m, b in C.ROBOT_BASES, usd_rate)
        releve_checks(rep, b, fini_m, os.path.join(folder, f"m1_{b}.csv") if f"m1_{b}.csv" in m1_files else None,
                      os.path.join(folder, f"r1_{b}.csv") if f"r1_{b}.csv" in r1_files else None, m1_df.get(b), r1_df.get(b),
                      digits_of.get(b))
    session_checks(rep, fiches, m1)
    counts = {s: sum(1 for c in rep.checks if c["status"] == s) for s in ("OK", "DIFFERENT", "UNKNOWN")}
    summary = {"tool": "read_mac_files", "version": 2, "releve_version": fini.get("version") if fini else None,
               "files_read": {**present, "m1": m1_files, "r1": r1_files},
               "problems": problems, "account": {k: v for k, v in fini.items() if k != "markets"} if fini else {},
               "releve_markets": fini.get("markets", {}) if fini else {}, "sonde_meta": sonde_meta,
               "fiches": fiches, "sonde": sonde_rows, "m1": m1, "checks": rep.checks, "counts": counts,
               "robot_names_by_brkresolve": {b: resolve(b, tous, ROBOT_ALIASES) for b in C.ROBOT_BASES} if tous else {}}
    lines = french(summary, rep.checks, counts, problems)
    C.write_json(os.path.join(out, "summary.json"), C.clean_json(summary), scrub)
    C.write_text(os.path.join(out, "summary_fr.txt"), lines["full"], scrub)
    print(scrub.text("\n".join(lines["short"])))
    return summary, out


def french(summary, checks, counts, problems):
    files = summary["files_read"]
    lus = [n for n in ("fiches.csv", "tous.csv", "fini.txt", "sonde.csv") if files.get(n)] + files.get("m1", []) + files.get("r1", [])
    head = [f"Lecture des fichiers du Mac : {', '.join(lus) if lus else 'aucun fichier reconnu'}.",
            f"{counts['OK']} points conformes, {counts['DIFFERENT']} differents, {counts['UNKNOWN']} inconnus."]
    full = list(head) + [""]
    for c in checks:
        tag = {"OK": "OK       ", "DIFFERENT": "DIFFERENT", "UNKNOWN": "INCONNU  "}[c["status"]]
        line = f"{tag} {c['market']:8s} {c['label']} : courtier {c['broker'] if c['broker'] is not None else '?'}"
        line += f" | robot/labo {c['assumed'] if c['assumed'] is not None else '?'}"
        if c["note"]:
            line += f" | {c['note']}"
        full.append(line)
    if problems:
        full += ["", "Problemes de lecture :"] + [f"  - {p}" for p in problems]
    short = list(head)
    key = [c for c in checks if c["status"] == "DIFFERENT"]
    if key:
        short.append("Points differents :")
        for c in key[:25]:
            short.append(f"  - {c['market']} {c['label']} : courtier {c['broker']} ; robot/labo {c['assumed']}"
                         + (f" ({c['note']})" if c["note"] else ""))
        if len(key) > 25:
            short.append(f"  ... et {len(key) - 25} autres (voir summary_fr.txt)")
    imp = [c for c in checks if c["item"] in ("margin_mode", "server_clock") or (c["market"] in ("BTCUSD", "ETHUSD") and c["item"] == "margin")
           or (c["market"] == "XAUUSD" and c["item"] in ("commission", "friday_session")) or (c["market"] == "US100" and c["item"] == "vol_min")]
    if imp:
        short.append("Points cles :")
        for c in imp:
            short.append(f"  - {c['market']} {c['label']} : {c['status'].replace('UNKNOWN', 'INCONNU')} (courtier {c['broker']})")
    if problems:
        short.append(f"{len(problems)} probleme(s) de lecture (voir summary_fr.txt).")
    return {"full": full, "short": short}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder")
    ap.add_argument("--out", default=C.DEFAULT_OUT)
    a = ap.parse_args(argv)
    if not os.path.isdir(a.folder):
        raise SystemExit("dossier introuvable")
    C.warn_if_in_repo([a.folder])
    summary, out = run(a.folder, a.out)
    print(f"Fichiers ecrits : {os.path.join(out, 'summary.json')} et {os.path.join(out, 'summary_fr.txt')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
