"""Synthesis: per-trial luck probabilities under each null, P(>=1 of N_eff passes), project-level
false-positive rate, corrected deflated Sharpe, posterior for the net edge, neighbour-vs-correlation."""
import json

from scipy import stats

from common import *  # noqa

J = lambda f: json.load(open(os.path.join(HERE, f)))
nul, fam, bc, hold = J("s02_nulls.json")["families"], J("s03_family.json"), J("s04_boot_conc.json"), J("s07_holdout.json")
ti = pd.read_parquet(os.path.join(HERE, "cand_trades_is.parquet"))
TI = ti[ti.cost == "normal"]
R = TI.R.to_numpy()
T = len(R)
out = {}

# ---------------------------------------------------------------- 1. per-trial luck probabilities
per = {}
for nm in ("N1", "N1y", "N1q", "N1m", "N2"):
    f = nul[nm]
    m, s = f["is_t_mean_sd_max"][0], f["is_t_mean_sd_max"][1]
    vm, vs = f["val_t_mean_sd"]
    ns = f["seeds"]
    per[nm] = {"seeds": ns, "emp_is_pass": f["frac_is_pass"], "emp_is_near": f["frac_is_near"], "emp_val_pass": f["frac_val_pass"],
               "cp95_upper_if_zero": round(1 - 0.05 ** (1 / ns), 5),
               "normal_tail_P(t>=2)": float(1 - stats.norm.cdf((2.0 - m) / s)),
               "normal_tail_P(t>=1.83)": float(1 - stats.norm.cdf((1.8297 - m) / s)),
               "cand_IS_z": round((1.8297 - m) / s, 2), "cand_VAL_z": round((0.7418 - vm) / vs, 2),
               "cand_VAL_p_one_sided": round(float(1 - stats.norm.cdf((0.7418 - vm) / vs)), 4)}
zn = bc["bootstrap"]
per["zero_net(week-block centred)"] = {"is_core": zn["is/week"]["zero_net_null"]["P(pf>=1.20 & t>=2)"],
                                       "is_near": zn["is/week"]["zero_net_null"]["P(pf>=obs_is_level 1.1773 & t>=1.83)"],
                                       "val_pass": zn["val/week"]["zero_net_null"]["P(pf>=1.10 & exp>0)"]}
out["per_trial"] = per


def atleast(p, n):
    return round(float(1 - (1 - p) ** n), 4)


NEFF = [10, 23, 48, 100, 200, 321, 370]
tab = {}
pr = per["N2"]["normal_tail_P(t>=2)"]
prn = per["N2"]["normal_tail_P(t>=1.83)"]
pz, pzn, pzv = per["zero_net(week-block centred)"]["is_core"], per["zero_net(week-block centred)"]["is_near"], per["zero_net(week-block centred)"]["val_pass"]
for n in NEFF:
    tab[n] = {"random_entry: IS core pass": atleast(pr, n), "random_entry: IS at candidate level": atleast(prn, n),
              "random_entry: IS core & VAL": atleast(pr * per["N2"]["emp_val_pass"], n),
              "zero_net: IS core pass": atleast(pz, n), "zero_net: IS at candidate level": atleast(pzn, n),
              "zero_net: IS core & VAL (if every trial got a VAL shot)": atleast(pz * pzv, n),
              "zero_net: IS at cand. level & VAL": atleast(pzn * pzv, n)}
out["P_at_least_one_of_Neff"] = tab
out["orb_family_mvn"] = fam["familywise_max_t"]
out["orb_meff"] = {"all48": fam["meff_all"], "stages1_4": fam["meff_stages1_4"], "asia_multiday": fam["meff_asia_multiday"]}

# ---------------------------------------------------------------- 2. project-level: >=1 track produces a candidate at least this good (IS) that also passes VAL
ratio = fam["meff_all"]["li_ji"] / 48
tracks = {"orb": 48, "trend": 50, "pivots": 72, "seasonality": 24, "meanrev": 38, "crossasset": 77}
proj = {}
p_track = {}
for k, n in tracks.items():
    me = max(1.0, n * ratio)
    p_is = 1 - (1 - pzn) ** me if k != "orb" else fam["familywise_max_t"]["all48/zero_net"]["P(max>=t_patched)"]
    p_track[k] = {"meff": round(me, 1), "P(best IS >= cand level)": round(float(p_is), 3), "P(& VAL pass)": round(float(p_is * pzv), 3)}
proj["tracks"] = p_track
proj["P(>=1 track yields IS>=cand level & VAL pass | global zero-net null)"] = round(float(1 - np.prod([1 - v["P(& VAL pass)"] for v in p_track.values()])), 3)
out["project_level"] = proj

# ---------------------------------------------------------------- 3. deflated Sharpe, corrected
sr = R.mean() / R.std(ddof=1)
sk = float(pd.Series(R).skew())
ku = float(pd.Series(R).kurt()) + 3
den = math.sqrt(max(1e-12, 1 - sk * sr + (ku - 1) / 4 * sr * sr))
g = 0.5772156649
dsr = {}
for N in (10, 23, 48, 100, 321):
    emax = (1 - g) * stats.norm.ppf(1 - 1 / N) + g * stats.norm.ppf(1 - 1 / (N * math.e))
    sr0 = math.sqrt(1 / T) * emax
    dsr[N] = {"sr0": round(float(sr0), 4), "dsr": round(float(stats.norm.cdf((sr - sr0) * math.sqrt(T - 1) / den)), 3)}
