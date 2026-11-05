"""What can a ~10-month 2026 holdout (~95 trades) tell us?
Predictive distribution of the holdout PF under
  H1_measured : the candidate's own history (IS+VAL 2013-2025), rolling 10-month windows
  H1_shrunk_x : same trades, R shifted so the overall mean is x (selection-shrunk edge)
  H0_zero     : same trades, R shifted to an overall mean of 0 (net edge exactly zero)
  H0_rand_N1  : random-side null at the candidate's signal times (s02 N1), rolling windows
  H0_rand_N2  : random-time random-side null (s02 N2), rolling windows
plus a parametric check: window mean R ~ N(mu, tau^2 + sd^2/n) with tau from the random-effects
fit across years (s04)."""
import json

from scipy import stats

from common import *  # noqa

ti = pd.read_parquet(os.path.join(HERE, "cand_trades_is.parquet"))
tv = pd.read_parquet(os.path.join(HERE, "cand_trades_val.parquet"))
TA = pd.concat([ti[ti.cost == "normal"], tv[tv.cost == "normal"]])
MONTHS = pd.period_range("2013-01", "2025-12", freq="M")
WIN = int(os.environ.get("WIN", 10))
mu_all = float(TA.R.mean())
sd_all = float(TA.R.std(ddof=1))
code = MONTHS.get_indexer(TA.entry_time.dt.tz_convert(None).dt.to_period("M"))
R = TA.R.to_numpy()


def monthly(Rs):
    pos = np.bincount(code, weights=np.where(Rs > 0, Rs, 0), minlength=len(MONTHS))
    neg = np.bincount(code, weights=np.where(Rs < 0, -Rs, 0), minlength=len(MONTHS))
    n = np.bincount(code, minlength=len(MONTHS)).astype(float)
    return np.stack([pos, neg, n], axis=-1)


def windows(mon):
    """mon (..., months, 3) -> PF of every rolling WIN-month window (..., months-WIN+1)."""
    cs = np.cumsum(mon, axis=-2)
    cs = np.concatenate([np.zeros_like(cs[..., :1, :]), cs], axis=-2)
    w = cs[..., WIN:, :] - cs[..., :-WIN, :]
    return w[..., 0] / w[..., 1], w[..., 2]


dist = {}
pf_c, n_c = windows(monthly(R))
dist["H1_measured"] = pf_c.ravel()
for x in (0.05, 0.03):
    dist[f"H1_shrunk_{x}"] = windows(monthly(R - mu_all + x))[0].ravel()
dist["H0_zero"] = windows(monthly(R - mu_all))[0].ravel()
for nm in ("N1", "N2"):
    mon = np.load(os.path.join(HERE, f"s02_{nm}_monthly.npy"))
    p_, n_ = windows(mon)
    dist[f"H0_rand_{nm}"] = p_.ravel()
out = {"window_months": WIN, "trades_per_window_median": float(np.median(n_c)), "mu_all": round(mu_all, 4),
       "sd_all": round(sd_all, 3)}
bins = [0, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4, np.inf]
blab = ["<0.8", "0.8-0.9", "0.9-1.0", "1.0-1.1", "1.1-1.2", "1.2-1.4", ">=1.4"]
summ = {}
for k, v in dist.items():
    v = v[np.isfinite(v)]
    h = np.histogram(v, bins=bins)[0] / len(v)
    summ[k] = {"n_windows": int(len(v)), "pf_q5_25_50_75_95": [round(float(np.percentile(v, p)), 3) for p in (5, 25, 50, 75, 95)],
               "P(pf>1.0)": round(float((v > 1.0).mean()), 3), "P(pf>1.1)": round(float((v > 1.1).mean()), 3),
               "P(pf>1.2)": round(float((v > 1.2).mean()), 3), "P(pf<0.9)": round(float((v < 0.9).mean()), 3),
               "P(pf<0.8)": round(float((v < 0.8).mean()), 3), "bins": dict(zip(blab, [round(float(x), 3) for x in h]))}
