"""PROTOCOL_V3 addendum E: the lead's single look at 2022-2025 for the stake profiles (and the same code path in
sample, as a dry run).

    python3 r2/tracks/stake/val.py dry     # common in-sample period 2018-02..2021: must reproduce the designer's figures
    python3 r2/tracks/stake/val.py val     # 2022-2025, once, logged in results/val_access.log

Each profile is judged against the reference (the ten rules at an equal stake of 1 %) with the three criteria of
addendum E (winning weeks >= reference + 8 points; worst week and maximum drawdown <= 1.25 x the reference's; total
profit > 0), twice:
  as designed   every signal taken, no compounding, base stake = the frozen base_scale (the accounting of the search)
  on 1,000 EUR  the account loop with minimum lots, 6 positions, 2 per market, account kept at 1,000 EUR (gains
                withdrawn), stop distances at TODAY's price level; the reference is simulated the same way at 1 %
Winning weeks are also counted on week-end equity (open trades marked at the last price). Reported as well: the
1,000 EUR account at the period's own prices, a 20,000 EUR account, a compounding account, the number of weeks worse
than -8 %, and the same profit earned with a plain flat stake (clarification of addendum E).
"""
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stake as S  # noqa: E402
import account as A  # noqa: E402

PROFILES = {
    "reference": ({}, 1.0),
    "cushion_only": (S.INFO_ONLY["cushion_only"]["config"], S.INFO_ONLY["cushion_only"]["base_scale"]),
    "soft": (S.FROZEN["soft"]["config"], S.FROZEN["soft"]["base_scale"]),
    "strong": (S.FROZEN["strong"]["config"], S.FROZEN["strong"]["base_scale"]),
}
WINDOW = {"dry": (S.COMMON_START, S.IS_END), "val": (pd.Timestamp("2022-01-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC"))}


def trades(period, raw=False):
    a, b = WINDOW[period]
    per = {}
    for name, sym in S.SLEEVES:
        t = pd.read_parquet(os.path.join(S.NET_DIR, f"{name}__{sym}.parquet"))
        per[(name, sym)] = t[(t.entry_time >= a) & (t.entry_time < b)]
    if period == "val":
        with open(os.path.join(S.LAB, "results", "val_access.log"), "a") as f:
            f.write(json.dumps({"time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "track": "stake",
                                "label": "stake_profiles:cushion_only+soft+strong:lead_single_look", "period": "val"}) + "\n")
    d = S.build_frame(per)
    return with_side(d, per)


def ideal(a, cfg, scale, years):
    m = S.run(a, cfg)
    st = S.stats(a, m)
    r = m * a["R"] * scale
    yr = pd.Series(r).groupby(pd.Series(years)).sum()
    wk = pd.Series(r).groupby(pd.Series(a["wk_out"])).sum()
    wy = pd.Series(years).groupby(pd.Series(a["wk_out"])).first()
    out = {k: st[k] for k in ("n_trades", "skipped_pct", "avg_stake", "max_stake", "win_days_pct", "win_weeks_pct", "win_months_pct",
                              "weeks", "longest_red_weeks")}
    for k in ("total", "avg_green_day", "avg_red_day", "avg_green_week", "avg_red_week", "worst_day", "worst_week", "worst_month", "max_dd"):
        out[k + "_pct"] = round(float(st[k] * scale), 2)
    out["by_year_pct"] = {int(y): round(float(v), 1) for y, v in yr.items()}
    out["win_weeks_by_year_pct"] = {int(y): round(float(100 * (wk[wy == y] > 0).mean()), 1) for y in sorted(wy.unique())}
    return out


