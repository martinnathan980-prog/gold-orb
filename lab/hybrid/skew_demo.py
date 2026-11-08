"""Does a hard stop 'save' a mean-reversion style, or does it remove the winners too?
Mechanical version of a Bollinger-band fade on gold H1 (enter on a close outside the 2-sigma band,
target = middle band), 2013-2026, low-cost ECN costs. Variants: no real stop (hold up to 20 trading
days, like a trader who waits for the price to come back) vs fixed stops of 1, 2, 3 x ATR(H1).
Then a leveraged account (constant exposure = L x equity) to see the monthly profile.
Illustration of a style, NOT a measurement of the user's discretionary trading."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np, pandas as pd, goldlab as gl
from goldlab.sim import Costs

sc = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audit", "cost_scenarios.json")))["low_cost_ecn"]
m1 = gl.load_m1("xauusd")
h1 = gl.bars(m1, "1h")
c = h1.c
mid, sd = c.rolling(20).mean(), c.rolling(20).std()
up, lo = mid + 2 * sd, mid - 2 * sd
a = gl.atr(h1, 14)
sig = np.where(c < lo, 1, np.where(c > up, -1, 0))
keep = (sig != 0) & mid.notna().to_numpy() & a.notna().to_numpy()
b = h1[keep]
side = sig[keep]
ei = gl.entry_index(m1, b.t_close)
out = {}
for name, k, days in (("sans stop (attendre 20 j)", 30.0, 28), ("stop 3 ATR", 3.0, 7), ("stop 2 ATR", 2.0, 7), ("stop 1 ATR", 1.0, 7)):
    o = pd.DataFrame({"entry_i": ei, "side": side, "stop_dist": k * a[keep].to_numpy(),
                      "target": mid[keep].to_numpy(),
                      "exit_i": gl.entry_index(m1, b.t_close + pd.Timedelta(days=days))})
    t = gl.simulate(m1, o, costs=Costs(**sc))
    r = t.ret.to_numpy()
    win = r > 0
    res = {"trades": len(t), "gagnants_pct": round(win.mean() * 100, 1),
           "gain_moyen_pct_prix": round(r[win].mean() * 100, 3), "perte_moyenne_pct_prix": round(r[~win].mean() * 100, 3),
           "pire_trade_pct_prix": round(r.min() * 100, 2), "pf": round(r[win].sum() / -r[~win].sum(), 3),
           "somme_pct_prix": round(r.sum() * 100, 1)}
    t["m"] = t.exit_time.dt.tz_convert(None).dt.to_period("M")
    for L in (10, 20):
        eq, wiped, months = 1.0, None, {}
        for _, row in t.iterrows():
            if eq <= 0.01:
                wiped = wiped or str(row.m); break
            eq *= max(0.0, 1 + L * row.ret)
            months.setdefault(row.m, []).append(1 + L * row.ret)
        mret = pd.Series({k_: np.prod(v) - 1 for k_, v in months.items()})
        res[f"levier_{L}"] = {"mois_+50pct_ou_plus": int((mret >= 0.5).sum()), "mois_-50pct_ou_pire": int((mret <= -0.5).sum()),
                              "meilleur_mois_pct": round(mret.max() * 100), "pire_mois_pct": round(mret.min() * 100),
                              "capital_final_x": round(eq, 3), "compte_detruit_en": wiped}
    out[name] = res
    print(name, json.dumps(res, ensure_ascii=False))
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "skew_demo_results.json"), "w"), indent=1, ensure_ascii=False)