out["dsr_noise_variance"] = {"sr_per_trade": round(float(sr), 4), "skew": round(sk, 2), "kurt": round(ku, 2), "by_N": dsr,
                             "note": "audit used the cross-trial SR variance (0.0635^2), which includes true cost differences "
                                     "between configs (e.g. COMEX/Zarattini) and inflates SR0; noise variance 1/T is the H0 variance"}

# ---------------------------------------------------------------- 4. posterior for the net edge (R/trade, primary costs)
m_v, t_v = 0.0651, 0.7418
se_v = m_v / t_v
m_i, t_i = float(R.mean()), tstat(R)
se_i = m_i / t_i
tau = bc["random_effects_years"]["is+val"]["tau"]
post = {}
# (a) empirical Bayes on the project's 6 finalists' VAL t-stats (same protocol, single shot each)
vt = np.array([-1.84, 0.74, -0.92, -0.79, -1.53, 1.49])
mbar, v = vt.mean(), vt.var(ddof=1)
om2 = max(v - 1, 1e-6)
th = mbar + om2 / (om2 + 1) * (0.7418 - mbar)
th_sd = math.sqrt(om2 / (om2 + 1))
post["EB_6_finalists_VAL_t"] = {"mean_t": round(float(mbar), 3), "omega": round(math.sqrt(om2), 3), "posterior_theta_t": round(float(th), 3),
                                "posterior_sd_t": round(th_sd, 3), "P(edge>0)": round(float(stats.norm.cdf(th / th_sd)), 3),
                                "posterior_mean_R_per_trade": round(float(th * se_v), 4)}
# (b) normal-normal: prior N(m0, s0) x VAL (unselected; +tau^2/4 for regime) x IS (bias-corrected for selection; +tau^2/9)
emax_fam = fam["familywise_max_t"]["stages1_4/zero_net"]["E_max_t"]
emax_sub = fam["familywise_max_t"]["asia_multiday/zero_net"]["E_max_t"]
res = []
for prior_name, m0, s0 in (("flat", 0.0, 10.0), ("sceptical N(-0.03,0.06)", -0.03, 0.06), ("neutral N(0,0.08)", 0.0, 0.08)):
    for is_mode, mi, si in (("IS ignored", None, None),
                            (f"IS - Emax(stages1-4)={emax_fam:.2f}SE", m_i - emax_fam * se_i, math.sqrt(se_i ** 2 + tau ** 2 / 9)),
                            (f"IS - Emax(asia sub)={emax_sub:.2f}SE", m_i - emax_sub * se_i, math.sqrt(se_i ** 2 + tau ** 2 / 9)),
                            ("IS naive", m_i, math.sqrt(se_i ** 2 + tau ** 2 / 9))):
        prec = 1 / s0 ** 2 + 1 / (se_v ** 2 + tau ** 2 / 4)
        num = m0 / s0 ** 2 + m_v / (se_v ** 2 + tau ** 2 / 4)
        if mi is not None:
            prec += 1 / si ** 2
            num += mi / si ** 2
        pm, ps = num / prec, math.sqrt(1 / prec)
        res.append({"prior": prior_name, "IS": is_mode, "post_mean": round(pm, 4), "post_sd": round(ps, 4),
                    "P(mu>0)": round(float(1 - stats.norm.cdf(-pm / ps)), 3),
                    "P(mu>0.05)": round(float(1 - stats.norm.cdf((0.05 - pm) / ps)), 3),
                    "P(mu>=0.10)": round(float(1 - stats.norm.cdf((0.10 - pm) / ps)), 3)})
post["normal_models"] = res
# (c) two-point Bayes factors from VAL alone (iid SE, and with tau^2/4)
bf = {}
for h1 in (0.10, 0.06):
    for h0 in (0.0, -0.07):
        for nm_, s_ in (("iid", se_v), ("with_tau", math.sqrt(se_v ** 2 + tau ** 2 / 4))):
            bf[f"mu1={h1} vs mu0={h0} ({nm_})"] = round(float(stats.norm.pdf(m_v, h1, s_) / stats.norm.pdf(m_v, h0, s_)), 2)
post["VAL_bayes_factors"] = bf
out["posterior"] = post

# ---------------------------------------------------------------- 5. neighbour PF vs correlation with F3 (are neighbours independent evidence?)
info = {r["label"]: r for r in fam["info"]}
nb = [k for k in info if k.startswith("N") and k[1:3].isdigit()] + ["A3_asia_hold2d"]
x = np.array([fam["corr_F3_with"][k] for k in nb])
y = np.array([info[k]["pf"] for k in nb])
b, a = np.polyfit(x, y, 1)
out["neighbours"] = {"pairs": sorted([(k, round(float(fam["corr_F3_with"][k]), 3), round(float(info[k]["pf"]), 3)) for k in nb], key=lambda z: -z[1]),
                     "fit_pf = a + b*corr": [round(float(a), 3), round(float(b), 3)],
                     "median_pf_corr>=0.9": round(float(np.median(y[x >= 0.9])), 3),
                     "median_pf_corr<0.9": round(float(np.median(y[x < 0.9])), 3),
                     "median_pf_corr<0.8": round(float(np.median(y[x < 0.8])), 3),
                     "spearman": round(float(stats.spearmanr(x, y).correlation), 3)}
json.dump(out, open(os.path.join(HERE, "s09_synthesis.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