def with_side(d, per):
    """Attach each trade's side to the engine frame (needed to mark open trades at the week end)."""
    fr = []
    for (name, sym), t in per.items():
        fr.append(pd.DataFrame({"sleeve": f"{name}_{sym}", "t_in": pd.to_datetime(t.entry_time, utc=True).to_numpy(),
                                "t_out": pd.to_datetime(t.exit_time, utc=True).to_numpy(), "side": t.side.to_numpy()}))
    k = pd.concat(fr, ignore_index=True)
    k["t_in"], k["t_out"] = pd.to_datetime(k.t_in, utc=True), pd.to_datetime(k.t_out, utc=True)
    out = d.merge(k, on=["sleeve", "t_in", "t_out"], how="left", validate="one_to_one")
    assert out.side.notna().all() and (out.sleeve.to_numpy() == d.sleeve.to_numpy()).all()
    return out


def week_marks(d, a, period):
    """Unrealised result in R (per unit of stake) of every trade still open at the end of a server week, at the last
    mid price before Monday 00:00 server time: list of (trade index, week index, R)."""
    from goldlab import r2
    span = np.nonzero(a["wk_in"] != a["wk_out"])[0]
    si = S.server_time(d.t_in)
    marks = []
    for sym in sorted(set(d.sym.to_numpy()[span])):
        px = r2.load(sym, end="2022-01-01") if period == "dry" else r2.load(sym)
        idx, cl = px.index, (px["bc"].to_numpy() + px["ac"].to_numpy()) / 2.0
        for i in span[d.sym.to_numpy()[span] == sym]:
            mon0 = si[i].normalize() - pd.Timedelta(days=int(si[i].dayofweek))
            for w in range(int(a["wk_in"][i]), int(a["wk_out"][i])):
                mon = mon0 + pd.Timedelta(days=7 * (w - int(a["wk_in"][i]) + 1))
                t_utc = (mon - pd.Timedelta(hours=7)).tz_localize("America/New_York").tz_convert("UTC")
                j = idx.searchsorted(t_utc, side="left") - 1
                marks.append((int(i), w, float(d.side.iat[i] * (cl[j] - d.entry.iat[i]) / d.risk.iat[i])))
        r2.free()
    return marks


def equity_weeks(a, m, scale, marks):
    """Weekly results counted on week-end equity: closed results + change of the open trades' unrealised result."""
    r = m * a["R"] * scale
    wk = np.bincount(a["wk_out"], weights=r, minlength=a["nwk"] + 1)
    for i, w, u in marks:
        wk[w] += u * m[i] * scale
        wk[w + 1] -= u * m[i] * scale
    live = np.bincount(np.r_[a["wk_out"], a["wk_in"]], minlength=a["nwk"] + 1) > 0
    x = wk[live]
    return {"win_weeks_equity_pct": round(float(100 * (x > 0).mean()), 1), "worst_week_equity_pct": round(float(x.min()), 2),
            "weeks_worse_than_-8pct": int((x < -8).sum()), "weeks": int(len(x))}


def flat_same_profit(a, total_pct, marks):
    """The reference at the flat stake that earns the same total: its worst week and its weeks worse than -8 %."""
    m = S.run(a, {})
    ref_total = float((m * a["R"]).sum())
    if ref_total <= 0 or total_pct <= 0:
        return None
    s = total_pct / ref_total
    wk = np.bincount(a["wk_out"], weights=m * a["R"] * s, minlength=a["nwk"])
    live = np.bincount(a["wk_out"], minlength=a["nwk"]) > 0
    return {"flat_stake_pct": round(float(s), 2), "worst_week_pct": round(float(wk[live].min()), 2),
            "weeks_worse_than_-8pct": int((wk[live] < -8).sum())}


def criteria(x, ref, weeks="win_weeks_pct", worst="worst_week_pct", dd="max_dd_pct", total=None):
    c = {"weeks>=ref+8": x[weeks] >= ref[weeks] + 8.0,
         "worst_week<=1.25x_ref": abs(x[worst]) <= 1.25 * abs(ref[worst]),
         "max_dd<=1.25x_ref": abs(x[dd]) <= 1.25 * abs(ref[dd]),
         "profit>0": (x[total] if total else x.get("total_pct", x.get("per_year_pct"))) > 0}
    c["pass"] = bool(all(c.values()))
    return {k: bool(v) for k, v in c.items()}


