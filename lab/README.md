# gold-orb lab

Banc de test commun. Lire `PROTOCOL.md` d'abord (critères figés).

Setup (une fois) : `pip install numba pyarrow scipy matplotlib && python3 lab/prep_data.py`

## API (`import goldlab as gl`, run from `lab/` or add it to `sys.path`)

```python
m1 = gl.load_m1("xauusd")          # M1 UTC, cols bo bh bl bc (bid) ao ah al ac (ask)
h1 = gl.bars(m1, "1h")             # '5min','15min','1h','4h','D' (D = trading day ending 17:00 NY)
                                   # adds mid o h l c and t_close (when the bar is KNOWN)
a  = gl.atr(h1, 14)                # known at h1.t_close
ei = gl.entry_index(m1, h1.t_close)   # first M1 bar tradable after the decision
gl.local(m1.index, gl.LDN)         # London / New York wall clock (DST handled)
gl.trading_day(m1.index)           # NY-17:00 trading date

orders = pd.DataFrame({
    "entry_i": ei, "side": +1 or -1,
    "etype": 0,               # 0 market at open | 1 stop-entry at level | 2 limit at level
    "level": nan, "expiry_i": ...,   # for pending orders
    "stop": abs_price or nan, "stop_dist": dist,      # one of them is REQUIRED
    "target": abs or nan, "target_dist": dist or nan,
    "exit_i": m1 index of forced exit (time stop),   # use it: max hold <= 5 trading days
    "trail": dist or nan, "be": dist or nan,
    # any extra column (e.g. 'tag') is carried to the trades frame
})
t = gl.simulate(m1, orders, sym="xauusd", no_overlap=True)   # one position at a time
rep = gl.report(gl.cut(t, "is")); gl.show(rep)

from goldlab.evalkit import evaluate_is, is_criteria, val_criteria
t, rep, rep_stress = evaluate_is(m1, orders)       # IS report + costs x1.5 report
gl.log_trial("mytrack", {"param": 1}, rep)          # log EVERY config you evaluate
crit = is_criteria(rep, rep_stress)
# only for the final pre-chosen config(s):
rv = gl.report(gl.cut(t, "val", track="mytrack", label="final-A")); val_criteria(rv)
```

R = pnl / initial risk (entry→stop). PF is computed on R (sizing = fixed % risk per trade).

## Pièges à éviter

- Une bougie `bars()` est indexée par son DÉBUT ; elle n'est connue qu'à `t_close`.
  Décider sur une bougie → `entry_index(m1, bar.t_close)`. Jamais l'index de début.
- Indicateurs : uniquement `shift`/fenêtres passées. Pas de `center=True`, pas de normalisation
  sur toute la série (z-score global, quantiles globaux) – utiliser des fenêtres glissantes.
- Les heures de session changent avec l'heure d'été : passer par `gl.local(...)`.
- Autres marchés que l'or : bid seul, spread fixe estimé → résultats indicatifs.
