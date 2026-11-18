"""Template of a run's run.py, on SYNTHETIC data (one planted edge, one pure noise): the whole flow of the kit.
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/kit/template/run_template.py
In a real idea folder: copy this file to lab/explore/ideas/NNN_slug/run.py, keep one_idea() and call it on the idea's
own folder (declared.json and declared.sha256 written and COMMITTED before, from declared.template.json), replace
build_signals() and the bars by real data (kit.data.load_bars, fred, binance_*, external, asof_join), and keep the
order: hash -> truncation -> run -> verdict. run.py never writes declared.json: demo_declare() below is for this demo.
Kit v2 (README 'Pairs', 'Exit on a condition', 'Crypto venues'): a pair is one market, bk = {name: sim.pair_book(name,
key_a, key_b, bars_a, bars_b, kind)}; an exit on a condition is exit=sim.event_exit(build_events(d), ("bdays", 5)) with
tre = checks.truncation_test(build_events, d, ...) passed as judge.verdict(..., event_truncation=tre); bitcoin before
2017-08: data.load_bars("btcusd", 2013, venue="bitstamp") (the declaration names the venue).
Kit v2.1 fix 3 (README): pass the truncation test the bars of data.load_bars (or data.daily_bars of them) and compute
EVERY feature (returns, ATR, z-scores) inside build: an input that carries a share's or oil's attrs but is not at the
price level is refused (ValueError), and a feature passed as a bare array or a renamed copy without attrs is not seen."""
import hashlib, json, os, sys, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import numpy as np, pandas as pd
from kit import checks, judge, sim, stats, synth
from kit.data import asof_join

def build_signals(d, hour_utc=14):
    """The WHOLE signal table from data complete at known_at only (filters included: the truncation report is bound
    to exactly this table). d['value']: an external series indexed by the time it is KNOWN."""
    days = pd.bdate_range("2013-02-01", "2021-12-20", tz="UTC") + pd.Timedelta(hours=hour_utc)
    x = asof_join(days, d["value"])
    ok = np.isfinite(x) & (x != 0)
    return pd.DataFrame({"known_at": days[ok], "side": np.sign(x[ok]).astype(int)})

def one_idea(folder, edge, seed, ten=None, data_desc="synthetic 2013-2021 (9 years)"):
    decl = json.load(open(os.path.join(folder, "declared.json")))   # the COMMITTED declaration (FileNotFoundError if none)
    checks.declared_hash(folder)                                   # 1. unchanged since it was committed
    cfgs, mk = decl["configurations"], decl["markets"][0]
    bars, sig0 = synth.signal_world(mk, seed=seed, edge=edge)       # real: bars = data.load_bars(mk)
    value = pd.Series(sig0.side.to_numpy(), index=pd.DatetimeIndex(sig0.known_at))   # stands for an external series
    d = {"bars": bars, "value": value}
    tr = checks.truncation_test(build_signals, d, ["2016-06-01 14:30", "2019-09-09 09:00"],
                                row_len={"bars": pd.Timedelta(hours=1), "value": pd.Timedelta(0)})
    assert tr["pass"], tr                                          # 2. no look-ahead in the signal build
    sig = build_signals(d).assign(market=mk)                       # simulate exactly what the truncation test built
    bk = sim.books({mk: bars})
    run = lambda c, mode="one": sim.simulate(sig, bk, exit=tuple(c["exit"]), stop=tuple(c["stop"]),
                                             target=tuple(c["target"]) if c.get("target") else None, mode=mode)
    main = run(cfgs[0])                                            # 3. main, neighbours, every-signal, null
    neigh = {c["id"]: run(c) for c in cfgs[1:]}
    every = run(cfgs[0], "every")
    null = stats.null_test(main, bk, exit=tuple(cfgs[0]["exit"]), stop=tuple(cfgs[0]["stop"]), n_draws=2000)
    shift = checks.shift_test(sig, bk, exit=tuple(cfgs[0]["exit"]), stop=tuple(cfgs[0]["stop"]))
    res = judge.verdict(folder, main, neigh, every, null, corr="compute", ten=ten, n_configs=len(cfgs),
                        truncation=tr, data_desc=data_desc, extra={"shift_test": shift})
    print(f"{os.path.basename(folder)}: {res['verdict']}  failed: {res['failed_bars']}")
    print("   ", res["ledger_line"])                               # 4. real run: judge.ledger_add(len(cfgs), line)
    return res

def demo_declare(folder, name):                  # DEMO ONLY: a real declaration is written and committed by hand first
    os.makedirs(folder, exist_ok=True)
    decl = {"idea": f"{name} (synthetic)", "markets": ["us500"],
            "configurations": [{"id": "01_main", "exit": ["hours", 5], "stop": ["d20", 1.5]},
                               {"id": "02_h4", "exit": ["hours", 4], "stop": ["d20", 1.5]},
                               {"id": "03_h6", "exit": ["hours", 6], "stop": ["d20", 1.5]},
                               {"id": "04_s1", "exit": ["hours", 5], "stop": ["d20", 1.0]}]}
    raw = json.dumps(decl, indent=1).encode()
    open(os.path.join(folder, "declared.json"), "wb").write(raw)
    open(os.path.join(folder, "declared.sha256"), "w").write(hashlib.sha256(raw).hexdigest() + "  declared.json\n")
    return folder

if __name__ == "__main__":
    tmp = tempfile.mkdtemp(prefix="kit_template_")
    ten = stats.ten_trades(synth.ten_fixture(os.path.join(tmp, "ten")))   # real run: ten=None reads the lab's ten
    a = one_idea(demo_declare(os.path.join(tmp, "991_planted"), "991 planted"), edge=0.0004, seed=5, ten=ten)
    b = one_idea(demo_declare(os.path.join(tmp, "992_noise"), "992 noise"), edge=0.0, seed=6, ten=ten)
    assert a["verdict"] == "pass" and b["verdict"] == "fail"
    if "--keep" in sys.argv:
        print("template OK; results in", tmp)
    else:
        import shutil; shutil.rmtree(tmp); print("template OK (temporary folder removed; --keep to inspect it)")