def look(period):
    d = trades(period)
    a = S.prepare(d)
    out = {"period": period, "window": [str(x.date()) for x in WINDOW[period]], "n_signals": int(len(d)), "profiles": {}}
    years = S.server_time(d.t_out).year.to_numpy()          # year of the exit, server clock (the booking clock)
    fr = A.frame(d=d)
    fr_today = A.frame(d=d, price_level="today")
    marks = week_marks(d, a, period)
    for name, (cfg, scale) in PROFILES.items():
        m = S.run(a, cfg)
        idl = ideal(a, cfg, scale, years)
        idl.update(equity_weeks(a, m, scale, marks))
        wkc = np.bincount(a["wk_out"], weights=m * a["R"] * scale, minlength=a["nwk"])
        idl["weeks_worse_than_-8pct_closed"] = int((wkc[np.bincount(a["wk_out"], minlength=a["nwk"]) > 0] < -8).sum())
        idl["same_profit_with_a_flat_stake"] = flat_same_profit(a, idl["total_pct"], marks)
        p = {"base_scale": scale, "as_designed": idl,
             "on_1000_eur_period_prices": A.account(cfg, 1000.0, base_pct=1.0 * scale, d=fr, compound=False),
             "on_1000_eur": A.account(cfg, 1000.0, base_pct=1.0 * scale, d=fr_today, compound=False),
             "on_20000_eur": A.account(cfg, 20000.0, base_pct=1.0 * scale, d=fr, compound=False),
             "compounding_from_1000_eur": A.account(cfg, 1000.0, base_pct=1.0 * scale, d=fr, compound=True)}
        out["profiles"][name] = p
    ref = out["profiles"]["reference"]
    for name, p in out["profiles"].items():
        if name == "reference":
            continue
        p["criteria_as_designed"] = criteria(p["as_designed"], ref["as_designed"])
        p["criteria_as_designed"]["weeks_on_equity>=ref+8"] = bool(
            p["as_designed"]["win_weeks_equity_pct"] >= ref["as_designed"]["win_weeks_equity_pct"] + 8.0)
        p["criteria_as_designed"]["pass"] = bool(all(v for k, v in p["criteria_as_designed"].items() if k != "pass"))
        p["criteria_on_1000_eur"] = criteria(p["on_1000_eur"], ref["on_1000_eur"], total="per_year_pct")
    for name, p in out["profiles"].items():
        i, r1 = p["as_designed"], p["on_1000_eur"]
        print(f"{name:13s} as designed: weeks {i['win_weeks_pct']:5.1f} days {i['win_days_pct']:5.1f} months {i['win_months_pct']:5.1f} | total {i['total_pct']:+7.1f}% "
              f"green/red week {i['avg_green_week_pct']:+.2f}/{i['avg_red_week_pct']:+.2f} worst week {i['worst_week_pct']:6.1f} DD {i['max_dd_pct']:5.1f} "
              f"red run {i['longest_red_weeks']} | by year {i['by_year_pct']} weeks by year {i['win_weeks_by_year_pct']}")
        print(f"{'':13s} on equity: weeks {i['win_weeks_equity_pct']:5.1f} worst week {i['worst_week_equity_pct']:6.1f} | weeks worse than -8 %: {i['weeks_worse_than_-8pct_closed']} "
              f"| same profit with a flat stake: {i['same_profit_with_a_flat_stake']}")
        print(f"{'':13s} on 1,000 EUR (today's prices): {A.short(r1)}")
        print(f"{'':13s} period prices: {A.short(p['on_1000_eur_period_prices'])}")
        print(f"{'':13s} 20,000 EUR  : {A.short(p['on_20000_eur'])}")
        if name != "reference":
            print(f"{'':13s} criteria as designed {p['criteria_as_designed']} | on 1,000 EUR {p['criteria_on_1000_eur']}")
    if period == "val":
        json.dump(out, open(os.path.join(S.OUT, "val_look.json"), "w"), indent=1, default=str)
    return out


if __name__ == "__main__":
    look(sys.argv[1])
