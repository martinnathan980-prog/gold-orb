"""IS dossier of the two finalists (no validation data loaded: frames end on 2021-12-31, except r2.null_test and
r2.evaluate which load the full frame internally but only report IS)."""
from diag import *      # noqa
A = dict(rule="noise")
B4 = dict(rule="ocm", n=4, stop="atr", k=0.3, size_min=1.0)
FIN = {"noise30_us100": ("us100", A), "ocm4_us100": ("us100", B4)}
out = {}
# null tests
pn = os.path.join(RES, "null_tests.json")
nulls = json.load(open(pn)) if os.path.exists(pn) else {}
for name, (sym, params) in FIN.items():
    key = "noise_us100" if name == "noise30_us100" else name
    if key not in nulls:
        t0 = time.time()
        nul = r2.null_test(sym, S.make_orders, S.resolve(params), n_seeds=200, mode="day")
        nul.update(secs=round(time.time() - t0, 1), params=S.resolve(params), sym=sym)
        nulls[key] = nul
        json.dump(nulls, open(pn, "w"), indent=1, default=str)
    print(name, "null:", {k: nulls[key][k] for k in ("n", "rule_mean_R", "null_mean_R", "null_p95_R", "null_max_R", "percentile", "pass")})
    d, t = describe(sym, params, name)
    d["null"] = {k: nulls[key][k] for k in ("n", "mode", "rule_mean_R", "null_mean_R", "null_p95_R", "null_max_R", "percentile", "pass")}
    # long / short detail and by-year per side
    t["yr"] = t.entry_time.dt.year
    d["by_year_side_R"] = {int(y): {"long": round(float(x.R[x.side > 0].sum()), 1), "short": round(float(x.R[x.side < 0].sum()), 1)} for y, x in t.groupby("yr")}
    # exposure: average minutes in market per trade, stop distance in bp and in price for the last IS year
    d["stop_bp_median_all"] = round(float((t.risk / t.entry * 1e4).median()), 1)
    d["stop_price_median_2021"] = round(float(t.risk[t.yr == 2021].median()), 1)
    d["loss_R_mean_of_losers"] = round(float(t.R[t.R < 0].mean()), 3)
    d["win_R_mean_of_winners"] = round(float(t.R[t.R > 0].mean()), 3)
    d["weekly_R"] = {"pos_pct": round(float((gl.weekly_R(t) > 0).mean() * 100), 1), "worst": round(float(gl.weekly_R(t).min()), 2)}
    d["monthly_R_pos_pct"] = round(float((t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("M")).R.sum() > 0).mean() * 100), 1)
    out[name] = d
    t.drop(columns=["day"]).to_csv(os.path.join(RES, f"trades_is_{name}.csv"), index=False)
    print(json.dumps(d, default=str))
    print()
json.dump(out, open(os.path.join(RES, "finalist_diag_is.json"), "w"), indent=1, default=str)