out["empirical"] = summ
# likelihood ratios of outcome bins (H1_measured vs each H0) and posterior for a 30% prior
lr = {}
for h0 in ("H0_zero", "H0_rand_N1", "H0_rand_N2"):
    for h1 in ("H1_measured", "H1_shrunk_0.05"):
        r = {}
        for b in blab:
            p1, p0 = summ[h1]["bins"][b], summ[h0]["bins"][b]
            r[b] = round(p1 / p0, 2) if p0 > 0 else None
        p1, p0 = summ[h1]["P(pf>1.0)"], summ[h0]["P(pf>1.0)"]
        r["PASS pf>1"] = round(p1 / p0, 2)
        r["FAIL pf<=1"] = round((1 - p1) / (1 - p0), 2)
        lr[f"{h1}_vs_{h0}"] = r
out["likelihood_ratios"] = lr


def post(prior, L):
    return round(prior * L / (prior * L + 1 - prior), 3)


out["posterior_from_prior_0.3_H1measured_vs_H0zero"] = {b: (post(0.3, v) if v else None) for b, v in lr["H1_measured_vs_H0_zero"].items()}
out["posterior_from_prior_0.3_H1measured_vs_H0randN1"] = {b: (post(0.3, v) if v else None) for b, v in lr["H1_measured_vs_H0_rand_N1"].items()}
# thresholds: what PF would a 10-month holdout need to reject each H0 at 5% / 10% one-sided, and its power under H1
thr = {}
for h0 in ("H0_zero", "H0_rand_N1", "H0_rand_N2"):
    v0 = dist[h0][np.isfinite(dist[h0])]
    for a in (0.05, 0.10):
        c = float(np.percentile(v0, 100 * (1 - a)))
        v1 = dist["H1_measured"][np.isfinite(dist["H1_measured"])]
        vs = dist["H1_shrunk_0.05"][np.isfinite(dist["H1_shrunk_0.05"])]
        thr[f"{h0}_alpha{a}"] = {"pf_threshold": round(c, 3), "power_H1_measured": round(float((v1 > c).mean()), 3),
                                 "power_H1_shrunk_0.05": round(float((vs > c).mean()), 3)}
out["rejection_thresholds"] = thr
# parametric check (normal approx on the window mean R; PF mapped via the empirical PF~mean relation)
s4 = json.load(open(os.path.join(HERE, "s04_boot_conc.json")))
tau = s4["random_effects_years"]["is+val"]["tau"]
nh = float(os.environ.get("NH", 95))
mw = np.array([w for w in windows(monthly(R))[0].ravel()])
# PF <-> mean R mapping from the candidate's own windows
cs = np.cumsum(monthly(R), axis=0)
cs = np.vstack([np.zeros((1, 3)), cs])
ww = cs[WIN:] - cs[:-WIN]
mean_w = (ww[:, 0] - ww[:, 1]) / ww[:, 2]
pf_w = ww[:, 0] / ww[:, 1]
slope, icpt = np.polyfit(mean_w, pf_w, 1)
par = {"tau": tau, "n_holdout": nh, "pf_vs_meanR_fit": [round(float(icpt), 3), round(float(slope), 3)]}
for nm, mu in (("H1_measured", mu_all), ("H1_shrunk_0.05", 0.05), ("H1_shrunk_0.03", 0.03), ("H0_zero", 0.0),
               ("H0_rand", -0.075)):
    sdm = math.sqrt(tau ** 2 + sd_all ** 2 / nh)
    m_thr = (1.0 - icpt) / slope
    par[nm] = {"mu": mu, "sd_window_mean": round(sdm, 4), "P(pf>1)": round(float(1 - stats.norm.cdf((m_thr - mu) / sdm)), 3),
               "pf_q5_50_95": [round(float(icpt + slope * (mu + z * sdm)), 3) for z in (-1.645, 0, 1.645)]}
    sdm0 = sd_all / math.sqrt(nh)
    par[nm]["no_year_effect"] = {"sd": round(sdm0, 4), "P(pf>1)": round(float(1 - stats.norm.cdf((m_thr - mu) / sdm0)), 3)}
out["parametric"] = par
# trades needed for an 80%-power, 5% one-sided test of mu=mu_all vs 0 (iid, no year effects)
out["trades_needed_80pct_power"] = {f"mu={m}": int(((1.645 + 0.8416) * sd_all / m) ** 2) for m in (mu_all, 0.05, 0.03)}
json.dump(out, open(os.path.join(HERE, "s07_holdout.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
